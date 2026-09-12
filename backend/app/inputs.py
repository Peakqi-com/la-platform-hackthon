"""
一個案件、多份輸入檔。

每份檔併入同一案件後記在 rec["inputs"]（檔名、種類、時間、操作者、併入摘要、缺漏、衝突、覆蓋），原檔存在
data/cases/<id>/inputs/ 供「移除輸入檔」時重新併入其餘檔案。這裡只放純函式（資料 → 資料），檔案讀寫與端點在 app/main.py。

合併規則（docs/03_data_schema.md「inputs」節）：
- 書表 PDF：區段、送審表5／表4 依區段編號、實例編號**聯集**；比準地只在空白時填入；比較標的依實例編號併入。
  同一格兩份檔給不同值 → 先來者留、後來者記 conflicts（審查頁列「輸入檔不一致」），不自動裁決。
- 清冊／實例 xlsx：依地號（實例編號）對到比準地與比較標的，覆蓋檔案裡有值的欄位（清冊是宗地屬性的權威來源），
  被覆蓋的欄位記 overrides；對不到的列 unmatched。
- 案件層欄位（案號、基準日、用地別、鄉鎮市區、簽章）以第一份為準，後來不一致記 conflicts 不覆蓋。
- 幾何（geometry 等）不由書表 PDF 合併覆蓋，地籍圖／區段圖各有匯入流程。
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

KIND_LABELS = {"pdf_forms": "送審書表 PDF", "parcels": "宗地個別因素清冊", "comparables": "買賣實例", "rules_table": "評價基準明細表",
               "cadastre": "地籍圖", "section_map": "地價區段圖"}
PAGE_LABELS = {"t1": "勘查表", "t5": "區域因素分析表", "t4": "比較法估價表", "map": "圖說", "other": "其他"}
CASE_KEYS = ("case_no", "valuation_date", "land_use", "district", "fill_date", "appraiser")
GEOM_KEYS = ("geometry", "geometry_source", "geometry_note", "status", "derived")
SKIP_ALWAYS = ("provenance",)
# 案件清單「輸入資料」徽章：鍵、顯示名
COMPONENTS = [("t1", "勘查表"), ("t5", "表5"), ("t4", "表4"), ("parcels", "清冊"), ("comparables", "實例"),
              ("rules", "基準表"), ("cadastre", "地籍圖"), ("section_map", "區段圖")]
COMPONENT_FULL = {"t1": "地價區段勘查表", "t5": "影響地價區域因素分析明細表", "t4": "比較法調查估價表", "parcels": "宗地個別因素清冊", "comparables": "買賣實例",
                  "rules": "評價基準明細表", "cadastre": "地籍圖", "section_map": "地價區段圖"}


@dataclass
class MergeReport:
    filled: list[str] = field(default_factory=list)          # 從空白填入的欄位路徑
    overrides: list[dict] = field(default_factory=list)      # 清冊／實例覆蓋既有值：{path, old, new}
    conflicts: list[dict] = field(default_factory=list)      # 書表不一致（保留先來者）：{path, kept, incoming}
    matched: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"filled": self.filled[:200], "overrides": self.overrides[:200], "conflicts": self.conflicts[:200],
                "matched": self.matched, "unmatched": self.unmatched, "notes": self.notes}


def _empty(v: Any) -> bool:
    return v is None or v == "" or v == {} or v == []


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_eq(a[k], b[k]) for k in a)
    return a == b


def _short(v: Any) -> Any:
    """衝突紀錄裡的值：巢狀結構縮成摘要字串，避免案件檔膨脹。"""
    if isinstance(v, (dict, list)):
        s = str(v)
        return s if len(s) <= 120 else s[:117] + "…"
    return v


def _merge_dict(dst: dict, src: dict, path: str, rep: MergeReport, *, skip: tuple[str, ...] = SKIP_ALWAYS) -> None:
    """只補空白；同格不同值記衝突（先來者留）。"""
    for k, v in src.items():
        if k in skip or v is None:
            continue
        p = f"{path}.{k}" if path else str(k)
        cur = dst.get(k)
        if _empty(cur):
            dst[k] = copy.deepcopy(v)
            rep.filled.append(p)
        elif isinstance(cur, dict) and isinstance(v, dict):
            _merge_dict(cur, v, p, rep, skip=skip)
        elif not _eq(cur, v):
            rep.conflicts.append({"path": p, "kept": _short(cur), "incoming": _short(v)})


def _is_blank_section(sec: dict) -> bool:
    if sec.get("range_desc") or sec.get("geometry") is not None:
        return False
    survey = sec.get("survey") or {}
    return all(_empty(v) for v in survey.values())


def _norm_keys(d: dict | None) -> dict:
    return {str(k): v for k, v in (d or {}).items()}


def _comp_no(c: dict) -> int:
    try:
        return int(c.get("comp_no"))
    except (TypeError, ValueError):
        return 10_000


def merge_pdf_forms(data: dict | None, t5: Any, t4: Any, parsed: dict) -> tuple[dict, Any, Any, MergeReport]:
    """把一份書表 PDF 的抽取結果（AdapterResult.data）併入案件資料與送審表。回傳新的 (data, t5, t4, report)；不改傳入物件。"""
    rep = MergeReport()
    data = copy.deepcopy(data) if data else {"case": {}, "sections": {}, "subject_parcel": None, "comparables": []}
    case = data.setdefault("case", {})
    pcase = parsed.get("case") or {}
    for k in CASE_KEYS:
        v = pcase.get(k)
        if _empty(v):
            continue
        cur = case.get(k)
        if _empty(cur):
            case[k] = v
            rep.filled.append(f"case.{k}")
        elif not _eq(cur, v):
            rep.conflicts.append({"path": f"case.{k}", "kept": cur, "incoming": v})
    if _empty(case.get("rulesets")) and pcase.get("rulesets"):
        case["rulesets"] = copy.deepcopy(pcase["rulesets"])
        rep.filled.append("case.rulesets")

    # 區段：聯集；既有唯一區段是空白暫編（從零建案的 P001-00）且書表帶不同編號 → 改用書表的
    secs = data.setdefault("sections", {}) or {}
    data["sections"] = secs
    incoming = parsed.get("sections") or {}
    if incoming and len(secs) == 1:
        old_sid = next(iter(secs))
        if old_sid not in incoming and _is_blank_section(secs[old_sid]):
            secs.pop(old_sid)
            rep.notes.append(f"區段 {old_sid} 為空白暫編，改用書表的區段 {'、'.join(incoming)}")
            subj0 = data.get("subject_parcel") or {}
            if subj0.get("section_id") == old_sid:
                subj0["section_id"] = next(iter(incoming))
    for sid, sec in incoming.items():
        if sid not in secs:
            secs[sid] = copy.deepcopy(sec)
            rep.filled.append(f"sections.{sid}")
        else:
            _merge_dict(secs[sid], sec, f"sections.{sid}", rep, skip=SKIP_ALWAYS + GEOM_KEYS)
    if case.get("fill_date"):                                          # 勘查表頁與表4頁分開的檔：勘查日期補自表4填寫日期（與整份讀取一致）
        for sid, sec in secs.items():
            if _empty(sec.get("survey_date")):
                sec["survey_date"] = case["fill_date"]
                rep.filled.append(f"sections.{sid}.survey_date")

    # 比準地：空白才填；有了就只補空欄
    subj, inc = data.get("subject_parcel"), parsed.get("subject_parcel")
    if inc:
        if not subj or _empty(subj.get("parcel_id")):
            keep = {k: subj[k] for k in GEOM_KEYS if subj and subj.get(k) is not None}
            data["subject_parcel"] = {**copy.deepcopy(inc), **keep}
            rep.filled.append("subject_parcel")
        else:
            _merge_dict(subj, inc, "subject_parcel", rep, skip=SKIP_ALWAYS + GEOM_KEYS)

    # 比較標的：依實例編號
    comps = data.setdefault("comparables", []) or []
    data["comparables"] = comps
    by_no = {str(c.get("comp_no")): c for c in comps}
    for c in parsed.get("comparables") or []:
        key = str(c.get("comp_no"))
        if key in by_no:
            _merge_dict(by_no[key], c, f"comparables[{key}]", rep, skip=SKIP_ALWAYS + GEOM_KEYS)
        else:
            comps.append(copy.deepcopy(c))
            by_no[key] = comps[-1]
            rep.filled.append(f"comparables[{key}]")
    comps.sort(key=_comp_no)

    # 送審表 5／4：依實例編號聯集（鍵一律字串，與 JSON 存檔一致）
    sub = parsed.get("submitted") or {}
    t5n = _norm_keys(copy.deepcopy(t5) if isinstance(t5, dict) else None)
    for cid, d in _norm_keys(sub.get("table5")).items():
        if cid not in t5n:
            t5n[cid] = copy.deepcopy(d)
            rep.filled.append(f"submitted_table5[{cid}]")
        else:
            _merge_dict(t5n[cid], d, f"submitted_table5[{cid}]", rep)
    t4n = copy.deepcopy(t4) if isinstance(t4, dict) else {}
    t4n["comparables"] = _norm_keys(t4n.get("comparables"))
    inc4 = sub.get("table4") or {}
    for cid, d in _norm_keys(inc4.get("comparables")).items():
        if cid not in t4n["comparables"]:
            t4n["comparables"][cid] = copy.deepcopy(d)
            rep.filled.append(f"submitted_table4[{cid}]")
        else:
            _merge_dict(t4n["comparables"][cid], d, f"submitted_table4[{cid}]", rep)
    _merge_dict(t4n, {k: v for k, v in inc4.items() if k != "comparables"}, "submitted_table4", rep)
    if parsed.get("notes") and _empty(data.get("notes")):
        data["notes"] = copy.deepcopy(parsed["notes"])
    t5_out = t5n or None
    t4_out = t4n if (t4n.get("comparables") or any(not _empty(v) for k, v in t4n.items() if k != "comparables")) else None
    return data, t5_out, t4_out, rep


def merge_parcel_list(data: dict, items: list[dict], kind: str) -> MergeReport:
    """清冊（parcels）／買賣實例（comparables）併入：依地號或實例編號對到比準地與比較標的；覆蓋檔案裡有值的欄位並記 overrides。就地修改 data。"""
    rep = MergeReport()
    subj = data.get("subject_parcel") or {}
    comps = data.setdefault("comparables", [])
    by_pid = {str(c.get("parcel_id") or ""): c for c in comps}
    by_no = {str(c.get("comp_no") or ""): c for c in comps}
    for it in items or []:
        pid = str(it.get("parcel_id") or "")
        target, label, path = None, "", ""
        if pid and pid == str(subj.get("parcel_id") or ""):
            target, label, path = subj, f"比準地 {pid}", "subject_parcel"
        elif pid and pid in by_pid:
            target, label, path = by_pid[pid], f"比較標的 {pid}", f"comparables[{by_pid[pid].get('comp_no')}]"
        elif kind == "comparables" and str(it.get("comp_no") or "") in by_no:
            target, label, path = by_no[str(it.get("comp_no"))], f"比較標的{it.get('comp_no')}", f"comparables[{it.get('comp_no')}]"
        elif kind == "comparables" and not _empty(it.get("comp_no")) and pid:
            comps.append(copy.deepcopy(it))                               # 案件還沒有這件實例：新增
            by_pid[pid] = comps[-1]
            by_no[str(it.get("comp_no"))] = comps[-1]
            rep.matched.append(f"新增比較標的{it.get('comp_no')} {pid}")
            rep.filled.append(f"comparables[{it.get('comp_no')}]")
            continue
        if target is None:
            rep.unmatched.append(pid or f"實例編號 {it.get('comp_no')}")
            continue
        n = 0
        for k, v in it.items():
            if k in SKIP_ALWAYS or v is None:
                continue
            cur = target.get(k)
            if _eq(cur, v):
                continue
            if not _empty(cur):
                rep.overrides.append({"path": f"{path}.{k}", "old": _short(cur), "new": _short(v)})
            else:
                rep.filled.append(f"{path}.{k}")
            target[k] = copy.deepcopy(v)
            (target.get("derived") or {}).pop(k, None)                    # 匯入值取代推定值，之後「依地號產生」不再覆寫
            n += 1
        rep.matched.append(f"{label}（{n} 欄）")
    comps.sort(key=_comp_no)
    return rep


def pdf_summary(pages: list[dict], rep: MergeReport, n_comp: int) -> str:
    kinds = [PAGE_LABELS.get(p.get("kind"), p.get("kind")) for p in pages if p.get("kind") in ("t1", "t5", "t4") and p.get("method") not in (None, "none")]
    seen: list[str] = []
    for k in kinds:
        if k not in seen:
            seen.append(k)
    parts = ["、".join(seen) or "未讀到書表頁"]
    if n_comp:
        parts.append(f"比較標的 {n_comp} 件")
    parts.append(f"填入 {len(rep.filled)} 處")
    if rep.conflicts:
        parts.append(f"不一致 {len(rep.conflicts)} 處")
    return "；".join(parts)


def list_summary(rep: MergeReport) -> str:
    s = f"對到 {len(rep.matched)} 筆"
    if rep.overrides:
        s += f"、覆蓋 {len(rep.overrides)} 欄"
    if rep.filled:
        s += f"、填入 {len(rep.filled)} 欄"
    if rep.unmatched:
        s += f"；對不到 {len(rep.unmatched)} 筆（{'、'.join(rep.unmatched[:5])}{'…' if len(rep.unmatched) > 5 else ''}）"
    return s


def aggregate_extraction(inputs: list[dict]) -> dict | None:
    """rec["extraction"]（抽取信心／缺漏／提醒／頁面）由所有書表 PDF 輸入檔彙總；沒有 PDF → None。"""
    pdfs = [i for i in inputs if i.get("kind") == "pdf_forms"]
    if not pdfs:
        return None
    conf: dict[str, float] = {}
    missing: list[str] = []
    warnings: list[str] = []
    pages: list[dict] = []
    for i in pdfs:
        for k, v in (i.get("confidence") or {}).items():
            conf[k] = min(conf[k], v) if k in conf else v
        for m in i.get("missing") or []:
            if m not in missing:
                missing.append(m)
        for w in i.get("warnings") or []:
            if w not in warnings:
                warnings.append(w)
        pages.extend({**p, "file": i.get("filename")} for p in i.get("pages") or [])
    # 後來的檔補上的欄位，就不再算缺漏
    filled = {f for i in inputs for f in (i.get("filled") or [])}
    missing = [m for m in missing if m not in filled and not any(f.startswith((m + ".", m + "[")) for f in filled)]
    return {"confidence": conf, "missing_fields": missing, "warnings": warnings, "pages": pages, "filename": "、".join(i.get("filename") or "" for i in pdfs)}


def inputs_status(rec: dict) -> dict:
    """案件清單與案件列用：這一案輸入了哪些資料（每一項：有／無、來源檔名）。輸入檔之外也看舊流程留下的標記（送審表、地籍圖、區段圖、上傳的基準表）。"""
    inputs = rec.get("inputs") or []
    src: dict[str, str] = {}
    for i in inputs:
        k, fn = i.get("kind"), i.get("filename") or ""
        if k == "pdf_forms":
            for p in i.get("pages") or []:
                if p.get("kind") in ("t1", "t5", "t4") and p.get("method") not in (None, "none"):
                    src.setdefault(p["kind"], fn)
        elif k == "rules_table":
            src.setdefault("rules", fn)
        elif k in ("parcels", "comparables", "cadastre", "section_map"):
            src.setdefault(k, fn)
    case = (rec.get("data") or {}).get("case") or {}
    if rec.get("submitted_table5") and "t5" not in src:
        src["t5"] = "送審書表"
    if rec.get("submitted_table4") and "t4" not in src:
        src["t4"] = "送審書表"
    if case.get("cadastre") and "cadastre" not in src:
        src["cadastre"] = case["cadastre"].get("filename") or "地籍圖"
    if case.get("section_map") and "section_map" not in src:
        src["section_map"] = case["section_map"].get("filename") or "地價區段圖"
    rs = case.get("rulesets") or {}
    if "rules" not in src and any(str(v).startswith("uploaded_") for v in rs.values()):
        src["rules"] = "上傳的基準表"
    kinds: dict[str, int] = {}
    for i in inputs:
        kinds[i.get("kind") or "?"] = kinds.get(i.get("kind") or "?", 0) + 1
    n_conf = sum(len(i.get("conflicts") or []) for i in inputs)
    return {"n": len(inputs), "kinds": kinds, "n_conflicts": n_conf,
            "items": [{"key": k, "label": lbl, "full": COMPONENT_FULL[k], "present": k in src, "source": src.get(k)} for k, lbl in COMPONENTS]}
