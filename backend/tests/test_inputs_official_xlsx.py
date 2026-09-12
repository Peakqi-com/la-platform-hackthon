"""地政局正式範本 xlsx 當輸入檔：辨識為 official_xlsx 並略過；範本符號不併入宗地欄位；健康檢查一項壞掉仍 200。"""
from pathlib import Path

from fastapi.testclient import TestClient

from app.inputs import _garbage, merge_parcel_list
from app.main import app, detect_kind

TPL = Path(__file__).resolve().parents[1] / "app" / "templates" / "official"


def test_official_templates_detected_not_as_comparables():
    for name in ("表3地價區段勘查表.xlsx", "表4比較法調查估價表.xlsx", "表5影響地價區域因素分析明細表.xlsx"):
        assert detect_kind(name, (TPL / name).read_bytes()) == "official_xlsx"


def test_template_symbols_not_merged_into_parcels():
    data = {"subject_parcel": {"parcel_id": "A段1地號", "terrain": None}, "comparables": [{"comp_no": 1, "parcel_id": "B段2地號", "terrain": "平坦", "road_type": None}]}
    items = [{"comp_no": 1, "parcel_id": "B段2地號", "terrain": "○", "road_type": "M", "street_parking": "廢棄物污染", "front_road": {"name": "M", "width_m": None}}]
    rep = merge_parcel_list(data, items, "comparables")
    c = data["comparables"][0]
    assert c["terrain"] == "平坦" and c["road_type"] is None and "front_road" not in c
    assert c["street_parking"] == "廢棄物污染"                       # 一般文字不擋（由承辦看），只擋符號與單位
    assert not rep.overrides
    assert _garbage("○") and _garbage("M") and _garbage(" - ") and not _garbage("平坦")


def test_health_stays_200_when_a_component_fails(monkeypatch):
    from app.market import lvr

    def boom():
        raise RuntimeError("no data")
    monkeypatch.setattr(lvr, "lvr_status", boom)
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True and "lvr" in r.json()["errors"] and "no data" in r.json()["lvr"]["error"]


def test_truncated_lvr_file_does_not_break(tmp_path, monkeypatch):
    from app.market.lvr import load_lvr, lvr_status
    bad = tmp_path / "f_land.json"
    bad.write_text('{"records": [{"district": "新北市樹林區", "lots": [{"section": "樹德段", "lot_raw": "0284', encoding="utf-8")
    monkeypatch.setenv("LVR_JSON", str(bad))
    if hasattr(load_lvr, "cache_clear"):
        load_lvr.cache_clear()
    try:
        d = load_lvr()
        assert d["records"] == [] and "損毀" in d["error"]
        assert lvr_status()["n"] == 0 and lvr_status()["error"]
    finally:
        if hasattr(load_lvr, "cache_clear"):
            load_lvr.cache_clear()


def test_removing_an_input_reruns_auto_from_lot(monkeypatch, tmp_path):
    """移除輸入檔會回到快照重併；重併後要再接依地號自動產生，否則推定的個別因素會變回空白。"""
    import app.main as M
    calls = []
    monkeypatch.setattr(M, "_auto_from_lot", lambda cid, request, results: calls.append(cid))
    client = TestClient(app)
    pdf = Path(__file__).resolve().parents[2] / "docs" / "reference" / "查估書表範本.pdf"
    rules = Path(__file__).resolve().parents[2] / "rules" / "shulin_residential_regional.json"
    r = client.post("/api/cases/from_inputs", files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf")), ("files", (rules.name, rules.read_bytes(), "application/json"))],
                    data={"name": "重併測試"})
    assert r.status_code == 200, r.text
    cid = r.json()["case"]["id"]
    iid = next(i["id"] for i in r.json()["case"]["inputs"] if i["kind"] == "rules_table")
    n = len(calls)
    r2 = client.delete(f"/api/cases/{cid}/inputs/{iid}")
    assert r2.status_code == 200 and len(calls) == n + 1 and calls[-1] == cid


