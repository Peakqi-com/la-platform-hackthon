"""勘查表推算：只有區段範圍時，設施距離／分區／主要道路自動填，實地勘查欄位列為需人工。"""
from pathlib import Path

from shapely.geometry import mapping

from app.engine.rules import load_ruleset
from app.maps.zoning import ZoningStore
from app.spatial.bootstrap import Roads
from app.spatial.survey_draft import draft_section_survey
from tests.test_spatial import SECTION, make_store, pt, square, straight_osrm

ROOT = Path(__file__).resolve().parents[2]


def _roads():
    def road(name, hw, *pts):
        from shapely.geometry import LineString
        return {"type": "Feature", "geometry": mapping(LineString([(p.x, p.y) for p in pts])), "properties": {"name": name, "highway": hw, "width": "18"}}
    return Roads([road("中山路", "primary", pt(-600, -300), pt(600, -300)), road("金包里街", "pedestrian", pt(-600, 300), pt(600, 300)), road("中正路", "residential", pt(-300, -600), pt(-300, 600))])


def test_draft_fills_distances_zoning_and_road():
    reg = load_ruleset("jinshan_commercial_regional")
    zoning = ZoningStore([{"type": "Feature", "geometry": mapping(square(0, 0, 400)), "properties": {"ZONE": "商業區"}}])
    sec = {"section_id": "P002-00", "geometry": mapping(SECTION), "range_desc": "測試", "survey": {}}
    r = draft_section_survey(sec, reg, store=make_store(), zoning=zoning, roads=_roads(), osrm=straight_osrm())
    sv = sec["survey"]
    assert "transport.major_station" in r["filled"] and sv["transport"]["major_station"][0]["distance_m"] == 300
    assert sv["special"]["utility"] and all(f["computed"] for f in sv["special"]["utility"])
    assert sv["land_control"]["urban_plan"] == "都市計畫內" and "land_control.urban_plan" in r["filled"]
    # 分區圖只有「商業區」，金山表要「第二種商業區」→ 只給建議不填值
    assert "zoning" not in sv["land_control"] and r["suggestions"]["land_control.zoning"]["value"] == "商業區"
    assert any("更細的分區" in w for w in r["warnings"])
    assert sv["transport"]["main_road_width_m"] == {"name": "中山路", "value": 18.0}
    assert ("natural.drainage" in r["manual"]) != ("natural.drainage" in r["filled"])      # 有淹水潛勢圖（data/flood）就推定，否則留人工
    assert "commerce.foot_traffic" in r["manual"] and "transport.main_road_width_m" not in r["manual"]
    assert sec["survey_provenance"]["filled"] == r["filled"]


def test_draft_without_geometry_warns():
    reg = load_ruleset("jinshan_commercial_regional")
    r = draft_section_survey({"section_id": "X", "survey": {}}, reg, store=make_store())
    assert any("沒有範圍多邊形" in w for w in r["warnings"]) and r["filled"] == [] and "natural.drainage" in r["manual"]


def test_blank_survey_demo_and_endpoint():
    from fastapi.testclient import TestClient

    from app import cases as C
    from app.main import app
    from app.maps import zoning as Z
    from app.spatial import service
    from app.spatial.roads_store import set_roads
    client = TestClient(app)
    d = C.demo_case("blank_survey")
    sv = d["data"]["sections"]["P002-00"]["survey"]
    assert sv["land_control"] == {} and d["data"]["subject_parcel"]["school"] is None
    assert d["data"]["sections"]["P002-00"].get("geometry") is not None          # 幾何估計還在
    service.set_poi_store(make_store()); service.set_osrm(straight_osrm()); set_roads(_roads())
    Z.set_zoning_store(ZoningStore([{"type": "Feature", "geometry": mapping(square(0, 0, 400)), "properties": {"ZONE": "商業區"}}]))
    body = dict(d["data"]); body["sections"]["P002-00"]["geometry"] = mapping(SECTION)
    r = client.post("/api/spatial/survey_draft", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "public.market" in j["filled"] and j["data"]["sections"]["P002-00"]["survey"]["public"]["market"][0]["in_section"] is True
    assert ("natural.drainage" in j["manual"]) or ("natural.drainage" in j["filled"])
    service.set_poi_store(type(make_store())()); set_roads(Roads([])); Z.set_zoning_store(ZoningStore([]))


# ---------------------------------------------------------------- 勘查表推定規則（docs/07「勘查表推定規則」）


def test_survey_inference_helpers(monkeypatch):
    from shapely.geometry import LineString, Point, Polygon, mapping

    from app.spatial import geo, terrain
    from app.spatial.bootstrap import Roads
    from app.spatial.poi import POI, POIStore
    from app.spatial.survey_draft import _avg_road_width, _road_density, _shop_stats
    LON, LAT = 121.6367, 25.2217
    pt = lambda dx, dy: geo.offset_point(LON, LAT, dx, dy)
    poly = Polygon([(p.x, p.y) for p in (pt(0, 0), pt(200, 0), pt(200, 100), pt(0, 100))])
    roads = Roads([{"type": "Feature", "geometry": mapping(LineString([(pt(0, 0).x, pt(0, 0).y), (pt(200, 0).x, pt(200, 0).y)])), "properties": {"name": "甲路", "highway": "primary", "lanes": "4"}},
                   {"type": "Feature", "geometry": mapping(LineString([(pt(0, 100).x, pt(0, 100).y), (pt(200, 100).x, pt(200, 100).y)])), "properties": {"name": "乙路", "highway": "residential", "width": "6"}}])
    avg = _avg_road_width(poly, roads)
    assert avg and avg["coverage"] == 1.0 and abs(avg["value"] - 10.0) < 0.2            # (14×200 + 6×200)/400
    assert 150 < _road_density(poly, roads) < 250                                        # 400 m / 2 ha
    store = POIStore([POI(type="shop", name=f"s{i}", geom=Point(pt(10 + i * 15, 5).x, pt(10 + i * 15, 5).y), source="t") for i in range(12)])
    sh = _shop_stats(poly, store)
    assert sh["n"] == 12 and sh["foot_traffic"] == "顧客通行量稍多" and 10 < sh["ratio_pct"] < 20          # 12×8/600 m；每 100 m 2 家 → 稍多
    # 高程：離線且無瓦片 → None，不猜
    monkeypatch.setenv("TERRAIN_OFFLINE", "1")
    monkeypatch.setattr(terrain, "TERRAIN_DIR", terrain.TERRAIN_DIR / "_none_")
    terrain._cache.clear()
    assert terrain.elevation(LON, LAT) is None and terrain.section_terrain(poly) is None
    terrain._cache.clear()
