"""
填寫結果清單：一鍵產生後，逐欄告訴承辦「填了什麼、依據是什麼、哪些是推定要確認、哪些資料不足留白」。

狀態：
  資料   來自匯入檔、送審書表或人工填載（系統不改）
  量測   系統依設施資料庫與路網量測（Facility.computed）
  推定   系統依地籍界線／路網／分區圖推定（parcel.derived、section.survey_provenance.filled／suggestions），須人工確認
  空白   資料不足，需人工填載
"""
from __future__ import annotations

from typing import Any

from app.engine.rules import RuleSet

PARCEL_EXTRA = [("bcr_pct", "建蔽率(%)"), ("far_pct", "容積率(%)"), ("building_restricted", "有無禁限建"), ("zoning", "使用分區或編定用地")]



_GEOM_SRC_ZH = {"cadastre_file": "地籍圖檔", "nlsc_api": "國土測繪中心地籍 API", "synthetic": "依清冊面積合成", "section_map": "地價區段圖",
                "estimate_osm_block": "路網推估街廓", "manual": "人工點圖", "address": "門牌定位", "road_midpoint": "路段中點"}
_MEASURE_ZH = {"walking": "步行距離", "straight": "直線距離", "straight_estimated": "直線估算距離", "osrm": "步行距離"}
_ORIGIN_ZH = {"parcel_centroid": "宗地中心", "parcel_boundary": "宗地界線", "section_boundary": "區段邊界", "section_centroid": "區段中心", "road_access": "出入口"}


def _measure_note(m: dict) -> str:
    """量測方式與起點的中文說明（畫面用；程式碼值不外露）。"""
    meas = _MEASURE_ZH.get(m.get("measure") or "", m.get("measure") or "")
    org = _ORIGIN_ZH.get(m.get("origin") or "", m.get("origin") or "")
    return f"{meas}，自{org}起算" if org else meas

def _blank(v: Any) -> bool:
    if v is None or v == "" or v == []:
        return True
    if isinstance(v, dict):
        return all(_blank(x) for k, x in v.items() if k not in ("computed", "measure", "origin", "source", "provenance"))
    return False


def _is_measured(v: Any) -> bool:
    if isinstance(v, dict):
        return bool(v.get("computed"))
    if isinstance(v, list) and v:
        return all(isinstance(x, dict) and x.get("computed") for x in v)
    return False


