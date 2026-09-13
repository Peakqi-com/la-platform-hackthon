"""收益法：以地政局範本表2（含附表成本法）的例題驗收；另測素地模式、房租指數與定存利率、收益實例搜尋、表14 比準地地價。"""
from decimal import ROUND_HALF_UP, Decimal

from app.engine.income import compute_income, land_price_decision
from app.market.rates import deposit_rate_at, rent_date_adjustment


def R(x, n=0):
    """Excel ROUND：四捨五入。"""
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))


def template_reference():
    """照範本「95表2收益附-成本法」與「94表2收益法」的格位公式逐格重算（獨立於系統程式）。"""
    M3, L4 = 33275, 1.03
    M5 = R(M3 * L4)
    M6 = R(M5 * 0.025)
    M7 = M5 + M6
    G10, G11, G12 = R(0.0136 * 0.4, 4), R(0.0289 * 0.4, 4), R(0 * 0.2, 4)
    I10 = R(G10 + G11 + G12, 4)
    G15 = R(I10 * 0.5 * 2.8, 4)
    L8, L9, L10, L14 = 0.045, 0.045, 0.01, 0.12
    J11, J13, J15 = L8 + L9 + L10, 1 + G15, 1 + L14
    M8, M9, M10 = (R(M7 * L * J13 * J15 / (1 - J11 * J13 * J15)) for L in (L8, L9, L10))
    M11 = M7 + M8 + M9 + M10
    M12 = R(M11 * G15)
    M14 = R((M11 + M12) * L14)
    M16 = M11 + M12 + M14
    H19, H18, D18 = 0.1, 50, 15
    H20 = (1 - H19) / H18 * D18 * M16
    M18 = M16 - H20
    C3, E3 = 457.4, 61
    P3, T3 = C3 * M16, C3 * M18
    F24, F25, F26 = R(330000 / 524), R(400000 / 613), R(61500 / 100)
    R24 = R(F24 * (1 + 0) * (1 + 0.025) * (1 + 0) * (1 - 0.02))
    R25 = R(F25 * (1 - 0.05) * (1 + 0.03) * (1 + 0) * (1 + 0))
    R26 = R(F26 * (1 + 0.02) * (1 + 0.05) * (1 + 0) * (1 + 0.02))
    U24 = R(R24 * 0.5 + R25 * 0.3 + R26 * 0.2)
    F5 = R(U24 * 12 * C3)
    F6 = R(U24 * C3 * 3)
    F7 = R(F6 * 0.0136)
    F8 = R(F5 + F7 + 0)
    K9 = R(F8 * (1 - 1.2 / 12))
    F12, F13 = F8 * 0.01, T3 * 0.00055
    R11 = R(P3 * 0.15 * 1 / 20 * (20 * 2) / 50)
    K14 = R(196387 + 135341 + F12 + F13 + 41623 + R11 + 0)
    F15 = K9 - K14
    R13 = R(((1 - H19) / H18) / (1 - ((1 - H19) / H18 * D18)), 4)
    F17 = R(T3 * (0.035 + R13))
    R18 = F15 - F17 - 0
    F20 = R(R18 / 0.025)
    F21 = R(F20 / E3)
    F22 = R(F21 * 0.90 / 0.95)
    return {"M5": M5, "M16": M16, "M18": M18, "U24": U24, "F5": F5, "F8": F8, "K9": K9, "R11": R11, "K14": K14, "F15": F15, "R13": R13, "F17": F17,
            "R18": R18, "F20": F20, "F21": F21, "F22": F22}


def template_case():
    ex = [{"example_no": 4, "area_m2": 524, "total_rent": 330000, "situation_pct": 0, "date_pct": 2.5, "regional_pct": 0, "individual_pct": -2, "weight_pct": 50},
          {"example_no": 7, "area_m2": 613, "total_rent": 400000, "situation_pct": -5, "date_pct": 3, "regional_pct": 0, "individual_pct": 0, "weight_pct": 30},
          {"example_no": 8, "area_m2": 100, "total_rent": 61500, "situation_pct": 2, "date_pct": 5, "regional_pct": 0, "individual_pct": 2, "weight_pct": 20}]
    return {"case": {"case_no": "1040301-○○-○○○", "valuation_date": "1040301", "district": "新北市樹林區", "land_use": "住宅用地"},
            "sections": {}, "subject_parcel": {"parcel_id": "○○段○○地號", "area_m2": 61}, "comparables": [],
            "income": {"enabled": True, "mode": "building", "examples": ex,
                       "subject": {"income_area_m2": 457.4, "land_share_m2": 61, "total_floors": 16, "level": 8, "floor_util_avg": 0.90, "floor_util_level": 0.95,
                                   "building": {"structure": "鋼筋混凝土造", "btype": "住宅大樓", "unit_cost_m2": 33275, "adj_rate": 1.03, "construction_years": 2.8,
                                                "own_fund_rate_pct": 1.36, "loan_rate_pct": 2.89, "age_years": 15, "life": 50, "residual": 0.1, "reg_area_m2": 457.4, "calc_area_m2": 418}},
                       "params": {"deposit_rate_pct": 1.36, "idle_months": 1.2, "deposit_months": 3, "management_pct_of_gross": 1, "insurance_pct_of_building_cost": 0.055,
                                  "land_value_tax": 196387, "house_tax": 135341, "maintenance": 41623, "replacement": None, "cap_rate_building_pct": 3.5, "cap_rate_land_pct": 2.5,
                                  "cost_approach": {"design_pct": 2.5, "advertising_sales_pct": 4.5, "management_pct": 4.5, "tax_pct": 1.0, "developer_profit_pct": 12,
                                                    "own_fund_ratio": 0.4, "loan_ratio": 0.4, "presale_ratio": 0.2, "installment_factor": 0.5}}}}


