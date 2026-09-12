"""
一個案件、多份輸入檔（app/inputs.py + /api/cases/from_inputs、/api/cases/{id}/inputs）：
  1. 範本 PDF 拆成三份（勘查表／表5／表4）一次建案 → 資料與送審表跟整份 PDF 讀出來的一致，審查 0 個 error
  2. 只有勘查表的 PDF 也能加入既有案件（舊流程會拒絕）
  3. 清冊 xlsx 覆蓋書表的宗地屬性：覆蓋欄位記 overrides、對不到的列 unmatched
  4. 案號不一致：後來的檔記 conflicts，不覆蓋
  5. 同一份檔重傳不重複併入
  6. 移除一份輸入檔 = 其餘檔重新併入；案件清單 inputs_summary 徽章正確
"""
import io
import json
import os
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient

from app import cases as C
from app.inputs import merge_pdf_forms
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
PDF = Path(os.environ.get("SAMPLE_PDF_DIR", ROOT / "docs" / "reference")) / "查估書表範本.pdf"
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))
client = TestClient(app)
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="沒有範本 PDF")


@pytest.fixture(autouse=True)
def _tmp_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "CASES_DIR", tmp_path / "cases")
    C._mem.clear()
    yield
    C._mem.clear()


def _page_pdf(pages: list[int]) -> bytes:
    src = fitz.open(str(PDF))
    out = fitz.open()
    for p in pages:
        out.insert_pdf(src, from_page=p, to_page=p)
    return out.tobytes()


def _files(named: dict[str, bytes]):
    return [("files", (name, io.BytesIO(content), "application/octet-stream")) for name, content in named.items()]


def _strip(d):
    """比較用：拿掉會因合併順序不同而不同的欄位。"""
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if k not in ("provenance", "geometry", "geometry_source", "geometry_note", "status", "derived")}
    if isinstance(d, list):
        return [_strip(x) for x in d]
    return d


def test_split_pdf_builds_one_case_equal_to_whole():
    whole = client.post("/api/adapt", files={"file": ("全.pdf", PDF.read_bytes(), "application/pdf")}, data={"use_vision": "never"}).json()
    r = client.post("/api/cases/from_inputs", files=_files({"1勘查表.pdf": _page_pdf([0]), "2表5.pdf": _page_pdf([1]), "3表4.pdf": _page_pdf([2])}),
                    data={"use_vision": "never"}, headers={"X-Actor-Name": "%E7%8E%8B", "X-Actor-Role": "officer"})
    assert r.status_code == 200, r.text
    j = r.json()
    rec = j["case"]
    assert len(rec["inputs"]) == 3 and all(i["kind"] == "pdf_forms" for i in rec["inputs"])
    assert [x.get("error") for x in j["results"]] == [None, None, None]
    assert rec["status"] == "reviewing" and rec["origin"] == "inputs"
    assert _strip(rec["data"]["sections"]) == _strip(whole["data"]["sections"])
    assert _strip(rec["data"]["subject_parcel"]) == _strip(whole["data"]["subject_parcel"])
    assert _strip(rec["data"]["comparables"]) == _strip(whole["data"]["comparables"])
    assert rec["submitted_table5"] == {str(k): v for k, v in whole["data"]["submitted"]["table5"].items()}
    assert rec["submitted_table4"]["subject_comparison_price"] == 212958
    assert rec["data"]["case"]["case_no"] == FIX["case"]["case_no"]
    assert not any(i["conflicts"] for i in rec["inputs"])
    body = {k: rec["data"][k] for k in ("case", "sections", "subject_parcel", "comparables")} | {"submitted_table5": rec["submitted_table5"], "submitted_table4": rec["submitted_table4"]}
    assert [f for f in client.post("/api/verify", json=body).json()["findings"] if f["severity"] == "error"] == []
    summ = j["inputs_summary"]
    present = {i["key"] for i in summ["items"] if i["present"]}
    assert {"t1", "t5", "t4"} <= present and "parcels" not in present
    lst = client.get("/api/cases").json()["cases"][0]
    assert lst["inputs_summary"]["n"] == 3
    # 原檔可下載
    f0 = rec["inputs"][0]
    assert client.get(f"/api/cases/{rec['id']}/inputs/{f0['id']}/file").status_code == 200


