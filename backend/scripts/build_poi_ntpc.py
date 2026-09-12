"""
全區設施資料庫 data/poi_ntpc.sqlite ＝
  1. OSM 全區設施（data/osm/poi_osm.sqlite，scripts/build_osm_ntpc.py）
  2. 既有政府來源（data/poi_osm_jinshan.sqlite 內非 OSM 的列：中油加油站、高公局交流道）
  3. 環境部列管污染源（ems_s_01：環境保護許可管理系統對象基本資料，WGS84）→ pollution_source
     只取「同時列管空污與水污」或「列管毒化物」的事業（重大固定污染源）；小型列管對象（餐飲、洗車等）不列，避免每個區段都判劣。
  4. 新北市交通局路邊停車格（data/sources/ntpc_roadside_parking.csv，scripts/fetch_ntpc_parking.py）→ roadside_parking（停車方便性推定）
  5. 經濟部商業發展署「全國商圈盤點清冊」（只有文字範圍）→ 用路網把商圈範圍內的路段圍成面 → commercial_district
用法：python3 scripts/build_poi_ntpc.py --ems /path/ems_s_01_all.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from shapely.geometry import Point
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.spatial.area import BBox, district_geom, pad_bbox
from app.spatial.geo import to_twd97, to_wgs84
from app.spatial.lot import road_names_from_text
from app.spatial.poi import POI, POIStore
from app.spatial.roads_store import get_roads

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
BBOX: BBox = (121.28, 24.67, 122.02, 25.31)
EMS_SRC = "環境部環境保護許可管理系統對象基本資料（data.moenv.gov.tw ems_s_01；取製造業／能源／廢棄物處理業中同時列管空污＋水污或列管毒化物者）"
INDUSTRY_OK = {f"{i:02d}" for i in range(8, 35)} | {"35", "36", "37", "38"}       # 行業標準分類中類：08–34 製造業、35 電力燃氣、36 用水、37 廢污水、38 廢棄物
PARK_SRC = "新北市政府交通局 路邊停車空位查詢（data.gov.tw 122901）"
SQ_SRC = "經濟部商業發展署 全國商圈盤點清冊（data.gov.tw 103804，114 年）；範圍由路網圍出"
NTPC_DISTRICTS = ["板橋", "三重", "中和", "永和", "新莊", "新店", "土城", "蘆洲", "樹林", "汐止", "鶯歌", "三峽", "淡水", "瑞芳", "五股", "泰山", "林口",
                  "深坑", "石碇", "坪林", "三芝", "石門", "八里", "平溪", "雙溪", "貢寮", "金山", "萬里", "烏來"]


def pollution_pois(path: Path) -> POIStore:
    store = POIStore()
    kept = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        try:
            lon, lat = float(r.get("wgs84lon") or 0), float(r.get("wgs84lat") or 0)
        except ValueError:
            continue
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            continue
        air, water, toxic = r.get("isair") == "1", r.get("iswater") == "1", r.get("istoxic") == "1"
        if not ((air and water) or toxic):
            continue
        if (r.get("industrygroup") or "")[:2] not in INDUSTRY_OK:      # 只留製造業、電力燃氣、用水、廢污水、廢棄物處理（行業標準分類中類）
            continue
        kinds = [k for k, f in (("空污", air), ("水污", water), ("毒化物", toxic), ("廢棄物", r.get("iswaste") == "1"), ("土壤", r.get("issoil") == "1")) if f]
        store.add(POI(type="pollution_source", name=r.get("facilityname") or "", geom=Point(lon, lat), source=EMS_SRC, source_id=r.get("emsno"),
                      attrs={"county": r.get("county"), "township": r.get("township"), "address": r.get("facilityaddress"),
                             "industry": r.get("industryname"), "industry_area": r.get("industryareaname"), "listed": "、".join(kinds)}))
        kept += 1
    print(f"污染源：保留 {kept} 筆", flush=True)
    return store


ALIASES = {"野柳": "萬里區", "菁桐": "平溪區", "猴硐": "瑞芳區", "九份": "瑞芳區", "中港": "新莊區", "府中": "板橋區", "新埔": "板橋區", "亞東": "板橋區",
           "韓國街": "永和區", "中興街": "永和區", "華新街": "中和區", "興南": "中和區", "副都心": "新莊區", "廟街": "新莊區", "渡船頭": "八里區", "十分": "平溪區"}


def district_of(name: str, org: str) -> str | None:
    for d in NTPC_DISTRICTS:                       # 商圈名或組織名裡直接有區名
        if name.startswith(d) or f"{d}區" in org or f"新北市{d}" in org:
            return d + "區"
    for k, d in ALIASES.items():                   # 地名別稱
        if k in name or k in org:
            return d
    return None


def landmark_point(text: str, dg, store: POIStore):
    """範圍文字提到「○○火車站／車站／捷運站」→ 設施庫同名車站（在該區內）的位置。"""
    m = re.search(r"([一-鿿]{2,4}?)(?:火車站|車站|捷運站)", text)
    if not m:
        return None
    key = m.group(1)
    for p in store.by_types(["rail_station", "mrt_station", "intercity_bus_station"]):
        if key in (p.name or "") and dg.buffer(0.002).contains(p.geom.centroid):
            return p.geom.centroid
    return None


def business_district_pois(csv_path: Path, store: POIStore | None = None) -> tuple[POIStore, list[str]]:
    """商圈清冊→圍面設施；`store` 是已建好的設施庫（找地標用），回傳的是新的商圈設施庫。"""
    lookup = store or POIStore()
    out = POIStore()
    misses: list[str] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("縣市別") or "").replace("台", "臺") == "新北市"]
    for r in rows:
        name, org, rng = r["商圈名稱"], r.get("商圈組織名稱") or "", r.get("商圈範圍") or ""
        d = district_of(name, org)
        dg = district_geom(d) if d else None
        if dg is None:
            misses.append(f"{name}：找不到行政區（{org}）")
            continue
        roads = get_roads(pad_bbox(dg.bounds, 500.0))
        names = road_names_from_text(rng.replace("~", "至"))
        segs = []
        for n in names:
            for cand in (n, re.sub(r"^(?:" + "|".join(NTPC_DISTRICTS) + r")(?:區|村|里)?", "", n)):      # 原名不中再試去掉地名前綴（「坪林北宜路」→「北宜路」）
                if len(cand) < 2:
                    continue
                got = [to_twd97(g) for g in roads.named(cand, exact=False) if dg.buffer(0.002).intersects(g)]
                if got:
                    segs += got
                    break
        if not segs:                                     # 路名對不到：①路網名稱含商圈名關鍵字（如「中興街 (韓國街)」）②範圍文字提到的地標（車站等）取設施點外擴 150 m
            kw = re.sub(r"(形象|觀光|夜市|商圈|發展協會)", "", name).strip()
            segs = [to_twd97(g) for n_, g, _p in roads.items if kw and kw in n_ and dg.buffer(0.002).intersects(g)]
        anchor = None
        if not segs:
            anchor = landmark_point(rng + name, dg, lookup)
        if not segs and anchor is None:
            misses.append(f"{name}（{d}）：路網對不到範圍「{rng[:40]}」路名 {names}")
            continue
        area = to_wgs84(unary_union(segs).buffer(40.0)) if segs else to_wgs84(to_twd97(anchor).buffer(150.0))
        if anchor is not None:
            print(f"商圈 {name}（{d}）：以地標定位（外擴 150 m）", flush=True)
        out.add(POI(type="commercial_district", name=name, geom=area, source=SQ_SRC, source_id=f"gcis/{r.get('序號')}",
                      attrs={"district": d, "org": org, "range_text": rng, "roads": names, "year": r.get("年度")}))
        print(f"商圈 {name}（{d}）：{len(segs)} 段 {'、'.join(names)[:60]}", flush=True)
    return out, misses


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ems", help="ems_s_01 全部紀錄 jsonl")
    ap.add_argument("--out", default=str(DATA / "poi_ntpc.sqlite"))
    a = ap.parse_args()
    store = POIStore()
    osm = DATA / "osm" / "poi_osm.sqlite"
    if osm.exists():
        s = POIStore.from_sqlite(osm)
        store.merge(s)
        print(f"OSM：{len(s)} 筆", flush=True)
    legacy = DATA / "poi_osm_jinshan.sqlite"
    if legacy.exists():
        gov = POIStore([p for p in POIStore.from_sqlite(legacy).pois if not p.source.startswith("OpenStreetMap")])
        for p in gov.pois:
            p.id = None
        store.merge(gov)
        print(f"政府來源（加油站、交流道）：{len(gov)} 筆", flush=True)
    if a.ems and Path(a.ems).exists():
        ems = pollution_pois(Path(a.ems))
        (DATA / "sources" / "ems_s_01_pollution_sources.geojson").write_text(json.dumps(ems.to_geojson(), ensure_ascii=False), encoding="utf-8")
        store.merge(ems)
    pk = DATA / "sources" / "ntpc_roadside_parking.csv"
    if pk.exists():
        with open(pk, encoding="utf-8-sig", newline="") as fh:
            prow = list(csv.DictReader(fh))
        park = POIStore()
        for r in prow:
            try:
                lon, lat = float(r["longitude"]), float(r["latitude"])
            except (KeyError, TypeError, ValueError):
                continue
            park.add(POI(type="roadside_parking", name=r.get("roadname") or "", geom=Point(lon, lat), source=PARK_SRC, source_id=f"cell/{r.get('id')}",
                         attrs={"kind": r.get("name"), "pay": r.get("pay"), "paycash": r.get("paycash"), "day": r.get("day"), "hour": r.get("hour"), "areacode": r.get("areacode")}))
        store.merge(park)
        print(f"路邊停車格：{len(park)} 筆", flush=True)
    sq, misses = business_district_pois(DATA / "sources" / "全國商圈盤點清冊.csv", store)
    store.merge(sq)
    for m in misses:
        print("  需人工標定：", m, flush=True)
    store.to_sqlite(a.out)
    print(f"→ {a.out}：{len(store)} 筆", flush=True)
    print(json.dumps(store.types(), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
