"""
預抓底圖瓦片到 data/tiles，讓會場沒有外網時互動地圖與三張圖說仍有底圖。
用法：cd backend && python3 scripts/prefetch_tiles.py [--bbox minlon,minlat,maxlon,maxlat] [--zooms 14-18]
預設範圍：金山區 P002-00 一帶（案件區段外擴約 1.5 km）。
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.maps.render import TILE_DIR, tile_bytes


def _xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", default="121.615,25.205,121.660,25.240")
    ap.add_argument("--zooms", default="14-18")
    a = ap.parse_args()
    minlon, minlat, maxlon, maxlat = (float(v) for v in a.bbox.split(","))
    z0, z1 = (int(v) for v in a.zooms.split("-"))
    total = ok = 0
    t0 = time.time()
    for z in range(z0, z1 + 1):
        x0, y1 = _xy(minlon, minlat, z)
        x1, y0 = _xy(maxlon, maxlat, z)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for layer in ("EMAP", "LANDSECT"):
                    total += 1
                    if tile_bytes(z, x, y, timeout=8.0, layer=layer) is not None:
                        ok += 1
        print(f"z{z}: 累計 {ok}/{total}", flush=True)
    print(f"完成：{ok}/{total} 塊，快取在 {TILE_DIR}，{time.time() - t0:.0f} 秒")


if __name__ == "__main__":
    main()
