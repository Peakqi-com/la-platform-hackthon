"""OSM 全量檔 → data/osm/districts.geojson（鄉鎮市區界：boundary=administrative，臺灣的區／鄉鎮市是 admin_level=7）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import osmium
from shapely import wkb
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parents[2]
BBOX = (121.28, 24.67, 122.02, 25.31)


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkbf = osmium.geom.WKBFactory()
        self.out = []

    def area(self, a):
        t = dict(a.tags)
        if t.get("boundary") != "administrative" or t.get("admin_level") != "7" or not a.from_way() is False:
            return
        try:
            g = wkb.loads(bytes.fromhex(self.wkbf.create_multipolygon(a)))
        except Exception:  # noqa: BLE001
            return
        c = g.centroid
        if BBOX[0] <= c.x <= BBOX[2] and BBOX[1] <= c.y <= BBOX[3]:
            self.out.append({"type": "Feature", "geometry": mapping(g), "properties": {"name": t.get("name"), "osm_id": a.orig_id(), "admin_level": 7}})


h = H()
h.apply_file(sys.argv[1], locations=True, idx="flex_mem")
(ROOT / "data" / "osm" / "districts.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": h.out}, ensure_ascii=False), encoding="utf-8")
print(len(h.out), sorted(f["properties"]["name"] for f in h.out))
