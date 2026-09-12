"""地籍幾何（cadastre）、區段 bootstrap（路網街廓、四至、分區切分）、三張圖圖層、對應 API。全部離線（NLSC 用假 transport）。"""
import json
from pathlib import Path

import httpx
import pytest
from shapely.geometry import LineString, Point, Polygon, mapping

from app.maps.layers import case_layers
from app.maps.zoning import ZoningStore
from app.spatial import geo
from app.spatial.bootstrap import Roads, block_from_roads, describe_range, propose_sections, section_from_roads
from app.spatial.cadastre import (
    CadastreNotConfigured,
    FileCadastreProvider,
    NLSCCadastreProvider,
    SectionCodes,
    normalize_lot_no,
    resolve_parcel_geometry,
    split_parcel_id,
    synthesize_parcel_geometry,
)

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
LON, LAT = 121.6367, 25.2217


def pt(dx, dy):
    return geo.offset_point(LON, LAT, dx, dy)


def line(*pts):
    return LineString([(p.x, p.y) for p in pts])


def road(name, hw, *pts):
    return {"type": "Feature", "geometry": mapping(line(*pts)), "properties": {"name": name, "highway": hw}}


# 合成路網：兩橫（北街 y=+150、南路 y=-150）兩直（西路 x=-200、東街 x=+200），北街東端留 60 m 缺口；一條市場巷穿過中間
ROADS = Roads([
    road("北街", "pedestrian", pt(-400, 150), pt(140, 150)),           # 沒接到東街（缺口 60 m）
    road("南路", "primary", pt(-400, -150), pt(400, -150)),
    road("西路", "primary", pt(-200, -400), pt(-200, 400)),
    road("東街", "residential", pt(200, -400), pt(200, 400)),
    road("市場巷", "pedestrian", pt(0, -150), pt(0, 150)),
    road("西路12巷", "residential", pt(-200, 0), pt(-100, 0)),
    road("小徑", "footway", pt(-200, 80), pt(200, 80)),
])


# ---------------------------------------------------------------- cadastre

@pytest.mark.parametrize("raw,exp", [("489", "489-0"), ("489-1", "489-1"), ("0489-0001", "489-1"), ("489地號", "489-0"), (489.0, "489-0"), ("489之2", "489-2")])
def test_normalize_lot_no(raw, exp):
    assert normalize_lot_no(raw) == exp


def test_split_parcel_id():
    assert split_parcel_id("新北市金山區金美段489地號") == ("金美段", "489-0")
    assert split_parcel_id("溫泉段218-3地號") == ("溫泉段", "218-3")
    assert split_parcel_id("頂中股段三重橋小段31地號") == ("頂中股段三重橋小段", "31-0")


def test_file_provider_and_resolve():
    sq = Polygon([(p.x, p.y) for p in (pt(0, 0), pt(10, 0), pt(10, 12), pt(0, 12))])
    feats = [{"type": "Feature", "geometry": mapping(sq), "properties": {"段名": "金美段", "地號": "04890000", "段代碼": "1027"}}]
    fp = FileCadastreProvider(feats, section_field="段名", lot_field="地號", section_code_field="段代碾" if False else "段代碼")
    assert fp.lookup("金美段", "489") and fp.lookup("1027", "489-0") and fp.lookup("金美段", "490") is None
    parcel = {"parcel_id": "金美段489地號", "area_m2": 113.21, "width_m": 5, "depth_m": 23}
    r = resolve_parcel_geometry(parcel, file_provider=fp)
    assert r["ok"] and parcel["geometry_source"] == "cadastre_file" and parcel["geometry"]["type"] == "Polygon"
    # 找不到 → 人工質心合成
    p2 = {"parcel_id": "金美段490地號", "area_m2": 113.21, "width_m": 5, "depth_m": 23}
    r = resolve_parcel_geometry(p2, file_provider=fp, manual_point=(LON, LAT))
    assert r["source"] == "synthetic" and "非地籤圖" not in p2["geometry_note"] and "非地籍圖" in p2["geometry_note"]
    assert geo.straight_distance_m(geo.centroid(p2["geometry"]), Point(LON, LAT)) < 0.5
    # 什麼都沒有 → ok False，不猜
    p3 = {"parcel_id": "金美段491地號"}
    assert resolve_parcel_geometry(p3, file_provider=fp)["ok"] is False and "geometry" not in p3
    # NLSC 未申請 → 記在 note，不炸
    p4 = {"parcel_id": "金美段492地號"}
    r = resolve_parcel_geometry(p4, nlsc=NLSCCadastreProvider(api_key=None), manual_point=None)
    assert r["ok"] is False and "申請" in r["note"]


