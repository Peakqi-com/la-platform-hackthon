"""
空間模組：用合成的金山座標重現範本的每個距離，驗證
  1. 直線距離、區段邊界最近點、區段內判定
  2. POI 庫 GeoJSON / SQLite round-trip、最近查詢
  3. OSRM 路徑距離（mock）與不可用時的 straight_estimated 退回
  4. 案件層級參照設施：兩宗地共用同一所學校（手冊 p.24 8(2)、p.51 (六)2(2)）
  5. fill_parcel / fill_section → 引擎 → 與範本相同等級（表5 全部、表4 15~20）
  6. /api/spatial/* 端點
"""
import json
from pathlib import Path

import httpx
import pytest
from shapely.geometry import Point, Polygon, mapping

from app.engine.rules import load_ruleset
from app.engine.tables import run_case
from app.spatial import geo
from app.spatial.distance import measure_distance
from app.spatial.osrm import OSRMClient
from app.spatial.poi import POI, POIStore
from app.spatial.reference import fill_parcel, select_reference_facilities
from app.spatial.service import fill_case

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
LON, LAT = 121.6367, 25.2217          # 金山區公所附近（合成座標）


def pt(dx, dy):
    return geo.offset_point(LON, LAT, dx, dy)


def square(cx_m, cy_m, half):
    c = pt(cx_m, cy_m)
    return Polygon([(p.x, p.y) for p in (geo.offset_point(c.x, c.y, -half, -half), geo.offset_point(c.x, c.y, half, -half),
                                          geo.offset_point(c.x, c.y, half, half), geo.offset_point(c.x, c.y, -half, half))])


SECTION = square(0, 0, 300)           # P002-00：600m × 600m，邊界在 ±300m
SUBJECT = square(0, 0, 8)             # 金美段489：質心在原點
COMP = square(-60, 40, 8)             # 溫泉段218


def make_store() -> POIStore:
    S = "合成測試資料"
    pois = [
        # 個別因素（距比準地質心 = 範本填值）
        POI("school", "金山國小", pt(150, 0), S), POI("school", "金美國小", pt(-200, 40), S),   # 距比準地 204m、距比較標的 140m：離比較標的更近，但參照設施要一致
        POI("traditional_market", "金山市場", pt(0, 30), S), POI("park", "中山溫泉公園", pt(0, -190), S),
        POI("bus_stop", "金山區公所站", pt(-80, 0), S), POI("commercial_district", "老街商圈", square(0, 0, 120), S),
        POI("cemetery", "金山第一公墓", pt(0, 260), S), POI("cemetery", "遠處公墓", pt(0, 2500), S),
        # 區域因素（距區段邊界 = 範本填值；區段內的放在方塊內）
        POI("intercity_bus_station", "國光客運金山站", pt(600, 0), S),                      # 邊界 300 → 300m
        POI("tourist_attraction", "金包里老街", pt(50, 50), S), POI("parking_lot", "金包里老街停車場", pt(0, -420), S),   # 120m
        POI("substation", "金山變電所", pt(1000, 0), S), POI("gas_station", "中油金山站", pt(0, 740), S),           # 700 / 440
        POI("columbarium", "金山區公所福緣納骨堂", pt(-1050, 0), S),                          # 750
        POI("bank", "新北市金山地區農會", pt(-510, 0), S), POI("tourist_hotel", "新北北海溫泉洲際酒店", pt(0, -1150), S),  # 210 / 850
    ]
    return POIStore(pois)


