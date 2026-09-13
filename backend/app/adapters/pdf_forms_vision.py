"""
pdf_forms 的 vision 備援：頁面 → PNG → app/llm provider → JSON（每欄位帶 confidence）→ 與文字層同樣的中間結構（ctx）。

合併規則：
  slot 空（掃描件）      → 用 vision 結果，confidence 依模型自報（缺 → 0.75）
  slot 已有文字層資料    → 逐葉比對；一致不動；不一致 → 保留文字層並 warning（use_vision="always" 的交叉比對）
"""
from __future__ import annotations

from typing import Any

from app.engine.rules import RuleSet

from .common import (
    AdapterResult,
    flatten,
    leaf_equal,
    make_facility,
    set_path,
    to_bool_有無,
    to_int_if_whole,
    to_number,
)
from .pdf_forms import _T1_MULTI, _T1_NAMED, _T1_SIMPLE, SOURCE_T1, _find_rule, _norm_level

DEFAULT_CONF = 0.75

SYSTEM = (
    "你是臺灣土地徵收補償市價查估書表的資料抽取員。你會看到一頁書表的影像，"
    "請把表上估價師實際填寫的內容逐格抄錄成 JSON，不要推算、不要補值、不要修正錯誤。"
    "看不清楚或空白的欄位填 null，並在 confidence 給低分（0~1）。只輸出 JSON。"
)


def _t1_paths() -> str:
    lines = []
    for lab, (path, kind) in _T1_SIMPLE.items():
        if not path.startswith("extra."):
            lines.append(f"- {path}: {lab}（{ {'num': '數字', 'bool': '有/無→true/false', 'checks': '勾選項目陣列'}.get(kind, '文字') }）")
    lines.append("- transport.main_road_width_m: 主要道路 {name, value}（value=寬度公尺）")
    lines.append("- transport.avg_road_width_m: 區段內道路平均寬度 {value}")
    for lab, (path, _t) in _T1_NAMED.items():
        if not path.startswith("extra."):
            lines.append(f"- {path}: {lab}（設施陣列）")
    for lab, (path, _t) in _T1_MULTI.items():
        lines.append(f"- {path}: {lab}（設施陣列，只列有勾選/有名稱者）")
    return "\n".join(lines)


PROMPT_T1 = """這是「表1 地價區段勘查表」。輸出 JSON：
{"section_id": "區段編號", "valuation_date": "年/期 7 碼", "district": "縣市＋鄉鎮市區", "range_desc": "區段範圍文字",
 "survey": { <path>: <value>, ... }, "confidence": { <path>: 0~1, ... }}
設施陣列的元素格式：{"name": "名稱", "in_section": true/false(●本區段內→true, ●本區段外→false, 未勾→null), "distance_m": 距離公尺或null}
path 清單：
%s
表上「無」或未勾選的設施不要列入陣列（陣列可為空）。"""

PROMPT_T5 = """這是「表5 影響地價區域因素分析明細表」。輸出 JSON：
{"case_no": "案號", "land_use": "標題括號內的用地別", "subject_section_id": "比準地地價區段號",
 "comparables": [{"comp_no": 實例編號(整數), "section_id": "比較標的地價區段號",
    "rows": [{"item": "修正細項名稱（照表抄）", "subject_num": 比準地等級數字, "subject_level": "比準地優劣等級文字",
              "comparable_num": 比較標的等級數字, "comparable_level": "比較標的優劣等級文字", "pct": 修正百分比數字}],
    "group_subtotals": {"1": 小計數字, "2": ..., "8": ...}, "total_pct": 總修正數數字}],
 "confidence": {"rows": 0~1, "subtotals": 0~1}}
沒有填資料的比較標的欄不要列。"""

