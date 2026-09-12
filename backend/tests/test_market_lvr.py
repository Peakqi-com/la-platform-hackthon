"""實價登錄 → 比較標的：§7 特殊情況、用地別、§17 期間與放寬、§19 階段、§13 建物成本。全部用合成資料，不碰 data/。"""
from app.market.lvr import build_comparables, classify, lot_no_from_raw, search_comparables, to_comparable, zone_matches

ZONE_TXT = {"商": "都市：其他:第二種商業區", "住": "都市：其他:第二種住宅區", "農": "都市：其他:農業區", "": ""}


def rec(i, *, district="金山區", date="1140515", zone="商", total=2_000_000, area=100.0, note="", target="土地", lots=None, building=None):
    return {"id": f"R{i}", "season": "114S2", "district": district, "target": target, "position": f"金美段{470 + i}地號", "total_area": area,
            "zone": zone, "date": date, "total_price": total, "unit_price": total / area, "note": note, "building": building,
            "lots": lots or [{"section": "金美段", "area": area, "zone": ZONE_TXT.get(zone, ""), "share": "1/1", "transfer": "全筆移轉", "lot_raw": f"{470 + i:04d}0000"}]}


def test_lot_no_and_classify():
    assert lot_no_from_raw("01310001") == "131-1" and lot_no_from_raw("04890000") == "489-0"
    c = classify(rec(1, note="親友、員工、共有人或其他特殊關係間之交易；"))
    assert c["excluded"] and c["flags"][0]["rule"] == "§7 第4款"
    assert classify(rec(2, note="包含公共設施保留地用地；"))["flags"][0]["rule"] == "§7 第10款"
    assert classify(rec(3, note="地清或未辦繼承標售；"))["flags"][0]["rule"] == "§7 第8款"
    assert not classify(rec(4))["excluded"]
    p = classify(rec(5, lots=[{"section": "金美段", "area": 50, "zone": "都市：其他:第二種商業區", "share": "1/2", "transfer": "持分移轉", "lot_raw": "04750000"}]))
    assert not p["excluded"] and p["flags"][0]["exclude"] is False          # 持分只標記
    b = classify(rec(6, target="房地(土地+建物)", building={"type": "公寓(5樓含以下無電梯)", "level": "二層", "material": "鋼筋混凝土造", "completed": "0840302", "area": 96.2, "floors": "五層"}))
    assert b["excluded"] and b["flags"][0]["rule"] == "§13 第3款" and b["flags"][0]["needs_building_cost"]


def test_zone_matches():
    assert zone_matches(rec(1, zone="商"), "商業用地") and not zone_matches(rec(1, zone="住"), "商業用地")
    assert zone_matches(rec(1, zone="", lots=[{"section": "s", "area": 1, "zone": "都市：其他:第二種住宅區", "share": None, "transfer": "", "lot_raw": "00010000"}]), "住宅用地")
    assert zone_matches(rec(1, zone="農"), "農業用地") and zone_matches(rec(1, zone="住"), "其他用地")


def _case():
    return {"case": {"case_no": "t", "valuation_date": "1140901", "district": "新北市金山區", "land_use": "商業用地"},
            "sections": {"P1": {"section_id": "P1", "geometry": {"type": "Polygon", "coordinates": [[[121.63, 25.22], [121.64, 25.22], [121.64, 25.23], [121.63, 25.23], [121.63, 25.22]]]}}},
            "subject_parcel": {"parcel_id": "金美段489地號", "section_id": "P1", "geometry": {"type": "Point", "coordinates": [121.635, 25.225]}}, "comparables": []}


