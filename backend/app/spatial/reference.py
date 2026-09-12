"""
參照設施與整案填值。

規則（手冊 p.24 8(2)、p.51 (六)2(2)）：
  同一細項若有多個設施，填「對當地影響最大者」（預設：離比準地／區段最近者）；
  同一徵收案內所有宗地、所有比較標的以同一參照設施填寫 → 先在案件層級選定 reference，再逐宗地量距離。
嫌惡設施（farther_is_better）例外：所有落在基準表最外級距內的設施都列出，等級由引擎取最不利者（aggregate=worst，範本推定）。
量測方式（手冊 p.24 8(3)）：依 rules/facility_measurement.json，可用 overrides 逐類覆寫，同案一致。
"""
from __future__ import annotations

import json
from typing import Any

from app.engine.rules import RULES_DIR, Rule, RuleSet

from .distance import facility_from_poi, parcel_origin
from .geo import as_shape
from .osrm import OSRMClient
from .poi import POI, POIStore

_FM: dict | None = None


def facility_measurement() -> dict:
    global _FM
    if _FM is None:
        _FM = json.loads((RULES_DIR / "facility_measurement.json").read_text(encoding="utf-8"))
    return _FM


def mode_for_type(ftype: str, overrides: dict[str, str] | None = None) -> str:
    if overrides and ftype in overrides:
        return overrides[ftype]
    return (facility_measurement()["facility_types"].get(ftype) or {}).get("mode", "straight")


def _better(rule: Rule, cand: dict, current: Any) -> bool:
    """cand 依基準表判出的等級是否優於 current（空清單＝無）。判不出來就不換。"""
    from app.engine.rules import GradeError, grade
    try:
        a = rule.levels.index(grade(rule, cand))
        b = rule.levels.index(grade(rule, current if current not in (None, {}) else []))
    except (GradeError, ValueError):
        return False
    return a < b


def _worse(rule: Rule, cand: list, current: list) -> bool:
    """嫌惡設施：cand 清單依基準表判出的等級是否劣於 current（空清單＝無）。"""
    from app.engine.rules import GradeError, grade
    try:
        a = rule.levels.index(grade(rule, cand))
        b = rule.levels.index(grade(rule, current if current is not None else []))
    except (GradeError, ValueError):
        return False
    return a > b


NUISANCE_K = 5   # 嫌惡設施最外級距內只列最近 5 筆（引擎 aggregate=worst 只看最近者；97 座鐵塔全列會淹沒表與地圖）


def outer_band_m(rule: Rule) -> float | None:
    """基準表最外級距的距離門檻（嫌惡設施：超過即為最優，不必列）。"""
    vals = [b.get(k) for b in rule.criteria.get("bands", []) for k in ("min", "max") if b.get(k) is not None]
    return max(vals) if vals else None


def is_farther_better(rule: Rule) -> bool:
    return rule.criteria.get("direction") == "farther_is_better"


def select_reference_facilities(anchor: Any, rules: list[Rule], store: POIStore, *, section: Any = None,
                                max_search_m: float = 10000.0) -> dict[str, list[POI]]:
    """
    案件層級參照設施：{rule_id: [POI, ...]}。
    愈近愈好 → 距 anchor（比準地或比準地所在區段）最近的一個；
    嫌惡設施 → 最外級距內全部（沒有 → 空清單 → 引擎 none_level）。
    """
    ref: dict[str, list[POI]] = {}
    for rule in rules:
        if rule.criteria.get("type") != "distance" or not rule.facility_types:
            continue
        if is_farther_better(rule):
            radius = outer_band_m(rule) or max_search_m
            ref[rule.id] = [p for p, _d in store.nearest(anchor, rule.facility_types, k=NUISANCE_K, max_m=radius)]
        else:
            hits = store.nearest(anchor, rule.facility_types, k=1, max_m=max_search_m)
            ref[rule.id] = [hits[0][0]] if hits else []
    return ref


