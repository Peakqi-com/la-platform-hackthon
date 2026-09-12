"""快速跑一個案件：python cli.py ../fixtures/sample_case_P002-00.json"""
import json, sys
from app.engine.rules import load_ruleset
from app.engine.tables import run_case

data = json.load(open(sys.argv[1], encoding="utf-8"))
rs = data["case"].get("rulesets", {})
r = run_case(load_ruleset(rs.get("regional", "jinshan_commercial_regional")),
             load_ruleset(rs.get("individual", "jinshan_commercial_individual")), data)
for comp_no, t5 in r["table5"].items():
    print(f"\n== 表5  比準地區段 {t5.subject_section} vs 比較標的{comp_no} 區段 {t5.comparable_section}")
    for row in t5.rows:
        flag = "  ⚠ " + "; ".join(row.issues) if row.issues else ""
        print(f"  {row.rule_id:5} {row.name[:22]:24} {row.subject_num or '-'} {row.subject_level or '-':3} | {row.comparable_num or '-'} {row.comparable_level or '-':3} | {row.pct if row.pct is not None else '-':>6}{flag}")
    print(f"  小計 {t5.group_subtotals}  總修正數 {t5.total_pct}%")
t4 = r["table4"]
for c in t4.comparables:
    print(f"\n== 表4  比較標的{c.comp_no} {c.parcel_id}  正常單價 {c.normal_unit_price:,}  期日 {c.date_adjustment_pct}%  → {c.price_at_valuation_date:,.0f}  區域 {c.regional_adjustment_pct}%")
    for row in c.rows:
        print(f"  {row.item_no:2} {row.name[:14]:16} {row.subject_level or '-':3} | {row.comparable_level or '-':3} | {row.pct if row.pct is not None else '-':>6}")
    print(f"  合計 {c.individual_total_pct}%  絕對值加總 {c.abs_sum_pct}%  {c.similarity} {c.weight_pct}%  試算 {c.trial_price:,.0f}")
print(f"\n比準地比較價格 {t4.subject_comparison_price:,.0f}")
