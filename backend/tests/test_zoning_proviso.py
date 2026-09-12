"""樹林都市計畫住一容積率：兩版土管要點皆 260%；面前道路未達 8 m 者依但書 200%（標需確認）；宗地值與勘查表不一致 → 需確認；核算 0% 填「-」不列。"""
import json
from pathlib import Path

from app.engine.rules import load_ruleset
from app.engine.tables import run_case
from app.engine.verify import collect_findings
from app.spatial.admin import bcr_far_for, fill_parcel_admin

FIX = Path(__file__).resolve().parents[2] / "fixtures"


def test_shulin_r1_far_260_and_proviso_200_below_8m():
    base = bcr_far_for("第一種住宅區", "新北市樹林區")
    assert base["far"] == 260 and base["bcr"] == 50 and not base.get("proviso")
    assert "2020-11-10" in base["note"] and base.get("proviso_possible")            # 寬度未知：只提醒但書
    narrow = bcr_far_for("第一種住宅區", "新北市樹林區", front_road_width_m=6.0)
    assert narrow["far"] == 200 and narrow["far_base"] == 260 and narrow["check"] and "但書" in narrow["note"]
    assert bcr_far_for("第一種住宅區", "新北市樹林區", front_road_width_m=8.0)["far"] == 260   # 未達 8 m 才適用
    assert bcr_far_for("第三種住宅區", "新北市樹林區", front_road_width_m=6.0)["far"] == 120   # 但書只限住一、住二


def test_fill_parcel_admin_uses_front_road_width():
    p = {"parcel_id": "樹德段284地號", "zoning": "第一種住宅區", "front_road": {"name": "啟智街", "width_m": 6.0}}
    fill_parcel_admin(p, district="新北市樹林區")
    assert p["far_pct"] == 200 and p["bcr_pct"] == 50 and "但書" in p["derived"]["far_pct"]["note"]


def _shulin():
    d = json.loads((FIX / "shulin_case_1110901.json").read_text(encoding="utf-8"))
    data = {k: d[k] for k in ("case", "sections", "subject_parcel", "comparables")}
    for p in [data["subject_parcel"], *data["comparables"]]:
        p["bcr_pct"], p["far_pct"] = 50, 260
    data["subject_parcel"]["zoning"] = "捷運開發區"                    # 22 使用分區：劣 vs 稍優 → 核算非 0
    reg = load_ruleset(data["case"]["rulesets"]["regional"])
    ind = load_ruleset(data["case"]["rulesets"]["individual"])
    return data, reg, ind, run_case(reg, ind, data)


def test_far_mismatch_with_section_survey_is_flagged_as_confirm():
    data, reg, ind, res = _shulin()                                      # P002-00 勘查表容積率 200，比較標的1 宗地 260
    fs = collect_findings(reg, ind, data, res, None, None)
    hit = [f for f in fs if f["item_no"] == 24 and f["comp_no"] == 1]
    assert len(hit) == 1 and hit[0]["severity"] == "warn" and "200" in hit[0]["submitted"] and "260" in hit[0]["computed"]
    assert "但書" in hit[0]["message"] and hit[0]["kind"] == "mismatch"
    assert not [f for f in fs if f["item_no"] == 23]                      # 建蔽率兩邊都 50，不列
    assert not [f for f in fs if f["item_no"] == 24 and f["comp_no"] in (2, 3)]


def test_dash_with_zero_pct_is_not_flagged():
    data, reg, ind, res = _shulin()
    sub = {"comparables": {1: {"individual": {"23": "-", "22": "-"}}}}
    fs = collect_findings(reg, ind, data, res, None, sub)
    assert not [f for f in fs if f["item_no"] == 23 and f["comp_no"] == 1 and f["kind"] == "mismatch" and "未修正" in f["message"]]
    f22 = [f for f in fs if f["item_no"] == 22 and f["comp_no"] == 1 and "未修正" in f["message"]]
    assert f22 and "核算差異率為" in f22[0]["message"]


def _local_feature(zone: str, coords_m: list[tuple[float, float]], lon0: float = 121.42, lat0: float = 24.99) -> dict:
    import math
    my = 111320.0
    mx = my * math.cos(math.radians(lat0))
    ring = [(lon0 + x / mx, lat0 + y / my) for x, y in coords_m]
    return {"type": "Feature", "properties": {"zone": zone, "ZONE": zone}, "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}}


def test_planned_road_width_measured_from_zoning_road_land():
    from app.maps.zoning import ZoningStore
    from app.spatial.bootstrap import Roads
    from app.spatial.planned_road import planned_road_frontage
    parcel = _local_feature("第一種住宅區", [(0, 0), (10, 0), (10, 10), (0, 10)])
    road = _local_feature("道路用地", [(10.2, -50), (17.2, -50), (17.2, 50), (10.2, 50)])          # 7 m 寬計畫道路貼宗地東邊
    zoning = ZoningStore([parcel, road], name_field="zone")
    line = {"type": "Feature", "properties": {"name": "測試街", "highway": "residential"},
            "geometry": {"type": "LineString", "coordinates": [list(_local_feature("x", [(13.7, -50)])["geometry"]["coordinates"][0][0]), list(_local_feature("x", [(13.7, 50)])["geometry"]["coordinates"][0][0])]}}
    pr = planned_road_frontage(parcel["geometry"], zoning, Roads([line]))
    assert pr["kind"] == "計畫道路" and 6.5 <= pr["width_m"] <= 7.5 and pr["names"] == ["測試街"]
    far = _local_feature("第一種住宅區", [(-40, 0), (-30, 0), (-30, 10), (-40, 10)])              # 離道路用地 40 m → 現有巷道
    assert planned_road_frontage(far["geometry"], zoning)["kind"] == "現有巷道"
    assert planned_road_frontage(far["geometry"], ZoningStore([parcel], name_field="zone")) is None   # 範圍內沒有道路用地 → 無法判定


def test_existing_lane_triggers_proviso():
    v = bcr_far_for("第一種住宅區", "新北市樹林區", existing_lane=True)
    assert v["far"] == 200 and v["check"] and "現有巷道" in v["note"]
    p = {"parcel_id": "太平段367地號", "zoning": "第一種住宅區", "front_road": {"name": "鎮前街367巷4弄", "width_m": 6.0, "kind": "現有巷道"}}
    fill_parcel_admin(p, district="新北市樹林區")
    assert p["far_pct"] == 200 and "現有巷道" in p["derived"]["far_pct"]["note"]
