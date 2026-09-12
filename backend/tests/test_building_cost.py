"""建物成本價格推定（第四號公報成本法）：表格對照、折舊、房價水準判定、實價登錄含建物實例自動採用。"""
from __future__ import annotations

from app.market.building_cost import (
    age_years,
    cn_to_int,
    district_price_level,
    estimate_building_cost,
    load_table,
    residual_rate,
    structure_of,
    unit_cost_per_ping,
    useful_life,
)


def test_table_values_match_bulletin():
    t = load_table()
    rc = t["construction_cost"]["rc_house_office"]
    assert rc[0]["ranges"][1] == [75100, 92000] and rc[9]["ranges"][5] == [220000, 257000] and rc[10]["ranges"][0] is None   # 附表一-2 逐格
    assert t["useful_life"]["house_office_shop"]["鋼筋混凝土造"] == 50 and t["useful_life"]["house_office_shop"]["加強磚造"] == 35
    assert t["residual_rate"]["rates"]["鋼筋混凝土造"] == [4, 5] and t["residual_rate"]["rates"]["加強磚造"] == [0, 0]


def test_lookup_and_depreciation():
    assert cn_to_int("二十九層") == 29 and cn_to_int("十層") == 10 and cn_to_int("全") is None
    assert structure_of("鋼筋混凝土構造") == "鋼筋混凝土造" and structure_of("鋼骨鋼筋混凝土構造") == "鋼骨鋼筋混凝土造"
    uc = unit_cost_per_ping("鋼筋混凝土造", "house", 4, 1)
    assert uc["value"] == (79600 + 96600) / 2 and "4~5F" in uc["row"]
    src = unit_cost_per_ping("鋼骨鋼筋混凝土造", "house", 29, 5)
    assert src["value"] == (220000 + 257000) / 2 + 40000                                   # 說明事項第 5 點加計中位 40,000
    assert useful_life("加強磚造", "house") == 35 and useful_life("鋼筋混凝土造", "factory") == 35 and residual_rate("鋼筋混凝土造") == 0.045
    assert abs(age_years("1030820", "114.05.28") - 10.8) < 0.1
    rec = {"building": {"area": 100.0, "type": "公寓(5樓含以下無電梯)", "material": "鋼筋混凝土造", "completed": "0900101", "floors": "五層", "level": "三層"}, "date": "114.09.01"}
    e = estimate_building_cost(rec, level={"level": 0, "label": "未達200,000", "n": 10, "median_per_ping": 150000})
    from app.market.building_cost import cci_factor
    ping = 100 / 3.305785
    cf = cci_factor("114.09.01")
    rebuild = (77300 + 98400) / 2 * (cf["factor"] if cf else 1.0) * ping                # 依新北市營造工程物價總指數調到交易日
    age = age_years("0900101", "114.09.01")
    expect = rebuild * (1 - (1 - 0.045) * min(age, 50) / 50)
    assert abs(e["cost"] - expect) < 2 and e["check"] is True and "第四號" in " ".join(e["basis"])
    assert estimate_building_cost({"building": {"area": 0}}, level=None) is None            # 沒面積推不了
    assert estimate_building_cost({"building": {"area": 50, "material": "鋼筋混凝土造", "type": "住宅大樓"}, "date": "114.01.01"}, level={"level": None}) is None   # 沒房價水準（住宅 RC 需欄位）


def test_price_level_from_registry():
    recs = [{"district": "板橋區", "target": "房地(土地+建物)", "total_price": 20_000_000, "date": "114.03.01", "building": {"area": 100}},
            {"district": "板橋區", "target": "房地(土地+建物)", "total_price": 10_000_000, "date": "114.06.01", "building": {"area": 100}},
            {"district": "板橋區", "target": "土地", "total_price": 99_000_000, "date": "114.06.01", "building": None},
            {"district": "板橋區", "target": "房地(土地+建物)", "total_price": 90_000_000, "date": "110.06.01", "building": {"area": 100}}]     # 三年前不算
    from app.engine.verify import _ord
    lv = district_price_level(recs, "板橋區", before_ord=_ord((114, 9, 1)))
    assert lv["n"] == 2 and lv["level"] == 2 and abs(lv["median_per_ping"] - 15_000_000 / (100 / 3.305785)) < 1


def test_search_auto_adopts_estimated_building_cost():
    from app.market.lvr import build_comparables, search_comparables
    lvr = {"records": [
        {"id": "A1", "season": "114S3", "district": "金山區", "target": "房地(土地+建物)", "position": "金山區某路1號", "total_area": 100.0, "zone": "都市：其他:第二種商業區", "date": "1140528",
         "counts": "土地1建物1車位0", "total_price": 30_000_000.0, "unit_price": None, "note": "", "lots": [{"section": "溫泉段", "area": 100.0, "zone": "都市：其他:第二種商業區", "share": "1/1", "transfer": "全筆移轉", "lot_raw": "02180000"}],
         "building": {"area": 200.0, "type": "透天厝", "material": "鋼筋混凝土造", "completed": "1000101", "floors": "三層", "level": "全"}}] + [
        {"id": f"H{i}", "season": "114S3", "district": "金山區", "target": "房地(土地+建物)", "total_area": 30.0, "zone": "都市：其他:第二種住宅區", "date": "1140401", "counts": "", "total_price": 8_000_000.0,
         "unit_price": None, "note": "", "lots": [], "building": {"area": 100.0, "type": "公寓", "material": "鋼筋混凝土造", "completed": "0950101", "floors": "五層", "level": "二層"}} for i in range(5)]}
    data = {"case": {"valuation_date": "1150101", "district": "新北市金山區", "land_use": "商業用地"}, "subject_parcel": {"parcel_id": "金美段473地號", "section_id": "P1"}, "sections": {"P1": {}}, "comparables": []}
    res = search_comparables(data, lvr=lvr, neighbors=False, relax=True)
    a1 = next(c for c in res["candidates"] if c["id"] == "A1")
    assert a1["needs_building_cost"] and a1["building_cost_estimate"] and a1["excluded"] is False
    assert any(c["id"] == "A1" for c in res["chosen"])
    comps = build_comparables(data, res, ["A1"])
    c = comps[0]
    assert c["source"]["building_cost"] == a1["building_cost_estimate"]["cost"] and "推定" in c["source"]["building_cost_source"]
    assert abs(c["normal_unit_price"] - (30_000_000 - a1["building_cost_estimate"]["cost"]) / 100.0) < 1
    comps2 = build_comparables(data, res, ["A1"], {"A1": 5_000_000})
    assert comps2[0]["source"]["building_cost"] == 5_000_000 and comps2[0]["source"]["building_cost_source"] == "估價師填載"   # 人工值優先


def test_cci_factor_uses_month_or_latest_before():
    from app.market.building_cost import cci_factor, load_cci
    ser = load_cci()["series"]
    if not ser:
        return
    f = cci_factor("113.11.15")
    assert f and abs(f["factor"] - 1.0) < 1e-9                                         # 基期當月係數 1
    g = cci_factor("999.01.01")
    assert g and g["month"] == max(ser)                                                  # 未來日期用最新一期
    assert cci_factor("050.01.01") is None                                               # 早於序列起點
