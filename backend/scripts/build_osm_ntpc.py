"""
Geofabrik 臺灣 OSM 全量檔（taiwan-latest.osm.pbf）→ 新北市（含鄰接縣市邊緣）圖資：
  data/osm/roads.sqlite      有名道路（highway + name）：name, highway, width, lanes, osm_id       → 路網（街廓、四至、道路寬度）
  data/osm/walk.sqlite       全部 highway 線段：name, highway, foot, access, osm_id                → 內建步行圖
  data/osm/poi_osm.sqlite    設施點位（build_poi.OVERPASS_TAGS 的類別 + 娛樂設施）                 → 設施資料庫
  data/osm/districts.geojson 鄉鎮市區界（boundary=administrative, admin_level=8）                → 依行政區取範圍
用法：python3 scripts/build_osm_ntpc.py /path/to/taiwan-latest.osm.pbf
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import osmium
from shapely import wkb
from shapely.geometry import mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_poi import OVERPASS_TAGS, _tag_match

from app.spatial.geodb import GeoDB
from app.spatial.poi import POI, POIStore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "osm"
BBOX = (121.28, 24.67, 122.02, 25.31)                  # 新北市外框（含臺北市、基隆、桃園邊緣，鄰接設施也量得到）
OSM_SRC = "OpenStreetMap（© OpenStreetMap contributors, ODbL）"
ENTERTAINMENT = [("amenity", "theatre"), ("amenity", "nightclub"), ("amenity", "karaoke_box"), ("amenity", "casino"),
                 ("leisure", "amusement_arcade"), ("leisure", "bowling_alley"), ("leisure", "water_park"), ("leisure", "escape_game"),
                 ("tourism", "theme_park"), ("leisure", "sports_centre"), ("leisure", "stadium")]
WASTE = [("amenity", "waste_transfer_station"), ("man_made", "incinerator")]


def poi_type(tags: dict) -> str | None:
    for k, v in ENTERTAINMENT:
        if tags.get(k) == v:
            return "entertainment"
    for k, v in WASTE:
        if tags.get(k) == v:
            return "incinerator"
    return next((ft for ft, tag in OVERPASS_TAGS.items() if _tag_match(tag, tags)), None)


def in_bbox(lon: float, lat: float) -> bool:
    return BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkbf = osmium.geom.WKBFactory()
        self.roads: list = []
        self.walk: list = []
        self.pois = POIStore()
        self.districts: list = []
        self.n_way = 0

    def node(self, n):
        if not n.location.valid() or not in_bbox(n.location.lon, n.location.lat):
            return
        tags = dict(n.tags)
        t = poi_type(tags)
        if t:
            from shapely.geometry import Point
            self.pois.add(POI(type=t, name=tags.get("name") or tags.get("name:zh") or "", geom=Point(n.location.lon, n.location.lat),
                              source=OSM_SRC, source_id=f"node/{n.id}", attrs=tags))

    def way(self, w):
        tags = dict(w.tags)
        hw = tags.get("highway")
        if not hw or len(w.nodes) < 2:
            return
        try:
            loc = w.nodes[0].location
            if not loc.valid() or not in_bbox(loc.lon, loc.lat):
                return
            g = wkb.loads(bytes.fromhex(self.wkbf.create_linestring(w)))
        except Exception:  # noqa: BLE001 - 節點不全
            return
        self.n_way += 1
        name = tags.get("name") or tags.get("name:zh")
        self.walk.append((name, {"highway": hw, "foot": tags.get("foot"), "access": tags.get("access"), "osm_id": w.id}, g))
        if name:
            self.roads.append((name, {"highway": hw, "width": tags.get("width"), "lanes": tags.get("lanes"), "osm_id": w.id}, g))
        if not w.is_closed():
            t = poi_type(tags)
            if t:
                self.pois.add(POI(type=t, name=name or "", geom=g, source=OSM_SRC, source_id=f"way/{w.id}", attrs=tags))

    def area(self, a):
        tags = dict(a.tags)
        t = poi_type(tags)
        admin = tags.get("boundary") == "administrative" and tags.get("admin_level") == "8"
        if not t and not admin:
            return
        try:
            g = wkb.loads(bytes.fromhex(self.wkbf.create_multipolygon(a)))
        except Exception:  # noqa: BLE001
            return
        c = g.centroid
        if not in_bbox(c.x, c.y):
            return
        if admin:
            self.districts.append({"type": "Feature", "geometry": mapping(g), "properties": {"name": tags.get("name"), "osm_id": a.orig_id()}})
        if t:
            self.pois.add(POI(type=t, name=tags.get("name") or tags.get("name:zh") or "", geom=g, source=OSM_SRC,
                              source_id=f"{'way' if a.from_way() else 'relation'}/{a.orig_id()}", attrs=tags))


def main() -> None:
    src = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    h = H()
    h.apply_file(src, locations=True, idx="flex_mem")
    print(f"讀取完成 {time.time() - t0:.0f} s：highway {h.n_way:,}、有名 {len(h.roads):,}、POI {len(h.pois):,}、行政區 {len(h.districts)}", flush=True)
    db = GeoDB.create(OUT / "roads.sqlite")
    db.write_many(h.roads)
    db.set_meta("source", OSM_SRC)
    db = GeoDB.create(OUT / "walk.sqlite")
    db.write_many(h.walk)
    db.set_meta("source", OSM_SRC)
    h.pois.to_sqlite(OUT / "poi_osm.sqlite")
    (OUT / "districts.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": h.districts}, ensure_ascii=False), encoding="utf-8")
    print(f"寫入完成 {time.time() - t0:.0f} s → {OUT}", flush=True)
    print(h.pois.types(), flush=True)


if __name__ == "__main__":
    main()