def test_search_stages_and_window():
    lvr = {"records": [
        rec(1, date="1140515"),                                             # 同鄉鎮、期間內、有界線在區段內 → 階段 1
        rec(2, date="1140601", note="親友、員工、共有人或其他特殊關係間之交易；"),   # 排除
        rec(3, date="1131001"),                                             # 期間外、一年內 → 階段 5（無界線）
        rec(4, date="1130801"),                                             # 超過一年 → 不列
        rec(5, date="1140701", district="萬里區"),                           # 鄰近鄉鎮 → 階段 3
        rec(6, date="1140701", district="板橋區"),                           # 非鄰近 → 不列
        rec(7, date="1140701", zone="住"),                                   # 用地別不符 → 不列
        rec(8, date="1140910"),                                             # 晚於基準日 → 不列
    ]}
    geoms = {("金美段", "471-0"): {"geometry": {"type": "Point", "coordinates": [121.636, 25.224]}}}
    r = search_comparables(_case(), lvr=lvr, cadastre_lookup=lambda s, l: geoms.get((s, l)))
    assert r["window"]["text"] == "114.03.02～114.09.01" and r["window"]["relaxed_from"] == "113.09.01"
    ids = [c["id"] for c in r["chosen"]]
    assert ids == ["R1", "R5", "R3"]                                         # 階段 1 → 3 → 5
    assert r["chosen"][0]["in_section"] is True and r["chosen"][0]["distance_m"] is not None
    assert r["stats"]["n_excluded"] == 1 and r["stats"]["n_zone"] == 4
    assert {c["id"] for c in r["candidates"]} == {"R1", "R2", "R3", "R5"}
    comps = build_comparables(_case(), r, ids)
    assert comps[0]["section_id"] == "P1" and comps[1]["section_id"] == "P1-C2" and comps[2]["section_id"] == "P1-C3"
    assert comps[0]["normal_unit_price"] == 20000 and comps[0]["transaction_date"] == "114.05.15" and comps[0]["source"]["lvr_id"] == "R1"
    assert "§13 第2款" in comps[0]["source"]["note"] and comps[0]["selection"]["stage"] == 1
    strict = search_comparables(_case(), lvr=lvr, relax=False, neighbors=False)
    assert [c["id"] for c in strict["chosen"]] == ["R1"]                     # 不放寬、不找鄰近鄉鎮


def test_building_cost_required_and_applied():
    b = rec(9, target="房地(土地+建物)", total=5_380_000, area=22.37,
            building={"type": "公寓(5樓含以下無電梯)", "level": "二層", "material": "鋼筋混凝土造", "completed": "0840302", "area": 96.24, "floors": "五層"})
    r = search_comparables(_case(), lvr={"records": [b]})
    cand = r["candidates"][0]
    assert cand["needs_building_cost"] and cand["building_cost_estimate"]["cost"] > 0          # 系統依第四號公報推定建物成本
    assert [c["id"] for c in r["chosen"]] == ["R9"]                                              # 有推定值即可自動採用（標需確認）
    auto = build_comparables(_case(), r, ["R9"])[0]
    assert "推定" in auto["source"]["building_cost_source"] and abs(auto["normal_unit_price"] - (5_380_000 - cand["building_cost_estimate"]["cost"]) / 22.37) < 1
    cand2 = {**cand, "building_cost_estimate": None}
    try:
        to_comparable(cand2, 1, "P1")
        raise AssertionError("推不出建物成本時應要求人工填")
    except ValueError as e:
        assert "建物成本" in str(e)
    c = to_comparable(r["candidates"][0], 1, "P1", building_cost=1_246_852)                       # 估價師填載優先
    assert c["normal_unit_price"] == 184763                                  # 範本 溫泉段218：(5,380,000 − 1,246,852) ÷ 22.37
    assert "§13 第3、4款" in c["source"]["note"] and c["source"]["building_cost"] == 1_246_852



# ---------------------------------------------------------------- 期日調整（都市地價指數，手冊 p.50 (四)）


def test_date_adjustment_from_index_table():
    from app.market.index import date_adjustment_for, index_at
    dates = ["113.09.30", "114.03.31", "114.09.30"]
    series = [107.74, 108.16, 109.52]
    assert index_at("114.03.31", series, dates)[0] == 108.16
    assert index_at("114.09.30", series, dates)[0] == 109.52 and index_at("115.01.01", series, dates)[0] == 109.52
    v, note = index_at("114.06.30", series, dates)                      # 91/183 天 → 108.16 + 1.36×0.497
    assert abs(v - 108.84) < 0.01 and "內插" in note
    r = date_adjustment_for("114.05.28", "1140901", district="新北市金山區", land_use="商業用地")
    assert r["pct"] is not None and r["index_at_valuation"] > r["index_at_transaction"] and "金山區商業區" in r["note"]
    assert r["pct"] == round((r["index_at_valuation"] / r["index_at_transaction"] - 1) * 100, 2)
    assert date_adjustment_for("114.05.28", "1140901", district="新北市金山區", land_use="農業用地")["pct"] is None


# ---------------------------------------------------------------- 行政條件（rules/zoning_bcr_far.json）


