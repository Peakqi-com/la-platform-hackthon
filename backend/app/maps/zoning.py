"""都市計畫使用分區圖（新北市城鄉局開放資料，TWD97 shapefile → 已轉 WGS84 GeoJSON，欄位 ZONE）。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from shapely.geometry import box, mapping, shape
from shapely.strtree import STRtree

from app.spatial.geo import as_shape

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
ZONE_COLORS = {"商業區": "#e5533d", "住宅區": "#f2c744", "工業區": "#8e6bbf", "乙種工業區": "#8e6bbf", "農業區": "#8bc34a", "保護區": "#4c8f5a",
               "市場用地": "#ff9e4a", "公園用地": "#57b96b", "公園綠地": "#57b96b", "學校用地": "#5aa9e6", "機關用地": "#5b7fc7",
               "道路用地": "#bdbdbd", "河川區": "#7fc7e6", "墓地": "#9e9e9e", "墳墓用地": "#9e9e9e", "停車場用地": "#c7b299"}


class ZoningStore:
    def __init__(self, features: list[dict], name_field: str = "ZONE", source: str = "新北市都市計畫土地使用分區（城鄉局開放資料）"):
        self.features = features
        self.name_field = name_field
        self.source = source
        self.geoms = [shape(f["geometry"]) for f in features]
        self.tree = STRtree(self.geoms) if self.geoms else None

    @classmethod
    def from_geojson(cls, path: str | Path, **kw) -> ZoningStore:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["features"], **kw)

    def __len__(self) -> int:
        return len(self.features)

    def at(self, point: Any) -> dict[str, Any] | None:
        """點 → {zone, source}；沒有 → None。"""
        if not self.tree:
            return None
        p = as_shape(point)
        for i in self.tree.query(p):
            if self.geoms[i].intersects(p):
                return {"zone": self.features[i]["properties"].get(self.name_field), "source": self.source}
        return None

    def within_bbox(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        if not self.tree:
            return []
        b = box(*bbox)
        out = []
        for i in self.tree.query(b):
            g = self.geoms[i]
            if g.intersects(b):
                f = self.features[i]
                z = f["properties"].get(self.name_field)
                out.append({"type": "Feature", "geometry": mapping(g.intersection(b)),
                            "properties": {"zone": z, "color": ZONE_COLORS.get(z, "#dddddd"), "source": self.source}})
        return out


class ZoningDB(ZoningStore):
    """全區使用分區 SQLite（data/zoning/ntpc_zoning.sqlite，scripts/build_zoning_db.py）：查 bbox 才組幾何，啟動不載入。"""

    def __init__(self, path: str | Path, name_field: str = "ZONE", source: str = "新北市都市計畫土地使用分區（城鄉局開放資料，全區）"):
        from app.spatial.geodb import GeoDB
        self.db = GeoDB(path)
        self.features = []
        self.geoms = []
        self.tree = None
        self.name_field = name_field
        self.source = source
        self._n = self.db.count()

    def __len__(self) -> int:
        return self._n

    def at(self, point: Any) -> dict[str, Any] | None:
        p = as_shape(point)
        for _id, name, props, g in self.db.query_geoms((p.x - 1e-7, p.y - 1e-7, p.x + 1e-7, p.y + 1e-7)):
            if g.intersects(p):
                return {"zone": props.get("zone") or name, "source": self.source}
        return None

    def within_bbox(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        b = box(*bbox)
        out = []
        for _id, name, props, g in self.db.query_geoms(bbox):
            if g.intersects(b):
                z = props.get("zone") or name
                out.append({"type": "Feature", "geometry": mapping(g.intersection(b)),
                            "properties": {"zone": z, "color": ZONE_COLORS.get(z, "#dddddd"), "source": self.source}})
        return out


_store: ZoningStore | None = None


def get_zoning_store() -> ZoningStore:
    global _store
    if _store is None:
        dbp = os.environ.get("ZONING_DB") or str(DATA_DIR / "zoning" / "ntpc_zoning.sqlite")
        path = os.environ.get("ZONING_GEOJSON") or str(DATA_DIR / "zoning" / "jinshan_zoning.geojson")
        if Path(dbp).exists() and not os.environ.get("ZONING_GEOJSON"):
            _store = ZoningDB(dbp)
        else:
            _store = ZoningStore.from_geojson(path) if Path(path).exists() else ZoningStore([])
    return _store


def set_zoning_store(s: ZoningStore | None) -> None:
    global _store
    _store = s
