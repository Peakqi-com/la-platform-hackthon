"""
案件 → 三張圖要疊的 GeoJSON 圖層。

  sections        地價區段多邊形（label = 區段號；range_desc、status）
  parcels         比準地／比較標的（role、parcel_id、geometry_source）
  facilities      有幾何的設施（type、distance_m、measure、origin、source、in_section、rule/field）
  distance_lines  量測起點 → 設施的直線（label「150 m 步行」），佐證用
  zoning          使用分區（裁到範圖 bbox，帶顏色）
  roads           有名道路（裁到 bbox）
所有圖層 WGS84。三張圖只是同一組圖層的不同開關組合：略圖 = sections+parcels+roads；分區圖 = zoning+sections；區段圖 = sections+parcels+facilities+distance_lines。
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import unary_union

from app.spatial.geo import offset_point

from .zoning import ZoningStore

MEASURE_LABEL = {"walking": "步行", "straight": "直線", "straight_estimated": "直線估算"}


def _feat(geom: Any, props: dict) -> dict:
    g = geom if isinstance(geom, dict) else mapping(geom)
    return {"type": "Feature", "geometry": g, "properties": props}


def _facility_feats(facs: Any, owner: str, field: str, scope: str) -> tuple[list[dict], list[dict]]:
    pts, lines = [], []
    items = facs if isinstance(facs, list) else ([facs] if isinstance(facs, dict) else [])
    for f in items:
        if not isinstance(f, dict):
            continue
        prov = f.get("provenance") or {}
        props = {"owner": owner, "field": field, "scope": scope, "name": f.get("name"), "type": f.get("type"),
                 "distance_m": f.get("distance_m"), "measure": f.get("measure"), "origin": f.get("origin"),
                 "source": f.get("source"), "in_section": f.get("in_section"), "assumed": f.get("assumed", False),
                 "label": f"{f.get('name') or ''} {f.get('distance_m') if f.get('distance_m') is not None else ''}{' m' if f.get('distance_m') is not None else ''}"
                          f"{'（' + MEASURE_LABEL.get(f.get('measure'), f.get('measure') or '') + '）' if f.get('measure') else ''}".strip()}
        if f.get("geometry"):
            pts.append(_feat(f["geometry"], props))
        elif prov.get("target_point"):
            pts.append(_feat(Point(*prov["target_point"]), props))
        if prov.get("origin_point") and prov.get("target_point") and f.get("in_section") is not True:
            lines.append(_feat(LineString([prov["origin_point"], prov["target_point"]]), {**props, "straight_m": prov.get("straight_m")}))
    return pts, lines


def load_cadastre_features(data: dict) -> list[dict]:
    """案件匯入的地籍圖檔（data.case.cadastre.file，WGS84 GeoJSON，屬性含 section／lot）。沒有就空。"""
    import json
    from pathlib import Path
    info = (data.get("case") or {}).get("cadastre") or {}
    path = info.get("file")
    if not path or not Path(path).exists():
        return []
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("features", [])
    except (OSError, ValueError):
        return []


def load_section_map_features(data: dict) -> list[dict]:
    """案件匯入的地價區段圖（data.case.section_map.file）。"""
    import json
    from pathlib import Path
    info = (data.get("case") or {}).get("section_map") or {}
    path = info.get("file")
    if not path or not Path(path).exists():
        return []
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("features", [])
    except (OSError, ValueError):
        return []


FOCUS_M = 2500.0     # 預設取景：離比準地 2.5 km 內的幾何


def _dist_m(a, b) -> float:
    import math
    return math.hypot((a.x - b.x) * 111_320 * math.cos(math.radians((a.y + b.y) / 2)), (a.y - b.y) * 111_320)


def case_layers(data: dict, *, zoning: ZoningStore | None = None, roads: Any | None = None, pad_m: float = 250.0) -> dict[str, Any]:
    sections, parcels, facilities, lines = [], [], [], []
    geoms = []
    for sid, sec in (data.get("sections") or {}).items():
        if sec.get("geometry"):
            sections.append(_feat(sec["geometry"], {"section_id": sid, "range_desc": sec.get("range_desc"), "status": sec.get("status", "confirmed"),
                                                    "geometry_source": sec.get("geometry_source"), "label": sid}))
            geoms.append(shape(sec["geometry"]))
        for grp, d in (sec.get("survey") or {}).items():
            if isinstance(d, dict):
                for k, v in d.items():
                    p, l = _facility_feats(v, sid, f"{grp}.{k}", "regional")
                    facilities += p
                    lines += l
    subject = data.get("subject_parcel") or {}
    for role, p in [("subject", subject)] + [("comparable", c) for c in data.get("comparables") or []]:
        if not p:
            continue
        if p.get("geometry"):
            parcels.append(_feat(p["geometry"], {"role": role, "parcel_id": p.get("parcel_id"), "comp_no": p.get("comp_no"),
                                                 "geometry_source": p.get("geometry_source"), "geometry_note": p.get("geometry_note"),
                                                 "label": ("比準地 " if role == "subject" else f"比較標的{p.get('comp_no')} ") + str(p.get("parcel_id") or "")}))
            geoms.append(shape(p["geometry"]))
        for f in ("school", "market", "park", "station", "commercial_district", "nuisance"):
            pf, lf = _facility_feats(p.get(f), p.get("parcel_id") or role, f, "individual")
            facilities += pf
            lines += lf
    if not geoms:   # 沒有區段／宗地幾何時才用設施定範圍
        for f in facilities:
            geoms.append(shape(f["geometry"]))
    # 取景以比準地為主：其他鄉鎮的比較標的（§19 第2項，可能在十幾公里外）不納入預設範圍，否則整張圖縮到看不見街廓；bbox_all 給「顯示全部」用
    focus = geoms
    if subject.get("geometry"):
        sc = shape(subject["geometry"]).centroid
        focus = [g for g in geoms if _dist_m(sc, g.centroid) <= FOCUS_M] or geoms
    bbox = None
    tight = None
    bbox_all = None
    if geoms:
        minx, miny, maxx, maxy = unary_union(focus).bounds
        tight = (minx, miny, maxx, maxy)
        p1, p2 = offset_point(minx, miny, -pad_m, -pad_m), offset_point(maxx, maxy, pad_m, pad_m)
        bbox = (p1.x, p1.y, p2.x, p2.y)
        ax0, ay0, ax1, ay1 = unary_union(geoms).bounds
        q1, q2 = offset_point(ax0, ay0, -pad_m, -pad_m), offset_point(ax1, ay1, pad_m, pad_m)
        bbox_all = (q1.x, q1.y, q2.x, q2.y)
    zoning_feats = zoning.within_bbox(bbox) if (zoning and bbox) else []
    cad_feats = []
    if bbox:
        b = box(*bbox)
        for f in load_cadastre_features(data):
            try:
                g = shape(f["geometry"])
            except (ValueError, TypeError, KeyError):
                continue
            if g.intersects(b):
                pr = f.get("properties") or {}
                cad_feats.append(_feat(g, {"section": pr.get("section"), "lot": pr.get("lot"), "label": f"{pr.get('section') or ''}{pr.get('lot') or ''}地號"}))
    secmap_feats = []
    if bbox:
        b = box(*bbox)
        own = set((data.get("sections") or {}).keys())
        for f in load_section_map_features(data):
            try:
                g = shape(f["geometry"])
            except (ValueError, TypeError, KeyError):
                continue
            sid = (f.get("properties") or {}).get("section_id") or ""
            if g.intersects(b) and sid not in own:
                secmap_feats.append(_feat(g, {"section_id": sid, "label": f"區段 {sid}"}))
    road_feats = []
    if roads is not None and bbox:
        b = box(*bbox)
        for n, g, props in roads.items:
            if g.intersects(b):
                road_feats.append(_feat(g.intersection(b), {"name": n, "highway": props.get("highway"), "label": n}))
    fc = lambda feats: {"type": "FeatureCollection", "features": feats}
    return {"sections": fc(sections), "parcels": fc(parcels), "facilities": fc(facilities), "distance_lines": fc(lines),
            "zoning": fc(zoning_feats), "roads": fc(road_feats), "cadastre": fc(cad_feats), "section_map": fc(secmap_feats), "bbox": bbox, "tight_bbox": tight, "bbox_all": bbox_all, "n_far": len(geoms) - len(focus),
            "attribution": {"basemap": "國土測繪中心 WMTS EMAP／LANDSECT", "zoning": zoning.source if zoning else None,
                            "roads": "© OpenStreetMap contributors (ODbL)" if road_feats else None}}
