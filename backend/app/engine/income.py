"""
收益法（直接資本化法）→ 表2 收益法調查估價表（含附表─成本法調查估價表）與表14 比準地地價估計表。

逐格對應地政局範本「94表2收益法」「95表2收益附-成本法」「114表14比準地地價估計表」的公式（backend/app/templates/official/表4比較法調查估價表.xlsx），
每個數字都能對回條文：
- 查估辦法 §14：以收益實例查估比準地收益價格，依不動產估價技術規則第三章第二節（§28～§47）辦理；§15 建物成本價格依第三章第三節（成本法）。
- 查估辦法 §17：收益實例租金調整至估價基準日（房租指數，app/market/rates.py）。
- 手冊 p.37～41 收益法調查估價表填寫說明；p.8 五(二)3、4 比準地地價由比較價格與收益價格綜合評估並敘明理由（表14）。
- 技術規則 §30 收益價格＝淨收益÷收益資本化率；§44 土地收益價格＝（房地淨收益－建物淨收益）÷土地收益資本化率；§41 折舊提存率（等速）；§43 收益資本化率；§100 樓層別效用比。
- 全聯會第五號公報：總收入、閒置損失、總費用各項比例區間（rules/income_params.json）。
比準地為素地（mode="land"）時只用素地收益實例，建物欄位免填，總費用只計地價稅與管理費（手冊 p.38 (3)、第五號公報 三(六)3(2)）。
所有系統預設參數都記在 sources，check=True 者需估價師確認；本模組只算數，不做判斷。
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.engine.tables import default_similarity_and_weights, round_half_up, round_land_price

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"
PING_M2 = 3.305785


def _r(x: float) -> int:
    """範本 ROUND(x,0)：四捨五入至整數。"""
    return int(round_half_up(x, 0))


def _r4(x: float) -> float:
    return float(round_half_up(x, 4))


@lru_cache(maxsize=1)
def load_params() -> dict[str, Any]:
    p = RULES_DIR / "income_params.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class _P:
    """參數：案件 data.income.params 覆寫 > rules/income_params.json 預設；每次取值都記下來源。"""

    def __init__(self, override: dict | None):
        self.o = override or {}
        self.d = load_params()
        self.sources: dict[str, dict[str, Any]] = {}

    def get(self, key: str, *, group: str | None = None) -> float | None:
        ov = (self.o.get(group) or {}) if group else self.o
        if _num(ov.get(key)) is not None:
            v = float(ov[key])
            self.sources[f"{group + '.' if group else ''}{key}"] = {"value": v, "source": "估價師填載", "check": False}
            return v
        spec = ((self.d.get(group) or {}) if group else self.d).get(key)
        if isinstance(spec, dict) and _num(spec.get("value")) is not None:
            v = float(spec["value"])
            self.sources[f"{group + '.' if group else ''}{key}"] = {"value": v, "source": spec.get("source", ""), "check": bool(spec.get("check")), "range": spec.get("range")}
            return v
        return None

    def note(self, key: str, value: Any, source: str, check: bool = False) -> None:
        self.sources[key] = {"value": value, "source": source, "check": check}


# ------------------------------------------------------------------ 推估月租金（表2 第 23～26 列）

def rent_rows(examples: list[dict]) -> tuple[list[dict[str, Any]], int | None, list[str]]:
    """收益實例 → 試算租金、權重、推估月租金。範本 F=ROUND(E/D)、R=ROUND(F×(1+H)(1+J)(1+K)(1+M))、U=ROUND(ΣR×T)。"""
    issues: list[str] = []
    rows: list[dict[str, Any]] = []
    for ex in examples or []:
        area, total = _num(ex.get("area_m2")), _num(ex.get("total_rent"))
        unit = _r(total / area) if area and total else (_r(float(ex["unit_rent"])) if _num(ex.get("unit_rent")) is not None else None)
        if unit is None:
            issues.append(f"收益實例 {ex.get('example_no')} 缺月租金或面積，未計入")
            continue
        adj = {k: float(ex.get(k) or 0.0) for k in ("situation_pct", "date_pct", "regional_pct", "individual_pct")}
        trial = _r(unit * (1 + adj["situation_pct"] / 100) * (1 + adj["date_pct"] / 100) * (1 + adj["regional_pct"] / 100) * (1 + adj["individual_pct"] / 100))
        rows.append({"example_no": ex.get("example_no"), "lvr_id": ex.get("lvr_id"), "section_id": ex.get("section_id") or "", "area_m2": area, "total_rent": total,
                     "unit_rent": unit, "rent_type": ex.get("rent_type") or "登錄租金", "rent_date": ex.get("rent_date"), **adj,
                     "abs_sum_pct": round(sum(abs(v) for v in adj.values()), 2), "n_adjusted": sum(1 for v in adj.values() if abs(v) > 1e-9),
                     "trial_rent": trial, "weight_pct": _num(ex.get("weight_pct")), "flags": ex.get("flags") or [], "note": ex.get("note") or ""})
    if not rows:
        return rows, None, issues or ["未選收益實例"]
    given = [r["weight_pct"] for r in rows]
    if not (all(w is not None for w in given) and abs(sum(given) - 100) < 0.01):
        if any(w is not None for w in given):
            issues.append(f"收益實例權重合計 {round(sum(w or 0 for w in given), 2)}% ≠ 100%，改用預設權重（依調整率絕對值加總排名，手冊 p.39 (15)）")
        for r, (sim, w) in zip(rows, default_similarity_and_weights([r["abs_sum_pct"] for r in rows])):
            r["similarity"], r["weight_pct"] = sim, w
    if any(r["weight_pct"] is None for r in rows):
        return rows, None, issues + ["收益實例件數不在 1～3 件，無預設權重，請填權重（手冊 p.37 (五)1(1) 以 3 件為原則）"]
    est = _r(sum(r["trial_rent"] * r["weight_pct"] / 100 for r in rows))
    return rows, est, issues


# ------------------------------------------------------------------ 附表─成本法調查估價表

def cost_approach(building: dict, *, valuation_date: str, district: str, p: _P, deposit_pct: float | None, mortgage_pct: float | None) -> dict[str, Any]:
    """範本附表 M3～M20：營造施工費→規劃設計費→廣告銷售、管理、稅捐（總成本比例，含資本利息與利潤回推）→資本利息→開發利潤→重建成本→定額法折舊→建物成本價格。"""
    from app.market.building_cost import (
        age_years,
        cci_factor,
        cn_to_int,
        district_price_level,
        residual_rate,
        structure_of,
        unit_cost_per_ping,
        use_class,
        useful_life,
    )
    issues: list[str] = []
    structure = building.get("structure") or structure_of(building.get("material") or "") or ""
    use = use_class(building.get("btype") or building.get("use") or "")
    floors_above = int(_num(building.get("floors_above")) or cn_to_int(str(building.get("floors") or "")) or 0) or None
    if _num(building.get("unit_cost_m2")) is not None:
        m3 = _r(float(building["unit_cost_m2"]))
        p.note("cost.unit_cost_m2", m3, "估價師填載")
    else:
        level = None
        if use == "house" and structure in ("鋼筋混凝土造", "預鑄混凝土造", "鋼骨造", "鋼骨鋼筋混凝土造"):
            from app.engine.verify import _ord, _roc
            from app.market.lvr import load_lvr
            vd = _roc(valuation_date)
            level = district_price_level(load_lvr().get("records", []), district, before_ord=_ord(vd) if vd else None).get("level")
        uc = unit_cost_per_ping(structure, use, floors_above, level) if structure else None
        if uc is None:
            issues.append("營造施工費標準單價無法由第四號公報推定（構造、樓層或當地房價水準不足），請填載")
            m3 = 0
        else:
            m3 = _r(uc["value"] / PING_M2)
            p.note("cost.unit_cost_m2", m3, f"全聯會第四號公報{uc['table']}：{uc['row']}，{uc['column']}；{uc['note']}（每坪 ÷ 3.305785 m²）", True)
    if _num(building.get("adj_rate")) is not None:
        l4 = float(building["adj_rate"])
        p.note("cost.adj_rate", l4, "估價師填載")
    else:
        cf = cci_factor(valuation_date)
        l4 = round(cf["factor"], 4) if cf else 1.0
        p.note("cost.adj_rate", l4, (cf["note"] + "（第四號公報說明事項第 14 點）") if cf else "無營造工程物價指數，調整單價率取 1", not cf)
    design = (p.get("design_pct", group="cost_approach") or 0) / 100
    adv = (p.get("advertising_sales_pct", group="cost_approach") or 0) / 100
    mgmt = (p.get("management_pct", group="cost_approach") or 0) / 100
    tax = (p.get("tax_pct", group="cost_approach") or 0) / 100
    profit = (p.get("developer_profit_pct", group="cost_approach") or 0) / 100
    own_r, loan_r, pre_r = (p.get(k, group="cost_approach") or 0 for k in ("own_fund_ratio", "loan_ratio", "presale_ratio"))
    inst = p.get("installment_factor", group="cost_approach") or 0
    years = _num(building.get("construction_years")) or p.get("construction_years", group="cost_approach") or 0
    own_rate = (_num(building.get("own_fund_rate_pct")) if _num(building.get("own_fund_rate_pct")) is not None else (deposit_pct or 0)) / 100
    loan_rate = (_num(building.get("loan_rate_pct")) if _num(building.get("loan_rate_pct")) is not None else (mortgage_pct or 0)) / 100
    m5 = _r(m3 * l4)
    m6 = _r(m5 * design)
    m7 = m5 + m6
    g10, g11, g12 = _r4(own_rate * own_r), _r4(loan_rate * loan_r), _r4(0.0 * pre_r)
    i10 = _r4(g10 + g11 + g12)
    g15 = _r4(i10 * inst * years)
    j11, j13, j15 = adv + mgmt + tax, 1 + g15, 1 + profit
    den = 1 - j11 * j13 * j15
    m8, m9, m10 = (_r(m7 * rate * j13 * j15 / den) for rate in (adv, mgmt, tax))
    m11 = m7 + m8 + m9 + m10
    m12 = _r(m11 * g15)
    m13 = m11 + m12
    m14 = _r(m13 * profit)
    m16 = m11 + m12 + m14
    life = _num(building.get("life")) or useful_life(structure, use) or 0
    residual = _num(building.get("residual")) if _num(building.get("residual")) is not None else (residual_rate(structure) or 0.0)
    if _num(building.get("age_years")) is not None:
        age = float(building["age_years"])
    else:
        a = age_years(building.get("completed") or "", valuation_date)
        age = float(_r(a)) if a is not None else 0.0
        if a is None:
            issues.append("建築完成年月缺漏，已經歷年數以 0 計，請填載")
    age_c = min(age, life) if life else age
    h20 = (1 - residual) / life * age_c * m16 if life else 0.0
    m18 = m16 - h20
    calc_area = _num(building.get("calc_area_m2")) or _num(building.get("reg_area_m2")) or _num(building.get("area_m2")) or 0.0
    return {"structure": structure, "use": use, "floors_above": floors_above, "floors_below": _num(building.get("floors_below")), "reg_area_m2": _num(building.get("reg_area_m2")),
            "calc_area_m2": calc_area, "level": building.get("level"), "completed": building.get("completed"),
            "unit_cost_m2": m3, "adj_rate": l4, "unit_cost_adj": m5, "design_rate": design, "design": m6, "cum1": m7,
            "own_rate": own_rate, "own_ratio": own_r, "loan_rate": loan_rate, "loan_ratio": loan_r, "presale_ratio": pre_r, "w_own": g10, "w_loan": g11, "w_presale": g12,
            "avg_rate": i10, "installment": inst, "years": years, "interest_rate": g15, "adv_rate": adv, "mgmt_rate": mgmt, "tax_rate": tax,
            "advertising": m8, "management": m9, "tax": m10, "cum2": m11, "interest": m12, "cum3": m13, "profit_rate": profit, "profit": m14,
            "rebuild_unit": m16, "age": age, "remaining": (life - age_c) if life else None, "life": life, "residual": residual,
            "accum_dep_unit": h20, "cost_unit": m18, "cost_total_calc": _r(m18 * calc_area), "issues": issues,
            "basis": "技術規則 §48～§67；全聯會第四號公報；手冊 p.41 (六)7；範本附表 M5＝ROUND(M3×L4)、M8～M10＝ROUND(M7×費率×(1+綜合利率)×(1+利潤率)÷(1−Σ費率×(1+綜合利率)×(1+利潤率)))、M16＝M11+M12+M14、H20＝(1−殘價率)÷耐用年數×已經歷年數×M16"}


# ------------------------------------------------------------------ 表2 主體

def compute_income(data: dict) -> dict[str, Any] | None:
    """data.income 未啟用 → None。回傳表2 每一格的值（JSON 可序列化）＋ sources（參數來源）＋ issues（需人工處理）。"""
    inc = data.get("income") or {}
    if not inc.get("enabled"):
        return None
    from app.market.rates import deposit_rate_at, mortgage_rate_at
    from app.market.rent import income_mode
    case = data.get("case") or {}
    vdate = case.get("valuation_date") or ""
    district = (case.get("district") or "").replace("新北市", "")
    mode = income_mode(data)
    p = _P(inc.get("params"))
    subj = inc.get("subject") or {}
    parcel = data.get("subject_parcel") or {}
    issues: list[str] = []

    rows, est, rissues = rent_rows(inc.get("examples") or [])
    issues += rissues
    land_area = _num(subj.get("land_share_m2")) or _num(parcel.get("area_m2"))
    income_area = _num(subj.get("income_area_m2")) or (land_area if mode == "land" else _num((subj.get("building") or {}).get("reg_area_m2")))
    if not income_area:
        issues.append("收益面積缺漏（素地為比準地面積；房地為建物登記面積），請填載")
    if not land_area:
        issues.append("土地持分面積缺漏，請填載")
    dep = deposit_rate_at(vdate)
    deposit_pct = _num((inc.get("params") or {}).get("deposit_rate_pct"))
    if deposit_pct is None:
        deposit_pct = dep["pct"]
        p.note("deposit_rate_pct", deposit_pct, dep["note"] + "（手冊 p.39 表2「一年期定存利率」）", deposit_pct is None)
    else:
        p.note("deposit_rate_pct", deposit_pct, "估價師填載")
    mort = mortgage_rate_at(vdate)

    months = p.get("deposit_months") or 0
    idle = p.get("idle_months") or 0
    other_income = _num((inc.get("params") or {}).get("other_income")) or 0.0
    out: dict[str, Any] = {"mode": mode, "valuation_date": vdate, "examples": rows, "est_monthly_rent": est, "income_area_m2": income_area, "land_share_m2": land_area,
                           "total_floors": subj.get("total_floors"), "level": subj.get("level"), "deposit_months": months, "idle_months": idle,
                           "deposit_rate_pct": deposit_pct, "other_income": other_income}
    if est is None or not income_area or not land_area:
        out.update(issues=issues, sources=p.sources, complete=False)
        return out
    annual = _r(est * 12 * income_area)
    deposit = _r(est * income_area * months)
    deposit_income = _r(deposit * (deposit_pct or 0) / 100)
    gross = _r(annual + deposit_income + other_income)
    egi = _r(gross * (1 - idle / 12))

    # 附表成本法（房地）
    cost = None
    rebuild_total = cost_total = construction_total = 0.0
    if mode == "building":
        b = subj.get("building") or {}
        cost = cost_approach(b, valuation_date=vdate, district=district, p=p, deposit_pct=deposit_pct, mortgage_pct=mort["pct"])
        issues += cost["issues"]
        rebuild_total = income_area * cost["rebuild_unit"]        # 範本 P3＝C3×附表 M16
        cost_total = income_area * cost["cost_unit"]              # 範本 T3＝C3×附表 M18
        construction_total = income_area * cost["unit_cost_adj"]  # 營造施工費（第五號公報維修費、重置提撥費之基數）

    # 總費用（第五號公報 三(四)；手冊 p.40～41 (六)）
    ov = inc.get("params") or {}
    exp: dict[str, float] = {}
    if _num(ov.get("land_value_tax")) is not None:
        exp["land_value_tax"] = float(ov["land_value_tax"])
        p.note("land_value_tax", exp["land_value_tax"], "估價師填載（稅單或洽稅捐單位，手冊 p.40 (六)1）")
    else:
        alp = _num(subj.get("announced_land_price"))
        rate = p.get("land_value_tax_rate_pct") or 0
        ratio = p.get("declared_to_announced_ratio") or 0
        if alp:
            exp["land_value_tax"] = _r(alp * land_area * ratio * rate / 100)
            p.note("land_value_tax", exp["land_value_tax"], f"公告地價 {alp:,.0f} 元/m² × 土地面積 {land_area} m² × {ratio:.0%} × 稅率 {rate}%", True)
        else:
            exp["land_value_tax"] = 0.0
            issues.append("地價稅未計：請填比準地公告地價（元/m²）或地價稅額（手冊 p.40 (六)1；第五號公報 三(四)1）")
    exp["management"] = gross * (p.get("management_pct_of_gross") or 0) / 100            # 範本 F12＝F8×1%（不取整，總費用合計再四捨五入）
    if mode == "building":
        if _num(ov.get("house_tax")) is not None:
            exp["house_tax"] = float(ov["house_tax"])
        else:
            exp["house_tax"] = 0.0
            issues.append("房屋稅未計：請填房屋稅額（稅單或房屋評定現值 × 稅率，第五號公報 三(四)3）")
        exp["insurance"] = cost_total * (p.get("insurance_pct_of_building_cost") or 0) / 100   # 範本 F13＝T3×費率
        exp["maintenance"] = float(ov["maintenance"]) if _num(ov.get("maintenance")) is not None else _r(construction_total * (p.get("maintenance_pct_of_construction") or 0) / 100)
        exp["replacement"] = float(ov["replacement"]) if _num(ov.get("replacement")) is not None else _r(construction_total * (p.get("replacement_pct_of_construction") or 0) / 100)
    exp["other"] = _num(ov.get("other_expense")) or 0.0
    total_exp = _r(sum(exp.values()))
    noi = egi - total_exp

    # 收益資本化率（技術規則 §43；預設風險溢酬法：一年期定存＋溢酬）
    def cap(key: str, prem_key: str, label: str) -> float | None:
        if _num(ov.get(key)) is not None:
            v = float(ov[key])
            p.note(key, v, "估價師填載（技術規則 §43，決定理由應敘明）")
            return v
        prem = p.get(prem_key) or 0
        if deposit_pct is None:
            issues.append(f"{label}收益資本化率無法推定（無定存利率），請填載")
            return None
        v = round(deposit_pct + prem, 4)
        p.note(key, v, f"風險溢酬法（技術規則 §43 第1款）：一年期定存 {deposit_pct}% ＋ 溢酬 {prem}%（系統預設，需估價師就流通性、風險性、增值性、管理難易決定）", True)
        return v
    land_cap = cap("cap_rate_land_pct", "cap_rate_premium_land_pct", "土地")
    out.update(annual_rent=annual, deposit=deposit, deposit_income=deposit_income, gross_income=gross, egi=egi, expenses=exp, total_expense=total_exp, noi=noi)
    other_ded = _num(ov.get("other_deduction")) or 0.0
    if mode == "building":
        bld_cap = cap("cap_rate_building_pct", "cap_rate_premium_building_pct", "建物")
        s, n_life, n_age = cost["residual"], cost["life"], cost["age"]
        dep_rate = _r4(((1 - s) / n_life) / (1 - ((1 - s) / n_life * n_age))) if n_life and (1 - ((1 - s) / n_life * n_age)) > 0 else 0.0
        building_noi = _r(cost_total * ((bld_cap or 0) / 100 + dep_rate))            # 範本 F17＝ROUND(T3×(F16+R13))；第五號公報 二(二)1(3)B
        land_noi = noi - building_noi - other_ded
        out.update(cost=cost, rebuild_total=rebuild_total, cost_total=cost_total, construction_total=construction_total, building_cap_rate_pct=bld_cap,
                   depreciation_rate=dep_rate, building_noi=building_noi)
        if bld_cap is not None and land_cap is not None and bld_cap <= land_cap:
            issues.append(f"建物收益資本化率 {bld_cap}% 未高於土地收益資本化率 {land_cap}%（手冊 p.41 (七)2：建物風險高於土地，宜高於）")
    else:
        land_noi = noi - other_ded
    out.update(other_deduction=other_ded, land_noi=land_noi, land_cap_rate_pct=land_cap)
    if land_cap:
        land_total = _r(land_noi / (land_cap / 100))
        land_unit = _r(land_total / land_area)
        fa, fl = _num(subj.get("floor_util_avg")), _num(subj.get("floor_util_level"))
        if mode == "building" and fa and fl:
            price = _r(land_unit * fa / fl)                                          # 技術規則 §100；範本 F22
            p.note("floor_util", f"{fa}/{fl}", "估價師填載（技術規則 §98、§100 樓層別效用比）")
        else:
            price = land_unit
            if mode == "building":
                issues.append("樓層別效用比未填：基地收益單價未作樓層別調整（技術規則 §100；手冊 p.41 (七)1）")
        out.update(land_income_total=land_total, land_income_unit=land_unit, floor_util_avg=fa, floor_util_level=fl, income_price=price, complete=True)
    else:
        out.update(complete=False)
    if land_noi <= 0:
        issues.append("土地淨收益小於等於 0，收益價格不具參考性，請檢查租金與費用")
    out.update(issues=issues, sources=p.sources,
               basis={"formula": "收益價格＝淨收益÷收益資本化率（技術規則 §30）；土地收益價格＝（房地淨收益－建物淨收益）÷土地收益資本化率（§44）；建物淨收益＝建物成本價格×（建物收益資本化率＋折舊提存率）（第五號公報 二(二)1(3)B）；折舊提存率＝折舊率÷（1－累積折舊率）（§41 等速）",
                      "rent": "試算租金＝月租金×(1+情況)×(1+價格日期)×(1+區域)×(1+個別)，推估月租金＝Σ試算×權重（手冊 p.38～39 (8)～(15)）",
                      "income": "年租金＝月租金×12×面積；押租金運用收益＝押租金×一年期定存；有效總收入＝總收入×(1－閒置月數÷12)（手冊 p.39；第五號公報 三(一)～(三)）"})
    return out


# ------------------------------------------------------------------ 表14 比準地地價估計表

def land_price_decision(comparison_price: float | None, income_price: float | None, weights: dict | None = None, reason: str | None = None) -> dict[str, Any]:
    """比準地地價＝比較價格×權重＋收益價格×權重，依查估辦法 §21 尾數無條件進位（範本表14 J 欄）。沒有收益價格 → 比較價格權重 1。"""
    w = weights or {}
    issues: list[str] = []
    wc = _num(w.get("comparison"))
    wi = _num(w.get("income"))
    if income_price is None:
        wc, wi = 1.0, 0.0
    else:
        wc = 1.0 if wc is None else wc
        wi = 0.0 if wi is None else wi
        if abs(wc + wi - 1) > 1e-6:
            issues.append(f"比較價格與收益價格權重合計 {wc + wi:g} ≠ 1，改以比較價格權重 1 計算")
            wc, wi = 1.0, 0.0
        if wi == 0:
            issues.append("有收益價格而權重為 0：比準地地價僅採比較價格，請於決定理由敘明（手冊 p.8 五(二)3、4）")
        if not (reason or "").strip():
            issues.append("比準地地價決定理由未填（手冊 p.8 五(二)4：應詳予敘明於比準地地價估計表）")
    if comparison_price is None:
        return {"comparison_price": None, "comparison_weight": wc, "income_price": income_price, "income_weight": wi, "land_price": None, "reason": reason or "", "issues": issues + ["無比較價格"]}
    value = comparison_price * wc + (income_price or 0) * wi
    return {"comparison_price": comparison_price, "comparison_weight": wc, "income_price": income_price, "income_weight": wi, "weighted": round(value, 2),
            "land_price": round_land_price(value) if value > 0 else None, "reason": reason or "", "issues": issues,
            "basis": "比準地地價＝比較價格×權重＋收益價格×權重，依查估辦法 §21 尾數無條件進位（表14；手冊 p.8 五(二)3、4）"}


__all__ = ["compute_income", "cost_approach", "land_price_decision", "load_params", "math", "rent_rows"]
