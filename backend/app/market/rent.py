"""
收益實例（實價登錄租賃）→ 收益法調查估價表的推估月租金。

法源：查估辦法 §14（收益實例查估比準地收益價格，依技術規則第三章第二節）、§17（租金調整至估價基準日；蒐集期間同買賣實例，
無適當實例得放寬至基準日前一年）；手冊 p.37～39 收益法調查估價表：以 3 件為原則，同區段不易選取得於同一供需圈或同一／鄰近鄉鎮市區選取；
比準地為素地應採素地收益案例、建物欄位免填；租金型態含實價登錄租金；特殊情況依 §7、§8 情況調整。
資料：data/lvr/<county>_rent.json（scripts/fetch_lvr_rent.py）。租賃實價登錄只涵蓋經紀業與包租業經手之案件，非全部租約。
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "lvr"

# 備註關鍵字 → 特殊情況（exclude=True 者不自動採用，可人工勾選並填情況調整）
FLAG_RULES: list[tuple[str, str, str, bool]] = [
    (r"親友|員工|關係人|二親等|股東", "親友、員工或關係人間之租賃", "查估辦法 §7", True),
    (r"未保存登記|未登記|增建|加蓋|鐵皮|地上.*建物", "租賃標的含地上建物或增建，土地租金含建物使用價值，需情況調整", "查估辦法 §7、§8；手冊 p.38 (8)ii", False),
    (r"免租|裝潢期|裝修期", "含免租期或裝潢期，租金需調整", "手冊 p.38 (8)ii", False),
    (r"部分|分之|一部", "僅租賃部分面積，需換算為整體面積之租金", "手冊 p.38 (6)i", False),
    (r"含傢俱|附傢俱|家電", "租金含傢俱或設備使用對價，需情況調整", "手冊 p.38 (8)ii", False),
    (r"第\s*\d+\s*[~～]\s*\d+\s*個?月", "分段租金（各期租金不同），需換算未來平均一年租金", "手冊 p.39 (五)4", False),
]
USE_WORDS = {"住宅用地": ("住家", "住宅", "集合住宅"), "商業用地": ("商業", "店", "辦公", "事務所"), "工業用地": ("工業", "廠房", "倉庫", "工廠")}


@lru_cache(maxsize=2)
def load_rent(path: str | None = None) -> dict[str, Any]:
    p = Path(path or os.environ.get("LVR_RENT_JSON") or DATA_DIR / "f_rent.json")
    if not p.exists():
        return {"records": [], "seasons": [], "source": None, "path": str(p)}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        return {"records": [], "seasons": [], "source": None, "path": str(p), "error": f"租賃資料檔損毀（{type(e).__name__}），請重新產生 data/lvr/f_rent.json"}
    d["path"] = str(p)
    return d


def rent_status() -> dict[str, Any]:
    d = load_rent()
    recs = d.get("records", [])
    return {"path": d.get("path"), "n": len(recs), "n_land": sum(1 for r in recs if r.get("target") == "土地"), "seasons": d.get("seasons", []),
            "source": d.get("source"), "error": d.get("error")}


def income_mode(data: dict) -> str:
    """比準地有建物資料（data.income.subject.building 或宗地 building）→ building（房地）；否則 land（素地，手冊 p.38 (3)）。"""
    inc = data.get("income") or {}
    if inc.get("mode") in ("land", "building"):
        return inc["mode"]
    b = ((inc.get("subject") or {}).get("building")) or (data.get("subject_parcel") or {}).get("building")
    return "building" if b and (b.get("area_m2") or b.get("area")) else "land"


def classify_rent(rec: dict) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    note = rec.get("note") or ""
    for pat, label, rule, excl in FLAG_RULES:
        if re.search(pat, note):
            flags.append({"label": label, "rule": rule, "exclude": excl})
    if (rec.get("furnished") or "") == "有" and not any("傢俱" in f["label"] for f in flags):
        flags.append({"label": "附傢俱，租金含傢俱使用對價，需情況調整", "rule": "手冊 p.38 (8)ii", "exclude": False})
    return flags


def _use_matches(rec: dict, land_use: str | None) -> bool:
    words = USE_WORDS.get(land_use or "", ())
    if not words:
        return True
    u = (rec.get("use") or "") + (rec.get("btype") or "")
    return any(w in u for w in words)


def _fmt(d: str) -> str:
    d = (d or "").strip()
    return f"{int(d[:-4])}.{d[-4:-2]}.{d[-2:]}" if d.isdigit() and len(d) >= 6 else d


def search_rent_examples(data: dict, *, mode: str | None = None, max_n: int = 3, relax: bool = True, neighbors: bool = True,
                         rent: dict | None = None) -> dict[str, Any]:
    """回傳 {"mode","chosen","candidates","reference","window","stats","coverage","note"}。階段：1 同鄉鎮期間內、2 鄰近期間內、3 同鄉鎮放寬、4 鄰近放寬。"""
    from app.engine.verify import _ord, _roc, _year_before, collection_window
    from app.market.lvr import adjacency, zone_matches

    case = data["case"]
    vdate = case.get("valuation_date") or ""
    district = (case.get("district") or "").replace("新北市", "").replace("台", "臺")
    land_use = case.get("land_use")
    mode = mode or income_mode(data)
    vd = _roc(vdate)
    rent = rent or load_rent()
    recs = rent.get("records", [])
    stats = {"n_total": len(recs), "n_target": 0, "n_window": 0, "n_relaxed": 0, "n_excluded": 0}
    if not vd:
        return {"mode": mode, "chosen": [], "candidates": [], "reference": [], "window": None, "stats": stats, "note": "估價基準日格式無法解析，無法決定蒐集期間（查估辦法 §17）"}
    win = collection_window(vdate)
    one_year = _year_before(vd)
    v_ord = _ord(vd)
    y, m, d = vd
    near = adjacency().get(district, []) if neighbors else []
    cands: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    for rec in recs:
        rd = (rec.get("district") or "").replace("台", "臺")
        if rd != district and rd not in near:
            continue
        tg = rec.get("target") or ""
        if mode == "land":
            if tg != "土地" or not zone_matches(rec, land_use):
                continue
        else:
            if tg == "土地" or tg == "車位" or not _use_matches(rec, land_use):
                continue
        if not rec.get("unit_rent"):
            continue
        stats["n_target"] += 1
        td = _roc(rec.get("date"))
        if not td:
            continue
        in_window = bool(win and _ord(win[0]) <= _ord(td) <= _ord(win[1]))
        out_of_window = _ord(td) > v_ord or _ord(td) < one_year
        same = rd == district
        stage = (1 if same else 2) if in_window else (3 if same else 4)
        flags = classify_rent(rec)
        c = {"id": rec["id"], "district": rd, "date": _fmt(rec.get("date")), "rent_date": rec.get("date"), "target": tg, "position": rec.get("position"),
             "area_m2": round(rec["land_area"], 2) if mode == "land" else round((rec.get("building_area") or 0) - (rec.get("park_area") or 0), 2),
             "total_rent": rec.get("rent_ex_park") or rec.get("total_rent"), "unit_rent": rec.get("unit_rent"), "unit_basis": rec.get("unit_basis"),
             "zone": rec.get("zone"), "lot_zones": sorted({(lt.get("zone") or "") for lt in rec.get("lots", [])}), "sections": sorted({lt.get("section") or "" for lt in rec.get("lots", [])}),
             "btype": rec.get("btype"), "use": rec.get("use"), "level": rec.get("level"), "floors": rec.get("floors"), "completed": rec.get("completed"),
             "material": rec.get("material"), "furnished": rec.get("furnished"), "note": rec.get("note"), "flags": flags,
             "excluded": any(f["exclude"] for f in flags), "in_window": in_window, "stage": stage, "season": rec.get("season")}
        if out_of_window:
            c["stage"] = 5
            c["out_of_window"] = True
            refs.append(c)
            continue
        stats["n_window" if in_window else "n_relaxed"] += 1
        stats["n_excluded"] += c["excluded"]
        cands.append(c)
    names = {1: "同鄉鎮市區、蒐集期間內（§17 第2項）", 2: "鄰近鄉鎮市區、蒐集期間內（手冊 p.37 (五)1(1)）", 3: "同鄉鎮市區、放寬至基準日前一年（§17 第3項）",
             4: "鄰近鄉鎮市區、放寬至基準日前一年（§17 第3項）", 5: "蒐集期間外參考案例"}
    usable = [c for c in cands if not c["excluded"] and (relax or c["in_window"]) and (neighbors or c["district"] == district)]
    usable.sort(key=lambda c: (c["stage"], bool(c["flags"]), -_ord(_roc(c["rent_date"]) or (0, 0, 0))))
    chosen = usable[:max_n]
    for c in cands + refs:
        c["basis"] = names[c["stage"]]
    cands.sort(key=lambda c: (c["excluded"], c["stage"], bool(c["flags"]), -_ord(_roc(c["rent_date"]) or (0, 0, 0))))
    refs.sort(key=lambda c: -_ord(_roc(c["rent_date"]) or (0, 0, 0)))
    window_txt = f"{win[0][0]}.{win[0][1]:02d}.{win[0][2]:02d}～{win[1][0]}.{win[1][1]:02d}.{win[1][2]:02d}" if win else "需人工確認（基準日非 9/1 或 3/1）"
    note = None
    if not recs:
        note = rent.get("error") or "尚無租賃資料：請執行 scripts/fetch_lvr_rent.py 產生 data/lvr/f_rent.json"
    elif not chosen:
        note = ("蒐集期間與放寬期間內，同鄉鎮與鄰近鄉鎮無" + ("素地（土地）" if mode == "land" else "同用途房屋") + "租賃實例；可改人工填寫收益實例（手冊 p.38 (9) 待租租金、詢問租金）")
    return {"mode": mode, "chosen": chosen, "candidates": cands[:60], "reference": refs[:12],
            "window": {"text": window_txt, "relaxed_from": f"{y - 1}.{m:02d}.{d:02d}", "vdate": f"{y}.{m:02d}.{d:02d}"},
            "stats": stats, "coverage": {"seasons": rent.get("seasons", [])}, "note": note}


def to_income_example(c: dict, example_no: int, valuation_date: str) -> dict[str, Any]:
    """候選 → data.income.examples 的一筆；價格日期調整依房租指數自動帶，其餘調整預設 0 由估價師填（標需確認）。"""
    from app.market.rates import rent_date_adjustment
    da = rent_date_adjustment(c.get("rent_date"), valuation_date)
    return {"example_no": example_no, "lvr_id": c.get("id"), "district": c.get("district"), "position": c.get("position"), "section_id": "",
            "area_m2": c.get("area_m2"), "total_rent": c.get("total_rent"), "unit_rent": c.get("unit_rent"), "rent_type": "登錄租金",
            "rent_date": c.get("rent_date"), "situation_pct": 0.0, "date_pct": da["pct"] if da["pct"] is not None else 0.0, "date_note": da["note"],
            "regional_pct": 0.0, "individual_pct": 0.0, "weight_pct": None, "flags": [f["label"] for f in c.get("flags") or []],
            "note": c.get("note") or "", "source": "內政部實價登錄租賃（" + (c.get("season") or "") + "）", "target": c.get("target")}
