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
               "道路用地": "#bdbdbd", "河川區": "#7fc7e6", "墓地": "#9e9e9e", "墳墓用地": "#9e9e9e", "停車場用地": "#c7b299",
               "第一種住宅區": "#fff1a8", "第二種住宅區": "#f2c744", "第三種住宅區": "#e6a63a", "第一之一種住宅區": "#fbe27a"}
# 分區名稱關鍵字 → 顏色（新北市分區名稱有 100 多種：住宅黃、商業紅、工業紫、農業／保護／公園綠、學校／機關藍、道路灰、鐵路捷運深灰、水系淺藍）；依序比對，先中先贏
_ZONE_KEYWORD_COLORS: list[tuple[tuple[str, ...], str]] = [
    (("第一種住宅",), "#fff1a8"), (("第二種住宅",), "#f2c744"), (("第三種住宅", "第四種住宅"), "#e6a63a"), (("住宅",), "#f2c744"),
    (("商業",), "#e5533d"), (("工業", "產業"), "#8e6bbf"), (("農業",), "#8bc34a"), (("保護", "保存", "風景"), "#4c8f5a"),
    (("公園", "兒童遊樂", "綠地", "綠帶"), "#57b96b"), (("廣場",), "#a8d5b5"),
    (("學校", "文小", "文中", "文高", "國小", "國中", "大專", "社教", "文教"), "#5aa9e6"),
    (("市場",), "#ff9e4a"), (("停車",), "#c7b299"), (("墓", "墳"), "#9e9e9e"),
    (("河川", "水溝", "排水", "溝渠", "滯洪", "堤防", "水域", "港"), "#7fc7e6"),
    (("鐵路", "捷運", "高鐵", "車站"), "#8d8d8d"), (("道路", "人行", "高速公路", "交通"), "#bdbdbd"),
    (("機關", "行政", "醫療", "宗教", "寺廟", "電力", "變電", "自來水", "污水", "抽水", "加油站", "郵政", "電信", "專用區", "公共設施", "公用"), "#5b7fc7"),
    (("電路鐵塔", "土石方", "垃圾", "環保"), "#b0a8a0"),
]


def zone_color(zone: str | None) -> str:
    """分區 → 色碼：先查明確對照表，再依名稱關鍵字歸類；都對不到給淺灰。"""
    z = (zone or "").strip()
    if z in ZONE_COLORS:
        return ZONE_COLORS[z]
    for keys, col in _ZONE_KEYWORD_COLORS:
        if any(k in z for k in keys):
            return col
    return "#dddddd"


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
                            "properties": {"zone": z, "color": zone_color(z), "source": self.source}})
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
                            "properties": {"zone": z, "color": zone_color(z), "source": self.source}})
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
