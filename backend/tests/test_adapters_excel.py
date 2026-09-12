"""表7 清冊 / 買賣實例 Excel adapter：fixture → Excel → 讀回，fixture 裡每個葉值都要還原（readback ⊇ fixture）。"""
import io
import json
from pathlib import Path

from openpyxl import Workbook

from app.adapters.common import flatten, leaf_equal
from app.adapters.excel_comparables import read_comparables, write_comparables_xlsx
from app.adapters.excel_parcels import PARCEL_SPECS, read_parcels, write_parcels_xlsx

ROOT = Path(__file__).resolve().parents[2]
FIX = json.loads((ROOT / "fixtures" / "sample_case_P002-00.json").read_text(encoding="utf-8"))


def _diff(expected: dict, got: dict) -> dict:
    g = flatten(got)
    return {k: (v, g.get(k)) for k, v in flatten(expected).items() if not leaf_equal(v, g.get(k))}


def test_parcels_roundtrip_transposed():
    buf = io.BytesIO()
    write_parcels_xlsx([FIX["subject_parcel"]] + FIX["comparables"], buf, project_name="金山測試案", case_no=FIX["case"]["case_no"])
    r = read_parcels(buf.getvalue())
    assert r.data["meta"]["layout"] == "transposed"
    assert r.data["meta"]["case_no"] == FIX["case"]["case_no"]
    assert len(r.data["parcels"]) == 2
    assert _diff(FIX["subject_parcel"], r.data["parcels"][0]) == {}
    assert r.missing_fields == []
    # 抄來的距離要帶 measure/origin/source 且標 assumed
    sch = r.data["parcels"][0]["school"]
    assert sch["measure"] == "walking" and sch["assumed"] is True and sch["source"]
    assert any("需人工確認" in w and "量測方式" in w for w in r.warnings)


def test_parcels_long_layout_and_missing_fields():
    wb = Workbook()
    ws = wb.active
    header = ["宗地流水號", "段小段名稱", "地號", "7.面積(M2)", "8.寬度(M)", "9.深度(M)", "10.形狀", "11.臨街情形", "12.地勢",
              "13.道路種類", "14.面前道路寬度", "學校名稱", "接近學校之程度(M)", "22.使用分區或編定用地", "23.建蔽率(%)", "24.容積率(%)", "25.有無禁、限建"]
    ws.append(header)
    ws.append(["0001", "金美段", 489, "113.21", 5, 23, "方形", "單面臨街", "平坦", "主要道路", 18, "金山國小", "1,020", "第二種商業區", "70%", "240%", "無"])
    ws.append(["0002", "金美段", 490, 80, None, 20, "不規則形", "單面臨街", "平坦", "巷道", "-", "無", None, "第二種商業區", "-", "-", "有"])
    buf = io.BytesIO()
    wb.save(buf)
    r = read_parcels(buf.getvalue())
    assert r.data["meta"]["layout"] == "long"
    p0, p1 = r.data["parcels"]
    assert p0["parcel_id"] == "金美段489地號" and p0["area_m2"] == 113.21 and p0["bcr_pct"] == 70
    assert p0["school"]["distance_m"] == 1020 and p0["building_restricted"] is False
    # 第二筆：寬度空白 → missing；面前道路寬度「-」→ None 不列 missing；學校「無」→ None 不列 missing；建蔽率「-」不列 missing
    assert "parcels[1].width_m" in r.missing_fields
    assert "parcels[1].front_road.width_m" not in r.missing_fields
    assert p1["school"] is None and "parcels[1].school" not in r.missing_fields
    assert p1["bcr_pct"] is None and "parcels[1].bcr_pct" not in r.missing_fields
    assert p1["building_restricted"] is True
    # 表頭沒有的欄位（市場、公園…）要列 missing
    assert "parcels[0].market" in r.missing_fields and "parcels[0].street_parking" in r.missing_fields


def test_comparables_roundtrip_long():
    buf = io.BytesIO()
    write_comparables_xlsx(FIX["comparables"], buf)
    r = read_comparables(buf.getvalue())
    assert r.data["meta"]["layout"] == "long"
    assert len(r.data["comparables"]) == 1
    assert _diff(FIX["comparables"][0], r.data["comparables"][0]) == {}
    assert r.missing_fields == []


def test_comparables_missing_price_and_date_adjustment():
    wb = Workbook()
    ws = wb.active
    ws.append(["實例編號", "交易日期", "土地正常單價", "段小段名稱", "地號", "面積(M2)"])
    ws.append([1, "114.05.28", None, "溫泉段", "218", 111.85])
    buf = io.BytesIO()
    wb.save(buf)
    r = read_comparables(buf.getvalue())
    assert "comparables[0].normal_unit_price" in r.missing_fields
    assert "comparables[0].date_adjustment.pct" in r.missing_fields
    assert r.data["comparables"][0]["transaction_date"] == "114.05.28"


def test_spec_labels_are_unique():
    seen = {}
    for s in PARCEL_SPECS:
        for lbl in s.labels:
            from app.adapters.common import norm_label
            n = norm_label(lbl)
            assert n not in seen or seen[n] == s.key, f"標籤「{lbl}」同時對到 {seen[n]} 與 {s.key}"
            seen[n] = s.key
