"""
期日調整：都市地價指數（rules/land_price_index.json，內政部地政司半年報附錄三／四／五）。

法源：查估辦法 §17 第1項「調整至估價基準日」；手冊 p.50 (四) 得以地價指數調整；問答八 p.78。
方法：交易日與估價基準日各取一個指數值；日期落在兩個計算期（3/31、9/30）之間依日期線性內插，
      早於最早期或晚於最新期用最近一期（外推不猜）。調整率＝(基準日指數 ÷ 交易日指數 − 1)，四捨五入至 2 位小數
      （engine/tables.date_adjustment_from_index）。手冊未規定取位與內插方式，屬系統推定，備註會寫明。
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from itertools import pairwise
from typing import Any

from app.engine.rules import RULES_DIR
from app.engine.tables import date_adjustment_from_index
from app.engine.verify import _roc

ZONE_FOR_LAND_USE = {"商業用地": "商業區", "住宅用地": "住宅區", "工業用地": "工業區"}


@lru_cache(maxsize=1)
def load_index() -> dict[str, Any]:
    p = RULES_DIR / "land_price_index.json"
    if not p.exists():
        return {"dates": [], "series": {}, "source": None}
    return json.loads(p.read_text(encoding="utf-8"))


def _to_date(roc: tuple[int, int, int]) -> date:
    return date(roc[0] + 1911, roc[1], roc[2])


def _series_for(district: str, land_use: str | None, idx: dict | None = None) -> tuple[str | None, str | None, list | None]:
    idx = idx or load_index()
    zone = ZONE_FOR_LAND_USE.get(land_use or "")
    if not zone:
        return None, zone, None
    d = (district or "").replace("台", "臺")
    keys = [d, d.replace("新北市", ""), f"新北市{d}"]
    for k in keys:
        s = idx.get("series", {}).get(k)
        if s and s.get(zone):
            return k, zone, s[zone]
    return None, zone, None


def index_at(roc_date: str, series: list[float | None], dates: list[str]) -> tuple[float | None, str]:
    """指數值與說明。線性內插；區間外取最近一期。"""
    d = _roc(roc_date)
    if not d:
        return None, "日期無法解析"
    pts = [(_to_date(_roc(ds)), v, ds) for ds, v in zip(dates, series, strict=False) if v is not None and _roc(ds)]
    if not pts:
        return None, "無指數資料"
    x = _to_date(d)
    if x <= pts[0][0]:
        return pts[0][1], f"早於最早期，採 {pts[0][2]} 期值"
    if x >= pts[-1][0]:
        return pts[-1][1], f"採 {pts[-1][2]} 期值" + ("" if x == pts[-1][0] else "（最新一期，之後無資料）")
    for (d0, v0, s0), (d1, v1, s1) in pairwise(pts):
        if d0 <= x <= d1:
            if x == d0:
                return v0, f"採 {s0} 期值"
            w = (x - d0).days / (d1 - d0).days
            return round(v0 + (v1 - v0) * w, 2), f"{s0}（{v0}）與 {s1}（{v1}）依日期內插"
    return None, "無法定位期別"


def date_adjustment_for(transaction_date: str, valuation_date: str, *, district: str, land_use: str | None) -> dict[str, Any]:
    """回傳 date_adjustment dict（pct 為 None 表示無法計算，note 說明原因）。"""
    idx = load_index()
    key, zone, series = _series_for(district, land_use, idx)
    if series is None:
        return {"pct": None, "index_at_valuation": None, "index_at_transaction": None,
                "note": f"都市地價指數無「{district}」{zone or land_use or ''}序列，期日調整率請人工填載（手冊 p.50 (四)）", "source": idx.get("source")}
    iv, nv = index_at(valuation_date, series, idx["dates"])
    it, nt = index_at(transaction_date, series, idx["dates"])
    if iv is None or it is None:
        return {"pct": None, "index_at_valuation": iv, "index_at_transaction": it, "note": f"指數缺漏：基準日 {nv}；交易日 {nt}", "source": idx.get("source")}
    pct = date_adjustment_from_index(iv, it)
    return {"pct": pct, "index_at_valuation": iv, "index_at_transaction": it, "source": idx.get("source"), "zone": zone, "district_key": key,
            "note": f"{idx.get('source')}：{key}{zone}指數（基期 {idx.get('base')}）。估價基準日 {valuation_date} → {iv}（{nv}）；交易日 {transaction_date} → {it}（{nt}）。"
                    f"調整率＝({iv} ÷ {it} − 1)＝{pct:.2f}%（四捨五入至 2 位；手冊 p.50 (四)、問答八）"}


def fill_date_adjustments(data: dict, *, overwrite: bool = False) -> list[str]:
    """案件所有比較標的的 date_adjustment 沒有 pct（或 overwrite）者，依指數表補上。回傳每筆說明。"""
    case = data["case"]
    out = []
    for c in data.get("comparables", []):
        da = c.get("date_adjustment") or {}
        if da.get("pct") is not None and not overwrite:
            continue
        if not c.get("transaction_date"):
            continue
        r = date_adjustment_for(c["transaction_date"], case.get("valuation_date") or "", district=case.get("district") or "", land_use=case.get("land_use"))
        c["date_adjustment"] = r
        c.setdefault("derived", {})["date_adjustment"] = {"source": "都市地價指數", "note": r["note"]}
        out.append(f"比較標的{c.get('comp_no')}：" + (f"期日調整 {r['pct']:.2f}%" if r["pct"] is not None else r["note"]))
    return out
