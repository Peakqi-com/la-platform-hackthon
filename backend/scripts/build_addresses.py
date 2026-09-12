"""OSM 全量檔 → data/osm/addresses.sqlite：新北一帶有 addr:street＋addr:housenumber 的點與面（門牌定位用；比較標的門牌 → 位置）。"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import osmium
from shapely import wkb
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.spatial.geodb import GeoDB

ROOT = Path(__file__).resolve().parents[2]
BBOX = (121.28, 24.67, 122.02, 25.31)
NUM_RE = re.compile(r"(\d+)")


def norm_street(s: str) -> str:
    return (s or "").replace("台", "臺").replace(" ", "").strip()


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.wkbf = osmium.geom.WKBFactory()
        self.rows = []

    def _add(self, tags, lon, lat, oid):
        st, hn = tags.get("addr:street"), tags.get("addr:housenumber")
        if not st or not hn:
            return
        m = NUM_RE.search(hn)
        if not m:
            return
        self.rows.append((norm_street(st), {"street": norm_street(st), "number": int(m.group(1)), "housenumber": hn, "district": tags.get("addr:district") or tags.get("addr:city") or "",
                                            "osm_id": oid}, Point(lon, lat)))

    def node(self, n):
        if n.location.valid() and BBOX[0] <= n.location.lon <= BBOX[2] and BBOX[1] <= n.location.lat <= BBOX[3] and "addr:housenumber" in n.tags:
            self._add(dict(n.tags), n.location.lon, n.location.lat, f"node/{n.id}")

    def area(self, a):
        if "addr:housenumber" not in a.tags:
            return
        try:
            g = wkb.loads(bytes.fromhex(self.wkbf.create_multipolygon(a)))
        except Exception:  # noqa: BLE001
            return
        c = g.centroid
        if BBOX[0] <= c.x <= BBOX[2] and BBOX[1] <= c.y <= BBOX[3]:
            self._add(dict(a.tags), c.x, c.y, f"area/{a.orig_id()}")


t0 = time.time()
h = H()
h.apply_file(sys.argv[1], locations=True, idx="flex_mem")
db = GeoDB.create(ROOT / "data" / "osm" / "addresses.sqlite")
n = db.write_many(h.rows)
db.set_meta("source", "OpenStreetMap addr:street + addr:housenumber（© OpenStreetMap contributors, ODbL）")
print(f"{n} 筆門牌 → data/osm/addresses.sqlite（{time.time() - t0:.0f} s）")
