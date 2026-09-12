"""
地價區段勘查表（表1）推算：只有區段基本資訊（年期、區段編號、區段範圍、位置）時，把能自動推的欄位填起來，其餘標「需人工填載」。

每個欄位都記來源（source）與是否推定（assumed）：
  設施距離類（交通運輸／公共建設／特殊設施／環境污染／工商活動之設施）→ 設施資料庫 + 路網量測（reference.fill_section）
  土地使用管制（都市計畫內外、使用分區）→ 都市計畫使用分區圖；分區圖只到「商業區」層級，若基準表要「第二種商業區」則只給建議、不填值
  主要道路名稱 → 貼著區段邊界之最高等級道路（路寬 OSM 多無 → 需人工）
  排水、地勢、顧客通行量、店舖毗連、道路規劃闢建、平均路寬 → 需人工填載（實地勘查事項）
法源：查估辦法 §9（區域因素項目）、§10（劃分地價區段應實地勘查）；手冊 p.11 審查重點 iii（勘查表描述與現況相符）。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.engine.rules import RuleSet

from .geo import as_shape, to_twd97
from .reference import fill_section

HIGHWAY_RANK = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4, "unclassified": 5, "residential": 6, "pedestrian": 7, "living_street": 8}
MANUAL_FIELDS = {
    "land_control.bcr": "建蔽率：依都市計畫書或土地使用分區管制要點填載",
    "land_control.far": "容積率：依都市計畫書或土地使用分區管制要點填載",
    "land_control.building_prohibited": "有無禁止建築：依都市計畫或相關公告",
    "land_control.building_restricted": "有無限制建築：依都市計畫或相關公告",
    "transport.main_road_width_m": "主要道路寬度：實地量測或都市計畫道路寬度",
    "transport.avg_road_width_m": "區段內道路平均寬度：實地勘查",
    "transport.road_development": "區段內道路規劃及闢建程度：實地勘查",
    "natural.drainage": "排水之良否：實地勘查／淹水潛勢",
    "natural.terrain": "地勢：實地勘查",
    "commerce.foot_traffic": "顧客通行量：實地勘查",
    "commerce.shop_ratio_pct": "店舖毗連狀態：實地勘查（店舖比例）",
}


def _enum_value_for(rule, suggested: str) -> str | None:
    """分區圖的值能不能直接當基準表 enum 的觀測值：map 或 normalize 有這個 key 才行。"""
    c = rule.criteria or {}
    if c.get("type") != "enum":
        return suggested
    keys = set((c.get("map") or {}).keys()) | set((c.get("normalize") or {}).keys())
    return suggested if suggested in keys else None


def draft_section_survey(section: dict, regional: RuleSet, *, store, zoning=None, roads=None, osrm=None, walk_graph=None,
                         overwrite: bool = False, subject: dict | None = None) -> dict[str, Any]:
    """回傳 {"section", "filled": [...], "suggestions": {...}, "manual": {...}, "warnings": [...]}。
    subject：比準地（有 zoning／geometry 時，區段使用分區以比準地所在細分區為準）。"""
    warnings: list[str] = []
    filled: list[str] = []
    suggestions: dict[str, Any] = {}
    survey = section.setdefault("survey", {})
    for grp in ("land_control", "transport", "natural", "public", "special", "pollution", "commerce"):
        survey.setdefault(grp, {})
    survey.setdefault("other", None)
    if section.get("geometry") is None:
        warnings.append("區段沒有範圍多邊形：無法推算設施距離與分區，請先在圖上推估區段範圍或提供區段圖")
    else:
        # 1. 設施距離
        r = fill_section(section, regional, store, osrm=osrm, walk_graph=walk_graph, overwrite=overwrite)
        filled += [f for f, meta in r["provenance"]["fields"].items()]
        poly = as_shape(section["geometry"])
        c = poly.centroid
        # 2. 分區圖
        if zoning is not None and len(zoning):
            hit = zoning.at((c.x, c.y))
            zones = {}
            for f in zoning.within_bbox(poly.bounds):
                g = as_shape(f["geometry"])
                inter = g.intersection(poly)
                if not inter.is_empty:
                    zones[f["properties"]["zone"]] = zones.get(f["properties"]["zone"], 0) + to_twd97(inter).area
            major = max(zones.items(), key=lambda kv: kv[1])[0] if zones else (hit["zone"] if hit else None)
            cands = _zone_candidates(subject, zoning, major)          # [(分區, 來源, 說明)]
            if major or cands:
                rule = next((x for x in regional.rules if x.survey_field == "land_control.zoning"), None)
                pick = next(((z, src, note) for z, src, note in cands if rule is None or _enum_value_for(rule, z) is not None), None)
                share = {k: round(v / sum(zones.values()), 2) for k, v in zones.items()} if zones else None
                if pick:
                    suggestions["land_control.zoning"] = {"value": pick[0], "source": pick[1], "note": pick[2] + (f"；街廓內面積最大分區為「{major}」" if major and major != pick[0] else ""), "area_share": share}
                else:
                    suggestions["land_control.zoning"] = {"value": major, "source": zoning.source, "note": "分區圖只到主分區；基準表若以「第X種」判定，請補細分區", "area_share": share}
                cur = survey["land_control"].get("zoning")
                if (overwrite or cur in (None, "")) and rule is not None:
                    if pick:
                        survey["land_control"]["zoning"] = pick[0]
                        filled.append("land_control.zoning")
                    else:
                        warnings.append(f"分區圖得到「{major}」，但基準表判定條件需要更細的分區（{list((rule.criteria.get('map') or {}).keys())[:4]}…），僅列為建議")
                if overwrite or survey["land_control"].get("urban_plan") in (None, ""):
                    survey["land_control"]["urban_plan"] = "都市計畫內"
                    filled.append("land_control.urban_plan")
                    suggestions["land_control.urban_plan"] = {"value": "都市計畫內", "source": zoning.source, "note": "區段落在都市計畫使用分區圖範圍內"}
            else:
                suggestions["land_control.urban_plan"] = {"value": "都市計畫外", "source": zoning.source, "note": "區段不在都市計畫使用分區圖範圍內（請確認圖資覆蓋）"}
        # 3. 主要道路（貼邊界的最高等級道路）
        if roads is not None and roads.items:
            ring = to_twd97(poly).boundary.buffer(12)
            best = None
            for n, g, props in roads.items:
                if re.search(r"\d+巷|弄", n):
                    continue
                seg = to_twd97(g).intersection(ring)
                if seg.is_empty or seg.length < 20:
                    continue
                rank = HIGHWAY_RANK.get((props.get("highway") or "").lower(), 9)
                key = (rank, -seg.length)
                if best is None or key < best[0]:
                    best = (key, n, props)
            if best:
                _, name, props = best
                width, wnote = _road_width(props)
                suggestions["transport.main_road_width_m"] = {"value": {"name": name, "value": width}, "source": "OpenStreetMap 路網（highway 等級最高者）",
                                                              "note": "路寬需實地量測或依都市計畫道路寬度填載" if width is None else f"路寬{wnote}，請確認"}
                cur = survey["transport"].get("main_road_width_m")
                if overwrite or not cur or not (isinstance(cur, dict) and cur.get("name")):
                    survey["transport"]["main_road_width_m"] = {"name": name, "value": width if width is not None else (cur or {}).get("value") if isinstance(cur, dict) else None}
                    filled.append("transport.main_road_width_m")
        # 4. 區段內道路平均寬度（路網 width／車道數，長度加權）
        avg = _avg_road_width(poly, roads) if roads is not None and roads.items else None
        if avg:
            suggestions["transport.avg_road_width_m"] = {"value": avg["value"], "source": "OpenStreetMap 路網（width／車道數 × 3.5 m；其餘依道路等級預設寬度）", "note": avg["note"]}
            if overwrite or survey["transport"].get("avg_road_width_m") in (None, ""):
                survey["transport"]["avg_road_width_m"] = avg["value"]
                filled.append("transport.avg_road_width_m")
        # 5. 地勢（高程瓦片取樣）
        try:
            from .terrain import section_terrain
            tr = section_terrain(poly)
        except Exception:  # noqa: BLE001
            tr = None
        if tr:
            suggestions["natural.terrain"] = {"value": tr["value"], "source": tr["note"].split("；")[-1], "note": tr["note"]}
            if overwrite or survey["natural"].get("terrain") in (None, ""):
                survey["natural"]["terrain"] = tr["value"]
                filled.append("natural.terrain")
        # 6. 工商活動：店舖毗連狀態、顧客通行量（OSM 店舖點位密度，系統推定規則）
        sh = _shop_stats(poly, store) if store is not None else None
        if sh:
            suggestions["commerce.shop_ratio_pct"] = {"value": sh["ratio_pct"], "source": "OpenStreetMap shop=*（店舖點位）", "note": sh["note"]}
            suggestions["commerce.foot_traffic"] = {"value": sh["foot_traffic"], "source": "OpenStreetMap shop=*（店舖點位）", "note": sh["note"]}
            if overwrite or survey["commerce"].get("shop_ratio_pct") in (None, ""):
                survey["commerce"]["shop_ratio_pct"] = sh["ratio_pct"]
                filled.append("commerce.shop_ratio_pct")
            if overwrite or survey["commerce"].get("foot_traffic") in (None, ""):
                survey["commerce"]["foot_traffic"] = sh["foot_traffic"]
                filled.append("commerce.foot_traffic")
        # 7. 道路闢建程度：分區圖「道路用地」（計畫道路）對照現況路網 → 闢建比例 → 基準表等級
        dens = _road_density(poly, roads) if roads is not None and roads.items else None
        rd = _road_development(poly, zoning, roads) if zoning is not None and len(zoning) and roads is not None and roads.items else None
        if rd:
            suggestions["transport.road_development"] = {"value": rd["value"], "source": "都市計畫使用分區圖（道路用地）× OpenStreetMap 路網", "note": rd["note"] + (f"；道路密度 {dens:.0f} m/ha" if dens else "")}
            rule = next((x for x in regional.rules if x.survey_field == "transport.road_development"), None)
            if (overwrite or survey["transport"].get("road_development") in (None, "")) and rule is not None and _enum_value_for(rule, rd["value"]) is not None:
                survey["transport"]["road_development"] = rd["value"]
                filled.append("transport.road_development")
        elif dens is not None:
            suggestions["transport.road_development"] = {"value": None, "source": "OpenStreetMap 路網", "note": f"區段內道路密度 {dens:.0f} m/ha（分區圖無道路用地可對照，闢建程度請實地勘查）"}
        # 8. 排水：淹水潛勢圖（data/flood/*.geojson）有才推
        fl = _flood_hint(poly)
        if fl:
            suggestions["natural.drainage"] = fl
            if fl.get("value") and (overwrite or survey["natural"].get("drainage") in (None, "")):
                survey["natural"]["drainage"] = fl["value"]
                filled.append("natural.drainage")
    manual = {}
    for f, why in MANUAL_FIELDS.items():
        grp, key = f.split(".")
        v = survey.get(grp, {}).get(key)
        empty = v in (None, "", []) or (isinstance(v, dict) and v.get("value") in (None, ""))
        if empty:
            manual[f] = why
    section["survey_provenance"] = {"filled": sorted(set(filled)), "suggestions": suggestions, "manual": manual}
    return {"section": section, "filled": sorted(set(filled)), "suggestions": suggestions, "manual": manual, "warnings": warnings}


# ---------------------------------------------------------------- 推定用小工具（規則寫在 docs/07「勘查表推定規則」）

LANE_WIDTH_M = 3.5
SHOP_FRONTAGE_M = 8.0        # 一家店舖以 8 m 臨街面估算（系統推定）


def _road_width(props: dict) -> tuple[float | None, str]:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)", str(props.get("width") or ""))
    if m:
        return float(m.group(1)), "取自路網記載之路寬"
    lanes = props.get("lanes")
    try:
        if lanes not in (None, ""):
            return float(lanes) * LANE_WIDTH_M, f"依車道數 {lanes} × {LANE_WIDTH_M} m 估算"
    except ValueError:
        pass
    dw = DEFAULT_WIDTH_M.get((props.get("highway") or "").lower())
    if dw is not None:
        return dw, f"路網無路寬記載，依道路等級（{props.get('highway')}）預設 {dw:g} m 推定，請實地量測或依都市計畫道路寬度填載"
    return None, "路網無路寬與車道數"


from .lot import DEFAULT_WIDTH_M

ROAD_DEV_BANDS = [(0.9, "已完全開發"), (0.7, "大部分已完成"), (0.4, "已規劃及闢建中"), (0.0, "已進行規劃")]   # 計畫道路闢建比例 → 基準表用語


def _zone_candidates(subject: dict | None, zoning, major: str | None) -> list[tuple[str, str, str]]:
    """區段使用分區候選（依序）：比準地清冊的細分區 → 分區圖在比準地位置 → 街廓內面積最大分區。"""
    out: list[tuple[str, str, str]] = []
    if subject:
        z = (subject.get("zoning") or "").split(":")[-1].strip()
        if z:
            src = ((subject.get("derived") or {}).get("zoning") or {}).get("source") or "比準地清冊"
            out.append((z, f"比準地使用分區（{src}）", "區段使用分區以比準地所在細分區為準（區段內宗地以比準地為代表）"))
        if subject.get("geometry") is not None and zoning is not None and len(zoning):
            c = as_shape(subject["geometry"]).centroid
            hit = zoning.at((c.x, c.y))
            if hit and hit.get("zone"):
                out.append((hit["zone"], zoning.source, "分區圖在比準地位置的分區"))
    if major:
        out.append((major, getattr(zoning, "source", "使用分區圖"), "街廓內面積最大的分區"))
    seen: set[str] = set()
    return [c for c in out if not (c[0] in seen or seen.add(c[0]))]


def _avg_road_width(poly, roads) -> dict[str, Any] | None:
    """區段內（含邊界）道路長度加權平均寬度。有 width／lanes 的用實際值；沒有的依道路等級預設寬度（DEFAULT_WIDTH_M）；coverage＝有實際寬度資訊的長度比例。"""
    pt = to_twd97(poly).buffer(15)
    tot = wsum = known = 0.0
    for n, g, props in roads.items:
        if re.search(r"\d+巷|弄", n):
            continue
        seg = to_twd97(g).intersection(pt)
        if seg.is_empty or seg.length < 5:
            continue
        w, _ = _road_width(props)
        if w is None:
            w = DEFAULT_WIDTH_M.get((props.get("highway") or "").lower())
            if w is None:
                continue
        else:
            known += seg.length
        tot += seg.length
        wsum += w * seg.length
    if tot == 0:
        return None
    cov = known / tot
    return {"value": round(wsum / tot, 1), "coverage": round(cov, 2),
            "note": f"區段內道路 {tot:.0f} m，其中 {cov:.0%} 有路寬或車道數記載，其餘依道路等級預設寬度（幹道 15～20 m、次要 10～12 m、巷道 6～8 m），長度加權平均 {wsum / tot:.1f} m（系統推定，請實地確認）"}


def _road_development(poly, zoning, roads) -> dict[str, Any] | None:
    """計畫道路闢建程度＝分區圖「道路用地」與區段相交面積中，被現況路網（單側 4 m 緩衝）覆蓋的比例。沒有道路用地 → None。"""
    from shapely.ops import unary_union
    pt = to_twd97(poly).buffer(15)
    planned = []
    for f in zoning.within_bbox(poly.buffer(0.0003).bounds):
        if "道路" not in str(f["properties"].get("zone") or ""):
            continue
        inter = to_twd97(as_shape(f["geometry"])).intersection(pt)
        if not inter.is_empty:
            planned.append(inter)
    if not planned:
        return None
    plan = unary_union(planned)
    if plan.area < 50:
        return None
    built = unary_union([to_twd97(g).buffer(4.0) for _n, g, _p in roads.items if to_twd97(g).intersects(pt)]) if roads.items else None
    ratio = plan.intersection(built).area / plan.area if built is not None and not built.is_empty else 0.0
    value = next(v for th, v in ROAD_DEV_BANDS if ratio >= th)
    return {"value": value, "ratio": round(ratio, 2),
            "note": f"區段內計畫道路（道路用地）{plan.area:,.0f} m²，現況路網覆蓋 {ratio:.0%} → 「{value}」（≥90% 已完全開發、≥70% 大部分已完成、≥40% 已規劃及闢建中、其餘已進行規劃；系統推定，請實地確認）"}


def _road_density(poly, roads) -> float | None:
    pt = to_twd97(poly)
    if pt.area <= 0:
        return None
    total = sum(to_twd97(g).intersection(pt).length for _n, g, _p in roads.items)
    return total / (pt.area / 10000)


def _shop_stats(poly, store) -> dict[str, Any] | None:
    """店舖毗連狀態（%）＝店舖數 × 8 m ÷ 區段周長；顧客通行量依每 100 m 店舖數：≥3 多、≥2 稍多、≥1 普通、≥0.5 較少、其餘少。"""
    minx, miny, maxx, maxy = poly.bounds
    pad = 0.001                                             # 先用經緯度外框粗篩（全區 2 萬家店舖逐筆投影太慢）
    shops = [p for p in getattr(store, "pois", []) if p.type == "shop" and minx - pad <= p.geom.bounds[2] and p.geom.bounds[0] <= maxx + pad
             and miny - pad <= p.geom.bounds[3] and p.geom.bounds[1] <= maxy + pad]
    if not shops and not any(p.type == "shop" for p in getattr(store, "pois", [])):
        return None
    pt = to_twd97(poly)
    area = pt.buffer(30)
    n = sum(1 for p in shops if to_twd97(p.geom).intersects(area))
    perim = pt.length
    if perim <= 0:
        return None
    ratio = min(100.0, n * SHOP_FRONTAGE_M / perim * 100)
    per100 = n / perim * 100
    ft = ("顧客通行量多" if per100 >= 3 else "顧客通行量稍多" if per100 >= 2 else "顧客通行量普通" if per100 >= 1 else "顧客通行量較少" if per100 >= 0.5 else "顧客通行量少")
    return {"ratio_pct": round(ratio, 1), "foot_traffic": ft, "n": n,
            "note": f"區段邊界 30 m 內店舖 {n} 家，周長 {perim:.0f} m：毗連比例≈{n}×{SHOP_FRONTAGE_M:.0f} m÷{perim:.0f} m＝{ratio:.0f}%，每 100 m {per100:.1f} 家（系統推定規則，非法規；店舖點位為 OSM，可能不完整）"}


@lru_cache(maxsize=2)
def _flood_index(files: tuple[str, ...]):
    """淹水潛勢圖只讀一次：投影後建 STRtree（每次推算重讀 2 MB GeoJSON 太慢）。"""
    import json

    from shapely.geometry import shape
    from shapely.strtree import STRtree
    geoms, depths = [], []
    for f in files:
        try:
            for feat in json.loads(Path(f).read_text(encoding="utf-8")).get("features", []):
                pr = feat.get("properties") or {}
                try:
                    depth = float(pr.get("depth_m") or pr.get("depth") or 0)
                except (TypeError, ValueError):
                    depth = 0.5
                geoms.append(to_twd97(shape(feat["geometry"])))
                depths.append(depth)
        except (OSError, ValueError):
            continue
    return geoms, depths, (STRtree(geoms) if geoms else None)


def _flood_hint(poly) -> dict[str, Any] | None:
    """data/flood/*.geojson（淹水潛勢圖，屬性 depth_m 或 class）→ 排水建議值；沒有檔案 → None。"""
    import os
    from pathlib import Path
    d = Path(__file__).resolve().parents[3] / "data" / "flood"
    files = sorted(d.glob("*.geojson")) if d.exists() else []
    scen = os.environ.get("FLOOD_SCENARIO", "24h350r")            # 只用一個情境（預設 24 小時 350 mm）；多個檔同時載會取全部情境的最深值
    picked = [f for f in files if scen in f.name] or files[:1]
    files = picked
    if not files:
        return None
    pt = to_twd97(poly)
    worst = 0.0
    src = files[0].name
    geoms, depths, tree = _flood_index(tuple(str(f) for f in files))
    if tree is not None:
        for i in tree.query(pt):
            if geoms[i].intersects(pt):
                worst = max(worst, depths[i])
    value = ("有排水系統不易淹水" if worst == 0 else "有排水系統偶有淹水但排水速度快" if worst < 0.5 else "有排水系統偶有淹水" if worst < 1.0 else "無排水系統易淹水")
    return {"value": value, "source": f"淹水潛勢圖（{src}）", "note": f"淹水潛勢圖模擬最大淹水深度 {worst} m → {value}（系統對應規則，排水系統有無請實地確認）"}