PROMPT_T4 = """這是「表4 比較法調查估價表」。輸出 JSON：
{"case_no": "案號", "valuation_date": "估價基準日 7 碼", "fill_date": "填寫日期 YYY-MM-DD 或 null",
 "subject": {"serial_no": "宗地流水號", "address": "0基本資料", "section_id": "地價區段", "items": {"7": <cond>, ..., "25": <cond>, "6": <cond>}},
 "comparables": [{"comp_no": 實例編號(整數), "address": "0基本資料", "section_id": "地價區段", "normal_unit_price": 數字,
    "transaction_date": "交易日期", "note": "備註欄該比較標的文字或null", "items": {"7": <cond>, ...},
    "submitted": {"date_adjustment_pct": 數字, "price_at_valuation_date": 數字, "regional_adjustment_pct": 數字,
                  "individual": {"7": 差異率數字或"-", ..., "25": ..., "6": ...}, "individual_total_pct": 數字,
                  "abs_sum_pct": 數字, "similarity": "相近程度文字", "trial_price": 數字, "weight_pct": 數字}}],
 "subject_comparison_price": 數字, "case_note": "備註欄全案文字", "confidence": {"items": 0~1, "prices": 0~1, "pcts": 0~1}}
<cond> 的格式：有名稱與距離的項目 {"name": "名稱", "num": 數字, "unit": "M"}；純數字 {"num": 數字}；純文字 "文字"；「-」→ "-"；空白 → null。
百分比一律填數字（2.00% → 2.0；70% → 70）。"""


def render_png(page, dpi: int = 150) -> bytes:
    return page.get_pixmap(dpi=dpi).tobytes("png")


def run_vision(vision_pages: list, ctx: dict, result: AdapterResult, *, provider=None, regional: RuleSet, individual: RuleSet) -> None:
    from app.llm import LLMError, LLMNotConfigured, get_provider
    try:
        prov = provider or get_provider()
    except LLMNotConfigured as e:
        result.warn(f"這份 PDF 有 {len(vision_pages)} 頁沒有文字層（掃描件），需要語言模型做影像辨識，但系統尚未設定（{e}）。請設定 ANTHROPIC_API_KEY（或 LLM_PROVIDER=bedrock 與 AWS 憑證）後重新上傳，或改上傳文字型 PDF；這些頁的欄位請人工輸入。")
        return
    # 頁數上限（MAX_VISION_PAGES，預設 10）：每頁一次模型呼叫（Bedrock 另有每秒一次節流），沒有上限時一份幾十頁的掃描件會讓一個請求跑半小時以上。
    # 已知是表單的頁（t1／t5／t4）優先，其餘依頁序；超過的頁列警告請人工輸入。
    import os
    cap = int(os.environ.get("MAX_VISION_PAGES", "10") or 10)
    ordered = sorted(vision_pages, key=lambda x: (x[2] == "other", x[0]))
    if len(ordered) > cap:
        skipped = [str(p) for p, _pg, _k in ordered[cap:]]
        result.warn(f"這份檔案有 {len(ordered)} 頁需要影像辨識，超過上限 {cap} 頁；只辨識前 {cap} 頁（表單頁優先），第 {'、'.join(skipped[:15])}{'…' if len(skipped) > 15 else ''} 頁未辨識，欄位請人工輸入或拆檔再上傳")
        ordered = ordered[:cap]
    for pno, page, kind in ordered:
        png = render_png(page)
        prompt = {"t1": PROMPT_T1 % _t1_paths(), "t5": PROMPT_T5, "t4": PROMPT_T4}.get(kind)
        if prompt is None:
            prompt = ("請判斷這頁是哪一種書表：表1 地價區段勘查表 / 表5 影響地價區域因素分析明細表 / 表4 比較法調查估價表 / 地圖 / 其他。"
                      '只輸出 JSON：{"kind": "t1|t5|t4|map|other"}')
            try:
                k = prov.complete_json(prompt, images=[png], system=SYSTEM, max_tokens=200).get("kind")
            except LLMError as e:
                result.warn(f"第 {pno} 頁分類失敗：{e}")
                continue
            if k not in ("t1", "t5", "t4"):
                continue
            kind = k
            prompt = {"t1": PROMPT_T1 % _t1_paths(), "t5": PROMPT_T5, "t4": PROMPT_T4}[kind]
            for pg in result.data["pages"]:
                if pg["page"] == pno:
                    pg["kind"] = kind
        try:
            out = prov.complete_json(prompt, images=[png], system=SYSTEM)
        except LLMError as e:
            result.warn(f"第 {pno} 頁（{kind}）vision 抽取失敗：{e}，請人工輸入")
            continue
        if not isinstance(out, dict):
            result.warn(f"第 {pno} 頁（{kind}）vision 回傳格式不對，略過")
            continue
        conf = out.get("confidence") or {}
        if kind == "t1":
            _apply_t1(out, conf, ctx, result, pno)
        elif kind == "t5":
            _apply_t5(out, conf, ctx, result, regional, pno)
        elif kind == "t4":
            _apply_t4(out, conf, ctx, result, pno)