def test_synthesize_geometry_area_and_bearing():
    poly = synthesize_parcel_geometry((LON, LAT), 113.21, 5, 23)
    assert geo.to_twd97(poly).area == pytest.approx(115, abs=1)          # 5×23
    poly2 = synthesize_parcel_geometry((LON, LAT), 100)
    assert geo.to_twd97(poly2).area == pytest.approx(100, abs=0.5)
    poly3 = synthesize_parcel_geometry((LON, LAT), 200, 5, 20)             # 5×20=100 < 0.8×200 → 等比放大到 200
    assert geo.to_twd97(poly3).area == pytest.approx(200, abs=1)


def test_section_codes_with_fake_nlsc(tmp_path):
    xml = {"ListCounty": "<countyItems><countyItem><countycode>F</countycode><countyname>新北市</countyname></countyItem></countyItems>",
           "ListTown/F": "<townItems><townItem><towncode>F25</towncode><townname>金山區</townname></townItem></townItems>",
           "ListLandSection/F/F25": "<sectItems><sectItem><office>FD</office><officestr>汐止</officestr><sectcode>1027</sectcode><sectstr>金美段</sectstr></sectItem></sectItems>"}
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, text=xml[req.url.path.split("/other/")[1]])
    sc = SectionCodes(cache_path=tmp_path / "codes.json", client=httpx.Client(transport=httpx.MockTransport(handler)))
    r = sc.resolve("新北市", "金山區", "金美段")
    assert r["county_code"] == "F" and r["town_code"] == "F25" and r["code"] == "1027" and r["office"] == "FD"
    sc2 = SectionCodes(cache_path=tmp_path / "codes.json", offline=True)          # 快取後離線可用
    assert sc2.resolve("台北市".replace("台北", "新北"), "金山區", "金美").get("code") == "1027"
    assert len(calls) == 3
    with pytest.raises(CadastreNotConfigured):
        SectionCodes(cache_path=tmp_path / "none.json", offline=True).counties()


# ---------------------------------------------------------------- bootstrap

def test_block_from_roads_snaps_gap_and_ignores_footway():
    res = block_from_roads([pt(100, 0)], ROADS)                      # 東半塊（市場巷把街廓切成兩半）
    assert res and res["hits"] == 1
    assert set(res["bounding_roads"]) >= {"北街", "南路", "東街", "市場巷"} and "小徑" not in res["bounding_roads"]
    assert res["area_m2"] == pytest.approx(200 * 300, rel=0.05)      # 缺口 60 m 被補起來，沒漏到外面
    whole = block_from_roads([pt(100, 0), pt(-100, 0)], ROADS, exclude_names=["市場巷"])
    assert whole["area_m2"] == pytest.approx(400 * 300, rel=0.05) and whole["hits"] == 2
    strict = section_from_roads(["北街", "南路", "西路", "東街"], ROADS, hint=pt(-100, 0))
    assert strict and strict["candidates"] >= 1 and all(strict["touched"].values())
    assert block_from_roads([pt(5000, 5000)], ROADS) is None


def test_describe_range_sides():
    whole = block_from_roads([pt(100, 0), pt(-100, 0)], ROADS, exclude_names=["市場巷"])
    rng = describe_range(whole["geometry"], ROADS, zoning="第二種商業區", section_id="P001-00")
    assert rng["sides"] == {"北側": "北街", "南側": "南路", "西側": "西路", "東側": "東街"}
    assert rng["range_desc"] == "北側至北街，南側至南路，西側至西路，東側至東街之第二種商業區土地劃為P001-00區段。"
    assert rng["status"] == "draft"


def test_propose_sections_splits_by_zoning():
    scope = Polygon([(p.x, p.y) for p in (pt(-190, -140), pt(190, -140), pt(190, 140), pt(-190, 140))])
    zoning = [{"type": "Feature", "geometry": mapping(Polygon([(p.x, p.y) for p in (pt(-500, -500), pt(0, -500), pt(0, 500), pt(-500, 500))])), "properties": {"zone": "商業區"}},
              {"type": "Feature", "geometry": mapping(Polygon([(p.x, p.y) for p in (pt(0, -500), pt(500, -500), pt(500, 500), pt(0, 500))])), "properties": {"zone": "住宅區"}}]
    drafts = propose_sections(scope, ROADS, zoning_features=zoning, zoning_name_field="zone")
    assert [d["zoning"] for d in drafts] == ["商業區", "住宅區"] and [d["section_id"] for d in drafts] == ["P001-00", "P002-00"]
    assert all(d["status"] == "draft" and "§10" in d["basis"] for d in drafts)
    assert drafts[0]["survey"]["land_control"]["zoning"] == "商業區" and drafts[0]["area_m2"] == pytest.approx(190 * 280, rel=0.02)
    one = propose_sections(scope, ROADS)
    assert len(one) == 1 and one[0]["zoning"] is None and "分區待確認" in one[0]["range_desc"]


