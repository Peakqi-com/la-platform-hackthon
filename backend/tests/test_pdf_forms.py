"""
pdf_forms：
  1. 文字層路徑餵地政局範本 PDF → 還原 fixture 的 input 欄位 ≥ 80%（實際接近 100%）、表5/表4 submitted 與 expected 一致
  2. 抽出的 submitted 餵回引擎審查 → 0 個 error（估價師的表與規則算的表一致）
  3. 掃描件（把範本每頁轉成純圖片 PDF）→ 文字層抽不到 → 走 vision（MockProvider 回 fixture 內容）→ 還原 ≥ 80%
  4. 信心值門檻：< 0.6 → missing；0.6–0.85 → warning
  5. use_vision="always" 交叉比對：vision 與文字層不一致 → warning 且採文字層
"""
import json
import os
from pathlib import Path

import fitz
import pytest

from app.adapters.common import flatten, leaf_equal
from app.adapters.pdf_forms import read_pdf_forms
from app.engine.rules import load_ruleset
from app.engine.tables import run_case
from app.engine.verify import verify_table4, verify_table5
from app.llm.mock_provider import MockProvider

ROOT = Path(__file__).resolve().parents[2]
PDF = Path(os.environ.get("SAMPLE_PDF_DIR", ROOT / "docs" / "reference")) / "查估書表範本.pdf"
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
INPUT_KEYS = ("sections", "subject_parcel", "comparables")


def _coverage(data: dict) -> tuple[float, dict]:
    exp = flatten({k: FIX[k] for k in INPUT_KEYS})
    got = flatten({k: data[k] for k in INPUT_KEYS})
    miss = {k: (v, got.get(k)) for k, v in exp.items() if not leaf_equal(v, got.get(k))}
    return 1 - len(miss) / len(exp), miss


@pytest.fixture(scope="module")
def text_result():
    return read_pdf_forms(PDF, use_vision="never")


def test_text_layer_pages_and_case(text_result):
    kinds = [p["kind"] for p in text_result.data["pages"]]
    assert kinds[:3] == ["t1", "t5", "t4"] and all(p["method"] == "text" for p in text_result.data["pages"][:3])
    case = text_result.data["case"]
    assert case["case_no"] == FIX["case"]["case_no"]
    assert case["valuation_date"] == FIX["case"]["valuation_date"]
    assert case["district"] == FIX["case"]["district"] and case["land_use"] == "商業用地"
    assert case["rulesets"] == FIX["case"]["rulesets"]
    assert text_result.missing_fields == []


def test_text_layer_coverage_80pct(text_result):
    cov, miss = _coverage(text_result.data)
    assert cov >= 0.8, miss
    # 除了 fixture 手寫的 note 以外全部還原
    assert set(miss) <= {"comparables[0].date_adjustment.note"}, miss
    # 抄來的距離要帶 measure/origin/source 並標 assumed
    st = text_result.data["sections"]["P002-00"]["survey"]["transport"]["major_station"][0]
    assert st["measure"] == "walking" and st["origin"] == "section_boundary" and st["assumed"] is True


def test_text_layer_submitted_matches_expected(text_result):
    t5 = text_result.data["submitted"]["table5"][1]
    assert {k: v["subject"] for k, v in t5["levels"].items()} == FIX["expected"]["table5"]["subject_levels"]
    assert t5["total_pct"] == 0.0 and t5["group_subtotals"] == {str(i): 0.0 for i in range(1, 9)}
    # 布林細項表上填「無」，抽取要正規化回「優」
    assert t5["levels"]["R1-5"]["subject"] == "優" and t5["levels"]["R1-5"]["subject_num"] == 1
    t4 = text_result.data["submitted"]["table4"]
    exp = FIX["expected"]["table4"]["comparable_1"]
    got = t4["comparables"][1]
    for k in ("date_adjustment_pct", "price_at_valuation_date", "regional_adjustment_pct", "individual_total_pct",
              "abs_sum_pct", "similarity", "weight_pct", "trial_price"):
        assert got[k] == exp[k], k
    assert {k: v for k, v in got["individual"].items() if k != "6"} == exp["individual"]
    assert got["individual"]["6"] == "-"
    assert t4["subject_comparison_price"] == FIX["expected"]["table4"]["subject_comparison_price"]
    # 表1 的等級數字也抓到了（審查重點 iii 用）
    lv = text_result.data["submitted"]["table1"]["P002-00"]["level_numbers"]
    assert lv["land_control.urban_plan"] == {"num": 1, "of": 2}


def test_extracted_case_verifies_clean(text_result):
    data = {k: text_result.data[k] for k in ("case", *INPUT_KEYS)}
    reg, ind = load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual")
    out = run_case(reg, ind, data)
    assert abs(out["table4"].subject_comparison_price - 212958) <= 1
    f5 = verify_table5(out["table5"][1], text_result.data["submitted"]["table5"][1])
    f4 = verify_table4(out["table4"], text_result.data["submitted"]["table4"])
    assert [f for f in f5 + f4 if f.severity == "error"] == []


# ------------------------------------------------------------------ vision 備援


def _scanned_pdf() -> bytes:
    """把範本前三頁轉成純圖片 PDF（沒有文字層）。"""
    src = fitz.open(str(PDF))
    out = fitz.open()
    for i in range(3):
        pix = src[i].get_pixmap(dpi=60)
        page = out.new_page(width=src[i].rect.width, height=src[i].rect.height)
        page.insert_image(page.rect, pixmap=pix)
    return out.tobytes()


def _vision_from_fixture(conf_overrides: dict | None = None):
    """MockProvider handler：依 prompt 判斷是哪張表，回 fixture 內容（模擬模型抄錄正確）。"""
    sec = FIX["sections"]["P002-00"]
    exp4 = FIX["expected"]["table4"]["comparable_1"]

    def survey_paths(s):
        out = {}
        for grp, d in s["survey"].items():
            if isinstance(d, dict):
                for k, v in d.items():
                    out[f"{grp}.{k}"] = v
        return out

    def cond(p, rule_field):
        v = p.get(rule_field)
        if isinstance(v, dict) and "distance_m" in v:
            return {"name": v["name"], "num": v["distance_m"], "unit": "M"}
        if rule_field == "front_road":
            return {"name": v["name"], "num": v["width_m"], "unit": "M"}
        if rule_field == "nuisance":
            return {"name": "、".join(f["name"] for f in v), "num": v[0]["distance_m"], "unit": "M"}
        if isinstance(v, bool):
            return "有" if v else "無"
        if v is None:
            return "-"
        return v

    ind = load_ruleset("jinshan_commercial_individual")
    fields = {r.item_no: ("front_road" if r.parcel_field == "front_road_width_m" else r.parcel_field) for r in ind.rules if r.item_no}

    state = {"n": 0}

    def handler(prompt, images, system):
        if "哪一種書表" in prompt:                      # 掃描件先分類：mock 依頁序回 t1/t5/t4
            k = ["t1", "t5", "t4"][state["n"] % 3]
            state["n"] += 1
            return {"kind": k}
        if "表1" in prompt:
            return {"section_id": "P002-00", "valuation_date": "1140901", "district": "新北市金山區", "range_desc": sec["range_desc"],
                    "survey": survey_paths(sec), "confidence": conf_overrides or {}}
        if "表5" in prompt:
            reg = load_ruleset("jinshan_commercial_regional")
            rows = [{"item": r.name, "subject_num": 1, "subject_level": lv, "comparable_num": 1, "comparable_level": lv, "pct": 0.0}
                    for r in reg.rules for lv in [FIX["expected"]["table5"]["subject_levels"].get(r.id)] if lv]
            return {"case_no": "1140901-99-001", "land_use": "商業用地", "subject_section_id": "P002-00",
                    "comparables": [{"comp_no": 1, "section_id": "P002-00", "rows": rows,
                                     "group_subtotals": {str(i): 0.0 for i in range(1, 9)}, "total_pct": 0.0}],
                    "confidence": {"rows": 0.9, "subtotals": 0.9}}
        if "表4" in prompt:
            sp, cp = FIX["subject_parcel"], FIX["comparables"][0]
            return {"case_no": "1140901-99-001", "valuation_date": "1140901", "fill_date": "114-09-18",
                    "subject": {"serial_no": "-", "address": sp["address"], "section_id": "P002-00",
                                "items": {str(no): cond(sp, f) for no, f in fields.items()}},
                    "comparables": [{"comp_no": 1, "address": cp["address"], "section_id": "P002-00", "normal_unit_price": cp["normal_unit_price"],
                                     "transaction_date": cp["transaction_date"], "note": None,
                                     "items": {str(no): cond(cp, f) for no, f in fields.items()},
                                     "submitted": {"date_adjustment_pct": 2.0, "price_at_valuation_date": 188459, "regional_adjustment_pct": 0.0,
                                                   "individual": exp4["individual"] | {"6": "-"}, "individual_total_pct": 13.0, "abs_sum_pct": 15.0,
                                                   "similarity": "普通", "trial_price": 212958, "weight_pct": 100}}],
                    "subject_comparison_price": 212958, "case_note": "略", "confidence": {"items": 0.9, "prices": 0.95, "pcts": 0.9}}
        return {"kind": "other"}
    return MockProvider(handler=handler)


def test_scanned_pdf_falls_back_to_vision():
    prov = _vision_from_fixture()
    res = read_pdf_forms(_scanned_pdf(), provider=prov, use_vision="auto")
    assert [p["method"] for p in res.data["pages"]] == ["vision"] * 3
    assert len(prov.calls) == 6 and all(c["n_images"] == 1 for c in prov.calls)   # 3 次分類 + 3 次抽取
    cov, miss = _coverage(res.data)
    assert cov >= 0.8, miss
    assert res.data["submitted"]["table4"]["comparables"][1]["trial_price"] == 212958
    assert res.data["submitted"]["table5"][1]["levels"]["R5-1"]["subject"] == "劣"
    assert res.data["case"]["land_use"] == "商業用地"


def test_confidence_policy():
    prov = _vision_from_fixture({"land_control.zoning": 0.5, "natural.drainage": 0.7})
    res = read_pdf_forms(_scanned_pdf(), provider=prov)
    assert "sections.P002-00.survey.land_control.zoning" in res.missing_fields
    assert any("natural.drainage" in w and "信心值 0.70" in w for w in res.warnings)


def test_vision_without_provider_warns(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    res = read_pdf_forms(_scanned_pdf())
    assert any("需要語言模型" in w for w in res.warnings)
    assert "subject_parcel" in res.missing_fields and "sections" in res.missing_fields


def test_cross_check_prefers_text_layer():
    prov = _vision_from_fixture()

    def tampered(prompt, images, system):
        out = prov._handler(prompt, images, system)
        if "表4" in prompt:
            out["comparables"][0]["submitted"]["individual"]["14"] = 2.5   # vision 看錯
        return out
    res = read_pdf_forms(PDF, provider=MockProvider(handler=tampered), use_vision="always")
    assert res.data["submitted"]["table4"]["comparables"][1]["individual"]["14"] == 5.0
    assert any("不一致" in w and "vision「2.5」" in w for w in res.warnings)