def test_pdf_merge_keeps_no_adjust_items_and_notes():
    from app.inputs import merge_pdf_forms
    parsed = {"case": {"case_no": "X", "regional_no_adjust": ["R1-2", "R1-3"], "notes": {"table5_case": "使用分區、建蔽率修正併同表4 考量"}},
              "sections": {}, "comparables": [], "submitted": {}, "notes": {"case": "依查估辦法第17條第3項擴大蒐集期間", "subject": "S"}}
    data, _t5, _t4, rep = merge_pdf_forms({"case": {}, "sections": {}, "comparables": []}, None, None, parsed)
    assert data["case"]["regional_no_adjust"] == ["R1-2", "R1-3"] and "併同" in data["case"]["notes"]["table5_case"]
    assert "第17條第3項" in data["case"]["notes"]["case"] and data["case"]["notes"]["subject"] == "S"
    assert "case.regional_no_adjust" in rep.filled


def test_blank_submitted_individual_and_widen_reason_in_notes():
    import json as _json

    from app.engine.rules import load_ruleset
    from app.engine.tables import run_case
    from app.engine.verify import collect_findings
    d = _json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "shulin_case_1110901.json").read_text(encoding="utf-8"))
    data = {k: d[k] for k in ("case", "sections", "subject_parcel", "comparables")}
    data["subject_parcel"]["zoning"] = "捷運開發區"
    data["case"]["notes"] = {}                                           # 範例資料本身帶了 §17 第3項理由；先拿掉測「沒寫理由」
    reg, ind = load_ruleset(data["case"]["rulesets"]["regional"]), load_ruleset(data["case"]["rulesets"]["individual"])
    res = run_case(reg, ind, data)
    blank = {"comparables": {"1": {"individual": {}}, "2": {"individual": {}}, "3": {"individual": {}}}}
    fs = collect_findings(reg, ind, data, res, None, blank)
    assert not [f for f in fs if "未修正" in f["message"]]                                  # 整欄空白＝待填，不列
    dates = [f for f in fs if f["location"].endswith("交易日期")]
    assert dates and all(f["severity"] == "warn" for f in dates)                             # 沒寫理由 → 需確認
    data["notes"] = {"case": "比準地所在區段無適當成交案例，依土地徵收補償市價查估辦法第17條第3項規定，擴大選取範圍及案例蒐集期間"}
    fs2 = collect_findings(reg, ind, data, res, None, blank)
    dates2 = [f for f in fs2 if f["location"].endswith("交易日期")]
    assert dates2 and all(f["severity"] == "info" and "已敘明" in f["message"] for f in dates2)


def test_table4_case_note_row_not_mistaken_for_header():
    """題目表4 最後一列「全案」備註含「比準地所在區段…」字樣，不能被當成比準地表頭列而跳過。"""
    from app.adapters.common import AdapterResult
    from app.adapters.pdf_forms import parse_table4
    from app.engine.rules import load_ruleset

    note = "1.價格日期調整係參酌平均區段地價表。\n2.比準地所在區段無適當成交案例，故依土地徵收補償市價查估辦法第17條第3項規定，擴大蒐集期間。"
    rows = [["", "", "", "比準地", "", "", "1", "", "", "", "2", "", "", "", "3", "", "", ""],
            ["全案", note] + [""] * 16]

    class _T:
        def extract(self):
            return rows

    class _TS:
        def __init__(self):
            self.tables = [_T()]

    class _P:
        def find_tables(self):
            return _TS()

        def get_text(self, _k="text"):
            return "1110901-99-XXX\n全案\n" + note

    out = parse_table4(_P(), load_ruleset("shulin_residential_individual"), AdapterResult(kind="pdf_forms", data={}))
    assert "第17條第3項" in (out["notes"].get("case") or "")
