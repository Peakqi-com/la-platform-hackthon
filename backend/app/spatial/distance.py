"""
單筆量測：起點幾何 + 設施幾何 + 量測方式 → Facility（docs/03），每筆帶 measure / origin / source 與計算佐證。

measure:
  straight            大地直線（TWD97 投影歐氏距離；面狀取最近點）
  walking             路徑距離：OSRM foot（router=osrm）或內建 OSM 步行圖 Dijkstra（router=osm_graph，walking.py）
  straight_estimated  要 walking 但兩者都不可用 → 直線 × WALKING_FALLBACK_FACTOR，UI 必須標示
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import mapping

from .geo import as_shape, centroid, nearest_point_on, straight_distance_m
from .osrm import OSRMClient, OSRMError
from .poi import POI

WALKING_FALLBACK_FACTOR = 1.3


def measure_distance(origin: Any, target: Any, mode: str, osrm: OSRMClient | None = None, walk_graph: Any = None) -> dict[str, Any]:
    """
    回傳 {"distance_m", "measure", "origin_point": [lon,lat], "target_point": [lon,lat], "straight_m", "note"}。
    origin / target 可為點或多邊形：直線距離取兩幾何最近點；步行距離用「origin 上最接近 target 的點」與「target 上最接近 origin 的點」。
    """
    o, t = as_shape(origin), as_shape(target)
    straight = straight_distance_m(o, t)
    op = nearest_point_on(o, t) if o.geom_type != "Point" else o
    tp = nearest_point_on(t, o) if t.geom_type != "Point" else t
    out: dict[str, Any] = {"straight_m": round(straight, 1), "origin_point": [op.x, op.y], "target_point": [tp.x, tp.y], "note": None, "router": None}
    if mode == "straight" or straight == 0.0:
        out.update(distance_m=round(straight, 1), measure="straight")
        if mode != "straight":
            out["note"] = "設施在起點幾何內，距離 0"
        return out
    if mode != "walking":
        raise ValueError(f"未知量測方式 {mode}")
    notes = []
    if osrm is not None and osrm.enabled:
        try:
            d = osrm.route_distance_m((op.x, op.y), (tp.x, tp.y))
            out.update(distance_m=round(d, 1), measure="walking", router="osrm")
            return out
        except OSRMError as e:
            notes.append(f"OSRM 不可用（{e}）")
    if walk_graph is not None:
        try:
            r = walk_graph.route_distance_m(op, tp)
            notes.append(f"內建步行路網（OSM）（含到路 {r['snap_a_m']:.0f}+{r['snap_b_m']:.0f} m）")
            out.update(distance_m=round(r["distance_m"], 1), measure="walking", router="osm_graph", note="；".join(notes))
            return out
        except ValueError as e:
            notes.append(f"內建步行路網（OSM）無法計算（{e}）")
    else:
        notes.append("內建步行路網（OSM）無資料")
    notes.append(f"以直線×{WALKING_FALLBACK_FACTOR} 估算步行距離")
    out["note"] = "；".join(notes)
    out.update(distance_m=round(straight * WALKING_FALLBACK_FACTOR, 1), measure="straight_estimated")
    return out


def facility_from_poi(poi: POI, origin: Any, mode: str, *, origin_label: str, osrm: OSRMClient | None = None,
                      in_section: bool | None = None, section: Any = None, walk_graph: Any = None) -> dict[str, Any]:
    """POI → Facility。in_section 未給且有 section 多邊形 → 以相交判定。"""
    if in_section is None and section is not None:
        in_section = bool(as_shape(section).intersects(poi.geom))
    m = measure_distance(origin, poi.geom, mode, osrm, walk_graph)
    d = m["distance_m"]
    f: dict[str, Any] = {
        "name": poi.name, "type": poi.type, "in_section": in_section,
        "distance_m": round(d) if d is not None else None,
        "measure": m["measure"], "origin": origin_label, "source": poi.source,
        "geometry": mapping(poi.geom), "computed": True,
        "provenance": {"poi_id": poi.id, "source_id": poi.source_id, "straight_m": m["straight_m"], "router": m.get("router"),
                       "origin_point": m["origin_point"], "target_point": m["target_point"], "note": m["note"]},
    }
    return f


def parcel_origin(parcel_geom: Any, mode: str, road_geom: Any = None):
    """個別因素量測起點：parcel_centroid（預設）| parcel_frontage（需面前道路幾何）| parcel（整個多邊形，取最近點）。"""
    g = as_shape(parcel_geom)
    if mode == "parcel_centroid" or g.geom_type == "Point":
        return centroid(g) if g.geom_type != "Point" else g
    if mode == "parcel_frontage":
        if road_geom is None:
            return centroid(g)
        return nearest_point_on(g, road_geom)
    return g
