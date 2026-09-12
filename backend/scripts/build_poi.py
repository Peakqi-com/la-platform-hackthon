"""
把各政府資料集轉成統一 POI 庫（data/poi.sqlite）。賽前執行一次；當天只讀。

用法：
  python scripts/build_poi.py --manifest ../data/sources/manifest.json --out ../data/poi.sqlite
  python scripts/build_poi.py --overpass "25.20,121.60,25.26,121.68" --out ../data/poi_osm.sqlite   # 以 OSM Overpass 補政府沒有的類別

manifest.json 範例（每個來源一筆；type 用 rules/facility_measurement.json 的 key）：
[
  {"type": "school", "format": "csv", "file": "schools.csv", "name": "學校名稱", "lon": "經度", "lat": "緯度", "source": "教育部全國各級學校基本資料"},
  {"format": "geojson", "file": "parks.geojson", "type": "park", "name_field": "PARK_NAME", "source": "新北市公園資料"},
  {"format": "geojson", "file": "mixed.geojson", "type_field": "kind", "type_map": {"市場": "traditional_market"}, "source": "..."}
]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.spatial.poi import POIStore

# OSM tag → facility type（政府開放資料沒有或不完整的類別）
OVERPASS_TAGS = {
    "supermarket": '["shop"="supermarket"]', "hypermarket": '["shop"="mall"]', "department_store": '["shop"="department_store"]',
    "cinema": '["amenity"="cinema"]', "bank": '["amenity"="bank"]', "post_office_bank": '["amenity"="post_office"]',
    "gas_station": '["amenity"="fuel"]', "substation": '["power"="substation"]', "hv_tower": '["power"="tower"]',
    "school": '["amenity"="school"]', "park": '["leisure"="park"]', "parking_lot": '["amenity"="parking"]',
    "bus_stop": '["highway"="bus_stop"]', "traditional_market": '["amenity"="marketplace"]', "cemetery": '["landuse"="cemetery"]',
    "tourist_hotel": '["tourism"="hotel"]', "tourist_attraction": '["tourism"="attraction"]',
    "intercity_bus_station": '["amenity"="bus_station"]', "pedestrian_zone": '["highway"="pedestrian"]', "plaza": '["place"="square"]',
    "funeral_home": '["amenity"="funeral_hall"]', "columbarium": '["amenity"="grave_yard"]', "rail_station": '["railway"="station"]',
    "incinerator": '["man_made"="wastewater_plant"]', "landfill": '["landuse"="landfill"]', "mrt_station": '["station"="subway"]',
    "shop": '["shop"]',                                   # 任何店舖（工商活動：店舖毗連狀態、顧客通行量推定用）
}


def load_manifest(manifest: Path, base: Path) -> POIStore:
    store = POIStore()
    for src in json.loads(manifest.read_text(encoding="utf-8")):
        f = base / src["file"]
        if src["format"] == "csv":
            with open(f, encoding=src.get("encoding", "utf-8-sig"), newline="") as fh:
                rows = list(csv.DictReader(fh))
            part = POIStore.from_rows(rows, type=src.get("type"), type_field=src.get("type_field"), name_field=src.get("name", "name"),
                                      lon_field=src.get("lon", "lon"), lat_field=src.get("lat", "lat"), source=src["source"],
                                      type_map=src.get("type_map"), id_field=src.get("id"))
        else:
            part = POIStore.from_geojson(f, source=src["source"], type_field=src.get("type_field", "type"),
                                         name_field=src.get("name_field", "name"), type_map=src.get("type_map"), default_type=src.get("type"))
        print(f"{src['file']}: {len(part)} 筆 → {part.types()}")
        store.merge(part)
    return store


OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter"]
HEADERS = {"User-Agent": "ntpc-appraisal-review/0.1 (hackathon POI build)", "Accept": "application/json"}


def fetch_overpass(bbox: str, types: list[str] | None = None, url: str | None = None) -> POIStore:
    import httpx

    from app.spatial.poi import POI
    types = types or list(OVERPASS_TAGS)
    parts = []
    for t in types:
        tag = OVERPASS_TAGS[t]
        parts.append(f"nwr{tag}({bbox});")
    q = f"[out:json][timeout:90];({''.join(parts)});out geom;"   # body+geom：relation 才會帶 members 幾何
    last = None
    for u in ([url] if url else OVERPASS_URLS):
        try:
            r = httpx.post(u, data={"data": q}, headers=HEADERS, timeout=150, follow_redirects=True)
            r.raise_for_status()
            break
        except httpx.HTTPError as e:
            print(f"{u}: {e}")
            last = e
    else:
        raise RuntimeError(f"Overpass 全部失敗：{last}")
    store = POIStore()
    for el in r.json().get("elements", []):
        tags = el.get("tags", {})
        t = next((ft for ft, tag in OVERPASS_TAGS.items() if _tag_match(tag, tags)), None)
        if not t:
            continue
        geom = _osm_geometry(el)
        if geom is None:
            continue
        store.add(POI(type=t, name=tags.get("name") or tags.get("name:zh") or "", geom=geom,
                      source="OpenStreetMap（© OpenStreetMap contributors, ODbL）", source_id=f"{el['type']}/{el['id']}", attrs=tags))
    return store


def _osm_geometry(el: dict):
    """node → Point；閉合 way → Polygon（面狀設施距離要量到邊界）；開放 way → LineString；relation → 外環聯集或中心點。"""
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    if el["type"] == "node":
        return Point(el["lon"], el["lat"])
    if el["type"] == "way" and el.get("geometry"):
        pts = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(pts) >= 4 and pts[0] == pts[-1]:
            return Polygon(pts)
        return LineString(pts) if len(pts) >= 2 else Point(*pts[0])
    if el["type"] == "relation":
        from shapely.ops import linemerge, polygonize
        outer = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]]) for m in el.get("members", [])
                 if m.get("role") in ("outer", "") and m.get("geometry") and len(m["geometry"]) >= 2]
        if outer:
            merged = linemerge(unary_union(outer))
            polys = list(polygonize(merged))
            if polys:
                return unary_union(polys)
            return merged.centroid
        pts = [Point(m["lon"], m["lat"]) for m in el.get("members", []) if "lon" in m]
        if pts:
            return unary_union(pts).centroid
        if "center" in el:
            return Point(el["center"]["lon"], el["center"]["lat"])
    return None


def _tag_match(tag_expr: str, tags: dict) -> bool:
    body = tag_expr.strip("[]")
    if "=" not in body:                                   # ["shop"]：有這個 key 就算
        return body.strip('"') in tags
    k, v = body.split("=")
    return tags.get(k.strip('"')) == v.strip('"')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest")
    ap.add_argument("--overpass", help="bbox south,west,north,east")
    ap.add_argument("--types", help="逗號分隔的 facility type（限 overpass）")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    store = POIStore.from_sqlite(a.out) if Path(a.out).exists() else POIStore()
    if len(store):
        print(f"既有 {a.out}：{len(store)} 筆，新資料合併進去（同 source_id 者以新為準）")
    if a.manifest:
        store.merge(load_manifest(Path(a.manifest), Path(a.manifest).parent))
    if a.overpass:
        store.merge(fetch_overpass(a.overpass, a.types.split(",") if a.types else None))
    store.to_sqlite(a.out)
    print(f"寫入 {a.out}：{len(store)} 筆 {store.types()}")
