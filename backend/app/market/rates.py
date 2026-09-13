"""
收益法用的公開序列查詢（rules/ 由 scripts/fetch_income_rates.py 產生）：
- 中央銀行五大銀行一年期定存（固定）與指數房貸（機動）月平均：押租金運用收益（手冊 p.39 表2「一年期定存利率」）、
  風險溢酬法基準（技術規則 §43 第1款）、成本法資本利息（技術規則 §63）。
- 主計總處消費者物價指數（房租）：收益實例租金調整至估價基準日（查估辦法 §17 第1項、手冊 p.39 (10)）。
查不到當月者取最近一個在前的月份，並在 note 註明。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"


@lru_cache(maxsize=4)
def _load(name: str) -> dict[str, Any]:
    p = RULES_DIR / name
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def parse_roc(s: Any) -> tuple[int, int, int] | None:
    """「1110901」「111.09.01」「111/9/1」「111年9月1日」→ (111, 9, 1)；不合法回 None。"""
    t = str(s or "").strip()
    if t.isdigit() and len(t) in (6, 7):
        y, m, d = int(t[:-4]), int(t[-4:-2]), int(t[-2:])
    else:
        parts = [p for p in re.split(r"[./\-年月日\s]+", t) if p]
        if len(parts) < 2:
            return None
        try:
            y, m = int(parts[0]), int(parts[1])
            d = int(parts[2]) if len(parts) > 2 else 1
        except ValueError:
            return None
    if not (1 <= m <= 12 and 1 <= d <= 31):
        return None
    return y, m, d


def _ym(s: Any) -> str | None:
    v = parse_roc(s)
    return f"{v[0]:03d}{v[1]:02d}" if v else None


def _at(series: dict[str, Any], ym: str | None) -> tuple[float | None, str | None]:
    if not ym:
        return None, None
    if series.get(ym) is not None:
        return float(series[ym]), ym
    keys = sorted(k for k, v in series.items() if k <= ym and v is not None)
    return (float(series[keys[-1]]), keys[-1]) if keys else (None, None)


def _ym_txt(k: str) -> str:
    return f"民國 {int(k[:3])} 年 {int(k[3:])} 月"


def deposit_rate_at(roc: Any) -> dict[str, Any]:
    """{"pct": 1.325, "ym": "11109", "source", "note"}（年利率 %）。"""
    d = _load("deposit_rates.json")
    want = _ym(roc)
    v, k = _at(d.get("deposit_1y_fixed") or {}, want)
    if v is None:
        return {"pct": None, "ym": None, "source": d.get("source"), "note": "無一年期定存利率資料，請人工填載"}
    lag = "" if k == want else f"（{_ym_txt(want)}尚無資料，取最近一期）"
    return {"pct": v, "ym": k, "source": d.get("source"), "note": f"{d.get('source')}：{_ym_txt(k)}五大銀行一年期定存（固定）平均 {v}%{lag}"}


def mortgage_rate_at(roc: Any) -> dict[str, Any]:
    d = _load("deposit_rates.json")
    want = _ym(roc)
    v, k = _at(d.get("mortgage_index_floating") or {}, want)
    if v is None:
        return {"pct": None, "ym": None, "source": d.get("source"), "note": "無指數房貸利率資料，請人工填載"}
    return {"pct": v, "ym": k, "source": d.get("source"), "note": f"{d.get('source')}：{_ym_txt(k)}五大銀行指數房貸（機動）平均 {v}%"}


def cpi_rent_at(roc: Any) -> dict[str, Any]:
    d = _load("cpi_rent.json")
    want = _ym(roc)
    v, k = _at(d.get("series") or {}, want)
    return {"index": v, "ym": k, "source": d.get("source"), "base": d.get("base")}


def rent_date_adjustment(rent_date: Any, valuation_date: Any) -> dict[str, Any]:
    """收益實例租金形成日期 → 估價基準日的價格日期調整率（%，四捨五入至 2 位）＝ 基準日房租指數 ÷ 租金形成月房租指數 − 1。"""
    a, b = cpi_rent_at(rent_date), cpi_rent_at(valuation_date)
    if a["index"] is None or b["index"] is None:
        return {"pct": None, "index_at_rent": a["index"], "index_at_valuation": b["index"], "source": a["source"],
                "note": "房租指數缺漏，價格日期調整率請人工填載（查估辦法 §17 第1項）"}
    from app.engine.tables import round_half_up
    pct = round_half_up((b["index"] / a["index"] - 1) * 100, 2)
    return {"pct": pct, "index_at_rent": a["index"], "index_at_valuation": b["index"], "source": a["source"],
            "note": f"{a['source']}（{a['base']}）：估價基準日 {_ym_txt(b['ym'])} {b['index']}；租金形成 {_ym_txt(a['ym'])} {a['index']}；"
                    f"調整率＝({b['index']} ÷ {a['index']} − 1)＝{pct:.2f}%（查估辦法 §17 第1項、手冊 p.39 (10)）"}


def status() -> dict[str, Any]:
    dep, cpi = _load("deposit_rates.json"), _load("cpi_rent.json")
    dk = sorted((dep.get("deposit_1y_fixed") or {}).keys())
    ck = sorted((cpi.get("series") or {}).keys())
    return {"deposit": {"months": len(dk), "latest": dk[-1] if dk else None, "source": dep.get("source")},
            "cpi_rent": {"months": len(ck), "latest": ck[-1] if ck else None, "source": cpi.get("source")}}
