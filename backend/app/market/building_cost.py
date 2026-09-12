"""
建物成本價格（成本法）推定：實價登錄含建物實例 → 依估價師公會第四號公報（rules/building_cost.json）算重建成本與折舊。

法源：查估辦法 §13 第3、4款（土地價格＝房地價格－建物成本價格）；手冊 p.6 (三)、p.34–35 (六)(七)；
     不動產估價技術規則 §54、§56（間接法單位面積比較法；營造或施工費標準表由全聯會公告）、§65（經濟耐用年數）、§66（耐用年數表）、§67（殘價率 ≤10%）；§98 樓層別效用比公報無表不推定。
每一步都回傳依據與頁碼；結果一律標「推定」，估價師可改。
"""
from __future__ import annotations

import json
import statistics
from functools import lru_cache
from typing import Any

from app.engine.rules import RULES_DIR

PING_M2 = 3.305785          # 1 坪 = 3.305785 m²
CN_NUM = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    return json.loads((RULES_DIR / "building_cost.json").read_text(encoding="utf-8"))


def cn_to_int(s: str) -> int | None:
    """「二十九層」「六層」「29」→ 整數；「全」「頂樓」等 → None。"""
    s = (s or "").replace("層", "").replace("樓", "").strip()
    if s.isdigit():
        return int(s)
    if not s or any(ch not in CN_NUM for ch in s):
        return None
    total, cur = 0, 0
    for ch in s:
        v = CN_NUM[ch]
        if v == 10:
            total += (cur or 1) * 10
            cur = 0
        else:
            cur = v
    return total + cur


def structure_of(material: str) -> str | None:
    m = (material or "").strip()
    mp = load_table()["material_map"]
    if m in mp:
        return mp[m]
    for k, v in mp.items():
        if k in m:
            return v
    if "鋼骨" in m and "混凝土" in m:
        return "鋼骨鋼筋混凝土造"
    if "混凝土" in m:
        return "鋼筋混凝土造"
    if "磚" in m:
        return "加強磚造" if "加強" in m else "磚造"
    return None


def use_class(btype: str) -> str:
    t = btype or ""
    if any(k in t for k in ("廠", "倉", "工業")):
        return "factory"
    return "house"


def price_level_index(median_per_ping: float | None) -> int | None:
    if median_per_ping is None:
        return None
    th = load_table()["construction_cost"]["price_level_thresholds"]
    return sum(1 for t in th if median_per_ping >= t)


def district_price_level(records: list[dict], district: str, before_ord: int | None = None, years: float = 1.0) -> dict[str, Any]:
    """同鄉鎮市區近一年房地交易（有建物面積）之每坪房價中位數（第四號公報說明事項第 4 點：當地新建建物二層以上平均房價水準；本系統以中位數代表）。"""
    from app.engine.verify import _ord, _roc
    vals = []
    for r in records:
        if (r.get("district") or "") != district or (r.get("target") or "土地") == "土地":
            continue
        b = r.get("building") or {}
        try:
            area = float(b.get("area") or 0)
            price = float(r.get("total_price") or 0)
        except (TypeError, ValueError):
            continue
        if area <= 0 or price <= 0:
            continue
        d = _roc(r.get("date") or "")
        if before_ord is not None and d:
            o = _ord(d)
            if o > before_ord or o < before_ord - int(365 * years):
                continue
        vals.append(price / (area / PING_M2))
    if not vals:
        return {"median_per_ping": None, "n": 0, "level": None, "label": None}
    med = statistics.median(vals)
    idx = price_level_index(med)
    return {"median_per_ping": round(med), "n": len(vals), "level": idx, "label": load_table()["construction_cost"]["price_level_labels"][idx]}


def _pick(rng: list | tuple | None) -> float | None:
    if not rng:
        return None
    lo, hi = rng
    mode = load_table().get("cost_pick", "mid")
    return float(lo if mode == "low" else hi if mode == "high" else (lo + hi) / 2)