def _display(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "有" if v else "無"
    if isinstance(v, dict):
        if "distance_m" in v:
            return f"{v.get('name') or ''} {v.get('distance_m')} m".strip()
        if "name" in v:
            return f"{v.get('name') or ''}{(' ' + str(v.get('width_m') or v.get('value'))) + ' m' if (v.get('width_m') or v.get('value')) is not None else ''}".strip()
        return str(v.get("value", v))
    if isinstance(v, list):
        return "、".join(_display(x) for x in v[:3]) + ("…" if len(v) > 3 else "")
    return str(v)


def parcel_rows(parcel: dict, individual: RuleSet) -> list[dict]:
    rows = []
    derived = parcel.get("derived") or {}
    seen = set()
    for r in individual.rules:
        f = r.parcel_field
        if not f or r.criteria.get("type") == "manual":
            continue
        key = "front_road" if f == "front_road_width_m" else f
        v = parcel.get("front_road", {}).get("width_m") if f == "front_road_width_m" else parcel.get(f)
        seen.add(key)
        if v == [] and r.criteria.get("type") == "distance" and parcel.get("geometry") is not None:      # 量過才算「無」；沒界線的空清單仍是空白
            rows.append(_none_row(f"{r.item_no} {r.name}", f, r))
            continue
        rows.append(_row(f"{r.item_no} {r.name}", f, v, derived.get(key)))
    for f, label in PARCEL_EXTRA:
        if f in seen:
            continue
        rows.append(_row(label, f, parcel.get(f), derived.get(f)))
    return rows


def _none_row(label: str, field: str, rule: Any) -> dict:
    """設施距離欄位為空清單＝「無」：設施資料庫搜尋範圍內沒有此類設施，基準表以 none_level 判定（不是資料不足）。"""
    c = rule.criteria or {}
    lvl = c.get("none_level")
    radius = "最外級距" if c.get("direction") == "farther_is_better" else "10 km"
    return {"label": label, "field": field, "value": "無", "status": "量測", "source": "設施資料庫（OpenStreetMap 等）",
            "note": f"{radius}內無此類設施，依基準表「無」判定" + (f"為「{lvl}」" if lvl else "") + "；設施資料庫可能不完整，如實地有此設施請補填"}


def _row(label: str, field: str, v: Any, dv: dict | None) -> dict:
    if _blank(v):
        return {"label": label, "field": field, "value": "", "status": "空白", "source": "", "note": "資料不足，請人工填載"}
    if dv:
        return {"label": label, "field": field, "value": _display(v), "status": "推定", "source": dv.get("source", ""), "note": dv.get("note", "")}
    if _is_measured(v):
        src = (v[0] if isinstance(v, list) else v).get("source") or ""
        prov = (v[0] if isinstance(v, list) else v).get("provenance") or {}
        return {"label": label, "field": field, "value": _display(v), "status": "量測", "source": src, "note": prov.get("note") or _measure_note(v[0] if isinstance(v, list) else v)}
    return {"label": label, "field": field, "value": _display(v), "status": "資料", "source": "匯入／填載", "note": ""}


def section_rows(section: dict, regional: RuleSet) -> list[dict]:
    survey = section.get("survey") or {}
    prov = section.get("survey_provenance") or {}
    filled, sugg, manual = set(prov.get("filled") or []), prov.get("suggestions") or {}, prov.get("manual") or {}
    rows = []
    for r in regional.rules:
        f = r.survey_field
        if not f or r.criteria.get("type") == "manual":
            continue
        grp, _, key = f.partition(".")
        v = (survey.get(grp) or {}).get(key) if key else survey.get(grp)
        if v == [] and r.criteria.get("type") == "distance" and section.get("geometry") is not None:
            rows.append(_none_row(r.name, f, r))
            continue
        if _blank(v):
            note = manual.get(f) or (f"建議值：{_display(sugg[f].get('value'))}（{sugg[f].get('note', '')}）" if f in sugg else "資料不足，請人工填載")
            rows.append({"label": r.name, "field": f, "value": "", "status": "空白", "source": sugg.get(f, {}).get("source", ""), "note": note})
        elif _is_measured(v):
            x = v[0] if isinstance(v, list) else v
            rows.append({"label": r.name, "field": f, "value": _display(v), "status": "量測", "source": x.get("source") or "", "note": (x.get("provenance") or {}).get("note") or _measure_note(x)})
        elif f in filled or f in sugg:
            rows.append({"label": r.name, "field": f, "value": _display(v), "status": "推定", "source": sugg.get(f, {}).get("source", "使用分區圖／路網"), "note": sugg.get(f, {}).get("note", "依圖資推算，請確認")})
        else:
            rows.append({"label": r.name, "field": f, "value": _display(v), "status": "資料", "source": "勘查表／填載", "note": ""})
    return rows


def build_fill_report(rec: dict, regional: RuleSet, individual: RuleSet) -> dict[str, Any]:
    data = rec["data"]
    subject = data["subject_parcel"]
    sid = subject.get("section_id")
    section = (data.get("sections") or {}).get(sid) or {}
    subj_rows = parcel_rows(subject, individual)
    sec_rows = section_rows(section, regional)
    head = [
        {"label": "比準地地號", "value": subject.get("parcel_id") or "", "status": "資料" if subject.get("parcel_id") else "空白", "source": "", "note": ""},
        {"label": "比準地界線", "value": {"cadastre_file": "地籍圖", "nlsc_api": "國土測繪中心", "synthetic": "依清冊面積合成（示意）"}.get(subject.get("geometry_source") or "", ""),
         "status": "資料" if subject.get("geometry_source") in ("cadastre_file", "nlsc_api") else "推定" if subject.get("geometry") else "空白", "source": _GEOM_SRC_ZH.get(subject.get("geometry_source") or "", subject.get("geometry_source") or ""), "note": subject.get("geometry_note") or ""},
        {"label": "區段範圍", "value": section.get("range_desc") or "", "status": "資料" if section.get("geometry_source") == "section_map" else "推定" if section.get("geometry") else "空白",
         "source": _GEOM_SRC_ZH.get(section.get("geometry_source") or "", section.get("geometry_source") or ""), "note": section.get("geometry_note") or ""},
    ]
    comps = []
    for c in data.get("comparables") or []:
        sel = c.get("selection") or {}
        da = c.get("date_adjustment") or {}
        comps.append({"comp_no": c.get("comp_no"), "parcel_id": c.get("parcel_id"), "transaction_date": c.get("transaction_date"),
                      "normal_unit_price": c.get("normal_unit_price"), "basis": sel.get("basis") or ("人工填載" if not c.get("source") else (c.get("source") or {}).get("note", "")),
                      "flags": sel.get("flags_text") or "", "date_adjustment": da.get("pct"), "date_note": da.get("note") or "",
                      "rows": parcel_rows(c, individual)})
    all_rows = head + subj_rows + sec_rows + [r for c in comps for r in c["rows"]]
    counts = {k: sum(1 for r in all_rows if r["status"] == k) for k in ("資料", "量測", "推定", "空白")}
    gaps = [r["label"] for r in head + subj_rows if r["status"] == "空白"] + [f"區段 {r['label']}" for r in sec_rows if r["status"] == "空白"]
    if not comps:
        gaps.append("比較標的（買賣實例）")
    return {"head": head, "subject": subj_rows, "section": sec_rows, "section_id": sid, "comparables": comps, "counts": counts, "gaps": gaps,
            "last_fill": rec.get("last_fill"), "outputs": rec.get("outputs")}