def test_template_example_reproduced_cell_by_cell():
    ref = template_reference()
    data = template_case()
    data["income"]["params"]["replacement"] = ref["R11"]          # 範本重置提撥費用自訂式（重建成本×15%÷20 年×40÷50），以金額帶入
    out = compute_income(data)
    c = out["cost"]
    assert c["unit_cost_adj"] == ref["M5"] and c["rebuild_unit"] == ref["M16"] and abs(c["cost_unit"] - ref["M18"]) < 1e-6
    assert [r["trial_rent"] for r in out["examples"]] == [633, 639, 672] and out["est_monthly_rent"] == ref["U24"] == 643
    assert out["annual_rent"] == ref["F5"] and out["gross_income"] == ref["F8"] and out["egi"] == ref["K9"]
    assert out["total_expense"] == ref["K14"] and out["noi"] == ref["F15"]
    assert out["depreciation_rate"] == ref["R13"] == 0.0247 and out["building_noi"] == ref["F17"]
    assert out["land_noi"] == ref["R18"] and out["land_income_total"] == ref["F20"] and out["land_income_unit"] == ref["F21"]
    assert out["income_price"] == ref["F22"]
    assert out["complete"] and not [i for i in out["issues"] if "未計" in i]


def test_land_mode_only_land_expenses_and_defaults_from_public_series():
    data = {"case": {"case_no": "X", "valuation_date": "1110901", "district": "新北市樹林區", "land_use": "住宅用地"}, "sections": {},
            "subject_parcel": {"parcel_id": "樹德段1415地號", "area_m2": 100}, "comparables": [],
            "income": {"enabled": True, "examples": [{"example_no": 1, "area_m2": 50, "total_rent": 20000, "rent_date": "1110630", "date_pct": 0.54}],
                       "subject": {"announced_land_price": 40000}}}
    out = compute_income(data)
    assert out["mode"] == "land" and out["est_monthly_rent"] == 402 and out["examples"][0]["weight_pct"] == 100
    assert set(out["expenses"]) == {"land_value_tax", "management", "other"}               # 素地：地價稅、管理費（第五號公報 三(六)3(2)）
    assert out["expenses"]["land_value_tax"] == 40000 * 100 * 0.8 * 0.01
    assert out["deposit_rate_pct"] == 1.325 and out["land_cap_rate_pct"] == 2.325           # 111.09 五大銀行一年期定存 1.325% ＋ 溢酬 1%
    assert out["land_income_unit"] == out["income_price"] and out["income_price"] > 0
    assert any(s.get("check") for s in out["sources"].values())


def test_rates_and_rent_date_adjustment():
    assert deposit_rate_at("1110901")["pct"] == 1.325
    r = rent_date_adjustment("1110630", "1110901")
    assert r["pct"] == 0.54 and r["index_at_rent"] == 101.65 and r["index_at_valuation"] == 102.2


def test_search_rent_examples_land_mode_stages_and_flags():
    from app.market.lvr import adjacency
    from app.market.rent import search_rent_examples
    near = adjacency().get("樹林區", [])[0]

    def rec(i, district, date, note="", zone="住"):
        return {"id": f"R{i}", "district": district, "target": "土地", "date": date, "land_area": 100.0, "total_rent": 30000, "rent_ex_park": 30000,
                "unit_rent": 300.0, "zone": zone, "lots": [{"section": "某段", "zone": "都市：" + zone}], "note": note}
    rent = {"records": [rec(1, "樹林區", "1110630"), rec(2, near, "1110501"), rec(3, "樹林區", "1110401", note="親友間租賃"),
                        rec(4, "樹林區", "1101001"), rec(5, "樹林區", "1100101"), rec(6, "樹林區", "1110615", zone="工")], "seasons": ["111S3"]}
    data = {"case": {"valuation_date": "1110901", "district": "新北市樹林區", "land_use": "住宅用地"}, "subject_parcel": {}, "sections": {}}
    s = search_rent_examples(data, rent=rent)
    assert s["mode"] == "land" and [c["id"] for c in s["chosen"]] == ["R1", "R2", "R4"]
    assert next(c for c in s["candidates"] if c["id"] == "R3")["excluded"]
    assert [c["id"] for c in s["reference"]] == ["R5"] and all(c["id"] != "R6" for c in s["candidates"])


def test_land_price_decision_weights_and_rounding():
    d = land_price_decision(131529, 150000, {"comparison": 0.7, "income": 0.3}, "收益實例可信度較低")
    assert d["weighted"] == 137070.3 and d["land_price"] == 138000 and not d["issues"]     # 131,529×0.7＋150,000×0.3，逾 10 萬千位進位
    d0 = land_price_decision(131529, 150000, None, "")
    assert d0["land_price"] == 132000 and any("權重為 0" in i for i in d0["issues"]) and any("理由" in i for i in d0["issues"])
    assert land_price_decision(131529, None)["land_price"] == 132000
