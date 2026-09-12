"""
書表文字欄位模板：表4／表5 備註（比準地、各比較標的、全案）與區段範圍描述。

原則（CLAUDE.md）：每一句都由結構化事實產生，數字與條號只引用引擎與資料，不由文字模型產生；
語言模型只做潤飾（polish_text），且守門：數字、百分比、金額、條號、地號不得增刪改，否則退回模板句。
法源引用：期日調整 手冊 p.50 (四)；免修正「－」p.52 (七)2；蒐集期間 §17；其他地區 §19 第2項；權重 p.53 (十一)；尾數 §21。
"""
from __future__ import annotations

import re
from typing import Any

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
_LAW_RE = re.compile(r"§\s?\d+|第\s?\d+\s?[條項款]|p\.\s?\d+")


def _pct(v: Any) -> str:
    return "－" if v is None else f"{float(v):.2f}%"


def comparable_note(c: dict, t4c: dict | None, case: dict) -> str:
    """單一比較標的備註（書表備註欄要放得下，控制在約 200 字）：交易日期與期間、實價登錄編號、含建物之扣除、期日調整、免修正、特殊情況、選取依據。
    完整推導（建物成本公式、指數內插）在買賣實例來源說明與填寫結果清單，不進書表。"""
    parts: list[str] = []
    sel = c.get("selection") or {}
    src = c.get("source") or {}
    if c.get("transaction_date"):
        if sel.get("out_of_window"):
            parts.append(f"交易日期 {c['transaction_date']}，在案例蒐集期間外，依作業手冊 p.77 問答四作為參考案例，理由：{sel.get('reason') or '（未填）'}")
        else:
            parts.append(f"交易日期 {c['transaction_date']}" + ("，在案例蒐集期間內" if sel.get("in_window") else "，依查估辦法第 17 條第 3 項放寬至估價基準日前一年內" if sel.get("in_window") is False else ""))
    if src.get("lvr_id"):
        parts.append(f"內政部實價登錄 {src.get('season') or ''} 編號 {src['lvr_id']}".replace("  ", " "))
    elif not src.get("note") and c.get("normal_unit_price"):
        parts.append(f"土地正常單價 {int(c['normal_unit_price']):,} 元/m²（買賣實例調查估價表）")
    if src.get("building_cost") is not None and src.get("price_total"):
        b = src.get("building") or {}
        whole = b.get("level") == "全" or "透天" in (b.get("type") or "")
        parts.append(f"含建物：房地價格 {float(src['price_total']):,.0f} 元 − 建物成本價格 {float(src['building_cost']):,.0f} 元"
                     + ("（系統依第四號公報成本法推定，需確認）" if "推定" in (src.get("building_cost_source") or "") else "（估價師填載）")
                     + f"，÷ 土地{'' if whole else '持分'}面積 {src.get('area_m2') or c.get('area_m2') or '—'} m²（查估辦法第 13 條第 {4 if whole else 3} 款）")
    da = c.get("date_adjustment") or {}
    if da.get("pct") is not None:
        idx = f"（都市地價指數 {da.get('index_at_transaction')} → {da.get('index_at_valuation')}，手冊 p.50 (四)）" if da.get("index_at_transaction") and da.get("index_at_valuation") else "（手冊 p.50 (四)）"
        parts.append(f"期日調整率 {float(da['pct']):+.2f}%{idx}")
    elif da.get("note"):
        parts.append("期日調整：" + str(da["note"])[:60])
    if t4c:
        skipped = [f"{r.get('item_no')} {r.get('name')}" for r in (t4c.get("rows") or []) if r.get("pct") is None]
        if skipped:
            parts.append(f"免修正 {len(skipped)} 項（以「－」表示，手冊 p.52 (七)2）" + ("：" + "、".join(skipped) if len(skipped) <= 4 else ""))
    flags = sel.get("flags") or []
    if flags:
        parts.append("特殊情況：" + "、".join(f"{_short_flag(f)}（{f.get('rule')}）" for f in flags))
    elif sel.get("flags_text"):
        parts.append("特殊情況：" + "；".join(x.split("：")[0][:16] for x in str(sel["flags_text"]).split("；")[:3]))
    if sel.get("basis"):
        parts.append("選取依據：" + sel["basis"] + (f"，距比準地約 {sel['distance_m']} m" if sel.get("distance_m") is not None else ""))
    return "；".join(parts) + ("。" if parts else "")


def _short_flag(f: dict) -> str:
    kw = f.get("keyword") or ""
    if kw == "房地":
        return "地上有建物（已扣建物成本）"
    if kw:
        return kw
    return (f.get("label") or "")[:12]


def subject_note(subject: dict, case: dict) -> str:
    d = subject.get("derived") or {}
    parts: list[str] = []
    if subject.get("geometry_source") in ("cadastre_file", "nlsc_api"):
        parts.append("宗地界線依地籍圖")
    elif subject.get("geometry_source") == "synthetic":
        parts.append("宗地位置為人工指定、範圍依清冊面積合成示意")
    labels = {"area_m2": "面積", "width_m": "寬度", "depth_m": "深度", "shape": "形狀", "frontage": "臨街情形", "terrain": "地勢", "road_type": "道路種類",
              "front_road": "面前道路", "zoning": "使用分區", "bcr_pct": "建蔽率", "far_pct": "容積率", "building_restricted": "禁限建"}
    inferred = [labels[k] for k in labels if k in d]
    if inferred:
        parts.append(f"系統推定 {len(inferred)} 欄（" + "、".join(inferred) + "），來源見填寫結果清單，請估價人員確認")
    if subject.get("zoning") and (subject.get("bcr_pct") is not None or subject.get("far_pct") is not None):
        parts.append(f"{subject['zoning']}法定建蔽率 {subject.get('bcr_pct') if subject.get('bcr_pct') is not None else '—'}%、容積率 {subject.get('far_pct') if subject.get('far_pct') is not None else '—'}%（手冊 p.51 (六)4）")
    return "；".join(parts) + ("。" if parts else "")