def test_zoning_store():
    zs = ZoningStore([{"type": "Feature", "geometry": mapping(Polygon([(p.x, p.y) for p in (pt(-100, -100), pt(100, -100), pt(100, 100), pt(-100, 100))])), "properties": {"ZONE": "商業區"}}])
    assert zs.at((LON, LAT))["zone"] == "商業區" and zs.at(pt(500, 500)) is None
    feats = zs.within_bbox((pt(-50, -50).x, pt(-50, -50).y, pt(50, 50).x, pt(50, 50).y))
    assert len(feats) == 1 and feats[0]["properties"]["color"] == "#e5533d"


# ---------------------------------------------------------------- 圖層 + API

def test_case_layers_and_apis(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as app_main
    monkeypatch.setattr(app_main, "DEFAULT_CADASTRE", Path("/nonexistent/default.geojson"))   # 不用預載地籍圖，測人工質心合成

    from app.main import app
    client = TestClient(app)
    demo = client.get("/api/cases/demo").json()
    assert demo["sections"]["P002-00"]["geometry"]["type"] == "Polygon" and demo["subject_parcel"]["geometry_source"] == "synthetic"
    layers = client.post("/api/maps/layers", json={k: demo[k] for k in ("case", "sections", "subject_parcel", "comparables")}).json()
    assert len(layers["sections"]["features"]) == 1 and len(layers["parcels"]["features"]) == 1
    assert layers["parcels"]["features"][0]["properties"]["geometry_source"] == "synthetic"
    assert layers["bbox"] and layers["attribution"]["basemap"]
    # 有設施幾何時會出現距離線
    data = json.loads(json.dumps({k: demo[k] for k in ("case", "sections", "subject_parcel", "comparables")}))
    data["subject_parcel"]["school"] = {"name": "X校", "type": "school", "distance_m": 150, "measure": "walking", "origin": "parcel_centroid", "source": "t",
                                        "geometry": mapping(pt(150, 0)), "provenance": {"origin_point": [LON, LAT], "target_point": [pt(150, 0).x, pt(150, 0).y]}}
    L = case_layers(data)
    assert len(L["distance_lines"]["features"]) == 1 and "步行" in L["distance_lines"]["features"][0]["properties"]["label"]
    # cadastre resolve：沒有地籍圖檔 → 人工質心合成
    r = client.post("/api/cadastre/resolve", json={k: FIX[k] for k in ("case", "sections", "subject_parcel", "comparables")} | {"manual_points": {"金美段489地號": [LON, LAT]}})
    assert r.status_code == 200 and r.json()["report"]["金美段489地號"]["source"] == "synthetic"
    assert r.json()["report"]["溫泉段218地號"]["ok"] is False
    assert client.get("/maps").status_code == 200 and "Leaflet" in client.get("/maps").text or "leaflet" in client.get("/maps").text
    # bootstrap API 用合成路網
    from app.spatial.roads_store import set_roads
    set_roads(ROADS)
    b = client.post("/api/bootstrap/block", json={"hints": [[pt(100, 0).x, pt(100, 0).y], [pt(-100, 0).x, pt(-100, 0).y]], "exclude_names": ["市場巷"], "zoning": "第二種商業區", "section_id": "P009-00"}).json()
    assert b["sides"]["北側"] == "北街" and "P009-00" in b["range_desc"]
    s = client.post("/api/bootstrap/sections", json={"scope": mapping(Polygon([(p.x, p.y) for p in (pt(-190, -140), pt(190, -140), pt(190, 140), pt(-190, 140))])), "use_zoning": False}).json()
    assert s["count"] == 1 and s["sections"][0]["status"] == "draft"
    assert client.post("/api/bootstrap/block", json={"hints": [[pt(9000, 9000).x, pt(9000, 9000).y]]}).status_code == 404
    set_roads(Roads([]))