def _conf(conf: dict, key: str, default: float = DEFAULT_CONF) -> float:
    v = conf.get(key)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _merge(slot_get, slot_set, new: Any, prefix: str, result: AdapterResult, conf: float) -> None:
    cur = slot_get()
    if cur is None or cur == {} or cur == []:
        slot_set(new)
        for path in flatten(new):
            result.confidence[f"{prefix}.{path}"] = conf
        return
    a, b = flatten(cur), flatten(new)
    for k, v in b.items():
        if k not in a:
            continue
        if not leaf_equal(a[k], v):
            result.warn(f"{prefix}.{k}: 文字層「{a[k]}」與 vision「{v}」不一致，採文字層")


def _apply_t1(out: dict, conf: dict, ctx: dict, result: AdapterResult, pno: int) -> None:
    survey: dict[str, Any] = {"land_control": {}, "transport": {}, "natural": {}, "public": {}, "special": {}, "pollution": {}, "commerce": {}, "other": None}
    for path, val in (out.get("survey") or {}).items():
        if isinstance(val, list):
            facs = []
            for f in val:
                if not isinstance(f, dict):
                    continue
                fac = make_facility(f.get("name"), to_number(f.get("distance_m")), ftype=f.get("type"),
                                    in_section=f.get("in_section"), source=SOURCE_T1 + "（vision）")
                if fac:
                    if "type" not in fac:
                        fac["type"] = _default_type(path)
                    facs.append(fac)
            set_path(survey, path, facs)
        elif isinstance(val, dict):
            set_path(survey, path, {k: (to_int_if_whole(to_number(v)) if k in ("value", "width_m", "distance_m") else v) for k, v in val.items()})
        elif path.endswith(("bcr", "far", "shop_ratio_pct")):
            set_path(survey, path, to_int_if_whole(to_number(val)))
        elif path.endswith(("building_prohibited", "building_restricted")):
            set_path(survey, path, val if isinstance(val, bool) else to_bool_有無(val))
        else:
            set_path(survey, path, val)
    sid = out.get("section_id") or f"section_p{pno}"
    sec = {"section_id": sid, "range_desc": out.get("range_desc"), "survey": survey, "level_numbers": {}}
    for k in ("valuation_date", "district"):
        if out.get(k):
            ctx["case"].setdefault(k, out[k])
    per_field = {k: v for k, v in conf.items() if isinstance(v, (int, float))}
    _merge(lambda: ctx["sections"].get(sid), lambda v: ctx["sections"].__setitem__(sid, v), sec, f"sections.{sid}", result,
           DEFAULT_CONF)
    for path, c in per_field.items():
        result.confidence[f"sections.{sid}.survey.{path}"] = float(c)


def _default_type(path: str) -> str:
    for p, t in _T1_NAMED.values():
        if p == path and t:
            return t
    for p, types in _T1_MULTI.values():
        if p == path:
            return types[0]
    return "unknown"


