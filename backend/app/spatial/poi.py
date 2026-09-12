"""
POI 庫。資料量小（一個鄉鎮幾千筆），直接記憶體 + shapely 掃描；持久化用 SQLite（不依賴 spatialite）。
每筆保留 source（資料集名稱）、source_id，會原樣出現在 Facility.source。
type 必須是 rules/facility_measurement.json 的 key。
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shapely import wkt
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry

from .geo import as_shape, to_twd97


@dataclass
class POI:
    type: str
    name: str
    geom: BaseGeometry                 # WGS84
    source: str
    source_id: str | None = None
    attrs: dict = field(default_factory=dict)
    id: int | None = None

    @property
    def lon(self) -> float:
        return float(self.geom.centroid.x)

    @property
    def lat(self) -> float:
        return float(self.geom.centroid.y)

    def to_feature(self) -> dict:
        return {"type": "Feature", "geometry": mapping(self.geom),
                "properties": {"id": self.id, "type": self.type, "name": self.name, "source": self.source,
                               "source_id": self.source_id, **self.attrs}}


class POIStore:
    def __init__(self, pois: Iterable[POI] = ()):
        self.pois: list[POI] = []
        for p in pois:
            self.add(p)

    def add(self, p: POI) -> POI:
        if p.id is None:
            p.id = len(self.pois) + 1
        self.pois.append(p)
        self._by_type.setdefault(p.type, []).append(p)
        self._bounds[id(p)] = p.geom.bounds
        return p

    _by_type: dict[str, list[POI]]
    _bounds: dict[int, tuple[float, float, float, float]]

    def __new__(cls, *a, **k):
        self = super().__new__(cls)
        self._by_type, self._bounds = {}, {}
        return self

    def bounds_of(self, p: POI) -> tuple[float, float, float, float]:
        b = self._bounds.get(id(p))
        if b is None:
            b = p.geom.bounds
            self._bounds[id(p)] = b
        return b

    def __len__(self) -> int:
        return len(self.pois)

    def types(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for p in self.pois:
            out[p.type] = out.get(p.type, 0) + 1
        return out

    def by_types(self, types: Iterable[str]) -> list[POI]:
        out: list[POI] = []
        for t in types:
            out.extend(self._by_type.get(t, []))
        return out

    def nearest(self, origin: Any, types: Iterable[str], k: int = 1, max_m: float | None = None) -> list[tuple[POI, float]]:
        """依直線距離排序的 (POI, 公尺)。origin 可為點或多邊形（多邊形取最近點距離；在內部 → 0）。"""
        og = as_shape(origin)
        o = to_twd97(og)
        scored = []
        cands = self.by_types(types)
        if max_m is not None and cands:                 # 先用經緯度外框粗篩（全區設施庫幾萬筆，逐筆投影太慢）
            deg = max_m / 100_000.0
            minx, miny, maxx, maxy = og.bounds
            x0, y0, x1, y1 = minx - deg, miny - deg, maxx + deg, maxy + deg
            bo = self.bounds_of
            cands = [p for p in cands if (b := bo(p))[2] >= x0 and b[0] <= x1 and b[3] >= y0 and b[1] <= y1]
        for p in cands:
            d = float(o.distance(to_twd97(p.geom)))
            if max_m is None or d <= max_m:
                scored.append((p, d))
        scored.sort(key=lambda x: x[1])
        return scored[:k] if k else scored

    def within(self, polygon: Any, types: Iterable[str]) -> list[POI]:
        poly = as_shape(polygon)
        minx, miny, maxx, maxy = poly.bounds
        bo = self.bounds_of
        return [p for p in self.by_types(types)
                if (b := bo(p))[2] >= minx and b[0] <= maxx and b[3] >= miny and b[1] <= maxy and poly.intersects(p.geom)]

    # ---------------------------------------------------------------- GeoJSON
    @classmethod
    def from_geojson(cls, src: str | Path | dict, *, source: str | None = None, type_field: str = "type",
                     name_field: str = "name", type_map: dict[str, str] | None = None, default_type: str | None = None) -> POIStore:
        data = src if isinstance(src, dict) else json.loads(Path(src).read_text(encoding="utf-8"))
        store = cls()
        feats = data["features"] if data.get("type") == "FeatureCollection" else [data]
        for f in feats:
            props = dict(f.get("properties") or {})
            raw_t = props.pop(type_field, None)
            t = (type_map or {}).get(raw_t, raw_t) or default_type
            if not t:
                continue
            name = props.pop(name_field, None) or props.get("名稱") or ""
            store.add(POI(type=t, name=str(name), geom=shape(f["geometry"]), source=props.pop("source", None) or source or "geojson",
                          source_id=str(props.pop("source_id", props.pop("id", "")) or "") or None, attrs=props))
        return store

    def to_geojson(self) -> dict:
        return {"type": "FeatureCollection", "features": [p.to_feature() for p in self.pois]}

    # ---------------------------------------------------------------- CSV（經緯度欄）
    @classmethod
    def from_rows(cls, rows: Iterable[dict], *, type: str | None = None, type_field: str | None = None,
                  name_field: str = "name", lon_field: str = "lon", lat_field: str = "lat", source: str = "csv",
                  type_map: dict[str, str] | None = None, id_field: str | None = None) -> POIStore:
        store = cls()
        for r in rows:
            try:
                lon, lat = float(r[lon_field]), float(r[lat_field])
            except (KeyError, TypeError, ValueError):
                continue
            t = type or (type_map or {}).get(r.get(type_field), r.get(type_field)) if (type or type_field) else None
            if not t:
                continue
            attrs = {k: v for k, v in r.items() if k not in (lon_field, lat_field, name_field, type_field, id_field)}
            store.add(POI(type=t, name=str(r.get(name_field) or ""), geom=Point(lon, lat), source=source,
                          source_id=str(r[id_field]) if id_field and r.get(id_field) is not None else None, attrs=attrs))
        return store

    # ---------------------------------------------------------------- SQLite
    def to_sqlite(self, path: str | Path) -> None:
        con = sqlite3.connect(str(path))
        con.execute("DROP TABLE IF EXISTS poi")
        con.execute("CREATE TABLE poi (id INTEGER PRIMARY KEY, type TEXT, name TEXT, lon REAL, lat REAL, geom_wkt TEXT, source TEXT, source_id TEXT, attrs TEXT)")
        con.execute("CREATE INDEX idx_poi_type ON poi(type)")
        con.executemany("INSERT INTO poi VALUES (?,?,?,?,?,?,?,?,?)",
                        [(p.id, p.type, p.name, p.lon, p.lat, p.geom.wkt, p.source, p.source_id, json.dumps(p.attrs, ensure_ascii=False)) for p in self.pois])
        con.commit()
        con.close()

    @classmethod
    def from_sqlite(cls, path: str | Path) -> POIStore:
        con = sqlite3.connect(str(path))
        store = cls()
        for row in con.execute("SELECT id, type, name, geom_wkt, source, source_id, attrs FROM poi ORDER BY id"):
            store.add(POI(id=row[0], type=row[1], name=row[2], geom=wkt.loads(row[3]), source=row[4], source_id=row[5],
                          attrs=json.loads(row[6] or "{}")))
        con.close()
        return store

    def reindex(self) -> None:
        self._by_type, self._bounds = {}, {}
        for p in self.pois:
            self._by_type.setdefault(p.type, []).append(p)
            self._bounds[id(p)] = p.geom.bounds

    def merge(self, other: POIStore) -> POIStore:
        """合併；同 (source, source_id) 者以 other 為準（人工標定同名覆寫、重跑 build_poi 不會重複）。"""
        keyed = {(p.source, p.source_id): i for i, p in enumerate(self.pois) if p.source_id}
        for p in other.pois:
            k = (p.source, p.source_id)
            if p.source_id and k in keyed:
                p.id = self.pois[keyed[k]].id
                self.pois[keyed[k]] = p
            else:
                p.id = None
                self.add(p)
                keyed[k] = len(self.pois) - 1
        self.reindex()
        return self
