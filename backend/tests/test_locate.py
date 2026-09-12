"""比較標的沒有地籍界線：門牌 → 路網推定位置；地址組字不重複行政區；點圖設定位置端點。"""
from __future__ import annotations

from app.spatial.locate import parse_address, point_from_address


def test_parse_address_district_road_lane_number():
    a = parse_address("新北市三芝區智成街２之１號二樓", "新北市金山區")
    assert a == {"district": "三芝區", "road": "智成街", "lane": None, "number": 2, "text": "新北市三芝區智成街2之1號二樓"}
    b = parse_address("金包里街５１號３樓", "新北市金山區")
    assert b["district"] == "金山區" and b["road"] == "金包里街" and b["number"] == 51
    c = parse_address("新北市金山區中山路１２３巷５號", None)
    assert c["road"] == "中山路" and c["lane"] == "123巷"
    assert parse_address("", None)["road"] is None


def test_point_from_address_uses_district_roads(monkeypatch):
    from shapely.geometry import LineString

    from app.spatial import locate as L
    from app.spatial.bootstrap import Roads
    monkeypatch.setattr(L, "_addr_db", False)                      # 沒有門牌索引 → 退回路段中點

    def fake_roads(_bbox):
        return Roads([{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[121.636, 25.221], [121.640, 25.222]]}, "properties": {"name": "金包里街", "highway": "residential"}},
                      {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[121.50, 25.25], [121.51, 25.26]]}, "properties": {"name": "智成街", "highway": "residential"}}])
    hit = point_from_address("新北市金山區金包里街５１號３樓", "新北市金山區", fake_roads)
    assert hit and hit["road"] == "金包里街" and 121.636 <= hit["lon"] <= 121.640 and "推定位置" in hit["note"]
    assert point_from_address("新北市金山區不存在路１號", "新北市金山區", fake_roads) is None
    assert LineString


def test_comparable_address_not_duplicated():
    from app.market.lvr import _address
    assert _address({"needs_building_cost": True, "position": "新北市三芝區智成街2之1號二樓", "district": "三芝區", "parcel_id": "茂長段1169地號"}, "新北市金山區") == "新北市三芝區智成街2之1號二樓"
    assert _address({"needs_building_cost": True, "position": "金包里街51號3樓", "district": "金山區", "parcel_id": "溫泉段456地號"}, "新北市金山區") == "新北市金山區金包里街51號3樓"
    assert _address({"needs_building_cost": False, "position": "", "district": "萬里區", "parcel_id": "X段1地號"}, "新北市金山區") == "新北市萬里區X段1地號"


def test_locate_endpoint_sets_geometry_and_enriches(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import cases as C
    from app.main import app
    monkeypatch.setattr(C, "CASES_DIR", tmp_path / "cases")
    C._mem.clear()
    with TestClient(app) as client:
        cid = client.get("/api/cases/demo", params={"variant": "template", "save": "true"}).json()["id"]
        d = client.get(f"/api/cases/{cid}").json()
        comp_no = d["data"]["comparables"][0]["comp_no"]
        r = client.post(f"/api/cases/{cid}/comparables/locate", json={"comp_no": comp_no, "lon": 121.6368, "lat": 25.2212}, headers={"X-Actor-Name": "t", "X-Actor-Role": "officer"})
        assert r.status_code == 200, r.text
        body = r.json()["case"]
        c = next(x for x in (body.get("data") or body)["comparables"] if x["comp_no"] == comp_no)
        assert c["geometry_source"] == "synthetic" and c["geometry"] and "人工指定位置" in c["geometry_note"]
        assert client.post(f"/api/cases/{cid}/comparables/locate", json={"comp_no": 99, "lon": 121.6, "lat": 25.2}).status_code == 404
    C._mem.clear()


def test_point_from_housenumber_when_index_exists(monkeypatch):
    import pytest

    from app.spatial import locate as L
    from app.spatial.roads_store import get_roads
    monkeypatch.setattr(L, "_addr_db", None)
    if L.address_db() is None:
        pytest.skip("沒有 data/osm/addresses.sqlite")
    hit = L.point_from_address("新北市金山區金包里街５１號３樓", "新北市金山區", get_roads)
    assert hit and hit["kind"] in ("exact", "nearest") and "門牌" in hit["note"] and 121.63 < hit["lon"] < 121.65
