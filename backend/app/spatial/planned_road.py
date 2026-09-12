"""計畫道路臨路判定（純幾何，不用 AI）：宗地是否緊鄰都市計畫圖「道路用地」，以及該計畫道路的寬度。

用途：土管要點但書多以「面臨計畫道路寬度未達 N 公尺」或「依指定現有巷道建築者」為條件（例：樹林都市計畫土管四(三)），
路網等級預設的路寬不夠準；改用城鄉局都市計畫土地使用分區的「道路用地」多邊形，沿宗地臨路邊每隔一段做垂線，量垂線穿過道路用地的長度，取中位數當計畫道路寬度。
宗地界線 1 m 內沒有道路用地 → 面臨的是現有巷道（非計畫道路）。路名由路網中落在該道路用地內、最靠近垂線的路段投票決定。
法源：手冊 p.23 5(2) 面前道路寬度；查估辦法 §20 行政條件。結果一律是推定值，供承辦確認。
"""
from __future__ import annotations

import math
import statistics
from itertools import pairwise
from typing import Any

from shapely.geometry import LineString, Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

SOURCE = "都市計畫圖道路用地量測"
TOUCH_M = 1.0          # 宗地界線與道路用地的距離門檻（地籍與分區圖套疊誤差）
PAD_M = 60.0           # 搜尋道路用地的範圍
RAY_M = 60.0           # 垂線長度上限（超過視為廣場或路口）
NAME_M = 4.0           # 路網線段離垂線多近才算同一條路


def _to_local(c: Point):
    my = 111320.0
    mx = my * math.cos(math.radians(c.y))
    return lambda x, y, z=None: ((x - c.x) * mx, (y - c.y) * my), mx, my


def _is_road_zone(zone: str | None) -> bool:
    return "道路" in (zone or "")


def planned_road_frontage(geometry: dict | BaseGeometry, zoning, roads=None, *, touch_m: float = TOUCH_M, pad_m: float = PAD_M) -> dict[str, Any] | None:
    """
    回傳 {"kind": "計畫道路"|"現有巷道", "width_m": float|None, "min_m", "max_m", "n": 垂線數, "names": [路名…依臨路長度排序], "note"}；
    分區圖沒有資料或搜尋範圍內完全沒有道路用地（無法判定）→ None。
    """
    if zoning is None or not len(zoning):
        return None
    g = shape(geometry) if isinstance(geometry, dict) else geometry
    if g.is_empty:
        return None
    c = g.centroid
    to_m, mx, my = _to_local(c)
    gm = transform(to_m, g)
    b = g.bounds
    feats = zoning.within_bbox((b[0] - pad_m / mx, b[1] - pad_m / my, b[2] + pad_m / mx, b[3] + pad_m / my))
    road_polys = [transform(to_m, shape(f["geometry"])) for f in feats if _is_road_zone((f.get("properties") or {}).get("zone") or (f.get("properties") or {}).get("ZONE"))]
    if not road_polys:
        return None
    adjacent = [rd for rd in road_polys if rd.distance(gm) <= touch_m]
    if not adjacent:
        return {"kind": "現有巷道", "width_m": None, "min_m": None, "max_m": None, "n": 0, "names": [],
                "note": f"宗地界線 {touch_m:g} m 內無都市計畫道路用地，面臨現有巷道（非計畫道路）；請確認出入道路及其寬度"}
    lines = []
    for name, ln, _props in getattr(roads, "items", []) or []:
        lm = transform(to_m, ln)
        if lm.distance(gm) <= pad_m:
            lines.append((name, lm))
    polys = [gm] if gm.geom_type == "Polygon" else [q for q in getattr(gm, "geoms", []) if q.geom_type == "Polygon"]
    widths: list[float] = []
    votes: dict[str, float] = {}
    for rd in adjacent:
        for poly in polys:
            coords = list(poly.exterior.coords)
            for (x0, y0), (x1, y1) in pairwise(coords):
                seg = LineString([(x0, y0), (x1, y1)])
                if seg.length < 0.5 or rd.distance(seg) > touch_m:
                    continue
                ex, ey = (x1 - x0) / seg.length, (y1 - y0) / seg.length
                nx, ny = -ey, ex
                mid = seg.interpolate(0.5, normalized=True)
                if poly.contains(Point(mid.x + 0.3 * nx, mid.y + 0.3 * ny)):      # 法線要朝宗地外
                    nx, ny = -nx, -ny
                for t in (0.25, 0.5, 0.75):
                    pt = seg.interpolate(t, normalized=True)
                    ray = LineString([(pt.x - 1.5 * nx, pt.y - 1.5 * ny), (pt.x + RAY_M * nx, pt.y + RAY_M * ny)])
                    s = ray.intersection(rd)
                    parts = [s] if s.geom_type == "LineString" else [q for q in getattr(s, "geoms", []) if q.geom_type == "LineString"]
                    parts = [q for q in parts if q.length > 0.3]
                    if not parts:
                        continue
                    first = min(parts, key=lambda q: q.distance(pt))
                    widths.append(first.length)
                    cand = [(n, ln.distance(first)) for n, ln in lines if ln.distance(first) <= NAME_M]
                    if cand:
                        n = min(cand, key=lambda x: x[1])[0]
                        votes[n] = votes.get(n, 0.0) + seg.length / 3
    if not widths:
        return {"kind": "計畫道路", "width_m": None, "min_m": None, "max_m": None, "n": 0, "names": sorted(votes, key=lambda k: -votes[k]),
                "note": "宗地緊鄰都市計畫道路用地，但垂線量不到寬度（路口或廣場），請人工量測"}
    width = round(statistics.median(widths), 1)
    names = sorted(votes, key=lambda k: -votes[k])
    note = (f"緊鄰都市計畫道路用地（{'、'.join(names) if names else '路網無對應路名'}），沿臨路邊 {len(widths)} 條垂線量得計畫道路寬度中位 {width:g} m"
            f"（{min(widths):.1f}～{max(widths):.1f}）；分區圖與地籍套疊有誤差，請以都市計畫樁位或實地量測確認")
    return {"kind": "計畫道路", "width_m": width, "min_m": round(min(widths), 1), "max_m": round(max(widths), 1), "n": len(widths), "names": names, "note": note}
