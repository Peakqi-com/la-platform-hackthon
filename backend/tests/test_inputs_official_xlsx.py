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
    d = load_lvr()
    assert d["records"] == [] and "損毀" in d["error"]
    assert lvr_status()["n"] == 0 and lvr_status()["error"]
