"""
案件範圍（bbox）：全區圖資改成依案件局部載入（roads.sqlite／walk.sqlite），這裡決定「載哪一塊」。
順序：案件內已有的幾何（比準地、比較標的、區段）外框 → 沒有幾何時用鄉鎮市區界（data/osm/districts.geojson，OSM admin_level=8）。
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import shape

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
BBox = tuple[float, float, float, float]


def pad_bbox(b: BBox, pad_m: float) -> BBox:
    lat = (b[1] + b[3]) / 2
    dy = pad_m / 111_320.0
    dx = pad_m / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return (b[0] - dx, b[1] - dy, b[2] + dx, b[3] + dy)


def _geoms_in_case(data: dict) -> list:
    out = []
    sp = data.get("subject_parcel") or {}
    if sp.get("geometry"):
        out.append(sp["geometry"])
    for c in data.get("comparables") or []:
        if c.get("geometry"):
            out.append(c["geometry"])
    for s in (data.get("sections") or {}).values():
        if s.get("geometry"):
            out.append(s["geometry"])
    return out


@lru_cache(maxsize=1)
def _districts() -> list[tuple[str, Any]]:
    p = DATA_DIR / "osm" / "districts.geojson"
    if not p.exists():
        return []
    out = []
    for f in json.loads(p.read_text(encoding="utf-8")).get("features", []):
        n = (f.get("properties") or {}).get("name") or ""
        if n:
            out.append((n, shape(f["geometry"])))
    return out


def district_geom(district: str | None):
    d = (district or "").replace("新北市", "").replace("台", "臺").strip()
    if not d:
        return None
    for n, g in _districts():
        if n == d or n.endswith(d) or (d.endswith("區") and n == d):
            return g
    return None


def district_bbox(district: str | None, pad_m: float = 1500.0) -> BBox | None:
    g = district_geom(district)
    return pad_bbox(g.bounds, pad_m) if g is not None else None


def case_bbox(data: dict | None, pad_m: float = 3000.0) -> BBox | None:
    """案件幾何外框（外擴 pad_m）；沒有幾何 → 鄉鎮市區界；都沒有 → None（呼叫端退回舊的整份圖檔）。"""
    if not data:
        return None
    gs = [shape(g) for g in _geoms_in_case(data)]
    if gs:
        minx = min(g.bounds[0] for g in gs)
        miny = min(g.bounds[1] for g in gs)
        maxx = max(g.bounds[2] for g in gs)
        maxy = max(g.bounds[3] for g in gs)
        return pad_bbox((minx, miny, maxx, maxy), pad_m)
    return district_bbox((data.get("case") or {}).get("district"))


def bbox_key(b: BBox, step: float = 0.01) -> BBox:
    """快取用：bbox 取到 0.01°（約 1 km）格網，相近案件共用同一份局部圖資。"""
    return (math.floor(b[0] / step) * step, math.floor(b[1] / step) * step, math.ceil(b[2] / step) * step, math.ceil(b[3] / step) * step)