def unit_cost_per_ping(structure: str, use: str, floors: int | None, level_idx: int | None) -> dict[str, Any] | None:
    """第四號公報附表一-2（新北市）→ 每坪營造施工費；回 {"value","range","row","column","note"}。"""
    cc = load_table()["construction_cost"]
    fl = floors or 1
    base_struct = structure
    add = 0.0
    add_note = ""
    if use == "house":
        if structure in ("鋼筋混凝土造", "預鑄混凝土造", "鋼骨造", "鋼骨鋼筋混凝土造"):
            if level_idx is None:
                return None
            row = next((r for r in cc["rc_house_office"] if r["floors"][0] <= fl <= r["floors"][1]), None)
            if row is None:
                row = cc["rc_house_office"][-1]
            rng = row["ranges"][level_idx]
            if rng is None:
                rng = next(r for r in row["ranges"] if r)
            if structure in ("鋼骨造", "鋼骨鋼筋混凝土造"):
                lo, hi = cc["src_sc_add_per_ping"]
                add = (lo + hi) / 2
                add_note = f"；{structure}依說明事項第 5 點按鋼筋混凝土造加計 {lo:,}～{hi:,} 元/坪（取中位 {add:,.0f}）"
                base_struct = "鋼筋混凝土造"
            return {"value": _pick(rng) + add, "range": rng, "row": f"{row['label']}（{row['basement']}，{'有' if row['elevator'] else '無'}電梯）", "column": cc["price_level_labels"][level_idx],
                    "table": f"附表一-2 新北市 {base_struct} 住宅、辦公室", "note": f"每坪 {rng[0]:,}～{rng[1]:,} 元取中位{add_note}"}
        if structure == "加強磚造":
            row = next((r for r in cc["brick_house_office"] if r["floors"][0] <= fl <= r["floors"][1]), cc["brick_house_office"][-1])
            return {"value": _pick(row["range"]), "range": row["range"], "row": row["label"], "column": "—", "table": "附表一-2 新北市 加強磚造 住宅、辦公室", "note": f"每坪 {row['range'][0]:,}～{row['range'][1]:,} 元取中位"}
        return None
    key = {"加強磚造": "brick_factory", "鋼筋混凝土造": "rc_factory", "預鑄混凝土造": "rc_factory", "鋼骨造": "rc_factory", "鋼骨鋼筋混凝土造": "rc_factory", "鋼架造": "steel_frame_factory"}.get(structure)
    if not key:
        return None
    rows = cc[key]
    row = next((r for r in rows if r["floors"][0] <= fl <= r["floors"][1]), rows[-1])
    return {"value": _pick(row["range"]), "range": row["range"], "row": row["label"], "column": "—", "table": f"附表一-2 新北市 {structure} 工廠", "note": f"每坪 {row['range'][0]:,}～{row['range'][1]:,} 元取中位"}


def useful_life(structure: str, use: str) -> int | None:
    tbl = load_table()["useful_life"]["factory_garage" if use == "factory" else "house_office_shop"]
    if structure == "鋼架造":
        return tbl["鋼架造(有披覆)"]
    return tbl.get(structure)


def residual_rate(structure: str) -> float | None:
    r = load_table()["residual_rate"]["rates"].get(structure)
    return None if r is None else (r[0] + r[1]) / 2 / 100.0


def age_years(completed: str, at: str) -> float | None:
    """完工年月日（民國 7 碼）到交易日的年數。"""
    from app.engine.verify import _ord, _roc
    a, b = _roc(completed or ""), _roc(at or "")
    if not a or not b:
        return None
    return max(0.0, (_ord(b) - _ord(a)) / 365.25)


@lru_cache(maxsize=1)
def load_cci() -> dict[str, Any]:
    p = RULES_DIR / "cci_ntpc.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"series": {}}


def cci_factor(at: str | None) -> dict[str, Any] | None:
    """營造工程物價指數調整係數＝交易日當月指數 ÷ 公報基期（113 年 11 月）指數；交易日在最新一期之後用最新一期。沒有資料 → None。"""
    from app.engine.verify import _roc
    d = _roc(at or "")
    cci = load_cci()
    ser = cci.get("series") or {}
    base = ser.get("11311")
    if not d or not base:
        return None
    keys = sorted(ser)
    key = f"{d[0]:03d}{d[1]:02d}"
    used = key if key in ser else (max(k for k in keys if k <= key) if any(k <= key for k in keys) else None)
    if used is None:
        return None
    return {"factor": ser[used] / base, "index_at": ser[used], "index_base": base, "month": used, "note": f"{cci.get('source', '').split('（')[0]}總指數 {used[:3]}年{int(used[3:])}月 {ser[used]} ÷ 113年11月 {base}"}


def estimate_building_cost(rec: dict, *, level: dict | None, at: str | None = None) -> dict[str, Any] | None:
    """實價登錄一筆含建物紀錄 → {"cost", "unit_cost_per_ping", "area_ping", "structure", "life", "residual", "age", "depreciation_pct", "basis", "note", "check"}；資料不足回 None。"""
    b = rec.get("building") or {}
    try:
        area_m2 = float(b.get("area") or 0)
    except (TypeError, ValueError):
        return None
    if area_m2 <= 0:
        return None
    structure = structure_of(b.get("material") or "")
    if not structure:
        return None
    use = use_class(b.get("type") or "")
    floors = cn_to_int(b.get("floors") or "")
    uc = unit_cost_per_ping(structure, use, floors, (level or {}).get("level"))
    if uc is None:
        return None
    life = useful_life(structure, use)
    rr = residual_rate(structure)
    if life is None or rr is None:
        return None
    age = age_years(b.get("completed") or "", at or rec.get("date") or "")
    area_ping = area_m2 / PING_M2
    cf = cci_factor(at or rec.get("date"))
    unit_adj = uc["value"] * (cf["factor"] if cf else 1.0)
    rebuild = unit_adj * area_ping
    used = min(age if age is not None else 0.0, float(life))
    dep_pct = (1 - rr) * used / life
    cost = rebuild * (1 - dep_pct)
    src = load_table()["source"]
    basis = [f"營造施工費：{uc['table']}，列 {uc['row']}，欄 {uc['column']}，{uc['note']}",
             f"耐用年數 {life} 年（{load_table()['useful_life']['page']}）、殘價率 {rr * 100:g}%（{load_table()['residual_rate']['page']}，取區間中位）",
             (f"物價調整：{cf['note']}，係數 {cf['factor']:.4f}（第四號公報說明事項第 14 點；新北市主計處僅公布總指數）" if cf else "物價調整：無營造工程物價指數資料，未調整（公報基期 113 年 11 月）"),
             f"折舊：定額法，屋齡 {age:.1f} 年" if age is not None else "折舊：實價登錄無完工日期，屋齡以 0 計（需確認）",
             load_table()["depreciation"]["formula"], f"來源：{src['title']}（{src['version']}）；{src['law']}"]
    note = (f"建物 {b.get('type') or ''} {structure} {b.get('floors') or ''}，登記面積 {area_m2:,.2f} m²＝{area_ping:,.2f} 坪；每坪 {uc['value']:,.0f} 元"
            + (f"×物價係數 {cf['factor']:.4f}＝{unit_adj:,.0f} 元" if cf else "") + f" × {area_ping:,.2f} 坪＝重建成本 {rebuild:,.0f} 元；"
            f"屋齡 {used:.1f}／{life} 年、殘價率 {rr * 100:g}% → 折舊 {dep_pct * 100:.1f}% → 建物成本價格 {cost:,.0f} 元"
            + (f"；房價水準依{level.get('n')} 筆同區房地交易中位數 {level.get('median_per_ping'):,} 元/坪判定為「{level.get('label')}」" if level and level.get("level") is not None else "")
            + ("；已依新北市營造工程物價總指數調整至交易日" if cf else "；未依營造工程物價指數調整（基期 113.11）") + "，系統推定請估價師確認")
    return {"cost": round(cost), "unit_cost_per_ping": round(unit_adj), "unit_cost_base": round(uc["value"]), "cci": cf, "area_ping": round(area_ping, 2), "structure": structure, "use": use, "floors": floors,
            "life": life, "residual_rate": rr, "age_years": None if age is None else round(age, 1), "depreciation_pct": round(dep_pct * 100, 1), "rebuild_cost": round(rebuild),
            "price_level": level, "basis": basis, "note": note, "check": True, "source": "系統推定（第四號公報成本法）"}
