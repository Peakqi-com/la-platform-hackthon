"""審查意見書：每句帶 [F-xxx] 與法源；結論依 error/warn；LLM 潤稿守門（標籤、數字）；API。"""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.engine.rules import load_ruleset
from app.engine.tables import run_case
from app.engine.verify import verify_comparables, verify_table4
from app.llm.mock_provider import MockProvider
from app.main import app
from app.report.opinion import build_report, polish_items, to_markdown

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
CASE = {k: FIX[k] for k in ("case", "sections", "subject_parcel", "comparables")}


def _findings(tamper: bool):
    out = run_case(load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual"), CASE)
    exp4 = json.loads(json.dumps(FIX["expected"]["table4"]["comparable_1"]))
    if tamper:
        exp4["individual"]["14"] = 2.5
        exp4["regional_adjustment_pct"] = 1.0
    f = [x.to_dict() for x in verify_comparables(CASE["case"], CASE["comparables"])]
    f += [x.to_dict() for x in verify_table4(out["table4"], {"comparables": {1: exp4}, "subject_comparison_price": 212958})]
    return f, {"table4": out["table4"].to_dict(), "table5": {k: v.to_dict() for k, v in out["table5"].items()}}


def test_clean_case_passes():
    f, computed = _findings(False)
    rep = build_report(CASE["case"], f, computed, subject_parcel_id="金美段489地號", reviewer="測試", review_date="2026-09-06")
    assert rep.conclusion_code == "pass" and rep.counts["error"] == 0
    md = to_markdown(rep)
    assert "審查通過" in md and "212,958" in md and "213,000" in md and "§21" in md


def test_tampered_case_sentences_and_conclusion():
    f, computed = _findings(True)
    rep = build_report(CASE["case"], f, computed)
    assert rep.conclusion_code == "revise" and rep.counts["error"] >= 2
    items = [it for its in rep.sections.values() for it in its]
    assert [it.fid for it in items] == [f"F-{i:03d}" for i in range(1, len(items) + 1)]
    s14 = next(it for it in items if "14 面前道路寬度" in it.location)
    assert s14.sentence.startswith(f"[{s14.fid}] 不符：比較法調查估價表「比較標的1 / 14 面前道路寬度」：估價師填載 2.50，依規則核算應為 5.00")
    assert "矩陣[稍優][稍劣]" in s14.sentence and "依據" in s14.sentence
    assert "vii" in rep.sections and "比較法調查估價表" in to_markdown(rep)
    assert items[0].severity == "error"          # error 排前面


def test_polish_guard():
    f, computed = _findings(True)
    rep = build_report(CASE["case"], f, computed)
    items = [it for its in rep.sections.values() for it in its]
    good = "\n".join(f"- {it.sentence.replace('估價師填載', '估價單位填載')}" for it in items)
    st = polish_items(items, MockProvider(response=good))
    assert st["status"] == "ok" and all(it.polished and "估價單位填載" in it.polished for it in items)
    # 改數字 → 拒絕；缺標籤 → 拒絕
    bad = good.replace("2.50", "3.50", 1).splitlines()
    bad = "\n".join(bad[1:])
    for it in items:
        it.polished = None
    st = polish_items(items, MockProvider(response=bad))
    assert st["status"] in ("partial", "rejected") and any("原文沒有的數字" in r or "缺少" in r for r in st["rejected"])
    assert items[0].polished is None
    md = to_markdown(rep)
    assert items[0].sentence in md                # 守門失敗退回模板句


def test_report_api():
    client = TestClient(app)
    exp4 = FIX["expected"]["table4"]
    body = CASE | {"submitted_table4": {"comparables": {"1": exp4["comparable_1"]}, "subject_comparison_price": exp4["subject_comparison_price"]},
                   "reviewer": "審查員甲", "polish": True}
    r = client.post("/api/report", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    # 範本案件沒有不符項，但金山個別因素表 13 道路種類 8% 超過附件25 上限 5%（疑點 D）→ 一項「需確認」，結論為 confirm 而非 pass
    assert j["report"]["conclusion_code"] == "confirm" and j["report"]["counts"]["error"] == 0 and "審查員甲" in j["markdown"]
    assert "道路種類" in j["markdown"] and "附件25" in j["markdown"]
    assert j["report"]["polish"]["status"] in ("unavailable", "skipped", "ok", "failed")   # 沒 key → unavailable；不影響產出


# ---------------------------------------------------------------- 書表備註模板與潤飾守門（app/report/notes.py）


def test_notes_templates_and_polish_guard():
    from app.engine.rules import load_ruleset
    from app.engine.tables import run_case
    from app.llm.mock_provider import MockProvider
    from app.report.notes import build_notes, guard_ok, polish_text
    data = {k: CASE[k] for k in ("case", "sections", "subject_parcel", "comparables")}
    res = run_case(load_ruleset("jinshan_commercial_regional"), load_ruleset("jinshan_commercial_individual"), data)
    n = build_notes(data, res)
    assert "114.03.02～114.09.01" in n["case"] and "第 17 條第 2 項" in n["case"] and "212,958" in n["case"] and "213,000" in n["case"]
    assert "1" in n["comparables"] and "期日調整" in n["comparables"]["1"] and "114.05.28" in n["comparables"]["1"]
    assert "第二種商業區" in n["subject"] and "70" in n["subject"] and "240" in n["subject"]
    # 人工文字優先
    data2 = {**data, "case": {**data["case"], "notes": {"case": "人工全案備註"}}}
    assert build_notes(data2, res)["case"] == "人工全案備註"
    # 守門：數字或條號改了就退回
    src = "交易日期 114.05.28，依查估辦法第 17 條第 2 項；期日調整率 2.00%。"
    assert guard_ok(src, "本案交易日期為 114.05.28，符合查估辦法第 17 條第 2 項規定；期日調整率採 2.00%。")[0]
    assert not guard_ok(src, "交易日期 114.05.29，依查估辦法第 17 條第 2 項；期日調整率 2.00%。")[0]
    assert not guard_ok(src, "交易日期 114.05.28，依查估辦法第 18 條第 2 項；期日調整率 2.00%。")[0]
    assert polish_text(src, MockProvider(response="交易日期 114.05.28，依查估辦法第 17 條第 2 項；期日調整率為 2.00%。"))["status"] == "ok"
    r = polish_text(src, MockProvider(response="交易日期 115.05.28"))
    assert r["status"] == "rejected" and r["text"] == src