def test_bcr_far_lookup_and_parcel_fill():
    from app.spatial.admin import bcr_far_for, fill_parcel_admin, fill_section_admin
    v = bcr_far_for("第二種商業區", "新北市金山區")
    assert (v["bcr"], v["far"]) == (70, 240) and "金山" in v["source"]                 # 範本比準地：70／240
    assert bcr_far_for("都市：其他:第二種住宅區", "金山區")["far"] == 180
    c = bcr_far_for("商業區", "新北市板橋區")
    assert c["bcr"] == 70 and c["far"] == 460 and "板橋" in c["source"]               # 板橋土管要點：容積率 460%，建蔽率依施行細則附表一 70%
    assert "附表一" in c["note"] and c["check"] is False
    c2 = bcr_far_for("商業區", "新北市某某區")
    assert c2["bcr"] == 70 and c2["far"] is None and "施行細則" in c2["source"]        # 沒有計畫區資料 → 主分區只給建蔽率
    assert bcr_far_for("不存在的分區", "金山區") is None
    p = {"parcel_id": "金美段9999地號", "zoning": "第二種商業區", "bcr_pct": 60}
    filled = fill_parcel_admin(p, district="新北市金山區")
    assert "far_pct" in filled and p["far_pct"] == 240 and p["bcr_pct"] == 60          # 已填的建蔽率不覆寫
    assert p["building_restricted"] is False and "預設" in p["derived"]["building_restricted"]["source"]
    sec = {"section_id": "S", "survey": {"land_control": {"zoning": "第二種商業區"}}}
    assert set(fill_section_admin(sec, district="金山區")) == {"land_control.bcr", "land_control.far", "land_control.building_prohibited", "land_control.building_restricted"}
    assert sec["survey"]["land_control"]["bcr"] == 70 and sec["survey_provenance"]["suggestions"]["land_control.far"]["value"] == 240


def test_bcr_far_public_facility_and_current_table():
    from app.spatial.admin import bcr_far_for, load_table
    assert "114.11.05" in load_table()["sources"]["施行細則"]
    m = bcr_far_for("市場用地", "金山區")
    assert (m["bcr"], m["far"]) == (70, 240) and "附表三" in m["note"] and m["check"] is True   # 金山計畫書多表不一致 → 建蔽率由附表三補、標需人工核對
    m2 = bcr_far_for("市場用地", "新北市某某區")
    assert (m2["bcr"], m2["far"]) == (70, 240) and "附表三" in m2["source"]
    pk = bcr_far_for("都市：其他:停車場用地", "金山區")
    assert pk["check"] is True                                                     # 平面／立體不同、計畫書多表不一致 → 需人工核對
    assert bcr_far_for("停車場用地", "新北市某某區")["bcr"] is None                  # 附表三：平面／立體不同，留給人工
    assert bcr_far_for("工業區", "新北市板橋區")["far"] == 210 and bcr_far_for("風景區", "新北市三峽區")["bcr"] == 20


def test_zoning_plan_tables_from_crawl():
    """各計畫區土管要點表（scripts/fetch_ntpc_zoning_rules.py + merge_zoning_rules.py）：每分區有來源與頁碼，主要三分區都齊。"""
    from app.spatial.admin import bcr_far_for, load_table
    plans = load_table()["plans"]
    assert len(plans) >= 15
    for name in ("板橋都市計畫", "三重都市計畫", "中和都市計畫", "新莊都市計畫", "淡水都市計畫"):
        zones = plans[name]["zones"]
        assert any("住宅區" in z for z in zones) and any("商業區" in z for z in zones)
        for v in zones.values():
            assert v["far"] and "頁" in v["note"]
    assert bcr_far_for("住宅區", "三重區")["far"] == 300 and bcr_far_for("商業區", "永和區")["far"] == 440
    v = bcr_far_for("第二種住宅區", "新莊區")                                          # 副都心細部計畫
    assert v["far"] == 350 and v["bcr"] == 50                                       # 建蔽率依附表一
    assert plans["淡水(竹圍地區)都市計畫"]["zones"]["住宅區(三)"]["far"] == 360
    v3 = bcr_far_for("住宅區（三）", "淡水區")                                         # 主計畫沒有此分區 → 查地區型計畫（竹圍），一律需人工核對
    assert v3["far"] == 360 and v3["check"] is True and "竹圍" in v3["note"]
    assert bcr_far_for("住宅區", "淡水區")["check"] is False                           # 主計畫有的分區不受影響