def _apply_t5(out: dict, conf: dict, ctx: dict, result: AdapterResult, regional: RuleSet, pno: int) -> None:
    if out.get("land_use") and not ctx["case"].get("land_use"):
        ctx["case"]["land_use"] = out["land_use"] if out["land_use"].endswith("用地") else out["land_use"] + "用地"
    if out.get("case_no"):
        ctx["case"].setdefault("case_no", out["case_no"])
    c_rows = _conf(conf, "rows")
    for comp in out.get("comparables") or []:
        cid = int(to_number(comp.get("comp_no")) or (len(ctx["t5"]) + 1))
        d = {"section_id": comp.get("section_id"), "subject_section_id": out.get("subject_section_id"), "levels": {},
             "group_subtotals": {str(k): to_number(v) for k, v in (comp.get("group_subtotals") or {}).items() if to_number(v) is not None},
             "total_pct": to_number(comp.get("total_pct")), "case_no": out.get("case_no")}
        for row in comp.get("rows") or []:
            rule = _find_rule(regional, str(row.get("item") or ""))
            if rule is None:
                result.warn(f"表5(vision) 細項「{row.get('item')}」對不到基準表，略過")
                continue
            d["levels"][rule.id] = {
                "subject": _norm_level(rule, str(row.get("subject_level") or "")),
                "comparable": _norm_level(rule, str(row.get("comparable_level") or "")),
                "subject_num": int(to_number(row.get("subject_num"))) if to_number(row.get("subject_num")) is not None else None,
                "comparable_num": int(to_number(row.get("comparable_num"))) if to_number(row.get("comparable_num")) is not None else None,
                "pct": to_number(row.get("pct")),
            }
        _merge(lambda _c=cid: ctx["t5"].get(_c), lambda v, _c=cid: ctx["t5"].__setitem__(_c, v), d, f"submitted.table5.{cid}", result, c_rows)


def _cond(v: Any) -> Any:
    if isinstance(v, dict):
        if v.get("num") is None and v.get("name") is None:
            return None
        if v.get("num") is not None and v.get("name") is None and v.get("unit") is None:
            return to_int_if_whole(to_number(v["num"]))
        return {"name": v.get("name"), "num": to_int_if_whole(to_number(v.get("num"))), "unit": v.get("unit") or ""}
    return v


def _apply_t4(out: dict, conf: dict, ctx: dict, result: AdapterResult, pno: int) -> None:
    subj = out.get("subject") or {}
    t4 = {"case_no": out.get("case_no"), "valuation_date": out.get("valuation_date"), "fill_date": out.get("fill_date"),
          "subject": {"serial_no": subj.get("serial_no"), "address": subj.get("address"), "section_id": subj.get("section_id"),
                      "items": {int(k): _cond(v) for k, v in (subj.get("items") or {}).items() if str(k).isdigit()}},
          "comparables": {}, "submitted": {"comparables": {}, "subject_comparison_price": to_number(out.get("subject_comparison_price"))},
          "notes": {"subject": None, "case": out.get("case_note")}}
    for i, comp in enumerate(out.get("comparables") or []):
        cid = int(to_number(comp.get("comp_no")) or (i + 1))
        t4["comparables"][cid] = {"comp_no": cid, "address": comp.get("address"), "section_id": comp.get("section_id"),
                                  "normal_unit_price": to_number(comp.get("normal_unit_price")),
                                  "transaction_date": comp.get("transaction_date"), "note": comp.get("note"),
                                  "items": {int(k): _cond(v) for k, v in (comp.get("items") or {}).items() if str(k).isdigit()}}
        s = comp.get("submitted") or {}
        sub = {k: to_number(s.get(k)) for k in ("date_adjustment_pct", "price_at_valuation_date", "regional_adjustment_pct",
                                                 "individual_total_pct", "abs_sum_pct", "trial_price", "weight_pct") if s.get(k) is not None}
        if s.get("similarity"):
            sub["similarity"] = s["similarity"]
        sub["individual"] = {str(k): ("-" if v in ("-", "－") else to_number(v)) for k, v in (s.get("individual") or {}).items()}
        t4["submitted"]["comparables"][cid] = sub
    c = min(_conf(conf, "items"), _conf(conf, "prices"), _conf(conf, "pcts"))
    _merge(lambda: ctx["t4"], lambda v: ctx.__setitem__("t4", v), t4, "table4", result, c)
    result.confidence["submitted.table4"] = min(_conf(conf, "prices"), _conf(conf, "pcts"))
    result.confidence["subject_parcel"] = _conf(conf, "items")
