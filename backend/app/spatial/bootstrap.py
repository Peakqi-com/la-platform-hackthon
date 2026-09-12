"""
地價區段 bootstrap（深模式，docs/04「區段 bootstrap」）：

  section_from_roads(names, roads)   四條（或更多）路名圍出的街廓 → 多邊形（範本 P002-00 的區段範圍就是這樣描述的）
  describe_range(polygon, roads)     多邊形 → 「北側至X，南側至Y，西側至Z，東側至W之…土地劃為…區段」草稿
  propose_sections(...)              徵收範圍（或宗地聯集）× 使用分區 → 區段草稿清單（status=draft，估價師要確認）

法源：查估辦法 §10（劃分地價區段實地勘查）、§11（區段界線以地形地貌、道路、溝渠…等為準）、手冊 p.11 審查重點 iv（區段範圍描述與現況相符）。
路網用 OSM（data/roads_osm_jinshan.geojson，© OpenStreetMap contributors）；有官方路網時換檔即可。
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from shapely import set_precision
from shapely.geometry import LineString, Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, unary_union

from .geo import as_shape, to_twd97, to_wgs84

SIDES = (("北側", 0, 1), ("南側", 0, -1), ("西側", -1, 0), ("東側", 1, 0))
# 會當區段界線的道路等級（OSM highway）；service/pedestrian/footway/path 之類不切街廓
CUT_HIGHWAYS = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "pedestrian", "living_street",
                "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}


class Roads:
    def __init__(self, features: Iterable[dict]):
        self.items: list[tuple[str, LineString, dict]] = []
        for f in features:
            name = (f.get("properties") or {}).get("name")
            if not name:
                continue
            g = shape(f["geometry"])
            if g.geom_type == "LineString":
                self.items.append((name, g, f.get("properties") or {}))
            elif g.geom_type == "MultiLineString":
                for part in g.geoms:
                    self.items.append((name, part, f.get("properties") or {}))

    @classmethod
    def from_geojson(cls, src: str | Path | dict) -> Roads:
        data = src if isinstance(src, dict) else json.loads(Path(src).read_text(encoding="utf-8"))
        return cls(data["features"])

    def named(self, name: str, exact: bool = True) -> list[LineString]:
        """同名路段；exact=False 時含 'X路NN巷' 以外的變體（去掉巷弄）。"""
        out = [g for n, g, _ in self.items if n == name]
        if not out and not exact:
            out = [g for n, g, _ in self.items if n.startswith(name) and not re.search(r"\d+巷|弄", n)]
        return out

    def nearest_name(self, pt: Any, max_m: float, exclude_lanes: bool = True) -> tuple[str, float] | None:
        p = to_twd97(as_shape(pt))
        best: tuple[str, float] | None = None
        for n, g, _ in self.items:
            if exclude_lanes and re.search(r"\d+巷|弄", n):
                continue
            d = p.distance(to_twd97(g))
            if d <= max_m and (best is None or d < best[1]):
                best = (n, d)
        return best

    def names(self) -> list[str]:
        return sorted({n for n, _, _ in self.items})


def section_from_roads(names: list[str], roads: Roads, hint: Any = None, buffer_m: float = 3.0, snap_m: float = 80.0) -> dict[str, Any] | None:
    """
    路名清單 → 由這些路圍出的街廓多邊形。做法：同名路段聯集 → polygonize → 只留邊界碰到「每一條」指定道路的面；
    多個候選時取含 hint 點者，否則取面積最大者。回傳 {"geometry": GeoJSON, "touched": {路名: 是否碰到}, "candidates": n}。
    """
    lines = []
    per_name: dict[str, BaseGeometry] = {}
    for n in names:
        segs = roads.named(n) or roads.named(n, exact=False)
        if not segs:
            return None
        u = unary_union([to_twd97(s) for s in segs])
        per_name[n] = u
        lines.append(u)
    merged = unary_union(set_precision(unary_union(_snap_dangles(lines, snap_m)), 0.01))   # 1 cm 網格後重新 noding，避免浮點微縫讓環不閉合
    faces = list(polygonize(merged))
    cands = []
    for f in faces:
        touched = {n: f.boundary.distance(g) <= buffer_m for n, g in per_name.items()}
        if all(touched.values()):
            cands.append((f, touched))
    if not cands:
        return None
    if hint is not None:
        hp = to_twd97(as_shape(hint))
        inside = [c for c in cands if c[0].contains(hp)]
        if inside:
            cands = inside
    face, touched = max(cands, key=lambda c: c[0].area)
    return {"geometry": mapping(to_wgs84(face)), "touched": touched, "candidates": len(cands), "area_m2": round(face.area, 1)}


def _snap_dangles(lines: list[BaseGeometry], tol_m: float) -> list[BaseGeometry]:
    """OSM 路段末端常差幾十公尺沒接到鄰路（金山 中山路—金包里街 差 60 m）。端點 tol_m 內有別的路 → 補一段連接線。"""
    out = list(lines)
    others = unary_union(lines)
    for ln in lines:
        parts = list(ln.geoms) if ln.geom_type == "MultiLineString" else [ln]
        for part in parts:
            for end in (Point(part.coords[0]), Point(part.coords[-1])):
                rest = others.difference(part.buffer(0.01))
                if rest.is_empty:
                    continue
                d = rest.distance(end)
                if 1e-6 < d <= tol_m:      # 含浮點誤差造成的微小未接合
                    from shapely.ops import nearest_points
                    q = nearest_points(rest, end)[0]
                    out.append(LineString([end, q]))
    return out


def block_from_roads(hints: Any, roads: Roads, *, exclude_lanes: bool = True, snap_m: float = 80.0,
                     search_m: float = 1500.0, extra_names: Iterable[str] = (), exclude_names: Iterable[str] = (),
                     on_road_tol_m: float = 12.0) -> dict[str, Any] | None:
    """
    街廓法：hint 附近的（非巷弄）道路 → 補接缺口 → polygonize → 取「包含最多 hint 點」的面（比準地常在路邊，
    單一 hint 可能落在路上，多給幾個區段內的點如市場、站牌）。
    回傳 {"geometry", "bounding_roads", "area_m2", "n_roads", "hits"}。
    """
    hint_list = hints if isinstance(hints, (list, tuple)) and hints and not isinstance(hints[0], (int, float)) else [hints]
    hps = [to_twd97(as_shape(h)) for h in hint_list]
    h0 = hps[0]
    sel = []
    for n, g, props in roads.items:
        if n in set(exclude_names):
            continue
        if n not in set(extra_names):
            if exclude_lanes and re.search(r"\d+巷|弄", n):
                continue
            hw = (props.get("highway") or "").lower()
            if hw and hw not in CUT_HIGHWAYS:
                continue
        gt = to_twd97(g)
        if gt.distance(h0) <= search_m:
            sel.append((n, gt))
    if not sel:
        return None
    lines = _snap_dangles([g for _, g in sel], snap_m)
    faces = [f for f in polygonize(unary_union(set_precision(unary_union(lines), 0.01))) if f.area > 50]
    if not faces:
        return None

    def hits(f):
        return sum(1 for hp in hps if f.contains(hp) or f.distance(hp) <= on_road_tol_m)
    best = max(faces, key=lambda f: (hits(f), -f.distance(h0)))
    if hits(best) == 0:
        return None
    bounding = sorted({n for n, g in sel if g.distance(best) <= 1.0})
    return {"geometry": mapping(to_wgs84(best)), "bounding_roads": bounding, "area_m2": round(best.area, 1),
            "n_roads": len(sel), "hits": hits(best)}


def describe_range(polygon: Any, roads: Roads, *, zoning: str | None = None, section_id: str | None = None,
                   touch_m: float = 10.0, max_m: float = 120.0) -> dict[str, Any]:
    """
    四至：找貼著區段邊界（touch_m 內）的有名道路，依其貼合段中點相對區段中心的方位分到北/南/西/東，每側取貼合最長者；
    某側沒有貼合道路 → 退回該側外接框中點 max_m 內最近的道路；還是沒有 → 「待確認」。
    """
    import math
    poly = to_twd97(as_shape(polygon))
    ring = poly.boundary.buffer(touch_m)
    c = poly.centroid
    best: dict[str, tuple[str, float]] = {}
    for n, g, props in roads.items:
        if re.search(r"\d+巷|弄", n):
            continue
        gt = to_twd97(g)
        seg = gt.intersection(ring)
        if seg.is_empty or seg.length < 5:
            continue
        m = seg.interpolate(0.5, normalized=True) if seg.geom_type == "LineString" else seg.centroid
        ang = math.degrees(math.atan2(m.x - c.x, m.y - c.y)) % 360      # 0=北, 90=東
        side = "北側" if ang < 45 or ang >= 315 else "東側" if ang < 135 else "南側" if ang < 225 else "西側"
        if side not in best or seg.length > best[side][1]:
            best[side] = (n, seg.length)
    sides: dict[str, str | None] = {}
    minx, miny, maxx, maxy = poly.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    for label, sx, sy in SIDES:
        if label in best:
            sides[label] = best[label][0]
            continue
        x = cx if sx == 0 else (maxx if sx > 0 else minx)
        y = cy if sy == 0 else (maxy if sy > 0 else miny)
        hit = roads.nearest_name(to_wgs84(Point(x, y)), max_m)
        sides[label] = hit[0] if hit else None
    parts = [f"{k}至{v}" if v else f"{k}（待確認）" for k, v in sides.items()]
    desc = "，".join(parts) + f"之{zoning or '（分區待確認）'}土地劃為{section_id or '（區段編號待定）'}區段。"
    return {"range_desc": desc, "sides": sides, "status": "draft"}


def propose_sections(scope: Any, roads: Roads, *, zoning_features: Iterable[dict] | None = None, zoning_name_field: str = "分區",
                     prefix: str = "P", start_no: int = 1, min_area_m2: float = 200.0) -> list[dict[str, Any]]:
    """
    徵收範圍（多邊形或多邊形清單＝宗地聯集）→ 區段草稿。有使用分區圖 → 依分區切開；同分區相連的合為一段。
    每段：section_id、geometry、zoning、range_desc（四至草稿）、area_m2、status="draft"、basis。
    """
    if isinstance(scope, list):
        area = unary_union([as_shape(g) for g in scope])
    else:
        area = as_shape(scope)
    pieces: list[tuple[BaseGeometry, str | None]] = []
    if zoning_features:
        for zf in zoning_features:
            zg = shape(zf["geometry"])
            inter = area.intersection(zg)
            if inter.is_empty:
                continue
            zname = (zf.get("properties") or {}).get(zoning_name_field)
            geoms = list(inter.geoms) if inter.geom_type.startswith("Multi") or inter.geom_type == "GeometryCollection" else [inter]
            for g in geoms:
                if g.geom_type in ("Polygon", "MultiPolygon") and to_twd97(g).area >= min_area_m2:
                    pieces.append((g, zname))
        rest = area.difference(unary_union([p for p, _ in pieces])) if pieces else area
        if not rest.is_empty and to_twd97(rest).area >= min_area_m2:
            pieces.append((rest, None))
    else:
        pieces.append((area, None))
    # 同分區相連合併
    merged: list[tuple[BaseGeometry, str | None]] = []
    for z in {z for _, z in pieces}:
        u = unary_union([g for g, zz in pieces if zz == z])
        for g in (u.geoms if u.geom_type.startswith("Multi") else [u]):
            merged.append((g, z))
    merged.sort(key=lambda gz: (-to_twd97(gz[0]).area, str(gz[1])))
    out = []
    for i, (g, z) in enumerate(merged):
        sid = f"{prefix}{start_no + i:03d}-00"
        rng = describe_range(g, roads, zoning=z, section_id=sid)
        out.append({"section_id": sid, "geometry": mapping(g), "zoning": z, "area_m2": round(to_twd97(g).area, 1),
                    "range_desc": rng["range_desc"], "sides": rng["sides"], "status": "draft",
                    "basis": "查估辦法 §10、§11；分區來自使用分區圖、四至來自路網，皆為草稿，估價師須實地勘查確認",
                    "survey": {"land_control": {"zoning": z}} if z else {}})
    return out


def sections_from_land_values(parcels: list[dict], roads: Roads | None = None, *, value_field: str = "land_value",
                              prefix: str = "P", start_no: int = 1, tol: float = 0.0) -> list[dict[str, Any]]:
    """
    地價區段圖拿不到時的替代：公告土地現值相同且相鄰的宗地 → 同一區段草稿（公告現值本來就是「地價區段區段地價」逐宗套用的結果，
    所以同值相鄰的宗地極可能屬同一區段）。輸入 parcels = [{"parcel_id", "geometry", land_value}]，需有幾何（地籍圖）。
    法源：平均地權條例 §46（地價區段、區段地價）；查估辦法 §10、§11。輸出 status=draft、basis 註明推定。
    """
    from shapely.ops import unary_union
    groups: dict[float, list] = {}
    for p in parcels:
        v = p.get(value_field)
        if v is None or p.get("geometry") is None:
            continue
        key = round(float(v) / (tol or 1)) * (tol or 1) if tol else float(v)
        groups.setdefault(key, []).append(p)
    out = []
    for v, ps in sorted(groups.items(), key=lambda kv: -kv[0]):
        u = unary_union([as_shape(p["geometry"]).buffer(0.5e-5) for p in ps]).buffer(-0.5e-5)   # 相鄰宗地（含路寬內小縫）併起來
        for g in (u.geoms if u.geom_type.startswith("Multi") else [u]):
            ids = [p["parcel_id"] for p in ps if as_shape(p["geometry"]).intersects(g)]
            out.append({"geometry": mapping(g), "land_value": v, "parcel_ids": ids, "area_m2": round(to_twd97(g).area, 1),
                        "status": "draft", "basis": "同公告現值且相鄰之宗地推定為同一地價區段（平均地權條例 §46；查估辦法 §10、§11），需估價師確認"})
    out.sort(key=lambda d: -d["area_m2"])
    for i, d in enumerate(out):
        d["section_id"] = f"{prefix}{start_no + i:03d}-00"
        if roads is not None:
            d.update({k: v for k, v in describe_range(d["geometry"], roads, section_id=d["section_id"]).items() if k in ("range_desc", "sides")})
    return out
