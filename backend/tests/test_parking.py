"""停車方便性推定：交通局停車格 → 面前道路寬度門檻 → 留人工。"""
from __future__ import annotations

from shapely.geometry import Point, mapping

from app.spatial.lot import _street_parking, derive_parcel_attributes
from app.spatial.poi import POI, POIStore


def _store(with_cell: bool) -> POIStore:
    st = POIStore()
    if with_cell:
        st.add(POI(type="roadside_parking", name="磺港路", geom=Point(121.6370, 25.2213), source="交通局", source_id="cell/1", attrs={"kind": "汽車停車位"}))
    return st


def test_parking_cell_wins_over_width():
    g = Point(121.6368, 25.2212).buffer(0.0001)
    r = _street_parking(g, {"front_road": {"name": "溫泉路13巷", "width_m": 6.0}}, _store(True))
    assert r["value"] == "可路邊停車" and "交通局" in r["source"] and "磺港路" in r["note"]


def test_width_threshold_when_no_cells():
    g = Point(121.6368, 25.2212).buffer(0.0001)
    assert _street_parking(g, {"front_road": {"width_m": 8}}, _store(False))["value"] == "可路邊停車"
    r = _street_parking(g, {"front_road": {"width_m": 6}}, _store(False))
    assert r["value"] == "不可路邊停車" and "推定" in r["source"]
    assert _street_parking(g, {"front_road": {}}, _store(False)) is None
    assert _street_parking(g, {"front_road": {"width_m": 6}}, None)["value"] == "不可路邊停車"        # 沒有設施庫也能走寬度規則


def test_derive_parcel_fills_street_parking_and_keeps_manual_value():
    parcel = {"parcel_id": "T", "geometry": mapping(Point(121.6368, 25.2212).buffer(0.0001)), "geometry_source": "synthetic", "front_road": {"name": "x", "width_m": 10}}
    d = derive_parcel_attributes(parcel, store=_store(True))
    assert "street_parking" in d["filled"] and parcel["street_parking"] == "可路邊停車" and parcel["derived"]["street_parking"]["source"].startswith("新北市政府交通局")
    manual = {"parcel_id": "T", "geometry": parcel["geometry"], "geometry_source": "synthetic", "front_road": {"width_m": 10}, "street_parking": "不可路邊停車"}
    derive_parcel_attributes(manual, store=_store(True))
    assert manual["street_parking"] == "不可路邊停車"                                                   # 人工值不覆寫
