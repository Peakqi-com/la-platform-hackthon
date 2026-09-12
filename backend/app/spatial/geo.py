"""座標與幾何。輸入輸出一律 WGS84（GeoJSON），計算時投影到 TWD97 / TM2 (EPSG:3826) 算公尺。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, transform

_TO_TWD97 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)
_TO_WGS84 = Transformer.from_crs("EPSG:3826", "EPSG:4326", always_xy=True)


def to_twd97(g: BaseGeometry) -> BaseGeometry:
    return transform(_TO_TWD97.transform, g)


def to_wgs84(g: BaseGeometry) -> BaseGeometry:
    return transform(_TO_WGS84.transform, g)


def as_shape(g: Any) -> BaseGeometry:
    """GeoJSON dict / shapely / (lon, lat) / {"lon","lat"} → shapely（WGS84）。"""
    if isinstance(g, BaseGeometry):
        return g
    if isinstance(g, dict):
        if "type" in g and ("coordinates" in g or g["type"] == "GeometryCollection"):
            return shape(g)
        if g.get("type") == "Feature":
            return shape(g["geometry"])
        if "lon" in g and "lat" in g:
            return Point(float(g["lon"]), float(g["lat"]))
    if isinstance(g, (list, tuple)) and len(g) == 2 and all(isinstance(x, (int, float)) for x in g):
        return Point(float(g[0]), float(g[1]))
    raise ValueError(f"無法解析幾何：{type(g)}")


def to_geojson(g: BaseGeometry) -> dict:
    return mapping(g)


def straight_distance_m(a: Any, b: Any) -> float:
    """直線距離（公尺）。面狀幾何取最近點；一方含另一方 → 0。"""
    pa, pb = to_twd97(as_shape(a)), to_twd97(as_shape(b))
    return float(pa.distance(pb))


def nearest_point_on(a: Any, b: Any) -> Point:
    """a 上最接近 b 的點（WGS84）。a 是多邊形時取邊界上的點。"""
    sa, sb = to_twd97(as_shape(a)), to_twd97(as_shape(b))
    base = sa.boundary if sa.geom_type in ("Polygon", "MultiPolygon") else sa
    p, _ = nearest_points(base, sb)
    return to_wgs84(p)


def boundary_nearest_point(polygon: Any, target: Any) -> Point:
    """區段邊界上最接近設施的點 —— 範本「本區段外(距 X M)」的推定量測起點。"""
    return nearest_point_on(polygon, target)


def centroid(g: Any) -> Point:
    return to_wgs84(to_twd97(as_shape(g)).centroid)


def frontage_point(parcel: Any, road: Any) -> Point:
    """臨路邊界點：宗地邊界上最接近面前道路（線或點）的點。"""
    return nearest_point_on(parcel, road)


def contains(container: Any, g: Any) -> bool:
    return bool(as_shape(container).intersects(as_shape(g)))


def offset_point(lon: float, lat: float, dx_m: float, dy_m: float) -> Point:
    """從 (lon, lat) 往東 dx、往北 dy 公尺的點（測試造資料用）。"""
    x, y = _TO_TWD97.transform(lon, lat)
    lon2, lat2 = _TO_WGS84.transform(x + dx_m, y + dy_m)
    return Point(lon2, lat2)


@lru_cache(maxsize=1)
def crs_info() -> dict:
    return {"storage": "EPSG:4326 (WGS84)", "compute": "EPSG:3826 (TWD97 / TM2 台灣本島)", "unit": "m"}
