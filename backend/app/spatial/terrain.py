"""
高程：AWS Terrain Tiles（Mapzen terrarium 格式，SRTM 等衛星測高，約 30 m 解析度），無需金鑰，離線快取在 data/terrain。
用途：宗地地勢（手冊 p.23 4(4)：以自主要出入道路需梯坡上行／下行通達判高亢、低窪）與區段地勢（表1 自然條件）之推定。
內政部 20 m DEM 開放資料若已下載成同格式瓦片可直接替換；本模組只提供「相對高差」判斷，門檻為系統推定規則（見 docs/07）。
"""
from __future__ import annotations

import io
import math
import os
import ssl
from pathlib import Path
from typing import Any

TERRAIN_DIR = Path(__file__).resolve().parents[3] / "data" / "terrain"
URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SOURCE = "衛星測高高程資料（Terrain Tiles，約 30 公尺格網）"
Z = 14
_cache: dict[tuple[int, int, int], Any] = {}


def _xy(lon: float, lat: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(z: int, x: int, y: int, *, fetch: bool = True):
    key = (z, x, y)
    if key in _cache:
        return _cache[key]
    from PIL import Image
    p = TERRAIN_DIR / str(z) / str(x) / f"{y}.png"
    if not p.exists():
        if not fetch or os.environ.get("TERRAIN_OFFLINE"):
            _cache[key] = None
            return None
        import urllib.request

        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        try:
            with urllib.request.urlopen(URL.format(z=z, x=x, y=y), timeout=20, context=ctx) as r:
                data = r.read()
        except Exception:  # noqa: BLE001 - 沒網路就當沒資料
            _cache[key] = None
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    im = Image.open(io.BytesIO(p.read_bytes())).convert("RGB")
    _cache[key] = im
    return im


def elevation(lon: float, lat: float, *, z: int = Z, fetch: bool = True) -> float | None:
    """公尺；沒瓦片 → None。"""
    fx, fy = _xy(lon, lat, z)
    tx, ty = int(fx), int(fy)
    im = _tile(z, tx, ty, fetch=fetch)
    if im is None:
        return None
    px, py = min(255, int((fx - tx) * 256)), min(255, int((fy - ty) * 256))
    r, g, b = im.getpixel((px, py))
    return round((r * 256 + g + b / 256) - 32768, 1)


def prefetch(bbox: tuple[float, float, float, float], z: int = Z) -> int:
    """賽前預抓：bbox=(minlon, minlat, maxlon, maxlat)。回傳瓦片數。"""
    x0, y1 = _xy(bbox[0], bbox[1], z)
    x1, y0 = _xy(bbox[2], bbox[3], z)
    n = 0
    for x in range(int(x0), int(x1) + 1):
        for y in range(int(y0), int(y1) + 1):
            if _tile(z, x, y) is not None:
                n += 1
    return n


def status() -> dict[str, Any]:
    n = sum(1 for _ in TERRAIN_DIR.rglob("*.png")) if TERRAIN_DIR.exists() else 0
    return {"tiles": n, "dir": str(TERRAIN_DIR), "source": SOURCE, "zoom": Z}


# ---------------------------------------------------------------- 推定規則（系統規則，非法規；門檻寫在 docs/07）

PARCEL_STEP_M = 1.0      # 宗地相對面前道路高差 > 1 m 視為需梯坡（手冊 p.23 4(4) 高亢／低窪）
SECTION_FLAT_M = 2.0     # 區段內取樣點與中位數高差 ≤ 2 m 視為平坦


def parcel_terrain(parcel_geom: Any, road_point: Any | None, *, fetch: bool = True) -> dict[str, Any] | None:
    """宗地地勢：平坦／緩坡（高亢）／低窪。road_point 沒有 → None。"""
    from .geo import as_shape, centroid
    c = centroid(as_shape(parcel_geom))
    zp = elevation(c.x, c.y, fetch=fetch)
    if road_point is None or zp is None:
        return None
    rp = as_shape(road_point)
    zr = elevation(rp.x, rp.y, fetch=fetch)
    if zr is None:
        return None
    d = zp - zr
    value = "平坦" if abs(d) <= PARCEL_STEP_M else ("緩坡" if d > 0 else "低窪")
    return {"value": value, "parcel_m": zp, "road_m": zr, "diff_m": round(d, 1),
            "note": f"宗地中心高程 {zp} m，面前道路 {zr} m，高差 {d:+.1f} m（|高差| ≤ {PARCEL_STEP_M} m 視為平坦；手冊 p.23 4(4)）；{SOURCE}"}


def section_terrain(polygon: Any, *, n: int = 36, fetch: bool = True) -> dict[str, Any] | None:
    """區段地勢：依取樣點平坦比例對應表1 五級描述。"""
    from shapely.geometry import Point

    from .geo import as_shape
    poly = as_shape(polygon)
    minx, miny, maxx, maxy = poly.bounds
    k = max(2, int(math.sqrt(n)))
    pts = []
    for i in range(k):
        for j in range(k):
            p = Point(minx + (maxx - minx) * (i + 0.5) / k, miny + (maxy - miny) * (j + 0.5) / k)
            if poly.contains(p):
                pts.append(p)
    zs = [z for z in (elevation(p.x, p.y, fetch=fetch) for p in pts) if z is not None]
    if len(zs) < 4:
        return None
    zs_sorted = sorted(zs)
    med = zs_sorted[len(zs) // 2]
    flat = sum(1 for z in zs if abs(z - med) <= SECTION_FLAT_M) / len(zs)
    value = ("該區地勢平坦" if flat >= 0.9 else "該區大部分地勢平坦" if flat >= 0.7 else "該區一半地勢平坦" if flat >= 0.5
             else "該區大部分地勢高亢或低窪" if flat >= 0.3 else "該區全部地勢高亢或低窪")
    return {"value": value, "flat_ratio": round(flat, 2), "median_m": med, "min_m": zs_sorted[0], "max_m": zs_sorted[-1], "n": len(zs),
            "note": f"區段內 {len(zs)} 個取樣點高程 {zs_sorted[0]}～{zs_sorted[-1]} m，中位數 {med} m，高差 ≤ {SECTION_FLAT_M} m 者占 {flat:.0%}（≥90% 平坦、≥70% 大部分平坦、≥50% 一半、≥30% 大部分高亢或低窪）；{SOURCE}"}
