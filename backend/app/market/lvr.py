"""
實價登錄 → 比較標的。

資料：data/lvr/<county>_land.json（scripts/fetch_lvr.py 產生；純土地交易）。
步驟與法源：
  1. 蒐集期間：查估辦法 §17 第2項（基準日 9/1 → 當年 3/2～9/1；3/1 → 前一年 9/2～當年 3/1）；無適當實例放寬至基準日前一年（第3項）。
  2. 特殊情況：§7 十三款（實價登錄備註的標準用語對應款次）→ 排除或標記；地上有建物者須依 §13 第3、4款扣除建物成本，系統不自動採用。
  3. 用地別：比準地用地別與實例使用分區相符（手冊 p.51 (七)1 依比準地所屬使用分區選同性質用地）。
  4. 選取順序：同一地價區段（§19 第1項第1款）→ 同鄉鎮其他地區 → 鄰近鄉鎮（§19 第2項、手冊 p.51 (五)1「同一或鄰近鄉鎮市區」）；
     期間內優先，再放寬一年。最多三件（§19 第1項第1款）。
  5. 正常單價：無建物 → 總價 ÷ 土地面積（§13 第2款、手冊 p.6 四(一)2）。
每一件都帶 source（實價登錄編號、總價、備註）與 selection（階段、法源、距離、旗標），給表2／表4 與意見書用。
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.engine.rules import RULES_DIR
from app.engine.verify import _ord, _roc, collection_window

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "lvr"

# 實價登錄備註標準用語 → 查估辦法 §7 款次。exclude=True 直接不採用；False 只標記需確認。
SPECIAL_RULES: list[tuple[str, str, str, bool]] = [
    ("親友、員工、共有人或其他特殊關係", "§7 第4款", "親友關係人間之交易", True),
    ("特殊關係", "§7 第4款", "親友關係人間之交易", True),
    ("包含公共設施保留地", "§7 第10款", "包含公共設施用地之交易", True),
    ("標售", "§7 第8款", "公有土地標售、讓售（或未辦繼承標售）", True),
    ("讓售", "§7 第8款", "公有土地標售、讓售", True),
    ("拍賣", "§7 第7款", "拍賣", True),
    ("法拍", "§7 第7款", "拍賣", True),
    ("法院拍賣", "§7 第7款", "法院拍賣", True),
    ("法院判決", "§7 第7款", "法院判決移轉", True),
    ("畸零", "§7 第5款", "畸零地或有合併使用之交易", True),
    ("債權債務", "§7 第3款", "受債權債務關係影響之交易", True),
    ("抵債", "§7 第3款", "受債權債務關係影響之交易（抵債）", True),
    ("債務", "§7 第3款", "受債權債務關係影響之交易", True),
    ("急買", "§7 第1款", "急買急賣", True),
    ("急賣", "§7 第1款", "急買急賣", True),
    ("重建或重劃、都更", "§7 第2款", "期待因素影響之交易", True),
    ("協議價購", "§7 第13款", "徵收前協議價購，非市場正常買賣", True),
    ("合建", "§7 第13款", "合建案建商與地主間之交易", True),
    ("佔用", "§7 第6款", "地上物處理有糾紛之交易", True),
    ("占用", "§7 第6款", "地上物處理有糾紛之交易", True),
    ("糾紛", "§7 第6款", "地上物處理有糾紛之交易", True),
    ("地上權", "§7 第13款", "非所有權買賣", True),
    ("未登記建物", "§13 第3、4款", "地上有未辦保存登記建物，須扣除建物成本後始得估計土地單價", True),
    ("農作物", "§8", "含農作物補償，價格須查證調整", True),
    ("34條之1", "§7 第13款", "土地法第 34 條之 1 共有人處分，需確認是否為正常買賣", False),
    ("持分", "備註", "持分移轉，單價以移轉面積計，需確認", False),
]
LAND_USE_ZONES = {"商業用地": ("商",), "住宅用地": ("住",), "工業用地": ("工",), "農業用地": ("農",), "其他用地": ()}


@lru_cache(maxsize=4)
def load_lvr(path: str | None = None) -> dict[str, Any]:
    p = Path(path or os.environ.get("LVR_JSON") or DATA_DIR / "f_land.json")
    if not p.exists():
        return {"records": [], "seasons": [], "source": None, "path": str(p)}
    d = json.loads(p.read_text(encoding="utf-8"))
    d["path"] = str(p)
    return d


def lvr_status() -> dict[str, Any]:
    d = load_lvr()
    recs = d.get("records", [])
    return {"path": d.get("path"), "n": len(recs), "seasons": d.get("seasons", []), "source": d.get("source"),
            "districts": sorted({r["district"] for r in recs})[:40], "coverage": dataset_coverage(d)}


def dataset_coverage(lvr: dict | None = None) -> dict[str, Any] | None:
    """資料庫涵蓋期間：依已下載的季別（113S3 = 113.07.01～113.09.30）。回 {"from","to","seasons","from_ord","to_ord"}；沒有季別回 None。"""
    d = lvr or load_lvr()
    seasons = sorted(s for s in (d.get("seasons") or []) if re.match(r"^\d{3}S[1-4]$", s))
    if not seasons:
        return None
    def bounds(s: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
        y, q = int(s[:3]), int(s[-1])
        return (y, 3 * q - 2, 1), (y, 3 * q, (31, 30, 30, 31)[q - 1])
    lo, hi = bounds(seasons[0])[0], bounds(seasons[-1])[1]
    fmt = lambda t: f"{t[0]}.{t[1]:02d}.{t[2]:02d}"
    return {"from": fmt(lo), "to": fmt(hi), "seasons": seasons, "from_ord": _ord(lo), "to_ord": _ord(hi)}


@lru_cache(maxsize=1)
def adjacency() -> dict[str, list[str]]:
    p = RULES_DIR / "ntpc_district_adjacency.json"
    d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {k: v for k, v in d.items() if not k.startswith("$")}


def lot_no_from_raw(raw: str) -> str:
    """'01310001' → '131-1'；'0489-0000' → '489-0'。"""
    s = re.sub(r"\D", "", raw or "")
    if len(s) >= 8:
        return f"{int(s[:4])}-{int(s[4:8])}"
    return s


def classify(rec: dict) -> dict[str, Any]:
    """§7／§13 特殊情況判定。回傳 {"excluded": bool, "flags": [{"rule", "label", "exclude"}]}。"""
    note = rec.get("note") or ""
    flags: list[dict] = []
    seen = set()
    for kw, rule, label, exclude in SPECIAL_RULES:
        if kw in note and (rule, label) not in seen:
            seen.add((rule, label))
            flags.append({"rule": rule, "label": label, "exclude": exclude, "keyword": kw})
    if any((lot.get("transfer") or "") == "持分移轉" for lot in rec.get("lots", [])) and not any(f["keyword"] == "持分" for f in flags):
        flags.append({"rule": "備註", "label": "持分移轉，單價以移轉面積計，需確認", "exclude": False, "keyword": "持分移轉"})
    if any("道路" in (lot.get("zone") or "") for lot in rec.get("lots", [])) and not any(f["rule"] == "§7 第10款" for f in flags):
        flags.append({"rule": "§7 第10款", "label": "含道路用地（公共設施用地）", "exclude": True, "keyword": "道路用地"})
    if not rec.get("total_price") or not rec.get("total_area"):
        flags.append({"rule": "§13", "label": "總價或面積缺漏，無法計算正常單價", "exclude": True, "keyword": ""})
    if (rec.get("target") or "土地") != "土地":
        b = rec.get("building") or {}
        level_missing = not (b.get("level") or "")
        whole = "透天" in (b.get("type") or "") or (b.get("level") or "") == "全"
        flags.append({"rule": "§13 第4款" if whole else "§13 第3款",
                      "label": ("地上有全棟建物：土地價格＝房地價格－建物成本價格，再 ÷ 土地面積" if whole else
                                "區分所有建物：土地權利價格＝房地價格－建物成本價格，÷ 土地持分面積，並考慮樓層別效用價差")
                               + "；填入建物成本價格（不動產估價技術規則第 3 章第 3 節、估價師公會第 4 號公報）即可採用"
                               + ("；實價登錄未載明建物層次，請確認是否全棟" if level_missing else ""),
                      "exclude": True, "keyword": "房地", "needs_building_cost": True})
    return {"excluded": any(f["exclude"] for f in flags), "flags": flags}


def zone_matches(rec: dict, land_use: str | None) -> bool:
    if not land_use or land_use == "其他用地":
        return True
    keys = LAND_USE_ZONES.get(land_use, ())
    z = rec.get("zone") or ""
    if any(z.startswith(k) for k in keys):
        return True
    lot_zones = " ".join((lot.get("zone") or "") for lot in rec.get("lots", []))
    return any(f"{k}業區" in lot_zones or f"{k}宅區" in lot_zones for k in keys) or ("農" in keys and "農牧" in lot_zones)


def _main_lot(rec: dict) -> dict | None:
    lots = [lot for lot in rec.get("lots", []) if "道路" not in (lot.get("zone") or "")] or rec.get("lots", [])
    return max(lots, key=lambda lot: lot.get("area") or 0) if lots else None


def _parcel_id(rec: dict) -> str:
    lot = _main_lot(rec)
    if lot:
        return f"{lot['section']}{lot_no_from_raw(lot['lot_raw']).replace('-0', '', 1) if lot_no_from_raw(lot['lot_raw']).endswith('-0') else lot_no_from_raw(lot['lot_raw'])}地號"
    return rec.get("position") or rec.get("id")


def _fmt_date(d: str) -> str:
    return f"{d[:3]}.{d[3:5]}.{d[5:7]}" if len(d) == 7 else d


def search_comparables(data: dict, *, max_n: int = 3, relax: bool = True, neighbors: bool = True,
                       cadastre_lookup=None, lvr: dict | None = None) -> dict[str, Any]:
    """
    回傳 {"chosen": [Comparable...], "candidates": [...摘要], "stages": [...], "window": {...}, "stats": {...}}。
    cadastre_lookup(section, lot_no) → {"geometry": ...}|None：有地籍圖時用來判同區段與量距離。
    """
    from shapely.geometry import shape

    from app.spatial.geo import straight_distance_m

    case = data["case"]
    vdate = case.get("valuation_date") or ""
    district = (case.get("district") or "").replace("新北市", "").replace("台", "臺")
    land_use = case.get("land_use")
    vd = _roc(vdate)
    win = collection_window(vdate)
    subject = data["subject_parcel"]
    sec_id = subject.get("section_id")
    sec_geom = (data.get("sections") or {}).get(sec_id, {}).get("geometry")
    sec_shape = shape(sec_geom) if sec_geom else None
    subj_geom = subject.get("geometry")
    lvr = lvr or load_lvr()
    recs = lvr.get("records", [])
    stats = {"n_total": len(recs), "n_district": 0, "n_zone": 0, "n_window": 0, "n_relaxed": 0, "n_clean": 0, "n_excluded": 0}
    if not vd:
        return {"chosen": [], "candidates": [], "stages": [], "window": None, "stats": stats,
                "note": "估價基準日格式無法解析，無法決定蒐集期間（查估辦法 §17）"}
    from app.engine.verify import _year_before
    y, m, d = vd
    one_year = _year_before(vd)                     # 基準日前一年（2/29 → 前一年 2/28）
    v_ord = _ord(vd)
    near = adjacency().get(district, []) if neighbors else []
    window_txt = f"{win[0][0]}.{win[0][1]:02d}.{win[0][2]:02d}～{win[1][0]}.{win[1][1]:02d}.{win[1][2]:02d}" if win else "需人工確認（基準日非 9/1 或 3/1）"
    vdate_txt = f"{y}.{m:02d}.{d:02d}"
    vdate_warning = None if (m, d) in ((3, 1), (9, 1)) else f"估價基準日 {vdate_txt} 不是 3 月 1 日或 9 月 1 日（查估辦法 §17 第2項），可能誤植，請確認。"
    # 資料庫涵蓋期間 vs 基準日前一年：不在範圍內時，0 筆是「沒下載那幾季」不是「市場沒有實例」
    cov = dataset_coverage(lvr)
    coverage = None
    if cov:
        covers = cov["from_ord"] <= one_year and cov["to_ord"] >= v_ord
        coverage = {**{k: cov[k] for k in ("from", "to", "seasons")}, "covers_window": covers,
                    "fetch_cmd": f"cd backend && python3 scripts/fetch_lvr.py --valuation {y:03d}{m:02d}{d:02d} --county f",
                    "note": None if covers else f"實價登錄資料庫只涵蓋 {cov['from']}～{cov['to']}（{'、'.join(cov['seasons'])}），估價基準日前一年 {y - 1}.{m:02d}.{d:02d}～{vdate_txt} 不在範圍內；0 筆不代表市場沒有實例。"}
    refs: list[dict] = []          # 蒐集期間外（早於基準日前一年或晚於基準日）的同用地別實例：只作參考（手冊 p.77 問答四），採用須敘明理由

    from app.market.building_cost import district_price_level, estimate_building_cost
    price_level = district_price_level(recs, district, before_ord=v_ord)      # 第四號公報說明事項第 4 點：當地平均房價水準 → 營造施工費欄位
    cands: list[dict] = []
    for rec in recs:
        rd = (rec.get("district") or "").replace("台", "臺")
        if rd != district and rd not in near:
            continue
        stats["n_district"] += rd == district
        td = _roc(rec.get("date"))
        if not td:
            continue
        out_of_window = _ord(td) > v_ord or _ord(td) < one_year
        in_window = bool(win and _ord(win[0]) <= _ord(td) <= _ord(win[1]))
        if not zone_matches(rec, land_use):
            continue
        if not out_of_window:
            stats["n_zone"] += 1
            stats["n_window" if in_window else "n_relaxed"] += 1
        cl = classify(rec)
        lot = _main_lot(rec)
        geom = None
        if cadastre_lookup and lot:
            hit = cadastre_lookup(lot["section"], lot_no_from_raw(lot["lot_raw"]))
            geom = hit.get("geometry") if hit else None
        in_section = None
        dist = None
        if geom is not None:
            g = shape(geom)
            if sec_shape is not None:
                in_section = bool(sec_shape.intersects(g))
            if subj_geom is not None:
                dist = round(straight_distance_m(subj_geom, g))
        same_district = rd == district
        stage = (1 if in_section else 2) if same_district else 3
        section_unknown = same_district and in_section is None        # 沒有地籍圖：不知道是否同區段，先歸「同鄉鎮其他地區」但標需確認
        if not in_window:
            stage += 3           # 4/5/6：放寬一年的同區段／同鄉鎮／鄰近鄉鎮
        c = {"id": rec["id"], "parcel_id": _parcel_id(rec), "district": rd, "date": _fmt_date(rec["date"]), "total_price": rec["total_price"],
             "total_area": rec["total_area"], "unit_price": round(rec["total_price"] / rec["total_area"]) if rec["total_area"] else None,
             "zone": rec.get("zone"), "lot_zones": sorted({(lot.get("zone") or "") for lot in rec.get("lots", [])}), "note": rec.get("note"),
             "flags": cl["flags"], "excluded": cl["excluded"], "in_window": in_window, "in_section": in_section, "distance_m": dist,
             "stage": stage, "geometry": geom, "n_lots": len(rec.get("lots", [])), "season": rec.get("season"),
             "target": rec.get("target"), "building": rec.get("building"), "position": rec.get("position"),
             "needs_building_cost": any(f.get("needs_building_cost") for f in cl["flags"]), "section_unknown": section_unknown}
        if c["needs_building_cost"]:
            est = estimate_building_cost(rec, level=price_level, at=rec.get("date"))
            c["building_cost_estimate"] = est
            if est and not any(f["exclude"] and not f.get("needs_building_cost") for f in cl["flags"]):
                c["excluded"] = False                    # 建物成本可推定 → 可自動採用（推定值標需確認，估價師可改）
                for f in c["flags"]:
                    if f.get("needs_building_cost"):
                        f["label"] += f"；系統已依第四號公報推定建物成本價格 {est['cost']:,} 元（需確認）"
        if out_of_window:
            c["stage"] = 7
            c["out_of_window"] = True
            c["days_from_window"] = (one_year - _ord(td)) if _ord(td) < one_year else (_ord(td) - v_ord)
            c["flags"] = c["flags"] + [{"rule": "手冊 p.77 問答四", "exclude": True, "out_of_window": True,
                                         "label": ("早於估價基準日前一年" if _ord(td) < one_year else "晚於估價基準日") + f" {c['days_from_window']} 天，逾查估辦法 §17 第3項放寬上限；僅作參考，採用須於備註詳予說明妥適性"}]
            c["excluded"] = True
            refs.append(c)
            continue
        if c["excluded"]:
            stats["n_excluded"] += 1
        else:
            stats["n_clean"] += 1
        cands.append(c)

    stage_names = {1: "同一地價區段、蒐集期間內（§19 第1項第1款、§17 第2項）", 2: "同鄉鎮其他地區、蒐集期間內（§19 第2項）",
                   3: "鄰近鄉鎮、蒐集期間內（§19 第2項；手冊 p.51 (五)1）", 4: "同一地價區段、放寬至基準日前一年（§17 第3項）",
                   5: "同鄉鎮其他地區、放寬至基準日前一年（§17 第3項、§19 第2項）", 6: "鄰近鄉鎮、放寬至基準日前一年（§17 第3項、§19 第2項）",
                   7: "蒐集期間外參考案例（手冊 p.77 問答四）"}
    usable = [c for c in cands if not c["excluded"] and (relax or c["in_window"]) and (neighbors or c["district"] == district)]
    usable.sort(key=lambda c: (c["stage"], c["distance_m"] if c["distance_m"] is not None else 1e9, -_ord(_roc(c["date"]) or (0, 0, 0))))
    chosen = usable[:max_n]
    stages = [{"stage": s, "name": stage_names[s], "n": sum(1 for c in usable if c["stage"] == s), "used": sum(1 for c in chosen if c["stage"] == s)} for s in range(1, 7)]
    for c in chosen:
        c["basis"] = stage_names[c["stage"]]
    cands.sort(key=lambda c: (c["excluded"], c["stage"], c["distance_m"] if c["distance_m"] is not None else 1e9))
    refs.sort(key=lambda c: (c["days_from_window"], c["district"] != district, c["distance_m"] if c["distance_m"] is not None else 1e9))
    for c in refs:
        c["basis"] = stage_names[7]
    return {"chosen": chosen, "candidates": cands[:60], "reference": refs[:12], "stages": stages,
            "window": {"text": window_txt, "relaxed_from": f"{y - 1}.{m:02d}.{d:02d}", "vdate": vdate_txt}, "stats": stats,
            "coverage": coverage, "vdate_warning": vdate_warning}


def _address(c: dict, district_name: str) -> str:
    """實價登錄的「位置」已含行政區（例：三芝區智成街2之1號）；沒有時用實例所在區＋地號，不重複加案件的區。"""
    pos = (c.get("position") or "").strip()
    rd = (c.get("district") or "").strip()
    if c.get("needs_building_cost") and pos:
        base = pos.replace("新北市", "")
        return "新北市" + (base if base.startswith(rd) or not rd else f"{rd}{base}")
    return f"新北市{rd}{c['parcel_id']}" if rd else f"{district_name}{c['parcel_id']}"


def to_comparable(c: dict, comp_no: int, section_id: str, *, district_name: str = "", building_cost: float | None = None, reason: str | None = None) -> dict[str, Any]:
    """
    搜尋結果 → 案件 comparables 元素（Parcel + 交易資料）。屬性欄位留空給「依地號產生」補。
    含建物者須給 building_cost（建物成本價格，元）：土地價格＝房地價格－建物成本（§13 第3、4款），÷ 土地（持分）面積。
    """
    flags_txt = "；".join(f"{f['label']}（{f['rule']}）" for f in c["flags"]) if c["flags"] else ""
    reason = (reason or "").strip()
    if c.get("out_of_window") and not reason:
        raise ValueError(f"{c['parcel_id']} 為蒐集期間外之參考案例，採用須填寫理由（手冊 p.77 問答四）")
    lots_txt = f"，共 {c['n_lots']} 筆地號" if c["n_lots"] > 1 else ""
    unit = c["unit_price"]
    price_note = f"交易總價 {c['total_price']:,.0f} 元 ÷ 土地面積 {c['total_area']} m²（查估辦法 §13 第2款）"
    cost_est = None
    if c.get("needs_building_cost"):
        if building_cost is None and c.get("building_cost_estimate"):
            cost_est = c["building_cost_estimate"]
            building_cost = cost_est["cost"]
        if building_cost is None:
            raise ValueError(f"{c['parcel_id']} 含建物，須先填建物成本價格（查估辦法 §13 第3、4款）")
        land_price = float(c["total_price"]) - float(building_cost)
        unit = round(land_price / c["total_area"]) if c["total_area"] else None
        b = c.get("building") or {}
        price_note = (f"房地價格 {c['total_price']:,.0f} 元 － 建物成本價格 {float(building_cost):,.0f} 元 ＝ 土地價格 {land_price:,.0f} 元，"
                      f"÷ 土地{'持分' if b.get('level') not in ('全', '') else ''}面積 {c['total_area']} m²（查估辦法 §13 第3、4款；建物 {b.get('type') or ''} {b.get('material') or ''}"
                      f" 完工 {b.get('completed') or '—'} 建物面積 {round(float(b['area']), 2) if b.get('area') else '—'} m²）"
                      + (f"；建物成本價格為系統推定：{cost_est['note']}" if cost_est else "；建物成本價格為估價師填載"))
    return {
        "comp_no": comp_no, "parcel_id": c["parcel_id"], "address": _address(c, district_name),
        "section_id": section_id,
        "normal_unit_price": unit, "transaction_date": c["date"],
        "date_adjustment": {"pct": None, "index_at_valuation": None, "index_at_transaction": None, "note": "待依地價指數計算"},
        "geometry": c.get("geometry"), "geometry_source": "cadastre_file" if c.get("geometry") else None,
        "nuisance": None,
        "source": {"lvr_id": c["id"], "price_total": c["total_price"], "area_m2": c["total_area"], "season": c["season"],
                   "building_cost": building_cost, "building": c.get("building"),
                   "building_cost_estimate": cost_est, "building_cost_source": "系統推定（第四號公報成本法，需確認）" if cost_est else ("估價師填載" if building_cost is not None else None),
                   "note": f"內政部實價登錄 {c['season']} 編號 {c['id']}；{price_note}{lots_txt}" + (f"；備註：{c['note']}" if c.get("note") else "")
                           + (f"；蒐集期間外參考案例，採用理由：{reason}" if c.get("out_of_window") else "")},
        "selection": {"stage": c["stage"], "basis": (c.get("basis") or "") + ("（無地籍圖，無法判定是否同區段，請確認）" if c.get("section_unknown") else "") + (f"：{reason}" if c.get("out_of_window") else ""),
                      "out_of_window": bool(c.get("out_of_window")), "reason": reason or None,
                      "section_unknown": bool(c.get("section_unknown")), "in_window": c["in_window"], "in_section": c["in_section"],
                      "distance_m": c["distance_m"], "flags": c["flags"], "flags_text": flags_txt, "zone": c.get("zone"), "lot_zones": c.get("lot_zones")},
        "area_m2": c["total_area"] if c["n_lots"] <= 1 else None,
        "zoning": next((z.split(":")[-1] for z in (c.get("lot_zones") or []) if "都市" in z and "道路" not in z), None),
        "derived": {"area_m2": {"source": "實價登錄", "note": "土地移轉總面積"}} if c["n_lots"] <= 1 else {},
    }


def build_comparables(data: dict, search: dict, ids: list[str], building_costs: dict[str, float] | None = None, reasons: dict[str, str] | None = None) -> list[dict]:
    """依使用者勾選（或自動選取）的實價登錄編號建立 comparables；同區段沿用比準地區段，其餘各給一個區段編號（表5 用）。
    reasons：蒐集期間外參考案例（search["reference"]）的採用理由，缺就拒絕。"""
    by_id = {c["id"]: c for c in search.get("reference", [])} | {c["id"]: c for c in search.get("candidates", [])} | {c["id"]: c for c in search.get("chosen", [])}
    sec_id = data["subject_parcel"].get("section_id") or next(iter(data.get("sections") or {}), "P001-00")
    district = (data["case"].get("district") or "")
    out = []
    for i, cid in enumerate(ids, start=1):
        c = by_id.get(cid)
        if not c:
            raise KeyError(f"候選清單沒有 {cid}，請重新搜尋")
        bc = (building_costs or {}).get(cid)
        target_sec = sec_id if c.get("in_section") else f"{sec_id}-C{i}"
        out.append(to_comparable(c, i, target_sec, district_name=district, building_cost=bc, reason=(reasons or {}).get(cid)))
    return out
