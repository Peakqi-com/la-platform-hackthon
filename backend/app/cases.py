"""
案件儲存（前端不做 localStorage 持久化，資料在後端）：記憶體 dict + data/cases/<id>.json。
demo 變體：template（範本，全綠）/ tampered（竄改版：面前道路差異率 5→2.5、表5 交通運輸小計 0→1.0、區域因素抄成 1.0、比較標的交易日期改到一年前）/
residential（同一案切到示範用住宅基準表，示範「換基準表」與缺欄位 → 需人工確認）。
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "fixtures"
CASES_DIR = Path(os.environ.get("CASES_DIR") or ROOT / "data" / "cases")
TZ = timezone(timedelta(hours=8))

_mem: dict[str, dict] = {}


def _now() -> str:
    return datetime.now(tz=TZ).isoformat(timespec="seconds")


def _load_all() -> None:
    if _mem or not CASES_DIR.exists():
        return
    for p in sorted(CASES_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            _migrate(d)
            _mem[d["id"]] = d
        except (OSError, json.JSONDecodeError, KeyError):
            continue


def _migrate(d: dict) -> None:
    """舊案件補欄位：輸入指紋、原始快照（以現況為準）、輸入修改時間。"""
    if not d.get("input_hash"):
        d["input_hash"] = input_hash(d.get("data"), d.get("submitted_table5"), d.get("submitted_table4"))
    if not d.get("original"):
        d["original"] = {"data": copy.deepcopy(d.get("data")), "submitted_table5": copy.deepcopy(d.get("submitted_table5")),
                         "submitted_table4": copy.deepcopy(d.get("submitted_table4")), "at": d.get("created_at") or d.get("updated_at") or _now()}
    d.setdefault("input_updated_at", d.get("updated_at"))
    d.setdefault("outputs", None)


STATUSES = ("draft", "reviewing", "done")     # 草稿／審查中／已完成


def list_cases() -> list[dict]:
    _load_all()
    out = []
    for d in _mem.values():
        c = d.get("data", {}).get("case", {})
        out.append({"id": d["id"], "name": d.get("name"), "case_no": c.get("case_no"), "district": c.get("district"),
                    "land_use": c.get("land_use"), "rulesets": c.get("rulesets"), "updated_at": d.get("updated_at"), "created_at": d.get("created_at"),
                    "opened_at": d.get("opened_at"), "origin": d.get("origin"), "status": d.get("status", "draft"),
                    "has_submitted": bool(d.get("submitted_table4") or d.get("submitted_table5")),
                    "n_decisions": len(d.get("decisions") or {}),
                    "generated_at": (d.get("outputs") or {}).get("generated_at"),
                    "stale": not d.get("outputs") or (d.get("outputs") or {}).get("input_hash") != d.get("input_hash"),
                    # 總覽儀表用：不符／需確認數、已裁決接受數、比較價格、最後一次操作
                    "n_error": ((d.get("outputs") or {}).get("summary") or {}).get("n_error"),
                    "n_warn": ((d.get("outputs") or {}).get("summary") or {}).get("n_warn"),
                    "n_accepted": sum(1 for v in (d.get("decisions") or {}).values() if isinstance(v, dict) and v.get("decision") == "accept" and not v.get("stale")),
                    "comparison_price": ((d.get("outputs") or {}).get("summary") or {}).get("subject_comparison_price"),
                    "subject_parcel_id": (d.get("data", {}).get("subject_parcel") or {}).get("parcel_id"),
                    "valuation_date": c.get("valuation_date"),
                    "n_comparables": len(d.get("data", {}).get("comparables") or []),
                    "archived": bool(d.get("archived")),
                    "last_action": _last_action(d["id"])})
    return sorted(out, key=lambda x: x["opened_at"] or x["updated_at"] or "", reverse=True)


def _last_action(cid: str) -> dict | None:
    from app.audit import read
    rows = read(cid, limit=1)
    if not rows:
        return None
    e = rows[0]
    return {"at": e.get("at"), "actor": e.get("actor_label"), "action": e.get("action_label")}


def pick_rulesets(land_use: str | None) -> dict:
    """依用地別挑基準表：先找正式表（非 demo_），再退回示範表，最後金山商業表。"""
    from app.engine.rules import RULES_DIR
    found: dict[str, str] = {}
    cands = sorted(RULES_DIR.glob("*.json"), key=lambda p: (p.name.startswith("demo_"), p.name.startswith("uploaded_"), p.name))
    for p in cands:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sc = d.get("scope")
        if sc in ("regional", "individual") and sc not in found and (not land_use or d.get("land_use") == land_use):
            found[sc] = d["id"]
    return {"regional": found.get("regional", "jinshan_commercial_regional"), "individual": found.get("individual", "jinshan_commercial_individual")}


def new_case(*, case_no: str, valuation_date: str, district: str, land_use: str, section_id: str, range_desc: str = "",
             subject_parcel_id: str = "", name: str | None = None) -> dict:
    """從零建案：只有案件基本資料與區段資訊，其餘欄位空白（勘查表可依圖資推算；比較標的待填）。"""
    data = {
        "case": {"case_no": case_no, "valuation_date": valuation_date, "district": district, "land_use": land_use, "rulesets": pick_rulesets(land_use)},
        "sections": {section_id: {"section_id": section_id, "range_desc": range_desc,
                                  "survey": {"land_control": {}, "transport": {}, "natural": {}, "public": {}, "special": {}, "pollution": {}, "commerce": {}, "other": None}}},
        "subject_parcel": {"parcel_id": subject_parcel_id, "section_id": section_id, "nuisance": None},
        "comparables": [],
    }
    return save_case(data, name=name or f"{case_no} {district} {section_id}", origin="manual")


def touch_opened(cid: str) -> None:
    """記錄最近開啟時間（列表排序用），不算修改。"""
    _load_all()
    rec = _mem.get(cid)
    if rec:
        rec["opened_at"] = _now()
        (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")


def patch_case(cid: str, **fields: Any) -> dict | None:
    """更新狀態／名稱／裁決／抽取資訊，不動案件資料。"""
    _load_all()
    rec = _mem.get(cid)
    if not rec:
        return None
    for k, v in fields.items():
        if v is None:
            continue
        if k == "status" and v not in STATUSES:
            raise ValueError(f"status 須為 {STATUSES}")
        rec[k] = v
    rec["updated_at"] = _now()
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def duplicate_case(cid: str, name: str | None = None) -> dict | None:
    _load_all()
    src = _mem.get(cid)
    if not src:
        return None
    return save_case(copy.deepcopy(src["data"]), name=name or f"{src.get('name')}（複本）", origin=f"copy:{cid}",
                     submitted_table5=copy.deepcopy(src.get("submitted_table5")), submitted_table4=copy.deepcopy(src.get("submitted_table4")),
                     extraction=copy.deepcopy(src.get("extraction")), decisions=copy.deepcopy(src.get("decisions") or {}))


def get_case(cid: str) -> dict | None:
    _load_all()
    return _mem.get(cid)


def input_hash(data: Any, t5: Any, t4: Any) -> str:
    """輸入指紋：案件資料＋送審書表填載值。產出（outputs）記下產生當時的指紋，不一致＝產出已過期。"""
    return hashlib.sha1(json.dumps([data, t5, t4], ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def save_case(data: dict, *, name: str | None = None, cid: str | None = None, origin: str = "manual",
              submitted_table5: Any = None, submitted_table4: Any = None, extraction: Any = None, status: str | None = None,
              decisions: Any = None) -> dict:
    _load_all()
    prev = _mem.get(cid) if cid else None
    cid = cid or re.sub(r"[^A-Za-z0-9_-]", "", (data.get("case", {}).get("case_no") or "")) + "-" + uuid.uuid4().hex[:6]
    h = input_hash(data, submitted_table5, submitted_table4)
    changed = not prev or prev.get("input_hash") != h
    rec = {"id": cid, "name": name or (prev or {}).get("name") or data.get("case", {}).get("case_no") or cid,
           "origin": (prev or {}).get("origin", origin), "created_at": (prev or {}).get("created_at") or _now(), "updated_at": _now(),
           "opened_at": (prev or {}).get("opened_at") or _now(),
           "status": status or (prev or {}).get("status", "draft"),
           "data": data, "submitted_table5": submitted_table5, "submitted_table4": submitted_table4,
           "extraction": extraction if extraction is not None else (prev or {}).get("extraction"),
           "decisions": decisions if decisions is not None else (prev or {}).get("decisions") or {},
           # 原始輸入快照（載入／上傳當時），「重置案件」回到這裡；舊案件第一次存檔時補建
           "original": (prev or {}).get("original") or {"data": copy.deepcopy(data), "submitted_table5": copy.deepcopy(submitted_table5),
                                                          "submitted_table4": copy.deepcopy(submitted_table4), "at": _now()},
           "input_hash": h,
           "input_updated_at": _now() if changed else (prev or {}).get("input_updated_at") or (prev or {}).get("updated_at") or _now(),
           "outputs": (prev or {}).get("outputs")}      # {generated_at, input_hash, summary, findings_keys}
    _mem[cid] = rec
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def set_archived(cid: str, archived: bool) -> dict | None:
    """封存＝從清單隱藏、不能再改；可復原。取代刪除，避免誤刪。"""
    _load_all()
    rec = _mem.get(cid)
    if not rec:
        return None
    rec["archived"] = archived
    rec["updated_at"] = _now()
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def delete_case(cid: str) -> bool:
    _load_all()
    if cid not in _mem:
        return False
    _mem.pop(cid)
    p = CASES_DIR / f"{cid}.json"
    if p.exists():
        p.unlink()
    return True


def delete_all_cases() -> dict:
    """重置所有案件：清記憶體與 data/cases/*.json（含封存案件），連同各案的操作紀錄與匯入的地籍圖／區段圖檔。回傳移除數量。"""
    _load_all()
    ids = list(_mem.keys())
    _mem.clear()
    n_files = 0
    if CASES_DIR.exists():
        for p in CASES_DIR.glob("*.json"):
            try:
                p.unlink()
                n_files += 1
            except OSError:
                pass
    n_aux = 0
    for d in (CASES_DIR.parent / "audit", CASES_DIR.parent / "cadastre" / "cases"):
        if not d.exists():
            continue
        for p in list(d.glob("*.jsonl")) + list(d.glob("*.geojson")):
            try:
                p.unlink()
                n_aux += 1
            except OSError:
                pass
    return {"cases": len(ids), "files": n_files, "aux_files": n_aux}


# ------------------------------------------------------------------ demo 變體


def _submitted_from_expected(fx: dict) -> tuple[dict, dict]:
    exp5, exp4 = fx["expected"]["table5"], fx["expected"]["table4"]
    t5 = {1: {"levels": {k: {"subject": v, "comparable": v, "pct": 0.0} for k, v in exp5["subject_levels"].items()},
              "group_subtotals": {str(i + 1): v for i, v in enumerate(exp5["comparable_1"]["group_subtotals"])},
              "total_pct": exp5["comparable_1"]["total_pct"]}}
    t4 = {"comparables": {1: copy.deepcopy(exp4["comparable_1"])}, "subject_comparison_price": exp4["subject_comparison_price"]}
    return t5, t4


def demo_case(variant: str = "template") -> dict:
    """回傳 {"data", "submitted_table5", "submitted_table4", "name", "notes"}。"""
    if variant == "shulin":                                            # 決賽題目：樹林區普通住宅用地（題目 PDF 的填載值，其餘待圖資與地籍圖）
        fx = json.loads((FIXTURES_DIR / "shulin_case_1110901.json").read_text(encoding="utf-8"))
        data = {k: copy.deepcopy(fx[k]) for k in ("case", "sections", "subject_parcel", "comparables")}
        return {"data": data, "submitted_table5": None, "submitted_table4": None, "name": "決賽題目：新北市樹林區普通住宅用地（P001-00 比準地樹德段1415）", "variant": variant,
                "notes": ["題目只給四個區段勘查表的部分欄位、三個比較標的的單價與期日調整率；設施距離、宗地個別因素待地籍圖與圖資推算。表5-1 使用分區、建蔽率、容積率依題目備註免修正。"]}
    fx = json.loads((FIXTURES_DIR / "sample_case_P002-00.json").read_text(encoding="utf-8"))
    data = {k: copy.deepcopy(fx[k]) for k in ("case", "sections", "subject_parcel", "comparables")}
    geo_path = FIXTURES_DIR / "sample_geometry_P002-00.json"
    notes: list[str] = []
    if geo_path.exists():
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
        for sid, g in (geo.get("sections") or {}).items():
            if sid in data["sections"]:
                data["sections"][sid].update(g)
        if geo.get("subject_parcel"):
            data["subject_parcel"].update(geo["subject_parcel"])
        for c in data["comparables"]:
            g = (geo.get("comparables") or {}).get(str(c["comp_no"]))
            if g:
                c.update(g)
        notes.append(geo.get("note", ""))
    t5, t4 = _submitted_from_expected(fx)
    name = "範例：新北市金山區 P002-00 地價區段（商業用地）"
    if variant == "tampered":
        name = "範例：含填載錯誤之送審書表（金山區 P002-00）"
        t4["comparables"][1]["individual"]["14"] = 2.5                 # 面前道路寬度 6m 填成 12m 那格的差異率
        t4["comparables"][1]["regional_adjustment_pct"] = 1.0          # 區域因素抄錯到表4
        t5[1]["group_subtotals"]["2"] = 1.0                            # 交通運輸小計加錯
        t5[1]["total_pct"] = 1.0
        data["comparables"][0]["transaction_date"] = "113.05.28"       # 超過 §17 一年放寬 → error
        notes.append("錯誤位置：比較法調查估價表比較標的1 第14項差異率 5.00→2.50；區域因素分析明細表交通運輸(2)小計 0→1.00 與總修正數 1.00；區域因素調整百分率 0→1.00；交易日期 114.05.28→113.05.28")
    elif variant == "blank_survey":
        name = "範例：僅有年期、區段編號、區段範圍之勘查表（金山區 P002-00）"
        sec = data["sections"]["P002-00"]
        basic = {k: sec.get(k) for k in ("section_id", "geometry", "geometry_source", "geometry_note", "status", "range_desc", "survey_date")}
        data["sections"]["P002-00"] = {**{k: v for k, v in basic.items() if v is not None},
                                       "survey": {"land_control": {}, "transport": {}, "natural": {}, "public": {}, "special": {}, "pollution": {}, "commerce": {}, "other": None}}
        for k in ("school", "market", "park", "station", "commercial_district"):
            data["subject_parcel"][k] = None
        data["subject_parcel"]["nuisance"] = None
        t5, t4 = None, None
        notes.append("勘查表除年期、區段編號、區段範圍外皆空白，宗地個別因素清冊之接近條件亦未填。於「地價區段勘查表」頁按「依圖資推算」，系統依使用分區圖、路網、設施資料庫填入可推算之欄位，其餘列為需人工填載。")
    elif variant == "residential":
        name = "範例：改用住宅用地評價基準明細表（示範表，金山區 P002-00）"
        data["case"]["land_use"] = "住宅用地"
        data["case"]["rulesets"] = {"regional": "demo_residential_regional", "individual": "demo_residential_individual"}
        t5, t4 = None, None
        notes.append("示範用基準表：項目結構依內政部附件24/25 住宅用地、max_pct 為內政部上限、級距沿用金山商業表假設，非正式基準表。勘查表沒有學校／服務性設施／日照等欄位 → 引擎標『需人工確認』而不是猜。")
    return {"data": data, "submitted_table5": t5, "submitted_table4": t4, "name": name, "variant": variant,
            "notes": [n for n in notes if n]}


def set_outputs(cid: str, outputs: dict) -> dict | None:
    """記錄「重新產生書表」的結果指紋、時間與摘要；並把對不到新不符項的裁決標 stale。"""
    _load_all()
    rec = _mem.get(cid)
    if not rec:
        return None
    rec["outputs"] = outputs
    keys = set(outputs.get("findings_keys") or [])
    for k, d in (rec.get("decisions") or {}).items():
        if isinstance(d, dict):
            d["stale"] = k not in keys
    rec["updated_at"] = _now()
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def reset_preview(cid: str) -> dict | None:
    """重置前給使用者看的清單：輸入改了幾處、幾筆裁決、產出時間。"""
    _load_all()
    rec = _mem.get(cid)
    if not rec:
        return None
    from app.audit import diff_paths
    orig = rec.get("original") or {}
    changes = diff_paths({"data": orig.get("data"), "submitted_table5": orig.get("submitted_table5"), "submitted_table4": orig.get("submitted_table4")},
                         {"data": rec.get("data"), "submitted_table5": rec.get("submitted_table5"), "submitted_table4": rec.get("submitted_table4")})
    return {"original_at": orig.get("at"), "n_input_changes": len(changes), "input_changes": changes[:20],
            "n_decisions": len(rec.get("decisions") or {}), "generated_at": (rec.get("outputs") or {}).get("generated_at"),
            "status": rec.get("status", "draft")}


def blank_survey() -> dict:
    return {"land_control": {}, "transport": {}, "natural": {}, "public": {}, "special": {}, "pollution": {}, "commerce": {}, "other": None}


def clear_case(cid: str) -> dict | None:
    """
    清空重填：保留案件基本資料（案號、估價基準日、鄉鎮市區、用地別、基準表、簽章欄、已匯入的地籍圖與區段圖）與區段編號，
    正式區段圖的範圍也保留；宗地、比較標的、勘查表、送審書表、抽取資訊、裁決、產出全部清空，狀態回草稿。
    原始快照改為清空後的狀態，之後「重置」就回到空白。
    """
    _load_all()
    rec = _mem.get(cid)
    if not rec:
        return None
    data = rec["data"]
    case = copy.deepcopy(data.get("case") or {})
    sid = (data.get("subject_parcel") or {}).get("section_id") or next(iter(data.get("sections") or {}), "P001-00")
    old = (data.get("sections") or {}).get(sid) or {}
    sec: dict = {"section_id": sid, "range_desc": "", "survey": blank_survey()}
    if old.get("geometry") is not None and old.get("geometry_source") == "section_map":
        for k in ("geometry", "geometry_source", "geometry_note", "status"):
            if k in old:
                sec[k] = copy.deepcopy(old[k])
    new_data = {"case": case, "sections": {sid: sec}, "subject_parcel": {"parcel_id": "", "section_id": sid, "nuisance": None}, "comparables": []}
    rec["data"] = new_data
    rec["submitted_table5"] = None
    rec["submitted_table4"] = None
    rec["extraction"] = None
    rec["decisions"] = {}
    rec["outputs"] = None
    rec["status"] = "draft"
    rec["original"] = {"data": copy.deepcopy(new_data), "submitted_table5": None, "submitted_table4": None, "at": _now()}
    rec["input_hash"] = input_hash(new_data, None, None)
    rec["input_updated_at"] = _now()
    rec["updated_at"] = _now()
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def reset_case(cid: str) -> dict | None:
    """回到原始輸入快照；清掉裁決、產出；狀態回草稿。extraction（抽取信心）保留。"""
    _load_all()
    rec = _mem.get(cid)
    if not rec or not rec.get("original"):
        return None
    orig = rec["original"]
    keep = {k: copy.deepcopy(v) for k, v in (rec["data"].get("case") or {}).items() if k in ("cadastre", "section_map") and v}
    rec["data"] = copy.deepcopy(orig.get("data"))
    rec["data"].setdefault("case", {}).update(keep)      # 匯入的地籍圖／區段圖檔案不是輸入變更，重置後仍保留
    rec["submitted_table5"] = copy.deepcopy(orig.get("submitted_table5"))
    rec["submitted_table4"] = copy.deepcopy(orig.get("submitted_table4"))
    rec["decisions"] = {}
    rec["outputs"] = None
    rec["status"] = "draft"
    rec["input_hash"] = input_hash(rec["data"], rec["submitted_table5"], rec["submitted_table4"])
    rec["input_updated_at"] = _now()
    rec["updated_at"] = _now()
    (CASES_DIR / f"{cid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec
