"""
基準明細表 adapter 反向驗證：金山 PDF（以及由它轉出的 canonical CSV）→ rules JSON，必須與手抄的 rules/*.json 等價：
levels、max_pct、所有 (比準地等級, 比較標的等級) 組合的修正率、bands/enum/boolean 判定條件。
手抄 JSON 裡的推定（none_level / in_section_level）在 PDF 上沒寫，adapter 要用同樣的推定並發 warning。
"""
import json
from pathlib import Path

import pytest

from app.adapters.rules_table import parse_condition, read_rules_table
from app.engine.rules import Rule, adjustment

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "docs" / "reference" / "評價基準明細表範例.pdf"
CSV = ROOT / "fixtures" / "jinshan_commercial_rules_table.csv"


def _rule(d: dict) -> Rule:
    return Rule(id=d["id"], name=d["name"], group=d["group"], levels=d["levels"], max_pct=d["max_pct"],
                criteria=d["criteria"], explicit_matrix=d.get("matrix"))


def _band_key(b: dict):
    return (b["level"], -1 if b.get("min") is None else b["min"], -1 if b.get("max") is None else b["max"])


def _assert_equivalent(gen: dict, existing_name: str, scope: str) -> None:
    ex = json.loads((ROOT / "rules" / f"{existing_name}.json").read_text(encoding="utf-8"))
    key = "survey_field" if scope == "regional" else "parcel_field"
    gmap = {r.get(key): r for r in gen["rules"]}
    problems = []
    for er in ex["rules"]:
        gr = gmap.get(er[key])
        if gr is None:
            # 「其他」只在內政部表/手抄 JSON，不在金山 PDF 上
            assert er["criteria"]["type"] == "manual", f"{er['id']} 在轉出的規則裡找不到"
            continue
        if gr["levels"] != er["levels"]:
            problems.append(f"{er['id']} levels {gr['levels']} != {er['levels']}")
        if abs(gr["max_pct"] - er["max_pct"]) > 1e-6:
            problems.append(f"{er['id']} max_pct {gr['max_pct']} != {er['max_pct']}")
        for s in er["levels"]:
            for c in er["levels"]:
                if abs(adjustment(_rule(gr), s, c) - adjustment(_rule(er), s, c)) > 1e-6:
                    problems.append(f"{er['id']} adjustment[{s}][{c}]")
        gc, ec = gr["criteria"], er["criteria"]
        if gc["type"] != ec["type"]:
            problems.append(f"{er['id']} criteria type {gc['type']} != {ec['type']}")
            continue
        if ec["type"] in ("bands", "distance"):
            if sorted(map(_band_key, gc["bands"])) != sorted(map(_band_key, ec["bands"])):
                problems.append(f"{er['id']} bands differ")
            for k in ("none_level", "in_section_level", "direction", "aggregate"):
                if ec.get(k) != gc.get(k):
                    problems.append(f"{er['id']} {k}: {gc.get(k)} != {ec.get(k)}")
        elif ec["type"] == "enum":
            for k, v in ec["map"].items():
                if gc["map"].get(k) != v:
                    problems.append(f"{er['id']} enum「{k}」: {gc['map'].get(k)} != {v}")
            if ec.get("default") != gc.get("default"):
                problems.append(f"{er['id']} default {gc.get('default')} != {ec.get('default')}")
        elif ec["type"] == "boolean":
            if (gc["true_level"], gc["false_level"]) != (ec["true_level"], ec["false_level"]):
                problems.append(f"{er['id']} boolean levels")
    assert not problems, "\n".join(problems)
    assert len(gen["rules"]) == len([r for r in ex["rules"] if r["criteria"]["type"] != "manual"])


@pytest.fixture(scope="module")
def from_pdf():
    return read_rules_table(PDF, id_prefix="jinshan_commercial")


def test_pdf_regional_equivalent(from_pdf):
    _assert_equivalent(from_pdf.data["rulesets"]["regional"], "jinshan_commercial_regional", "regional")


def test_pdf_individual_equivalent(from_pdf):
    _assert_equivalent(from_pdf.data["rulesets"]["individual"], "jinshan_commercial_individual", "individual")


def test_pdf_meta_and_warnings(from_pdf):
    assert from_pdf.data["meta"]["land_use"] == "商業用地"
    assert from_pdf.data["meta"]["regional_moi_column"] == "普通商業用地"
    w = "\n".join(from_pdf.warnings)
    assert "I13 道路種類 max 8.0 > 上限 5" in w           # 範本疑點：超過內政部上限 → warning 不判錯
    assert "「km」疑為「m」" in w                          # 基準表打字錯誤
    assert "推定" in w                                      # 無設施/區段內有 的推定要標出來
    # 等距矩陣不該帶 matrix；金山表全部等距
    for rs in from_pdf.data["rulesets"].values():
        assert all("matrix" not in r for r in rs["rules"])


def test_csv_roundtrip_equivalent():
    res = read_rules_table(CSV, id_prefix="jinshan_commercial", land_use="商業用地")
    _assert_equivalent(res.data["rulesets"]["regional"], "jinshan_commercial_regional", "regional")
    _assert_equivalent(res.data["rulesets"]["individual"], "jinshan_commercial_individual", "individual")


def test_generated_ruleset_reproduces_acceptance_case(from_pdf):
    """用轉出的規則跑範本案件，仍要得到 13.00% / 212,958。"""
    from app.engine.rules import RuleSet
    from app.engine.tables import run_case

    def to_rs(d):
        return RuleSet(id=d["id"], scope=d["scope"], land_use=d["land_use"], groups={g["no"]: g["name"] for g in d["groups"]},
                       rules=[Rule(id=r["id"], name=r["name"], group=r["group"], levels=r["levels"], max_pct=r["max_pct"],
                                   criteria=r["criteria"], item_no=r.get("item_no"), survey_field=r.get("survey_field"),
                                   parcel_field=r.get("parcel_field"), facility_types=r.get("facility_types", []),
                                   explicit_matrix=r.get("matrix")) for r in d["rules"]])
    fix = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
    out = run_case(to_rs(from_pdf.data["rulesets"]["regional"]), to_rs(from_pdf.data["rulesets"]["individual"]), fix)
    c = out["table4"].comparables[0]
    assert c.individual_total_pct == 13.0
    assert abs(out["table4"].subject_comparison_price - 212958) <= 1
    assert out["table5"][1].total_pct == 0.0


@pytest.mark.parametrize("text,expected", [
    ("未滿500m", {"kind": "range", "ranges": [{"max": 500.0}], "or_none": False}),
    ("500m以上未滿1,000m", {"kind": "range", "ranges": [{"min": 500.0, "max": 1000.0}], "or_none": False}),
    ("1,800m以上或無", {"kind": "range", "ranges": [{"min": 1800.0}], "or_none": True}),
    ("未滿10m或100m以上", {"kind": "range", "ranges": [{"max": 10.0}, {"min": 100.0}], "or_none": False}),
    ("80%以上作為店舖", {"kind": "range", "ranges": [{"min": 80.0}], "or_none": False}),
    ("區段內有", {"kind": "in_section"}),
    ("無禁止或限制建築", {"kind": "bool", "value": False}),
    ("有排水系統偶有淹水", {"kind": "enum", "values": ["有排水系統偶有淹水"]}),
    ("農業區、保護區建地目", {"kind": "enum", "values": ["農業區建地目", "保護區建地目", "農業區、保護區建地目"]}),
])
def test_parse_condition(text, expected):
    got = parse_condition(text)
    for k, v in expected.items():
        assert got[k] == v, (text, k, got)