def straight_osrm() -> OSRMClient:
    """假 OSRM：路徑距離 = 直線距離（讓數字與範本一致），驗證 walking 路徑有被呼叫。"""
    def handler(req: httpx.Request) -> httpx.Response:
        if "/route/" in req.url.path:
            a, b = req.url.path.split("/")[-1].split(";")
            (x1, y1), (x2, y2) = (map(float, a.split(","))), (map(float, b.split(",")))
            d = geo.straight_distance_m(Point(x1, y1), Point(x2, y2))
            return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": d}]})
        return httpx.Response(200, json={"code": "Ok", "waypoints": [{"location": [0, 0]}]})
    return OSRMClient("http://osrm.test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def dead_osrm() -> OSRMClient:
    def handler(req):
        raise httpx.ConnectError("refused")
    return OSRMClient("http://osrm.dead", client=httpx.Client(transport=httpx.MockTransport(handler)))


# ---------------------------------------------------------------- 1. geo

def test_geo_distances_and_boundary():
    assert abs(geo.straight_distance_m(pt(0, 0), pt(1000, 0)) - 1000) < 0.5
    assert geo.straight_distance_m(SECTION, pt(1000, 0)) == pytest.approx(700, abs=0.5)      # 邊界最近點
    assert geo.straight_distance_m(SECTION, pt(50, 50)) == 0                                  # 區段內
    bp = geo.boundary_nearest_point(SECTION, pt(1000, 0))
    assert geo.straight_distance_m(bp, pt(300, 0)) < 0.5
    assert geo.contains(SECTION, pt(50, 50)) and not geo.contains(SECTION, pt(600, 0))
    c = geo.centroid(SUBJECT)
    assert geo.straight_distance_m(c, pt(0, 0)) < 0.5


# ---------------------------------------------------------------- 2. POI store

def test_poi_store_roundtrips(tmp_path):
    st = make_store()
    gj = st.to_geojson()
    st2 = POIStore.from_geojson(gj)
    assert len(st2) == len(st) and st2.types() == st.types()
    st.to_sqlite(tmp_path / "poi.sqlite")
    st3 = POIStore.from_sqlite(tmp_path / "poi.sqlite")
    assert len(st3) == len(st) and st3.pois[5].geom.geom_type == "Polygon"
    near = st3.nearest(pt(0, 0), ["cemetery"], k=2)
    assert [p.name for p, _ in near] == ["金山第一公墓", "遠處公墓"] and near[0][1] == pytest.approx(260, abs=0.5)
    assert [p.name for p in st3.within(SECTION, ["tourist_attraction", "substation"])] == ["金包里老街"]
    rows = [{"名稱": "A校", "經度": LON, "緯度": LAT}, {"名稱": "壞資料", "經度": "", "緯度": ""}]
    assert len(POIStore.from_rows(rows, type="school", name_field="名稱", lon_field="經度", lat_field="緯度", source="教育部")) == 1


# ---------------------------------------------------------------- 3. OSRM / fallback

def test_measure_walking_and_fallback():
    m = measure_distance(pt(0, 0), pt(150, 0), "walking", straight_osrm())
    assert m["measure"] == "walking" and m["distance_m"] == pytest.approx(150, abs=0.5)
    m = measure_distance(pt(0, 0), pt(150, 0), "walking", dead_osrm())
    assert m["measure"] == "straight_estimated" and m["distance_m"] == pytest.approx(195, abs=0.5) and "OSRM" in m["note"]
    m = measure_distance(pt(0, 0), pt(150, 0), "walking", None)
    assert m["measure"] == "straight_estimated" and "內建步行路網（OSM）無資料" in m["note"] and "OSRM" not in m["note"].replace("（OSM）", "")
    m = measure_distance(pt(0, 0), pt(260, 0), "straight", straight_osrm())
    assert m["measure"] == "straight" and m["distance_m"] == pytest.approx(260, abs=0.5)
    assert not OSRMClient("").enabled


# ---------------------------------------------------------------- 4. 參照設施一致

def test_reference_facility_shared_across_parcels():
    ind = load_ruleset("jinshan_commercial_individual")
    st = make_store()
    rules = [r for r in ind.rules if r.criteria.get("type") == "distance"]
    ref = select_reference_facilities(geo.centroid(SUBJECT), rules, st)
    assert [p.name for p in ref["I15"]] == ["金山國小"]
    assert [p.name for p in ref["I20"]] == ["金山第一公墓"]        # 遠處公墓超過最外級距 500m 不列
    comp = {"parcel_id": "溫泉段218地號", "geometry": mapping(COMP)}
    out = fill_parcel(comp, ind, st, reference=ref, osrm=straight_osrm())
    # 參照設施是金山國小；但比較標的附近的金美國小依基準表判出更優等級 → 依手冊 p.51 (六)2(2) 但書採用並註明
    assert out["parcel"]["school"]["name"] == "金美國小" and "但書" in out["parcel"]["school"]["provenance"]["note"]
    assert out["provenance"]["fields"]["school"]["note"]
    assert out["parcel"]["school"]["measure"] == "walking" and out["parcel"]["school"]["origin"] == "parcel_centroid"
    assert out["parcel"]["nuisance"][0]["measure"] == "straight"


# ---------------------------------------------------------------- 5. 整案 → 引擎 → 範本等級

def test_fill_case_reproduces_template_levels():
    data = json.loads(json.dumps({k: FIX[k] for k in ("case", "sections", "subject_parcel", "comparables")}))
    data["subject_parcel"]["geometry"] = mapping(SUBJECT)
    data["sections"]["P002-00"]["geometry"] = mapping(SECTION)
    for f in ("school", "market", "park", "station", "commercial_district", "nuisance"):
        data["subject_parcel"][f] = None
    sv = data["sections"]["P002-00"]["survey"]
    for grp, key in (("transport", "major_station"), ("transport", "bus_stop"), ("transport", "interchange"), ("public", "market"), ("public", "park"),
                     ("public", "tourism"), ("public", "parking"), ("special", "utility"), ("special", "funeral"), ("special", "waste"),
                     ("pollution", "source"), ("commerce", "department_store"), ("commerce", "bank"), ("commerce", "entertainment"), ("commerce", "hotel")):
        sv[grp][key] = None
    out = fill_case(data, store=make_store(), osrm=straight_osrm())
    assert out["warnings"] == ["比較標的1 溫泉段218地號 沒有位置或界線，距離未計算"]
    sp = data["subject_parcel"]
    assert sp["school"]["distance_m"] == 150 and sp["market"]["distance_m"] == 30 and sp["park"]["distance_m"] == 190
    assert sp["station"]["distance_m"] == 80 and sp["commercial_district"]["distance_m"] == 0
    assert [n["name"] for n in sp["nuisance"]] == ["金山第一公墓"] and sp["nuisance"][0]["distance_m"] == 260
    assert all(f["computed"] and f["source"] == "合成測試資料" for f in (sp["school"], sp["market"], sp["nuisance"][0]))
    s = data["sections"]["P002-00"]["survey"]
    assert s["transport"]["major_station"][0]["distance_m"] == 300 and s["transport"]["major_station"][0]["in_section"] is False
    assert s["transport"]["bus_stop"][0]["in_section"] is True and s["transport"]["interchange"] == []
    assert s["public"]["parking"][0]["distance_m"] == 120 and s["public"]["tourism"][0]["in_section"] is True
    assert sorted(f["distance_m"] for f in s["special"]["utility"]) == [440, 700]
    assert s["special"]["funeral"][0]["origin"] == "section_boundary" and s["special"]["funeral"][0]["measure"] == "straight"
    assert s["commerce"]["bank"][0]["distance_m"] == 210 and s["commerce"]["hotel"][0]["distance_m"] == 850
    assert s["commerce"]["department_store"] == [] and s["special"]["waste"] == []
    # 引擎：表5 比準地等級全部等於範本；表4 個別因素差異率等於範本
    res = run_case(load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual"), data)
    got5 = {r.rule_id: r.subject_level for r in res["table5"][1].rows if r.subject_level}
    assert got5 == FIX["expected"]["table5"]["subject_levels"]
    c = res["table4"].comparables[0]
    assert {str(r.item_no): r.pct for r in c.rows if r.pct is not None} == FIX["expected"]["table4"]["comparable_1"]["individual"]
    assert abs(res["table4"].subject_comparison_price - 212958) <= 1
    assert out["provenance"]["reference"]["I15"][0]["name"] == "金山國小"


def test_fill_keeps_manual_values_unless_overwrite():
    ind = load_ruleset("jinshan_commercial_individual")
    p = {"parcel_id": "x", "geometry": mapping(SUBJECT), "school": {"name": "人工填的學校", "distance_m": 999}}
    out = fill_parcel(p, ind, make_store(), osrm=straight_osrm())
    assert p["school"]["name"] == "人工填的學校" and "school" in out["provenance"]["skipped"]
    fill_parcel(p, ind, make_store(), osrm=straight_osrm(), overwrite=True)
    assert p["school"]["name"] == "金山國小"
    with pytest.raises(ValueError):
        fill_parcel({"parcel_id": "no-geom"}, ind, make_store())


# ---------------------------------------------------------------- 6. API

def test_spatial_api(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.spatial import service
    service.set_poi_store(make_store())
    service.set_osrm(straight_osrm())
    client = TestClient(app)
    st = client.get("/api/spatial/status").json()
    assert st["poi"]["count"] == len(make_store()) and st["osrm"]["enabled"] is True
    r = client.post("/api/spatial/distances", json={"origin": mapping(Point(pt(0, 0).x, pt(0, 0).y)), "types": ["school", "cemetery"], "k": 2,
                                                     "section": mapping(SECTION)})
    assert r.status_code == 200, r.text
    j = r.json()["facilities"]
    assert [f["name"] for f in j["school"]] == ["金山國小", "金美國小"] and j["school"][0]["in_section"] is True
    assert j["cemetery"][0]["distance_m"] == 260 and j["cemetery"][0]["measure"] == "straight"
    data = json.loads(json.dumps({k: FIX[k] for k in ("case", "sections", "subject_parcel", "comparables")}))
    data["subject_parcel"]["geometry"] = mapping(SUBJECT)
    data["comparables"][0]["geometry"] = mapping(COMP)
    r = client.post("/api/spatial/fill", json=data | {"overwrite": True})
    assert r.status_code == 200, r.text
    filled = r.json()
    assert filled["data"]["comparables"][0]["school"]["name"] in ("金山國小", "金美國小")        # 同等級→沿用參照；更優→但書採用
    assert "區段 P002-00 沒有範圍多邊形" in filled["warnings"][0]
    service.set_poi_store(POIStore())


# ---------------------------------------------------------------- 內建步行圖（OSRM 備援）

def _grid_graph():
    from app.spatial.walking import WalkGraph
    # 兩條東西向路 y=0、y=200，一條南北向 x=300 連接；A(0,0)→B(0,200) 直線 200，步行 300+200+300=800
    def feat(hw, *pts, **props):
        return {"type": "Feature", "geometry": mapping(LineString([(p.x, p.y) for p in pts])), "properties": {"highway": hw, **props}}
    from shapely.geometry import LineString
    return WalkGraph([feat("residential", pt(-50, 0), pt(300, 0)), feat("residential", pt(-50, 200), pt(300, 200)),
                      feat("footway", pt(300, 0), pt(300, 200)), feat("motorway", pt(-50, 0), pt(-50, 200)),   # 高速公路不能走
                      feat("path", pt(1000, 1000), pt(1100, 1000))])                                             # 不連通的孤島


def test_walk_graph_routes_and_fallback_order():
    g = _grid_graph()
    r = g.route_distance_m(pt(0, 0), pt(0, 200))
    assert r["distance_m"] == pytest.approx(800, abs=2) and r["snap_a_m"] < 0.5
    with pytest.raises(ValueError):
        g.route_distance_m(pt(0, 0), pt(1000, 1000))            # 不連通
    with pytest.raises(ValueError):
        g.route_distance_m(pt(0, 0), pt(0, 5000))               # 離路網太遠
    m = measure_distance(pt(0, 0), pt(0, 200), "walking", dead_osrm(), walk_graph=g)
    assert m["measure"] == "walking" and m["router"] == "osm_graph" and m["distance_m"] == pytest.approx(800, abs=2) and "OSRM 不可用" in m["note"]
    m = measure_distance(pt(0, 0), pt(0, 200), "walking", straight_osrm(), walk_graph=g)
    assert m["router"] == "osrm" and m["distance_m"] == pytest.approx(200, abs=1)       # OSRM 優先
    m = measure_distance(pt(0, 0), pt(0, 5000), "walking", None, walk_graph=g)
    assert m["measure"] == "straight_estimated" and "內建步行路網（OSM）無法計算" in m["note"]


def test_manual_poi_and_land_value_sections(tmp_path, monkeypatch):
    from app.spatial import service
    from app.spatial.bootstrap import sections_from_land_values
    monkeypatch.setattr(service, "MANUAL_POI_PATH", tmp_path / "manual_poi.geojson")
    service.set_poi_store(POIStore())
    f = service.add_manual_poi("substation", "金山變電所", LON, LAT, note="台電 EMF 資料只有『中正路』，UI 手點", by="tester")
    assert f["properties"]["source"] == "人工標定" and (tmp_path / "manual_poi.geojson").exists()
    assert service.get_poi_store().nearest((LON, LAT), ["substation"])[0][0].name == "金山變電所"
    service.add_manual_poi("substation", "金山變電所", LON + 0.001, LAT)          # 同名覆寫
    assert len(service.get_poi_store().by_types(["substation"])) == 1
    service.set_poi_store(POIStore())
    # 公告現值分段：三塊相鄰宗地，兩塊同值 → 兩個區段
    sq = lambda x, v: {"parcel_id": f"p{x}", "geometry": mapping(square(x, 0, 10)), "land_value": v}
    drafts = sections_from_land_values([sq(0, 55396), sq(20, 55396), sq(40, 29700)])
    assert [d["land_value"] for d in drafts] == [55396, 29700] and drafts[0]["parcel_ids"] == ["p0", "p20"]
    assert drafts[0]["status"] == "draft" and "§46" in drafts[0]["basis"]
