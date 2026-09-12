"""
審查意見書產生器。

原則（CLAUDE.md）：意見書的每一句話都要能對回一條 finding（[F-001] 標籤），法源引用手冊審查重點條號與辦法條號；
數字全部來自引擎與估價師填值，LLM 只負責把模板句改寫成公文語氣，改寫後要通過守門：
  1. 每個 [F-xxx] 標籤都還在、沒有多出不存在的標籤
  2. 沒有出現原文沒有的數字（避免幻覺改數）
守門不過 → 退回模板文字並記 warning。沒有 LLM（未設 key）→ 直接輸出模板文字，功能不受影響。

審查重點條號（手冊 p.11–13）→ 章節標題：
  iii 勘查表　v 買賣實例　vi 表5 區域因素　vii 表4 比較法　ix 比準地地價估計表　x 宗地市價估計表　p.53(十二) 尾數
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

CHECKLIST_TITLES = {
    "iii": "地價區段勘查表 — 審查重點 iii",
    "iv": "地價區段劃設與圖說 — 審查重點 iv",
    "v": "買賣實例蒐集與正常單價 — 審查重點 v",
    "vi": "影響地價區域因素分析明細表 — 審查重點 vi",
    "vii": "比較法調查估價表 — 審查重點 vii",
    "ix": "比準地地價估計表 — 審查重點 ix",
    "x": "宗地市價估計表 — 審查重點 x",
    "p.53(十二)": "比準地比較價格尾數 — 手冊 p.53（十二）",
}
SEVERITY_LABEL = {"error": "不符", "warn": "需確認", "info": "備註"}
KIND_LABEL = {"gap": "資料缺口", "inferred": "需確認（依推定值核算）"}
SEVERITY_ORDER = {"error": 0, "warn": 1, "info": 2}


@dataclass
class OpinionItem:
    fid: str
    severity: str
    checklist: str
    table: str
    location: str
    sentence: str            # 模板句（含 [F-xxx]）
    submitted: str | None
    computed: str | None
    basis: str | None
    polished: str | None = None
    decision: str | None = None      # accept | reject | pending（承辦裁決）
    decision_note: str | None = None


@dataclass
class OpinionReport:
    case_no: str
    subject_parcel_id: str
    valuation_date: str
    review_date: str
    reviewer: str
    counts: dict[str, int]
    conclusion: str
    conclusion_code: str     # pass | revise | confirm
    sections: dict[str, list[OpinionItem]]
    computed_summary: dict[str, Any]
    notes: list[str] = field(default_factory=list)
    polish: dict[str, Any] = field(default_factory=dict)
    figures: list[dict] = field(default_factory=list)   # [{mode, title, url}] 圖說（意見書附圖）

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _fmt(v: Any) -> str:
    if v is None or v == "":
        return "—"
    return str(v)


def sentence_for(f: dict, fid: str, has_submitted: bool = True) -> str:
    """finding → 一句可讀的意見；數字照 finding 原字串，不重算。
    沒有送審書表（依地號產生的案件）時不寫「估價師填載」，改寫「目前」。"""
    sev = KIND_LABEL.get(f.get("kind") or "", SEVERITY_LABEL.get(f["severity"], f["severity"]))
    loc = f"{TABLE_NAMES.get(f.get('table') or '', f.get('table') or '')}「{f.get('location') or ''}」".strip()
    sub, comp, basis = f.get("submitted"), f.get("computed"), f.get("basis")
    core = f.get("message") or ""
    if sub not in (None, "") and comp not in (None, ""):
        body = f"{loc}：估價師填載 {sub}，依規則核算應為 {comp}，{core}" if has_submitted else f"{loc}：目前 {sub}，依規定應為 {comp}，{core}"
    elif comp not in (None, ""):
        body = f"{loc}：核算值 {comp}，{core}"
    else:
        body = f"{loc}：{core}"
    if basis:
        body += f"（依據：{basis}）"
    return f"[{fid}] {sev}：{body}。"


def finding_key(f: dict) -> str | None:
    """與前端 findingKey 一致：表5 → 5:{comp}:{rule_id}；表4 → 4:{comp}:{item_no}；其餘用位置字串。"""
    if f.get("table") == "表5" and f.get("rule_id"):
        return f"5:{f.get('comp_no') or ''}:{f['rule_id']}"
    if f.get("table") == "表4" and f.get("item_no") is not None:
        return f"4:{f.get('comp_no') or ''}:{f['item_no']}"
    return f"loc:{f.get('table')}:{f.get('location')}"


TABLE_NAMES = {"表1": "地價區段勘查表", "表5": "影響地價區域因素分析明細表", "表4": "比較法調查估價表"}
DECISION_LABEL = {"accept": "承辦裁決：接受估價單位填載", "reject": "承辦裁決：維持不符，請補正", "pending": "承辦裁決：待處理"}


def build_report(case: dict, findings: list[dict], computed: dict | None = None, *, subject_parcel_id: str = "",
                 reviewer: str = "", review_date: str | None = None, decisions: dict | None = None,
                 figures: list[dict] | None = None, has_submitted: bool = True) -> OpinionReport:
    fs = sorted(findings, key=lambda f: (SEVERITY_ORDER.get(f.get("severity"), 9), f.get("checklist") or "", f.get("location") or ""))
    counts = {"error": 0, "warn": 0, "info": 0}
    sections: dict[str, list[OpinionItem]] = {}
    for i, f in enumerate(fs, start=1):
        fid = f"F-{i:03d}"
        counts[f.get("severity", "info")] = counts.get(f.get("severity", "info"), 0) + 1
        item = OpinionItem(fid, f.get("severity", "info"), f.get("checklist") or "其他", f.get("table") or "", f.get("location") or "",
                           sentence_for(f, fid, has_submitted), _fmt(f.get("submitted")) if f.get("submitted") is not None else None,
                           _fmt(f.get("computed")) if f.get("computed") is not None else None, f.get("basis"))
        d = (decisions or {}).get(finding_key(f) or "")
        if has_submitted and d and d.get("decision") in DECISION_LABEL:
            item.decision, item.decision_note = d["decision"], d.get("note")
            extra = "；".join(x for x in [d.get("note") or "", f"裁決人 {d['by']}" if d.get("by") else ""] if x)
            item.sentence = item.sentence.rstrip("。") + f"。{DECISION_LABEL[d['decision']]}" + (f"（{extra}）" if extra else "") + "。"
        sections.setdefault(item.checklist, []).append(item)
    accepted = sum(1 for its in sections.values() for it in its if it.severity == "error" and it.decision == "accept")
    if not has_submitted:
        # 依地號產生的書表：沒有估價單位填載可比對，error 是資料缺口，不是「不符」
        if counts["error"]:
            code, concl = "incomplete", (f"本案為依地號產生之書表，尚無估價單位送審書表可比對；目前有 {counts['error']} 項資料缺口待補（如比較標的），"
                                         f"另有 {counts['warn']} 項系統推定或格式事項需確認；補齊並重新產生書表後方可作為查估書表輸出。")
        elif counts["warn"]:
            code, concl = "confirm", f"本案為依地號產生之書表，尚無估價單位送審書表可比對；各項等級與價格鏈經核算一致，另有 {counts['warn']} 項系統推定或格式事項請確認後輸出。"
        else:
            code, concl = "pass", "本案為依地號產生之書表，各項等級、修正率、加總與尾數經核算均與作業手冊及基準明細表相符。"
    elif counts["error"] - accepted > 0:
        code, concl = "revise", (f"本案經核算有 {counts['error']} 項與作業手冊及基準明細表不符"
                                 + (f"，其中 {accepted} 項經承辦審酌接受估價單位填載，餘 {counts['error'] - accepted} 項" if accepted else "，")
                                 + f"請估價單位補正後再送審；另有 {counts['warn']} 項需確認事項。")
    elif counts["error"]:
        code, concl = "confirm", f"本案核算有 {counts['error']} 項與基準明細表不符，均經承辦審酌接受估價單位填載（理由如各條所述）；另有 {counts['warn']} 項需確認事項。"
    elif counts["warn"]:
        code, concl = "confirm", f"本案各項等級、修正率、加總與跨表抄填經核算均相符；另有 {counts['warn']} 項推定或格式事項請估價單位於備註欄敘明或確認。"
    else:
        code, concl = "pass", "本案各項等級、修正率、加總、跨表抄填與尾數經核算均與作業手冊及基準明細表相符，審查通過。"
    summary: dict[str, Any] = {}
    if computed:
        t4 = computed.get("table4") or {}
        summary = {"subject_comparison_price": t4.get("subject_comparison_price"), "subject_land_price": t4.get("subject_land_price"),
                   "comparables": [{"comp_no": c.get("comp_no"), "trial_price": round(c["trial_price"]) if c.get("trial_price") else None,
                                    "individual_total_pct": c.get("individual_total_pct"), "regional_adjustment_pct": c.get("regional_adjustment_pct"),
                                    "weight_pct": c.get("weight_pct")} for c in t4.get("comparables", [])],
                   "table5_totals": {str(k): v.get("total_pct") for k, v in (computed.get("table5") or {}).items()}}
    return OpinionReport(case_no=case.get("case_no", ""), subject_parcel_id=subject_parcel_id, valuation_date=case.get("valuation_date", ""),
                         review_date=review_date or datetime.now(tz=timezone(timedelta(hours=8))).date().isoformat(), reviewer=reviewer, counts=counts, conclusion=concl,
                         conclusion_code=code, sections=sections, computed_summary=summary, figures=list(figures or []))


def to_markdown(r: OpinionReport, use_polished: bool = True) -> str:
    lines = ["# 土地徵收補償市價查估案件審查意見書", "",
             f"- 案號：{r.case_no}", f"- 比準地：{r.subject_parcel_id or '—'}", f"- 估價基準日：{r.valuation_date}",
             f"- 審查日期：{r.review_date}", f"- 審查人：{r.reviewer or '—'}", "",
             "## 一、審查結論", "", r.conclusion, "",
             f"不符 {r.counts.get('error', 0)} 項、需確認 {r.counts.get('warn', 0)} 項、備註 {r.counts.get('info', 0)} 項。", ""]
    if r.computed_summary and (r.computed_summary.get("comparables") or r.computed_summary.get("subject_comparison_price") is not None):
        s = r.computed_summary
        lines += ["## 二、核算摘要", ""]
        for c in s.get("comparables", []):
            lines.append(f"- 比較標的{c['comp_no']}：區域因素調整 {c['regional_adjustment_pct']}%、個別因素合計 {c['individual_total_pct']}%、"
                         f"試算價格 {c['trial_price']:,} 元/m²、權重 {c['weight_pct']}%")
        if s.get("subject_comparison_price") is not None:
            lines.append(f"- 比準地比較價格 {int(s['subject_comparison_price']):,} 元/m²（四捨五入至個位，手冊 p.53（十二））")
        if s.get("subject_land_price") is not None:
            lines.append(f"- 比準地地價（僅比較法，依查估辦法 §21 尾數進位）{int(s['subject_land_price']):,} 元/m²")
        lines.append("")
    lines += ["## 三、逐項意見", ""]
    if not r.sections:
        lines.append("（無）")
    for key, items in r.sections.items():
        lines += [f"### {CHECKLIST_TITLES.get(key, key)}", ""]
        for it in items:
            lines.append(f"- {(it.polished if use_polished and it.polished else it.sentence)}")
        lines.append("")
    if r.figures:
        lines += ["## 四、圖說", ""]
        for fg in r.figures:
            lines.append(f"![{fg.get('title', '')}]({fg.get('url', '')})")
        lines += ["", "（區段略圖、使用分區圖、地價區段圖由系統依區段範圍、宗地位置、設施量測與使用分區圖資產生；底圖 © 國土測繪中心。）", ""]
    if r.polish:
        lines += ["---", f"文字潤稿：{r.polish.get('status')}（{r.polish.get('provider') or '無 LLM'}）" + (f"；{r.polish['note']}" if r.polish.get("note") else ""), ""]
    lines += ["---", "本意見書由規則引擎依作業手冊與基準明細表核算產生，各條意見標籤 [F-xxx] 對應系統 findings；數字未經人工修改。"]
    return "\n".join(lines)


# ------------------------------------------------------------------ LLM 潤稿（有守門）

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
_TAG_RE = re.compile(r"\[F-\d{3}\]")

POLISH_SYSTEM = ("你是地政機關的審查人員，負責把系統產生的審查意見改寫成正式、簡潔的公文語氣（繁體中文）。"
                 "規則：每一條保留開頭的 [F-xxx] 標籤；不得新增、刪除或更改任何數字、百分比、金額、條號、表號；不得新增意見或推論；"
                 "一條一行，順序不變，不加標題與說明。只輸出改寫後的條列。")


def polish_items(items: list[OpinionItem], provider) -> dict[str, Any]:
    """用 LLM 改寫語氣；守門失敗（標籤或數字不符）→ 保留模板句。回傳狀態摘要。"""
    if not items:
        return {"status": "skipped", "note": "沒有意見需要潤稿"}
    src = "\n".join(it.sentence for it in items)
    try:
        text = provider.complete(f"請改寫下列審查意見：\n\n{src}", system=POLISH_SYSTEM, max_tokens=4000).text
    except Exception as e:  # noqa: BLE001 — LLM 任何錯誤都不能影響意見書產出
        return {"status": "failed", "note": f"LLM 呼叫失敗：{e}", "provider": getattr(provider, "name", None)}
    out_lines = [l.strip().lstrip("-•* ").strip() for l in text.splitlines() if _TAG_RE.search(l)]
    by_tag = {_TAG_RE.search(l).group(0): l for l in out_lines}
    ok, rejected = 0, []
    for it in items:
        tag = f"[{it.fid}]"
        cand = by_tag.get(tag)
        if not cand:
            rejected.append(f"{it.fid}: 潤稿缺少此條")
            continue
        src_nums = set(_NUM_RE.findall(it.sentence))
        new_nums = set(_NUM_RE.findall(cand)) - set(_NUM_RE.findall(tag))
        extra = new_nums - src_nums - {n for n in _NUM_RE.findall(tag)}
        if extra:
            rejected.append(f"{it.fid}: 出現原文沒有的數字 {sorted(extra)}")
            continue
        if len(_TAG_RE.findall(cand)) != 1:
            rejected.append(f"{it.fid}: 標籤數量不對")
            continue
        it.polished = cand
        ok += 1
    return {"status": "ok" if not rejected else ("partial" if ok else "rejected"), "polished": ok, "rejected": rejected,
            "provider": getattr(provider, "name", None), "model": getattr(provider, "model", None)}
