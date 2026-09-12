"""
行政條件推定：使用分區細分區 → 法定建蔽率／容積率（rules/zoning_bcr_far.json）、禁限建預設。

法源：手冊 p.51 (六)2(3) 行政條件按土地使用管制填、(六)4 容積率係指法定容積率；查估辦法 §20 第5項 行政條件依徵收計畫報送時之管制填寫。
數值來源：都市計畫法新北市施行細則附表一／附表三、各都市計畫「土地使用分區管制要點」計畫書（scripts/fetch_ntpc_zoning_rules.py 抓取＋
scripts/merge_zoning_rules.py 併入；plans[計畫區].zones[分區] 有 page/source，check=true 表示抽取時數值不唯一，須人工核對）。全部標「推定」由承辦確認。
細分區來源：宗地若在實價登錄有交易紀錄，用其「使用分區或編定」（例：都市：其他:第二種商業區）；否則只有分區圖的主分區。
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from app.engine.rules import RULES_DIR

MAIN_ZONE = {"商業區": "商業區", "住宅區": "住宅區", "工業區": "工業區", "農業區": "農業區", "保護區": "保護區", "風景區": "風景區", "行政區": "行政區", "文教區": "文教區"}


@lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    p = RULES_DIR / "zoning_bcr_far.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"county_default": {}, "plans": {}, "sources": {}}


def _plan_for(district: str) -> tuple[str, dict] | None:
    d = (district or "").replace("新北市", "").replace("台", "臺")
    for name, plan in load_table().get("plans", {}).items():
        if d in plan.get("districts", []):
            return name, plan
    return None


def _secondary_plans(district: str) -> list[tuple[str, dict]]:
    """同一行政區內的地區型（子）計畫區：浮洲、頂埔、山佳、竹圍…；主計畫查不到該分區時才用，結果標需人工核對。"""
    d = (district or "").replace("新北市", "").replace("台", "臺")
    return [(n, p) for n, p in load_table().get("plans", {}).items() if d in p.get("districts_secondary", [])]


def main_zone_of(zone: str) -> str | None:
    z = (zone or "").split(":")[-1]
    for k in MAIN_ZONE:
        if k in z:
            return k
    return None


def bcr_far_for(zone: str, district: str) -> dict[str, Any] | None:
    """{"bcr", "far", "note", "source", "zone"}；查不到 → None。"""
    z = (zone or "").split(":")[-1].strip()
    if not z:
        return None
    plan = _plan_for(district)
    county = load_table().get("county_default", {}).get("新北市", {})
    hit = _lookup_plan(plan, z, county) if plan else None
    if hit is None:
        for sp in _secondary_plans(district):
            h2 = _lookup_plan(sp, z, county)
            if h2 is not None:
                h2["check"] = True
                h2["note"] = (h2["note"] + "；" if h2["note"] else "") + f"取自{sp[0]}（地區型計畫）之數值，請確認宗地位於該計畫範圍"
                return h2
    else:
        return hit
    key = z if z in county else main_zone_of(z)
    if key and key in county:
        v = county[key]
        note = v.get("note", "")
        if plan and plan[1].get("deferred_to_county"):
            note = (note + "；" if note else "") + plan[1].get("deferred_note", f"{plan[0]}土管要點已回歸施行細則")
        return {"bcr": v.get("bcr"), "far": v.get("far"), "note": note, "source": load_table()["sources"].get("施行細則", "施行細則"), "zone": key}
    pub = load_table().get("public_facility", {}).get("新北市", {})
    pkey = z if z in pub else next((k for k in pub if k.replace("用地", "") in z), None)
    if pkey:
        v = pub[pkey]
        return {"bcr": v.get("bcr"), "far": v.get("far"), "note": v.get("note", ""), "source": load_table()["sources"].get("施行細則附表三", "施行細則附表三"), "zone": pkey}
    return None


def _lookup_plan(plan: tuple[str, dict], z: str, county: dict) -> dict[str, Any] | None:
    if plan:
        zones = plan[1].get("zones", {})
        zn = z.replace("（", "(").replace("）", ")")
        pk = next((k for k in zones if k.replace("（", "(").replace("）", ")") == zn), None)
        if pk is None and "(" not in zn and z not in MAIN_ZONE:
            pk = next((k for k in zones if k.replace("（", "(").replace("）", ")").startswith(zn + "(")), None)
        if pk is not None:
            v = zones[pk]
            bcr, note = v.get("bcr"), v.get("note", "")
            if bcr is None and v.get("bcr_by_county", False):
                mk = main_zone_of(pk)
                pub_ = load_table().get("public_facility", {}).get("新北市", {})
                pk2 = pk if pk in pub_ else next((k for k in pub_ if k.replace("用地", "") in pk), None)
                if mk and mk in county:                 # 土管要點寫「建蔽率依施行細則規定辦理」→ 附表一
                    bcr = county[mk].get("bcr")
                    note = (note + "；" if note else "") + "建蔽率依施行細則附表一"
                elif pk2 and pub_[pk2].get("bcr") is not None:      # 公共設施用地 → 附表三
                    bcr = pub_[pk2]["bcr"]
                    note = (note + "；" if note else "") + "建蔽率依施行細則附表三"
            return {"bcr": bcr, "far": v.get("far"), "note": note, "source": load_table()["sources"].get(plan[0], plan[0]), "zone": pk,
                    "check": bool(v.get("check"))}
    return None


@lru_cache(maxsize=1)
def _lvr_zone_index() -> dict[tuple[str, str], str]:
    """(段名, 地號) → 實價登錄細分區文字（同一筆多次交易取最近）。"""
    try:
        from app.market.lvr import load_lvr, lot_no_from_raw
    except Exception:  # noqa: BLE001
        return {}
    out: dict[tuple[str, str], str] = {}
    for rec in sorted(load_lvr().get("records", []), key=lambda r: r.get("date") or ""):
        for lot in rec.get("lots", []):
            z = (lot.get("zone") or "").strip()
            if z and "都市" in z and "道路" not in z:
                out[(lot.get("section") or "", lot_no_from_raw(lot.get("lot_raw") or ""))] = z.split(":")[-1]
    return out


def lvr_zone_for(section: str, lot_no: str) -> str | None:
    return _lvr_zone_index().get((section, lot_no))


def _blank(v: Any) -> bool:
    return v is None or v == ""


def fill_parcel_admin(parcel: dict, *, district: str, overwrite: bool = False) -> list[str]:
    """補 parcel.zoning（細分區，若實價登錄有）、bcr_pct、far_pct、building_restricted；記 derived。回傳填了哪些欄位。"""
    from app.spatial.cadastre import split_parcel_id
    derived = parcel.setdefault("derived", {})
    filled: list[str] = []
    sec, lot = split_parcel_id(parcel.get("parcel_id") or "")
    cur_zone = parcel.get("zoning") or ""
    if sec and lot and (overwrite or _blank(cur_zone) or not re.search(r"第[一二三四五六]種", cur_zone)):
        z = lvr_zone_for(sec, lot)
        if z:
            parcel["zoning"] = z
            derived["zoning"] = {"source": "實價登錄（該筆土地交易紀錄之使用分區）", "note": "細分區取自實價登錄該地號的交易紀錄；請與都市計畫圖核對"}
            filled.append("zoning")
    zone = parcel.get("zoning") or ""
    v = bcr_far_for(zone, district)
    if v:
        for field, key, label in (("bcr_pct", "bcr", "建蔽率"), ("far_pct", "far", "容積率")):
            if v.get(key) is None:
                continue
            if overwrite or _blank(parcel.get(field)) or field in derived:
                parcel[field] = v[key]
                derived[field] = {"source": v["source"], "note": f"{zone.split(':')[-1] or v['zone']} 法定{label} {v[key]}%；{v['note']}（手冊 p.51 (六)4 容積率指法定容積率）" + ("；計畫書抽取數值不唯一，需人工核對" if v.get("check") else "")}
                filled.append(field)
        if v.get("far") is None and (overwrite or _blank(parcel.get("far_pct"))):
            derived.setdefault("far_pct_note", {"source": v["source"], "note": v["note"]})
    if overwrite or parcel.get("building_restricted") is None:
        parcel["building_restricted"] = False
        derived["building_restricted"] = {"source": "預設", "note": "無禁限建範圍圖資，預設「無」；如屬禁限建範圍請改為「有」（查估辦法 §5 禁限建範圍圖）"}
        filled.append("building_restricted")
    return filled


def fill_section_admin(section: dict, *, district: str, overwrite: bool = False) -> list[str]:
    """勘查表土地使用管制：依 survey.land_control.zoning 補建蔽率、容積率、禁止建築、限制建築。"""
    survey = section.setdefault("survey", {})
    lc = survey.setdefault("land_control", {})
    prov = section.setdefault("survey_provenance", {"filled": [], "suggestions": {}, "manual": {}})
    filled: list[str] = []
    zone = lc.get("zoning") or ""
    v = bcr_far_for(zone, district)
    if v:
        for key, src_key, label in (("bcr", "bcr", "建蔽率"), ("far", "far", "容積率")):
            if v.get(src_key) is None:
                continue
            if overwrite or _blank(lc.get(key)):
                lc[key] = v[src_key]
                prov["suggestions"][f"land_control.{key}"] = {"value": v[src_key], "source": v["source"], "note": f"{v['zone']} 法定{label} {v[src_key]}%；{v['note']}" + ("；計畫書抽取數值不唯一，需人工核對" if v.get("check") else "")}
                filled.append(f"land_control.{key}")
    for key, label in (("building_prohibited", "禁止建築"), ("building_restricted", "限制建築")):
        if overwrite or lc.get(key) is None:
            lc[key] = False
            prov["suggestions"][f"land_control.{key}"] = {"value": False, "source": "預設", "note": f"無禁限建範圍圖資，{label}預設「無」，請確認（查估辦法 §5）"}
            filled.append(f"land_control.{key}")
    for f in filled:
        prov["manual"].pop(f, None)
    prov["filled"] = sorted(set(prov.get("filled", [])) | set(filled))
    return filled
