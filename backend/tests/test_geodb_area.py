"""全區圖資局部載入：GeoDB（R-tree + WKB）、案件範圍 bbox、ZoningDB、路網／步行圖依 bbox 取用。"""
from __future__ import annotations

from shapely.geometry import LineString, Point, Polygon, mapping

from app.spatial.area import bbox_key, case_bbox, pad_bbox
from app.spatial.geodb import GeoDB


def test_geodb_roundtrip_and_bbox_query(tmp_path):
    db = GeoDB.create(tmp_path / "t.sqlite")
    n = db.write_many([("A路", {"highway": "primary"}, LineString([(121.60, 25.20), (121.61, 25.21)])),
                       ("B街", {"highway": "residential"}, LineString([(121.90, 25.00), (121.91, 25.01)])),
                       (None, {"zone": "商業區"}, Polygon([(121.6, 25.2), (121.61, 25.2), (121.61, 25.21), (121.6, 25.21)]))])
    assert n == 3 and db.count() == 3
    hits = db.query((121.59, 25.19, 121.62, 25.22))
    assert {h["properties"].get("name") or h["properties"].get("zone") for h in hits} == {"A路", "商業區"}
    assert db.query((122.5, 26.0, 122.6, 26.1)) == []
    db.set_meta("source", "x")
    assert db.meta("source") == "x"


def test_case_bbox_from_geometry_and_key():
    data = {"case": {"district": "金山區"}, "subject_parcel": {"geometry": mapping(Point(121.636, 25.221).buffer(0.0005))}, "sections": {}, "comparables": []}
    b = case_bbox(data, pad_m=1000.0)
    assert b[0] < 121.636 < b[2] and b[1] < 25.221 < b[3]
    assert (b[2] - b[0]) * 111_320 > 1900                                 # 兩側各外擴約 1 km
    k = bbox_key(b)
    assert k[0] <= b[0] and k[2] >= b[2]
    assert case_bbox({"case": {}, "subject_parcel": {}, "sections": {}}) is None          # 沒幾何、沒行政區
    pb = pad_bbox((121.0, 25.0, 121.1, 25.1), 0.0)
    assert pb == (121.0, 25.0, 121.1, 25.1)


def test_zoning_db_and_roads_by_bbox(tmp_path, monkeypatch):
    from app.maps import zoning as Z
    from app.spatial import roads_store as RS
    db = GeoDB.create(tmp_path / "z.sqlite")
    db.write_many([(None, {"zone": "第二種商業區"}, Polygon([(121.6, 25.2), (121.61, 25.2), (121.61, 25.21), (121.6, 25.21)]))])
    zs = Z.ZoningDB(tmp_path / "z.sqlite")
    assert len(zs) == 1 and zs.at((121.605, 25.205))["zone"] == "第二種商業區" and zs.at((121.7, 25.3)) is None
    assert len(zs.within_bbox((121.6, 25.2, 121.605, 25.205))) == 1
    rdb = GeoDB.create(tmp_path / "r.sqlite")
    rdb.write_many([("金包里街", {"highway": "residential"}, LineString([(121.636, 25.221), (121.637, 25.222)])),
                    ("遠方路", {"highway": "primary"}, LineString([(121.9, 25.0), (121.91, 25.0)]))])
    monkeypatch.setenv("ROADS_DB", str(tmp_path / "r.sqlite"))
    RS._db = None
    RS._cache.clear()
    try:
        r = RS.get_roads((121.63, 25.215, 121.64, 25.225))
        assert r.names() == ["金包里街"]
        assert RS.get_roads(data={"case": {}, "subject_parcel": {}, "sections": {}}).items == []      # 沒範圍就不整份載入
    finally:
        RS._db = None
        RS._cache.clear()
