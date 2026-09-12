"""
用作業手冊自己的範例驗證價格鏈的每一步，法源見 docs/07_calculation_basis.md。
  p.100-101 表4 範例：三件比較標的 → 試算 16,309 / 15,372 / 15,254，權重 50/30/20，比準地比較價格 15,817
  p.10、辦法 §21：15,817 → 比準地地價 15,900（逾 1,000 至 10 萬 → 百位無條件進位）
  p.102 宗地市價範例：15,900 × (1−5%) = 15,105 → 15,200；−6% → 14,946 → 15,000；−3% → 15,423 → 15,500
"""
import json
from pathlib import Path

import pytest

from app.engine.rules import load_ruleset
from app.engine.tables import (
    abs_sum,
    comparison_price,
    date_adjusted_price,
    date_adjustment_from_index,
    default_similarity_and_weights,
    parcel_market_price,
    round_half_up,
    round_land_price,
    run_case,
    trial_price,
)
from app.engine.verify import collection_window, verify_comparables

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))

# 手冊 p.100-101：(正常單價, 期日%, 區域%, 個別合計%, 個別各項%)
MANUAL = [
    (15200, 0.0, 4.17, 3.0, [1, 1, 0, 0, 0, 0, 0, 0, 3, -2, 0]),
    (13500, 0.0, 7.42, 6.0, [-1, 0, -1, 0, 0, 3, 0, 1, 2, 2, 0]),
    (12150, 0.0, 9.17, 15.0, [0, 0, 0, 2, 2, 3, 0, 2, 3, 1, 2]),
]


def test_manual_p100_trial_prices_are_multiplicative():
    trials = [trial_price(date_adjusted_price(p, d), r, i) for p, d, r, i, _ in MANUAL]
    assert [round_half_up(t) for t in trials] == [16309, 15372, 15254]
    # 加法會得到 16,290 / 15,312 / 15,086，與手冊範例不符 → 乘法才是手冊的算法
    additive = [p * (1 + (r + i) / 100) for p, d, r, i, _ in MANUAL]
    assert [round_half_up(t) for t in additive] != [16309, 15372, 15254]


def test_manual_p100_abs_sum_and_weights():
    sums = [abs_sum(d, r, items) for p, d, r, i, items in MANUAL]
    assert sums == [11.17, 17.42, 24.17]
    assert default_similarity_and_weights(sums) == [("較高", 50.0), ("普通", 30.0), ("較低", 20.0)]
    assert default_similarity_and_weights([10.0, 7.0]) == [("普通", 30.0), ("較高", 70.0)]
    assert default_similarity_and_weights([15.0]) == [("普通", 100.0)]
    assert default_similarity_and_weights([1, 2, 3, 4]) == [(None, None)] * 4   # 辦法 §19：一至三件


def test_manual_p100_comparison_price_and_p102_parcel_prices():
    trials = [trial_price(date_adjusted_price(p, d), r, i) for p, d, r, i, _ in MANUAL]
    price = comparison_price(trials, [50, 30, 20])
    assert price == 15817                     # 四捨五入至個位（p.53 (十二)）
    land = round_land_price(price)
    assert land == 15900                      # §21：逾 1,000 至 10 萬 → 百位無條件進位
    assert parcel_market_price(land, -5.0) == (15105.0, 15200)
    assert parcel_market_price(land, -6.0)[1] == 15000
    assert parcel_market_price(land, -3.0)[1] == 15500
    assert parcel_market_price(land, 0.0)[1] == 15900


@pytest.mark.parametrize("price,expected", [
    (100, 100), (100.01, 110), (57.2, 58), (101, 110), (1000, 1000), (1000.5, 1100), (15817, 15900),
    (100000, 100000), (100001, 101000), (212958, 213000), (250000, 250000),
])
def test_round_land_price_boundaries(price, expected):
    assert round_land_price(price) == expected


def test_round_half_up_not_bankers():
    assert round_half_up(2.5) == 3 and round_half_up(0.125, 2) == 0.13
    assert date_adjustment_from_index(48481, 47513) == 2.04     # 範本填 2.00%，差 0.04 個百分點（估價師取整）


def test_fixture_land_price_and_basis():
    out = run_case(load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual"), FIX)
    t4 = out["table4"]
    assert t4.subject_comparison_price == 212958 and t4.subject_land_price == 213000
    assert "§21" in t4.price_basis["subject_land_price"]


# ---------------------------------------------------------------- 查估辦法 §17 蒐集期間

def test_collection_window():
    assert collection_window("1140901") == ((114, 3, 2), (114, 9, 1))
    assert collection_window("1140301") == ((113, 9, 2), (114, 3, 1))
    assert collection_window("1140615") is None


def _comp(date, **kw):
    c = dict(FIX["comparables"][0])
    c["transaction_date"] = date
    c.update(kw)
    return c


def test_verify_comparables_period_rules():
    case = FIX["case"]
    assert [f for f in verify_comparables(case, FIX["comparables"]) if f.severity == "error"] == []
    f = verify_comparables(case, [_comp("114.01.15")])          # 原則期間外、一年內 → warn（§17 第3項放寬須敘明）
    assert f and f[0].severity == "warn" and "§17" in f[0].basis
    f = verify_comparables(case, [_comp("113.05.28")])          # 超過一年 → error
    assert any(x.severity == "error" and "一年" in x.message for x in f)
    f = verify_comparables(case, [_comp("114.09.15")])          # 晚於基準日 → error
    assert any(x.severity == "error" and "晚於" in x.message for x in f)
    f = verify_comparables(case, [_comp("114.05.28", date_adjustment={"pct": 1.0, "index_at_valuation": 48481, "index_at_transaction": 47513})])
    assert any("地價指數" in x.message for x in f)
    f = verify_comparables(case, [_comp("114.05.28", source={"price_total": 30_000_000}, area_m2=111.85)])
    assert any(x.checklist == "v" and "§13" in (x.basis or "") for x in f)
    assert any(x.severity == "error" for x in verify_comparables(case, []))
    assert any("三件" in x.message for x in verify_comparables(case, [_comp("114.05.28")] * 4))


# ---------------------------------------------------------------- 等級數字（手冊 p.49 (七)2、p.52 (八)2）與內政部上限（附件24/25）


def test_level_number_follows_manual():
    from app.engine.rules import Rule, level_number
    two = Rule(id="x", name="x", group=1, levels=["優", "劣"], max_pct=10, criteria={})
    three = Rule(id="y", name="y", group=1, levels=["優", "普通", "劣"], max_pct=10, criteria={})
    five = Rule(id="z", name="z", group=1, levels=["優", "稍優", "普通", "稍劣", "劣"], max_pct=10, criteria={})
    assert [level_number(two, lv) for lv in two.levels] == [1, 2]
    assert [level_number(three, lv) for lv in three.levels] == [1, 2, 3]
    assert [level_number(five, lv) for lv in five.levels] == [1, 2, 3, 4, 5]


def test_verify_rulesets_flags_moi_excess_as_warn_only():
    from app.engine.rules import load_ruleset
    from app.engine.verify import verify_rulesets
    reg, ind = load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual")
    fs = verify_rulesets(reg, ind)
    assert all(f.severity == "warn" for f in fs)
    assert [f.item_no for f in fs if f.table == "表4"] == [13]            # 疑點 D：道路種類 8 > 5
    assert [f for f in fs if f.table == "表5"] == []                        # 區域表全在普通商業用地欄內
    assert verify_rulesets(load_ruleset("demo_residential_regional"), load_ruleset("demo_residential_individual")) == []