def test_t1_only_pdf_into_existing_case_and_no_pdf_requires_case_no():
    r = client.post("/api/cases/from_inputs", files=_files({"清冊.xlsx": b"x"}), data={})
    assert r.status_code == 422 and "案號" in r.json()["detail"]
    base = client.post("/api/cases/new", json={"case_no": "1150301-01-001", "valuation_date": "1150301", "district": "新北市金山區", "land_use": "商業用地", "section_id": "P001-00"}).json()
    r = client.post(f"/api/cases/{base['id']}/inputs", files=_files({"勘查表.pdf": _page_pdf([0])}), data={"use_vision": "never"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["results"][0].get("error") is None
    rec = j["record"]
    assert "P002-00" in rec["data"]["sections"] and "P001-00" not in rec["data"]["sections"]     # 空白暫編區段讓位給書表的區段
    assert rec["data"]["subject_parcel"]["section_id"] == "P002-00"
    assert rec["data"]["case"]["case_no"] == "1150301-01-001"                                     # 案件層欄位以既有為準
    assert rec["submitted_table5"] is None and rec["status"] == "draft"                            # 只有勘查表，沒有可比對的送審表
    assert rec["inputs_base"]["data"]["sections"].get("P001-00")                                    # 併入前快照


def test_xlsx_overrides_and_conflicts_and_duplicates():
    from app.adapters.excel_parcels import write_parcels_xlsx
    r = client.post("/api/cases/from_inputs", files=_files({"書表.pdf": PDF.read_bytes()}), data={"use_vision": "never"}).json()
    cid = r["case"]["id"]
    subj = dict(r["case"]["data"]["subject_parcel"])
    subj["width_m"] = 9
    buf = io.BytesIO()
    write_parcels_xlsx([subj, {"parcel_id": "不存在段999地號", "width_m": 1}], buf)
    r2 = client.post(f"/api/cases/{cid}/inputs", files=_files({"清冊.xlsx": buf.getvalue()})).json()
    e = r2["results"][0]
    assert e["kind"] == "parcels" and r2["record"]["data"]["subject_parcel"]["width_m"] == 9
    assert any(o["path"] == "subject_parcel.width_m" for o in e["overrides"]) and any("不存在段999地號" in u for u in e["unmatched"])
    # 同一份 PDF 再傳一次 → 略過
    r3 = client.post(f"/api/cases/{cid}/inputs", files=_files({"書表-again.pdf": PDF.read_bytes()}), data={"use_vision": "never"}).json()
    assert r3["results"][0].get("skipped") and len(r3["record"]["inputs"]) == 2
    # 案號不一致（純函式）：先來者留，記衝突
    data, _t5, _t4, rep = merge_pdf_forms(r3["record"]["data"], r3["record"]["submitted_table5"], r3["record"]["submitted_table4"],
                                        {"case": {"case_no": "9999999-99-999"}, "sections": {}, "comparables": [], "submitted": {}})
    assert data["case"]["case_no"] == FIX["case"]["case_no"] and rep.conflicts[0]["path"] == "case.case_no" and rep.conflicts[0]["incoming"] == "9999999-99-999"
    # 清單徽章：宗地清冊有了
    summ = client.get("/api/cases").json()["cases"][0]["inputs_summary"]
    assert {i["key"]: i["present"] for i in summ["items"]}["parcels"] is True


def test_remove_input_replays_the_rest():
    from app.adapters.excel_parcels import write_parcels_xlsx
    r = client.post("/api/cases/from_inputs", files=_files({"書表.pdf": PDF.read_bytes()}), data={"use_vision": "never"}).json()
    cid = r["case"]["id"]
    width0 = r["case"]["data"]["subject_parcel"]["width_m"]
    subj = dict(r["case"]["data"]["subject_parcel"])
    subj["width_m"] = 9
    buf = io.BytesIO()
    write_parcels_xlsx([subj], buf)
    r2 = client.post(f"/api/cases/{cid}/inputs", files=_files({"清冊.xlsx": buf.getvalue()})).json()
    iid = next(i["id"] for i in r2["record"]["inputs"] if i["kind"] == "parcels")
    assert r2["record"]["data"]["subject_parcel"]["width_m"] == 9
    r3 = client.delete(f"/api/cases/{cid}/inputs/{iid}", headers={"X-Actor-Name": "%E7%8E%8B", "X-Actor-Role": "officer"})
    assert r3.status_code == 200, r3.text
    rec = r3.json()["record"]
    assert [i["kind"] for i in rec["inputs"]] == ["pdf_forms"] and rec["data"]["subject_parcel"]["width_m"] == width0
    assert rec["submitted_table4"]["subject_comparison_price"] == 212958
    assert client.get(f"/api/cases/{cid}/audit").json()["entries"][0]["action"] == "input_remove"
    # 移除最後一份 → 回到空案
    pid = rec["inputs"][0]["id"]
    rec2 = client.delete(f"/api/cases/{cid}/inputs/{pid}").json()["record"]
    assert rec2["inputs"] == [] and rec2["submitted_table5"] is None and not rec2["data"]["subject_parcel"].get("parcel_id")
    # 刪案件連原檔目錄一起刪
    assert client.delete(f"/api/cases/{cid}").status_code == 200 and not C.inputs_dir(cid).exists()