def case_note(data: dict, t4: dict | None) -> str:
    from app.engine.verify import collection_window
    case = data["case"]
    comps = data.get("comparables") or []
    parts: list[str] = []
    win = collection_window(case.get("valuation_date") or "")
    if win:
        parts.append(f"案例蒐集期間 {win[0][0]}.{win[0][1]:02d}.{win[0][2]:02d}～{win[1][0]}.{win[1][1]:02d}.{win[1][2]:02d}（查估辦法第 17 條第 2 項）")
    if comps:
        sid = data["subject_parcel"].get("section_id")
        n_in = sum(1 for c in comps if c.get("section_id") == sid)
        n_out = len(comps) - n_in
        parts.append(f"比較標的 {len(comps)} 件" + (f"，其中 {n_out} 件位於其他地區，已作區域因素調整（查估辦法第 19 條第 2 項）" if n_out else "，皆在同一地價區段"))
        if t4 and t4.get("comparables"):
            ws = [(c.get("comp_no"), c.get("weight_pct"), c.get("abs_sum_pct")) for c in t4["comparables"]]
            parts.append("權重依調整百分率絕對值加總排名（手冊 p.53 (十一)）：" + "、".join(f"比較標的{n} 絕對值加總 {_pct(a)}、權重 {w if w is not None else '—'}%" for n, w, a in ws))
        if t4 and t4.get("subject_comparison_price") is not None:
            parts.append(f"比準地比較價格 {round(t4['subject_comparison_price']):,} 元/m²（四捨五入至個位，手冊 p.53 (十二)）")
        if t4 and t4.get("subject_land_price") is not None:
            parts.append(f"比準地地價 {int(t4['subject_land_price']):,} 元/m²（尾數依查估辦法第 21 條無條件進位）")
    else:
        parts.append("尚無比較標的：實價登錄在蒐集期間與放寬期間內無可採用之純土地實例，請人工填寫買賣實例或採用含建物實例扣除建物成本")
    return "；".join(parts) + ("。" if parts else "")


def build_notes(data: dict, result: dict | None = None) -> dict[str, Any]:
    """{"subject", "comparables": {comp_no: text}, "case"}；案件 case.notes 的人工文字優先。"""
    t4 = result["table4"].to_dict() if result and hasattr(result.get("table4"), "to_dict") else (result or {}).get("table4")
    by_no = {str(c.get("comp_no")): c for c in (t4 or {}).get("comparables", [])}
    manual = data["case"].get("notes") or {}
    notes = {"subject": manual.get("subject") or subject_note(data["subject_parcel"], data["case"]),
             "comparables": {str(c.get("comp_no")): (manual.get("comparables") or {}).get(str(c.get("comp_no"))) or comparable_note(c, by_no.get(str(c.get("comp_no"))), data["case"])
                             for c in data.get("comparables") or []},
             "case": manual.get("case") or case_note(data, t4)}
    return notes


# ---------------------------------------------------------------- 語言模型潤飾（守門：數字、條號不變）

POLISH_SYSTEM = ("你是地政機關承辦人，負責把系統產生的書表備註改寫成通順、正式的公文語氣（繁體中文）。"
                 "規則：不得新增、刪除或更改任何數字、百分比、金額、日期、條號、頁碼、地號與設施名稱；不得新增事實或推論；保持一段文字。只輸出改寫後的文字。")


def guard_ok(src: str, out: str) -> tuple[bool, str]:
    """潤飾後數字集合與條號集合必須與原文相同。"""
    a, b = set(_NUM_RE.findall(src)), set(_NUM_RE.findall(out))
    if a != b:
        return False, f"數字不一致：多 {sorted(b - a)} 少 {sorted(a - b)}"
    la, lb = {x.replace(" ", "") for x in _LAW_RE.findall(src)}, {x.replace(" ", "") for x in _LAW_RE.findall(out)}
    if la != lb:
        return False, f"條號不一致：多 {sorted(lb - la)} 少 {sorted(la - lb)}"
    if not out.strip():
        return False, "潤飾結果為空"
    return True, ""


def polish_text(text: str, provider) -> dict[str, Any]:
    """回傳 {"status": ok|rejected|failed|skipped, "text": 採用的文字, "note"}。失敗一律退回原文。"""
    if not (text or "").strip():
        return {"status": "skipped", "text": text, "note": "無文字"}
    try:
        out = provider.complete(f"請改寫下列文字：\n\n{text}", system=POLISH_SYSTEM, max_tokens=2000).text.strip()
    except Exception as e:  # noqa: BLE001 - 語言模型任何錯誤都不能影響書表
        return {"status": "failed", "text": text, "note": f"語言模型呼叫失敗：{e}"}
    ok, why = guard_ok(text, out)
    return {"status": "ok", "text": out, "note": ""} if ok else {"status": "rejected", "text": text, "note": f"守門未通過，保留模板句（{why}）"}
