"""
從內部 schema 的案件資料產出 表5（影響地價區域因素分析明細表）與 表4（比較法調查估價表）。

每一步計算的法源（完整對照見 docs/07_calculation_basis.md）：
  調整至估價基準日單價 = 土地正常單價 × (1 + 期日調整%)          查估辦法 §17；手冊 p.50 (四) 得以地價指數調整
  試算價格            = 調整後單價 × (1 + 區域總修正%) × (1 + 個別合計%)   查估辦法 §19 第1項第2款、第2、3項；乘法依手冊 p.100-101 範例驗證
                                                                  （15,200 × 1.0417 × 1.03 = 16,309）
  調整百分率絕對值加總 = |期日%| + |區域%| + Σ|個別各項%|            手冊 p.53 (十)
  相近程度與權重       = 依絕對值加總排名 3件 50/30/20、2件 70/30、1件 100  手冊 p.53 (十一)，引不動產估價技術規則 §27（權重仍須考量資料可信度 → 引擎值只是預設）
  比準地比較價格       = Σ(試算價格 × 權重)，四捨五入至個位數          手冊 p.53 (十二)
  比準地地價（尾數）   = 比較價格依單價區間無條件進位                  查估辦法 §21；手冊 p.10 六(六)
  宗地市價            = 比準地地價 × (1 + 個別因素總調整率)，再依 §21 進位   手冊 p.55 (五)(六)；範例 p.102
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .rules import GradeError, Rule, RuleSet, adjustment, grade, level_number


def _get(d: dict, dotted: str) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if cur is None:
            return None
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


# ------------------------------------------------------------------ 表5

@dataclass
class T5Row:
    rule_id: str
    item_no: int | None
    group: int
    name: str
    subject_level: str | None
    comparable_level: str | None
    subject_num: int | None
    comparable_num: int | None
    pct: float | None
    issues: list[str] = field(default_factory=list)


@dataclass
class Table5:
    subject_section: str
    comparable_section: str
    rows: list[T5Row]
    group_subtotals: dict[int, float]
    total_pct: float
    group_names: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["group_subtotals"] = {str(k): v for k, v in self.group_subtotals.items()}
        d["group_names"] = {str(k): v for k, v in self.group_names.items()}
        return d


class InputError(ValueError):
    """案件資料不足以核算（例如比較標的沒有正常單價）：對外回 422 中文訊息，不是 500。"""


def _grade_safe(rule: Rule, obs: Any, issues: list[str], who: str) -> str | None:
    try:
        return grade(rule, obs)
    except GradeError as e:
        issues.append(f"[{who}] {e}")
        return None


def build_table5(rs: RuleSet, subject_section: dict, comparable_section: dict, no_adjust: list[str] | None = None) -> Table5:
    """no_adjust：本案在表5 免修正的細項（rule id 或細項名）；等級照判、修正率填「-」不計入小計。
    例：決賽題目表5-1 備註「使用分區、建蔽率、容積率修正併同於比較法調查估價表宗地個別因素考量調整修正」。"""
    rows: list[T5Row] = []
    subtotals: dict[int, float] = {g: 0.0 for g in rs.groups}
    skip = set(no_adjust or [])
    for rule in rs.rules:
        issues: list[str] = []
        s_obs = _get(subject_section["survey"], rule.survey_field) if rule.survey_field else None
        c_obs = _get(comparable_section["survey"], rule.survey_field) if rule.survey_field else None
        s_lv = _grade_safe(rule, s_obs, issues, "比準地區段") if not rule.is_manual else None
        c_lv = _grade_safe(rule, c_obs, issues, "比較標的區段") if not rule.is_manual else None
        if rule.id in skip or rule.name in skip:
            issues.append("本案免修正（併同比較法調查估價表個別因素調整）")
            pct = None
        else:
            pct = adjustment(rule, s_lv, c_lv) if not rule.is_manual else 0.0
        if pct is not None:
            subtotals[rule.group] += pct
        rows.append(T5Row(rule.id, rule.item_no, rule.group, rule.name, s_lv, c_lv,
                          level_number(rule, s_lv), level_number(rule, c_lv), pct, issues))
    total = round(sum(subtotals.values()), 4)
    return Table5(subject_section["section_id"], comparable_section["section_id"], rows,
                  {g: round(v, 4) for g, v in subtotals.items()}, total, dict(rs.groups))


# ------------------------------------------------------------------ 價格鏈（純函式，法源見模組 docstring 與 docs/07）


def round_half_up(x: float, ndigits: int = 0) -> float:
    """四捨五入（不是 Python 預設的銀行家捨入）。"""
    q = Decimal(1).scaleb(-ndigits)
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def date_adjusted_price(normal_unit_price: float, date_pct: float) -> float:
    """調整至估價基準日單價。查估辦法 §17、手冊 p.50 (四)。"""
    return normal_unit_price * (1 + date_pct / 100)


def date_adjustment_from_index(index_at_valuation: float, index_at_transaction: float) -> float:
    """以地價指數計算期日調整率（%），填至 2 位小數。手冊 p.50 (四)、問答八 (p.78)。"""
    return round_half_up((index_at_valuation / index_at_transaction - 1) * 100, 2)


def trial_price(price_at_date: float, regional_pct: float, individual_pct: float) -> float:
    """試算價格 = 調整後單價 × (1+區域%) × (1+個別%)。查估辦法 §19；乘法形式依手冊 p.100-101 範例驗證。"""
    return price_at_date * (1 + regional_pct / 100) * (1 + individual_pct / 100)


def abs_sum(date_pct: float, regional_pct: float, individual_pcts: list[float]) -> float:
    """調整百分率絕對值加總。手冊 p.53 (十)：各項先取絕對值再加總。"""
    return round(abs(date_pct) + abs(regional_pct) + sum(abs(p) for p in individual_pcts), 4)


DEFAULT_WEIGHTS = {1: [100.0], 2: [70.0, 30.0], 3: [50.0, 30.0, 20.0]}
SIMILARITY_LABELS = {1: ["普通"], 2: ["較高", "普通"], 3: ["較高", "普通", "較低"]}


def default_similarity_and_weights(abs_sums: list[float]) -> list[tuple[str | None, float | None]]:
    """
    依絕對值加總排名給相近程度與預設權重。手冊 p.53 (十一)（引不動產估價技術規則 §27）：
    3 件 → 較高/普通/較低 50/30/20；2 件 → 70/30；1 件 → 普通 100。
    §27 另要求考量蒐集資料可信度，所以這只是預設，估價師可改，審查時不同只給 warn。
    件數不在 1~3 → 回 None（查估辦法 §19 第1項第1款：選擇一至三件）。
    """
    n = len(abs_sums)
    if n not in DEFAULT_WEIGHTS:
        return [(None, None)] * n
    order = sorted(range(n), key=lambda i: abs_sums[i])
    out: list[tuple[str | None, float | None]] = [(None, None)] * n
    for rank, i in enumerate(order):
        out[i] = (SIMILARITY_LABELS[n][rank], DEFAULT_WEIGHTS[n][rank])
    return out


def comparison_price(trials: list[float], weights_pct: list[float]) -> float:
    """比準地比較價格 = Σ 試算價格 × 權重，四捨五入至個位數。手冊 p.53 (十二)。"""
    return round_half_up(sum(t * w / 100 for t, w in zip(trials, weights_pct)), 0)


def round_land_price(price: float) -> int:
    """
    比準地地價／宗地市價尾數。查估辦法 §21、手冊 p.10 六(六)：
    ≤100 元 → 個位；逾 100 至 1,000 → 十位；逾 1,000 至 10 萬 → 百位；逾 10 萬 → 千位；皆無條件進位。
    """
    d = Decimal(str(price))
    if d <= 100:
        unit = 1
    elif d <= 1000:
        unit = 10
    elif d <= 100000:
        unit = 100
    else:
        unit = 1000
    return math.ceil(d / unit) * unit


def parcel_market_price(subject_land_price: float, total_individual_pct: float) -> tuple[float, int]:
    """
    宗地市價：以比準地地價（已依 §21 進位）× (1 + 個別因素總調整率)，再依 §21 進位。
    手冊 p.55 (五)(六)、範例 p.102：15,900 × (1−5%) = 15,105 → 15,200。回傳 (試算價格, 宗地市價)。
    """
    trial = subject_land_price * (1 + total_individual_pct / 100)
    return trial, round_land_price(trial)


# ------------------------------------------------------------------ 表4

@dataclass
class T4Row:
    item_no: int
    group: int
    name: str
    subject_value: Any
    comparable_value: Any
    subject_level: str | None
    comparable_level: str | None
    pct: float | None           # None = 免修正（表上填「-」）
    issues: list[str] = field(default_factory=list)


@dataclass
class T4Comparable:
    comp_no: int
    parcel_id: str
    section_id: str
    normal_unit_price: float
    date_adjustment_pct: float
    price_at_valuation_date: float
    regional_adjustment_pct: float
    rows: list[T4Row]
    individual_total_pct: float
    abs_sum_pct: float
    similarity: str | None
    weight_pct: float | None
    trial_price: float


@dataclass
class Table4:
    case_no: str
    subject_parcel_id: str
    comparables: list[T4Comparable]
    subject_comparison_price: float | None     # 表4 比準地比較價格（四捨五入至個位，手冊 p.53 (十二)）
    subject_land_price: int | None = None      # 比準地地價：比較價格依查估辦法 §21 尾數進位（僅比較法；§19 第4項若有收益價格須綜合評估）
    price_basis: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _display_value(rule: Rule, obs: Any) -> Any:
    """給表格顯示用：設施帶名稱與距離。"""
    if isinstance(obs, dict):
        if "name" in obs and ("distance_m" in obs or "width_m" in obs):
            return obs
        return obs.get("value", obs)
    if isinstance(obs, list):
        return obs
    return obs


def _parcel_obs(rule: Rule, parcel: dict) -> Any:
    f = rule.parcel_field
    if f is None:
        return None
    if f == "front_road_width_m":
        return _get(parcel, "front_road.width_m")
    return parcel.get(f)


def build_table4(rs: RuleSet, case: dict, subject: dict, comparables: list[dict],
                 regional_totals: dict[int, float]) -> Table4:
    """
    regional_totals: {comp_no: 區域因素總修正數%}，來自 build_table5。
    每個 comparable 需有 normal_unit_price, date_adjustment.pct（或 index_at_*）, 個別因素欄位。
    """
    out: list[T4Comparable] = []
    for comp in comparables:
        rows: list[T4Row] = []
        ind_total = 0.0
        abs_sum_items = 0.0
        for rule in sorted([r for r in rs.rules if r.item_no], key=lambda r: r.item_no):
            issues: list[str] = []
            s_obs = _parcel_obs(rule, subject)
            c_obs = _parcel_obs(rule, comp)
            if rule.is_manual or (s_obs is None and c_obs is None):
                rows.append(T4Row(rule.item_no, rule.group, rule.name, s_obs, c_obs, None, None, None,
                                  [] if rule.is_manual else ["雙方皆無資料，視為免修正「-」"]))
                continue
            s_lv = _grade_safe(rule, s_obs, issues, "比準地")
            c_lv = _grade_safe(rule, c_obs, issues, "比較標的")
            pct = adjustment(rule, s_lv, c_lv)
            if pct is not None:
                ind_total += pct
                abs_sum_items += abs(pct)
            rows.append(T4Row(rule.item_no, rule.group, rule.name, _display_value(rule, s_obs),
                              _display_value(rule, c_obs), s_lv, c_lv, pct, issues))

        da = comp.get("date_adjustment") or {}
        if "pct" in da and da["pct"] is not None:
            date_pct = float(da["pct"])          # 估價師填值為準（手冊 p.50 (四)：填寫調整百分率）
        elif da.get("index_at_valuation") and da.get("index_at_transaction"):
            date_pct = date_adjustment_from_index(da["index_at_valuation"], da["index_at_transaction"])
        else:
            date_pct = 0.0
        regional_pct = float(regional_totals.get(comp["comp_no"], 0.0))
        if comp.get("normal_unit_price") in (None, ""):
            raise InputError(f"比較標的{comp.get('comp_no')} 缺少土地正常單價，無法計算試算價格；請填寫或先移除該比較標的")
        try:
            unit = float(comp["normal_unit_price"])
        except (TypeError, ValueError):
            raise InputError(f"比較標的{comp.get('comp_no')} 土地正常單價「{comp['normal_unit_price']}」不是數字") from None
        price_at_date = date_adjusted_price(unit, date_pct)
        trial = trial_price(price_at_date, regional_pct, ind_total)
        abs_total = abs_sum(date_pct, regional_pct, [abs_sum_items])
        out.append(T4Comparable(
            comp_no=comp["comp_no"], parcel_id=comp["parcel_id"], section_id=comp["section_id"],
            normal_unit_price=unit, date_adjustment_pct=date_pct,
            price_at_valuation_date=price_at_date, regional_adjustment_pct=regional_pct, rows=rows,
            individual_total_pct=round(ind_total, 4), abs_sum_pct=abs_total,
            similarity=None, weight_pct=comp.get("weight_pct"), trial_price=trial,
        ))

    # 相近程度與預設權重（手冊 p.53 (十一)、技術規則 §27）；估價師填的權重要全部有值且合計 100% 才採用，否則用預設並記錄
    weights_note = None
    given = [c.weight_pct for c in out]
    if out and all(w is not None for w in given):
        try:
            total = sum(float(w) for w in given)
        except (TypeError, ValueError):
            total = None
        if total is None or abs(total - 100.0) > 0.01:
            weights_note = f"填載權重合計 {total if total is None else round(total, 2)}% ≠ 100%，本表改用預設權重計算（審查另列不符）"
            for c in out:
                c.weight_pct = None
    for c, (sim, w) in zip(out, default_similarity_and_weights([c.abs_sum_pct for c in out])):
        c.similarity = sim
        if c.weight_pct is None:
            c.weight_pct = w
        else:
            c.weight_pct = float(c.weight_pct)

    if out and all(c.weight_pct is not None for c in out):
        subject_price: float | None = comparison_price([c.trial_price for c in out], [c.weight_pct for c in out])
        land_price: int | None = round_land_price(subject_price)
    else:
        subject_price, land_price = None, None
    basis = {
        "trial_price": "調整後單價×(1+區域%)×(1+個別%)：查估辦法§19；手冊p.100-101範例",
        "subject_comparison_price": "Σ試算×權重，四捨五入至個位：手冊p.53(十二)",
        "subject_land_price": "比較價格依查估辦法§21尾數無條件進位（僅比較法）",
        "weights": "預設依絕對值加總排名：手冊p.53(十一)、技術規則§27" + (f"；{weights_note}" if weights_note else ""),
    }
    return Table4(case["case_no"], subject["parcel_id"], out, subject_price, land_price, basis)


# ------------------------------------------------------------------ 一鍵跑整案

def run_case(regional_rs: RuleSet, individual_rs: RuleSet, data: dict) -> dict:
    """data = fixtures/sample_case_*.json 的結構（不含 expected）。回傳 {table5: {comp_no: Table5}, table4: Table4}。"""
    sections = data["sections"]
    subject = data["subject_parcel"]
    t5: dict[int, Table5] = {}
    totals: dict[int, float] = {}
    for comp in data["comparables"]:
        t = build_table5(regional_rs, sections[subject["section_id"]], sections[comp["section_id"]], no_adjust=data["case"].get("regional_no_adjust"))
        t5[comp["comp_no"]] = t
        totals[comp["comp_no"]] = t.total_pct
    t4 = build_table4(individual_rs, data["case"], subject, data["comparables"], totals)
    return {"table5": t5, "table4": t4}
