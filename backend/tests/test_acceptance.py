"""
驗收測試：餵範本（金山區 P002-00）的事實進引擎，必須完整重現估價師填的表 5-2 與表 4。
這是整個專案的「地基測試」——任何規則或引擎改動都不能讓它掛掉。
"""
import json
from pathlib import Path

import pytest

from app.engine.rules import adjustment, grade, load_ruleset
from app.engine.tables import run_case
from app.engine.verify import verify_table4, verify_table5

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rulesets():
    return load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual")


@pytest.fixture(scope="module")
def result(rulesets):
    return run_case(*rulesets, FIX)


# ---------------------------------------------------------------- 表5

def test_table5_subject_levels_match_appraiser(result):
    t5 = result["table5"][1]
    got = {r.rule_id: r.subject_level for r in t5.rows if r.subject_level is not None}
    exp = FIX["expected"]["table5"]["subject_levels"]
    diff = {k: (got.get(k), v) for k, v in exp.items() if got.get(k) != v}
    assert not diff, f"等級不符 (rule: (engine, appraiser)): {diff}"


def test_table5_totals(result):
    t5 = result["table5"][1]
    exp = FIX["expected"]["table5"]["comparable_1"]
    assert [t5.group_subtotals[g] for g in sorted(t5.group_subtotals)] == exp["group_subtotals"]
    assert t5.total_pct == exp["total_pct"]
    assert not any(r.issues for r in t5.rows), [r.issues for r in t5.rows if r.issues]


# ---------------------------------------------------------------- 表4

def test_table4_individual_rates(result):
    c = result["table4"].comparables[0]
    got = {str(r.item_no): r.pct for r in c.rows if r.pct is not None}
    exp = FIX["expected"]["table4"]["comparable_1"]["individual"]
    diff = {k: (got.get(k), v) for k, v in exp.items() if got.get(k) is None or abs(got[k] - v) > 1e-6}
    assert not diff, f"差異率不符 (item: (engine, appraiser)): {diff}"


def test_table4_price_chain(result):
    c = result["table4"].comparables[0]
    exp = FIX["expected"]["table4"]["comparable_1"]
    assert c.date_adjustment_pct == exp["date_adjustment_pct"]
    assert c.regional_adjustment_pct == exp["regional_adjustment_pct"]
    assert c.individual_total_pct == exp["individual_total_pct"]
    assert c.abs_sum_pct == exp["abs_sum_pct"]
    assert c.similarity == exp["similarity"]
    assert c.weight_pct == exp["weight_pct"]
    assert abs(c.price_at_valuation_date - exp["price_at_valuation_date"]) <= 1
    assert abs(c.trial_price - exp["trial_price"]) <= 1
    assert abs(result["table4"].subject_comparison_price - FIX["expected"]["table4"]["subject_comparison_price"]) <= 1


# ---------------------------------------------------------------- 審查模式

def test_verify_clean_submission_has_no_errors(result):
    """把估價師填的值餵回審查器，應該沒有 error。"""
    exp4 = FIX["expected"]["table4"]
    submitted4 = {"comparables": {1: exp4["comparable_1"]}, "subject_comparison_price": exp4["subject_comparison_price"]}
    f4 = verify_table4(result["table4"], submitted4)
    assert [f for f in f4 if f.severity == "error"] == []

    exp5 = FIX["expected"]["table5"]
    submitted5 = {"levels": {k: {"subject": v, "comparable": v, "pct": 0.0} for k, v in exp5["subject_levels"].items()},
                  "group_subtotals": {str(i + 1): v for i, v in enumerate(exp5["comparable_1"]["group_subtotals"])},
                  "total_pct": 0.0}
    f5 = verify_table5(result["table5"][1], submitted5)
    assert [f for f in f5 if f.severity == "error"] == []


def test_verify_catches_tampering(result):
    """竄改：面前道路寬度差異率填 2.5（應為 5.0）、區域因素抄成 1.0、合計沒改。審查器要抓到三個 error。"""
    exp4 = json.loads(json.dumps(FIX["expected"]["table4"]["comparable_1"]))
    exp4["individual"]["14"] = 2.5
    exp4["regional_adjustment_pct"] = 1.0
    f = verify_table4(result["table4"], {"comparables": {1: exp4}})
    locs = [x.location for x in f if x.severity == "error"]
    assert any("14 面前道路寬度" in l for l in locs)
    assert any("區域因素調整百分率" in l for l in locs)
    assert len([x for x in f if x.severity == "error"]) >= 2


# ---------------------------------------------------------------- 單元：矩陣方向

def test_matrix_direction(rulesets):
    _, ind = rulesets
    r = ind.by_item_no(14)  # 面前道路寬度 max 10, 5 級
    assert grade(r, 18) == "稍優" and grade(r, 6) == "稍劣"
    assert adjustment(r, "稍優", "稍劣") == 5.0     # 比準地優 → 正
    assert adjustment(r, "稍劣", "稍優") == -5.0
    r20 = ind.by_item_no(20)  # 嫌惡設施：愈遠愈好
    assert grade(r20, [{"name": "公墓", "distance_m": 260}]) == "普通"
    assert grade(r20, [{"name": "公墓", "distance_m": 80}]) == "劣"
    assert grade(r20, []) == "優"
    assert adjustment(r20, "普通", "劣") == 3.0