def fill_parcel(parcel: dict, individual: RuleSet, store: POIStore, *, reference: dict[str, list[POI]] | None = None,
                osrm: OSRMClient | None = None, origin_mode: str = "parcel_centroid", road_geom: Any = None,
                mode_overrides: dict[str, str] | None = None, overwrite: bool = False, walk_graph: Any = None) -> dict[str, Any]:
    """
    依個別因素基準表的 distance 規則填 parcel[school|market|park|station|commercial_district|nuisance]。
    reference 未給 → 以本宗地為 anchor 自選（單宗地情境）。已有人工值且 overwrite=False → 保留並記錄 skipped。
    回傳 {"parcel": parcel, "provenance": {...}}。
    """
    if parcel.get("geometry") is None:
        raise ValueError(f"{parcel.get('parcel_id')} 沒有 geometry，無法計算距離")
    origin = parcel_origin(parcel["geometry"], origin_mode, road_geom)
    origin_label = origin_mode if origin_mode in ("parcel_centroid", "parcel_frontage") else "parcel"
    rules = [r for r in individual.rules if r.criteria.get("type") == "distance" and r.parcel_field]
    ref = reference or select_reference_facilities(origin, rules, store)
    prov: dict[str, Any] = {"origin_mode": origin_mode, "origin_point": [origin.x, origin.y] if origin.geom_type == "Point" else None,
                            "fields": {}, "skipped": []}
    for rule in rules:
        f = rule.parcel_field
        if not overwrite and parcel.get(f) not in (None, [], {}) and not _is_computed(parcel.get(f)):
            prov["skipped"].append(f)
            continue
        pois = ref.get(rule.id, [])
        facs = []
        for p in pois:
            mode = mode_for_type(p.type, mode_overrides)
            facs.append(facility_from_poi(p, origin, mode, origin_label=origin_label, osrm=osrm, walk_graph=walk_graph))
        note = None
        if is_farther_better(rule):
            chosen_list = facs
            if reference is not None:                    # 嫌惡設施也適用但書：本宗地附近另有同類設施且依基準表更劣（更近）→ 採用本地清單
                radius = outer_band_m(rule) or 10000.0
                own_pois = [p for p, _d in store.nearest(origin, rule.facility_types, k=NUISANCE_K, max_m=radius)]
                if own_pois and {p.id for p in own_pois} != {p.id for p in pois}:
                    own_facs = [facility_from_poi(p, origin, mode_for_type(p.type, mode_overrides), origin_label=origin_label, osrm=osrm, walk_graph=walk_graph) for p in own_pois]
                    if _worse(rule, own_facs, facs):
                        for of in own_facs:
                            of.setdefault("provenance", {})["note"] = f"參照設施為 {'、'.join(p.name for p in pois) if pois else '無'}，本宗地附近另有更近之同類嫌惡設施，依手冊 p.51 (六)2(2) 但書採用"
                        note = own_facs[0]["provenance"]["note"]
                        chosen_list = own_facs
            parcel[f] = chosen_list
        else:
            chosen = facs[0] if facs else []
            if reference is not None:                    # 案件層級參照設施；本宗地附近另有同類且等級更優者 → 採用（手冊 p.51 (六)2(2)「除另有同等級設施」）
                own = store.nearest(origin, rule.facility_types, k=1, max_m=10000.0)
                if own and (not pois or own[0][0].id != pois[0].id):
                    of = facility_from_poi(own[0][0], origin, mode_for_type(own[0][0].type, mode_overrides), origin_label=origin_label, osrm=osrm, walk_graph=walk_graph)
                    if _better(rule, of, chosen):
                        of.setdefault("provenance", {})["note"] = f"參照設施為 {pois[0].name if pois else '無'}，本宗地附近另有更近之同類設施，依手冊 p.51 (六)2(2) 但書採用"
                        note = of["provenance"]["note"]
                        chosen = of
            parcel[f] = chosen                          # 10 km 內找不到 → 空清單＝「無」（已搜尋過），引擎依基準表 none_level 判定
        prov["fields"][f] = {"rule": rule.id, "n": len(facs), "measure": sorted({x["measure"] for x in facs}), "searched_radius_m": 10000.0,
                             **({"note": note} if note else {})}
    return {"parcel": parcel, "provenance": prov}


def fill_section(section: dict, regional: RuleSet, store: POIStore, *, osrm: OSRMClient | None = None,
                 origin_mode: str = "section_boundary", anchor: Any = None, mode_overrides: dict[str, str] | None = None,
                 overwrite: bool = False, walk_graph: Any = None) -> dict[str, Any]:
    """
    依區域因素基準表的 distance 規則填 section.survey.<group>.<field>（Facility 清單）。
    區段內有設施 → in_section=True、距離 0；區段外 → 從區段邊界最近點量（推定，origin=section_boundary），
    origin_mode="subject_parcel" 時改從 anchor（比準地）量。
    """
    geom = section.get("geometry")
    if geom is None:
        raise ValueError(f"{section.get('section_id')} 沒有 geometry，無法計算距離")
    poly = as_shape(geom)
    origin = poly if origin_mode == "section_boundary" else as_shape(anchor)
    origin_label = "section_boundary" if origin_mode == "section_boundary" else "subject_parcel"
    survey = section.setdefault("survey", {})
    rules = [r for r in regional.rules if r.criteria.get("type") == "distance" and r.survey_field]
    prov: dict[str, Any] = {"origin_mode": origin_mode, "fields": {}, "skipped": []}
    for rule in rules:
        grp, key = rule.survey_field.split(".", 1)
        cur = (survey.get(grp) or {}).get(key)
        if not overwrite and cur not in (None, []) and not all(_is_computed(x) for x in cur):
            prov["skipped"].append(rule.survey_field)
            continue
        inside = store.within(poly, rule.facility_types)
        facs = []
        if is_farther_better(rule):
            radius = outer_band_m(rule) or 10000.0
            cands = [p for p, _d in store.nearest(poly, rule.facility_types, k=NUISANCE_K, max_m=radius)]
        else:
            cands = inside if inside else [p for p, _d in store.nearest(poly, rule.facility_types, k=1, max_m=10000.0)]
        for p in cands:
            mode = mode_for_type(p.type, mode_overrides)
            facs.append(facility_from_poi(p, origin, mode, origin_label=origin_label, osrm=osrm, section=poly, walk_graph=walk_graph))
        survey.setdefault(grp, {})[key] = facs
        prov["fields"][rule.survey_field] = {"rule": rule.id, "n": len(facs), "in_section": any(x["in_section"] for x in facs),
                                             "measure": sorted({x["measure"] for x in facs})}
    return {"section": section, "provenance": prov}


def _is_computed(v: Any) -> bool:
    if isinstance(v, dict):
        return bool(v.get("computed"))
    if isinstance(v, list):
        return bool(v) and all(_is_computed(x) for x in v)
    return False
