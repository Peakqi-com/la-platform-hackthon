"""
新北市都市計畫使用分區 shapefile（城鄉局開放資料，TWD97，欄位 ZONE，34,190 面）→ data/zoning/ntpc_zoning.sqlite（R-tree + WKB）。
整份轉 GeoJSON 有 243 MB、每次啟動要讀 10 秒以上；SQLite 版查 bbox 才組幾何（app/maps/zoning.ZoningDB）。
用法：python3 scripts/build_zoning_db.py [../data/zoning/shp/新北市使用分區.shp]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import shapefile
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform
from shapely.validation import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.spatial.geodb import GeoDB

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "zoning" / "shp" / "新北市使用分區.shp"
    out = ROOT / "data" / "zoning" / "ntpc_zoning.sqlite"
    t0 = time.time()
    r = shapefile.Reader(str(src), encoding="big5")
    tr = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)

    def rows():
        for sr in r.iterShapeRecords():
            zone = (sr.record[0] or "").strip()
            g = shape(sr.shape.__geo_interface__)
            if not g.is_valid:
                g = make_valid(g)
            yield zone, {"zone": zone}, transform(tr.transform, g)

    db = GeoDB.create(out)
    n = db.write_many(rows())
    db.set_meta("source", "新北市都市計畫土地使用分區（城鄉局開放資料，TWD97 shapefile 轉 WGS84）")
    print(f"{n} 面 → {out}（{time.time() - t0:.0f} s）")


if __name__ == "__main__":
    main()
