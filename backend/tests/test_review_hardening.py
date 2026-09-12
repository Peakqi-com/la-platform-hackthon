"""審查硬化：推定值不判錯、設施無距離、nuisance 未量測、送審值非數字、非法日期、權重合計、缺正常單價 422、無送審書表的意見書措辭。"""
from __future__ import annotations

import pytest

from app.engine.rules import GradeError, grade, load_ruleset
from app.engine.tables import InputError, run_case
from app.engine.verify import _roc, _year_before, collect_findings, inferred_keys, verify_comparables, verify_table4
from app.report.opinion import build_report


@pytest.fixture(scope="module")
def rs():
    return load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual")


def _template():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        d = client.get("/api/cases/demo", params={"variant": "template"}).json()
        return {"data": {k: d[k] for k in ("case", "sections", "subject_parcel", "comparables")}, "submitted_table4": d["submitted_table4"]}


def test_distance_listed_but_no_distance_needs_human(rs):
    _reg, ind = rs
    r = next(x for x in ind.rules if x.item_no == 20)
    assert grade(r, []) == r.criteria["none_level"]                                  # 「無」＝空清單 → 依基準表
    with pytest.raises(GradeError):
        grade(r, [{"name": "變電所", "distance_m": None}])                            # 有列設施但沒距離 → 不能推成最優


def test_nuisance_unmeasured_is_none_and_not_optimal(rs, tmp_path, monkeypatch):
    from app import cases as C
    from app.cases import new_case
    monkeypatch.setattr(C, "CASES_DIR", tmp_path / "cases")
    reg, ind = rs
    rec = new_case(case_no="T", valuation_date="1140901", district="新北市金山區", land_use="商業用地", section_id="P1")
    assert rec["data"]["subject_parcel"]["nuisance"] is None
    comp = {"comp_no": 1, "parcel_id": "X段1地號", "section_id": "P1", "normal_unit_price": 100000, "transaction_date": "114.05.01",
            "date_adjustment": {"pct": 0}, "nuisance": None}
    data = rec["data"]
    data["subject_parcel"].update({"nuisance": [], "area_m2": 500})
    data["comparables"] = [comp]
    res = run_case(reg, ind, data)
    row = next(r for r in res["table4"].comparables[0].rows if r.item_no == 20)
    assert row.pct is None and any("缺少觀測值" in i for i in row.issues)              # 未量測 → 免修正並列需人工，不是「優」


def test_inferred_values_only_warn(rs):
    reg, ind = rs
    d = _template()["data"]
    d["comparables"][0]["derived"] = {"width_m": {"source": "地籍圖", "note": "推定"}}
    keys = inferred_keys(d, reg, ind)
    assert ("表4", 1, 8) in keys and ("表4", 2, 8) not in keys
    res = run_case(reg, ind, d)
    sub4 = {"comparables": {1: {"individual": {"8": 99.0}}}}                          # 寬度差異率亂填
    fs = collect_findings(reg, ind, d, res, None, sub4)
    f = next(x for x in fs if x["table"] == "表4" and x["item_no"] == 8 and x["comp_no"] == 1)
    assert f["severity"] == "warn" and f["kind"] == "inferred" and f["message"].startswith("依系統推定值核算")
    f2 = next((x for x in fs if x["table"] == "表4" and x["item_no"] == 8 and x["comp_no"] == 2), None)
    assert f2 is None or f2["severity"] != "warn" or f2["kind"] != "inferred"


def test_submitted_non_numeric_values_do_not_crash(rs):
    reg, ind = rs
    d = _template()["data"]
    res = run_case(reg, ind, d)
    sub4 = {"comparables": {1: {"regional_adjustment_pct": None, "trial_price": "免", "individual": {"7": "無"}, "weight_pct": "五十"}},
            "subject_comparison_price": "-"}
    fs = verify_table4(res["table4"], sub4)
    assert all(f.severity in ("warn", "info") for f in fs)
    assert any("無法解析" in f.message for f in fs)


def test_invalid_dates_and_leap_day():
    assert _roc("114.13.01") is None and _roc("114.02.30") is None and _roc("1140901") == (114, 9, 1)
    assert _year_before((113, 2, 29)) == _year_before((113, 2, 28))                   # 2/29 退到前一年 2/28
    fs = verify_comparables({"valuation_date": "114.13.01"}, [{"comp_no": 1, "transaction_date": "114.05.01"}])
    assert any("估價基準日格式無法解析" in f.message for f in fs) and all(f.severity != "error" or f.kind == "gap" for f in fs)


def test_weights_must_sum_to_100(rs):
    reg, ind = rs
    import copy
    d = _template()["data"]
    c2 = copy.deepcopy(d["comparables"][0])
    c2["comp_no"], c2["parcel_id"] = 2, "溫泉段999地號"
    d["comparables"].append(c2)
    res = run_case(reg, ind, d)
    n = len(res["table4"].comparables)
    sub4 = {"comparables": {c.comp_no: {"weight_pct": 60 if c.comp_no == 1 else 50} for c in res["table4"].comparables}}
    fs = verify_table4(res["table4"], sub4)
    assert n >= 2 and any(f.severity == "error" and f.location == "比較標的權重合計" for f in fs)
    for c in d["comparables"]:
        c["weight_pct"] = 60 if c["comp_no"] == 1 else 50
    res2 = run_case(reg, ind, d)
    assert "≠ 100%" in res2["table4"].price_basis["weights"] and abs(sum(c.weight_pct for c in res2["table4"].comparables) - 100) < 1e-6   # 書表改用預設權重


def test_missing_unit_price_is_422():
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as client:
        d = _template()["data"]
        d["comparables"][0]["normal_unit_price"] = None
        r = client.post("/api/run", json=d)
        assert r.status_code == 422 and "比較標的1" in r.json()["detail"] and "正常單價" in r.json()["detail"]
    with pytest.raises(InputError):
        reg, ind = load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual")
        run_case(reg, ind, d)


def test_generate_mode_report_wording(rs):
    reg, ind = rs
    d = _template()["data"]
    d["comparables"] = []
    res = run_case(reg, ind, d)
    fs = collect_findings(reg, ind, d, res, None, None)
    gap = next(f for f in fs if f["location"] == "比較標的")
    assert gap["severity"] == "error" and gap["kind"] == "gap"
    rep = build_report(d["case"], fs, has_submitted=False, decisions={"loc:表4:比較標的": {"decision": "accept"}})
    assert rep.conclusion_code == "incomplete" and "資料缺口" in rep.conclusion and "估價單位補正" not in rep.conclusion
    txt = " ".join(it.sentence for its in rep.sections.values() for it in its)
    assert "估價師填載" not in txt and "承辦裁決" not in txt and "資料缺口" in txt
