"""
路網：全區 SQLite（data/osm/roads.sqlite，scripts/build_osm_ntpc.py）依案件 bbox 局部載入；
沒有全區檔時退回單一 GeoJSON（ROADS_GEOJSON 或 data/roads_osm_jinshan.geojson）。
"""
from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path

from .area import BBox, bbox_key, case_bbox
from .bootstrap import Roads

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
_roads: Roads | None = None
_db = None
_cache: OrderedDict[BBox, Roads] = OrderedDict()
CACHE_N = 6


def roads_db():
    global _db
    if _db is None:
        path = os.environ.get("ROADS_DB") or str(DATA_DIR / "osm" / "roads.sqlite")
        if Path(path).exists():
            from .geodb import GeoDB
            _db = GeoDB(path)
        else:
            _db = False
    return _db or None


def get_roads(bbox: BBox | None = None, *, data: dict | None = None, pad_m: float = 3000.0) -> Roads:
    """bbox 或案件（data）→ 該範圍的路網。沒有全區 SQLite 時忽略範圍，回傳整份舊圖檔。"""
    global _roads
    db = roads_db()
    if db is not None:
        b = bbox or case_bbox(data, pad_m=pad_m)
        if b is None:
            return Roads([])
        k = bbox_key(b)
        if k in _cache:
            _cache.move_to_end(k)
            return _cache[k]
        r = Roads(db.query(k))
        _cache[k] = r
        while len(_cache) > CACHE_N:
            _cache.popitem(last=False)
        return r
    if _roads is None:
        path = os.environ.get("ROADS_GEOJSON") or str(DATA_DIR / "roads_osm_jinshan.geojson")
        _roads = Roads.from_geojson(path) if Path(path).exists() else Roads([])
    return _roads


def set_roads(r: Roads) -> None:
    global _roads, _db
    _roads = r
    _db = False
    _cache.clear()


def roads_status() -> dict:
    db = roads_db()
    if db is not None:
        return {"mode": "sqlite", "path": db.path, "features": db.count()}
    return {"mode": "geojson", "path": os.environ.get("ROADS_GEOJSON") or str(DATA_DIR / "roads_osm_jinshan.geojson"), "features": len(get_roads().items)}
