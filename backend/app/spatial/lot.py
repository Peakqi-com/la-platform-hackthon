"""
依地號產生：比準地地號 → 地籍界線 → 宗地屬性推定 → 區段範圍草稿 → 勘查表推算 → 設施距離。

每一步回報 {"step", "ok", "note"}。推定值只填空白欄位（換了地號或 overwrite=True 才覆寫），
並記到 parcel["derived"][欄位] = {"source", "note"}，介面據此標示「推定，需確認」。
法源：查估辦法 §5、§20 第4項（宗地個別因素資料與地籍圖以需用土地人函送者為準，系統推定只是草稿）；
手冊 p.22 4(1)～(4) 宗地條件、p.23 5(1)(2) 道路種類與面前道路寬度、p.24 8 設施距離、§10／§11 區段範圍。
"""
from __future__ import annotations

import math
import re
from typing import Any

from shapely.geometry import LineString, Point

from .geo import as_shape, centroid, to_twd97

# OSM highway → 手冊 p.23 5(1) 道路種類（主要道路／次要道路／巷道；既成巷道為金山表用語）。對不上的不填。
HIGHWAY_TO_ROAD_TYPE = {
    "trunk": "主要道路", "trunk_link": "主要道路", "primary": "主要道路", "primary_link": "主要道路", "secondary": "主要道路", "secondary_link": "主要道路",
    "tertiary": "次要道路", "tertiary_link": "次要道路",
    "residential": "巷道", "unclassified": "巷道",
    "service": "既成巷道", "living_street": "既成巷道", "pedestrian": "既成巷道",
}
REAL_SOURCES = ("cadastre_file", "nlsc_api", "twland")
FIELD_LABELS = {"area_m2": "面積", "width_m": "寬度", "depth_m": "深度", "shape": "形狀", "frontage": "臨街情形", "road_type": "道路種類",
                "front_road": "面前道路", "street_parking": "停車方便性", "zoning": "使用分區", "bcr_pct": "建蔽率", "far_pct": "容積率", "building_restricted": "禁限建", "terrain": "地勢"}


HIGHWAY_LABELS = {"trunk": "快速道路", "trunk_link": "快速道路連絡道", "primary": "主要幹道", "primary_link": "主要幹道連絡道", "secondary": "次要幹道",
                  "secondary_link": "次要幹道連絡道", "tertiary": "聯絡道路", "tertiary_link": "聯絡道路連絡道", "residential": "住宅區道路",
                  "unclassified": "一般道路", "service": "服務道路", "living_street": "生活街道", "pedestrian": "人行徒步道"}


def field_label(f: str) -> str:
    return FIELD_LABELS.get(f, f)
LANE_WIDTH_M = 3.5


def _blank(v: Any) -> bool:
    return v is None or v == "" or (isinstance(v, dict) and not any(x not in (None, "") for x in v.values()))


def _nearest_road(poly_twd, roads, max_m: float):
    """(name, LineString(TWD97), props, distance) 中距宗地最近者；沒有路網或超過 max_m → None。"""
    best = None
    for name, g, props in getattr(roads, "items", []) or []:
        gt = to_twd97(g)
        d = poly_twd.distance(gt)
        if d <= max_m and (best is None or d < best[3]):
            best = (name, gt, props, d)
    return best


DEFAULT_WIDTH_M = {"motorway": 25.0, "trunk": 20.0, "primary": 15.0, "secondary": 12.0, "tertiary": 10.0, "unclassified": 8.0,
                   "residential": 8.0, "pedestrian": 6.0, "living_street": 6.0, "service": 6.0,
                   "primary_link": 10.0, "secondary_link": 8.0, "tertiary_link": 8.0}      # 路網沒記路寬時依道路等級的預設寬度（系統推定）


def _road_width(props: dict) -> tuple[float | None, str | None]:
    w = props.get("width")
    if w not in (None, ""):
        m = re.search(r"[\d.]+", str(w))
        if m:
            return float(m.group(0)), "取自路網記載之路寬"
    lanes = props.get("lanes")
    if lanes not in (None, ""):
        try:
            return float(lanes) * LANE_WIDTH_M, f"依車道數 {lanes} × {LANE_WIDTH_M} m 估算"
        except ValueError:
            pass
    dw = DEFAULT_WIDTH_M.get((props.get("highway") or "").lower())
    if dw is not None:
        return dw, f"路網無路寬記載，依道路等級（{props.get('highway')}）預設 {dw:g} m 推定，請實地量測"
    return None, None


PARKING_CELL_M = 50.0          # 宗地 50 m 內有交通局劃設的路邊停車格 → 可路邊停車
PARKING_WIDTH_M = 8.0          # 沒有停車格資料時：面前道路寬度 ≥ 8 m 推定可路邊停車、未達 8 m 推定不可（系統門檻，非法規）
PARKING_SRC = "新北市政府交通局 路邊停車空位查詢（data.gov.tw 122901）"


def _street_parking(g, parcel: dict, store) -> dict[str, Any] | None:
    """停車方便性（基準表 21：可／不可路邊停車）。①交通局停車格資料 → ②面前道路寬度門檻 → ③None（留人工）。"""
    if store is not None:
        try:
            hits = store.nearest(g, ["roadside_parking"], k=1, max_m=PARKING_CELL_M)
        except Exception:  # noqa: BLE001
            hits = []
        if hits:
            poi, d = hits[0]
            kind = (poi.attrs or {}).get("kind") or "汽車停車位"
            return {"value": "可路邊停車", "source": PARKING_SRC,
                    "note": f"宗地 {d:.0f} m 內有交通局劃設之路邊停車格（{poi.name}，{kind}）；車格資料只涵蓋已劃設路段"}
    w = (parcel.get("front_road") or {}).get("width_m")
    if w in (None, ""):
        return None
    try:
        w = float(w)
    except (TypeError, ValueError):
        return None
    if w >= PARKING_WIDTH_M:
        return {"value": "可路邊停車", "source": "面前道路寬度（系統推定）",
                "note": f"交通局停車格資料 {PARKING_CELL_M:.0f} m 內無劃設車格；面前道路寬 {w:g} m ≥ {PARKING_WIDTH_M:g} m，依系統門檻推定可路邊停車（非法規，紅黃線請實地確認）"}
    return {"value": "不可路邊停車", "source": "面前道路寬度（系統推定）",
            "note": f"交通局停車格資料 {PARKING_CELL_M:.0f} m 內無劃設車格；面前道路寬 {w:g} m 未達 {PARKING_WIDTH_M:g} m，依系統門檻推定不可路邊停車（非法規，請實地確認）"}


def _side_lengths_by_road(rect, road_line: LineString | None, c: Point) -> tuple[float, float]:
    """最小外接矩形的兩邊：與面前道路平行的那邊當寬、另一邊當深；沒有道路時短邊當寬。"""
    cs = list(rect.exterior.coords)[:4]
    v1 = (cs[1][0] - cs[0][0], cs[1][1] - cs[0][1])
    v2 = (cs[2][0] - cs[1][0], cs[2][1] - cs[1][1])
    l1, l2 = math.hypot(*v1), math.hypot(*v2)
    if road_line is None or l1 == 0 or l2 == 0:
        return (min(l1, l2), max(l1, l2))
    s = road_line.project(c)
    a, b = road_line.interpolate(max(0.0, s - 5)), road_line.interpolate(min(road_line.length, s + 5))
    rv = (b.x - a.x, b.y - a.y)
    rl = math.hypot(*rv)
    if rl == 0:
        return (min(l1, l2), max(l1, l2))

    def para(v, lv):
        return abs((v[0] * rv[0] + v[1] * rv[1]) / (lv * rl))
    return (l1, l2) if para(v1, l1) >= para(v2, l2) else (l2, l1)


def derive_parcel_attributes(parcel: dict, *, roads=None, zoning=None, overwrite: bool = False, road_max_m: float = 30.0, district: str = "", store=None) -> dict[str, Any]:
    """
    由宗地幾何推定清冊欄位。真實地籍界線（cadastre_file／nlsc_api）才推面積、寬深、形狀、臨街；
    合成幾何只推道路種類、面前道路與使用分區。回傳 {"filled": [...], "notes": [...]}。
    """
    filled: list[str] = []
    notes: list[str] = []
    if parcel.get("geometry") is None:
        return {"filled": filled, "notes": ["沒有幾何，無法推定宗地屬性"]}
    derived = parcel.setdefault("derived", {})
    g = as_shape(parcel["geometry"])
    gt = to_twd97(g)
    real = parcel.get("geometry_source") in REAL_SOURCES

    def put(field: str, value: Any, source: str, note: str) -> None:
        if value is None:
            return
        cur = parcel.get(field)
        if not overwrite and not _blank(cur):
            if field not in derived:
                return
            rec = derived[field]
            if "value" in rec and rec["value"] != cur:      # 推定後被人工（或匯入清冊）改過 → 不再覆寫，改列人工值
                derived.pop(field, None)
                return
        parcel[field] = value
        derived[field] = {"source": source, "note": note, "value": value}
        filled.append(field)

    road = _nearest_road(gt, roads, road_max_m) if roads is not None else None
    c = gt.centroid
    if real and gt.geom_type in ("Polygon", "MultiPolygon"):
        put("area_m2", round(gt.area, 2), "地籍圖", "依地籍界線計算之面積；以登記面積為準")
        rect = gt.minimum_rotated_rectangle
        w, d = _side_lengths_by_road(rect, road[1] if road else None, c)
        put("width_m", round(w, 1), "地籍圖", "最小外接矩形與面前道路平行之邊；不規則形請人工量測")
        put("depth_m", round(d, 1), "地籍圖", "最小外接矩形垂直面前道路之邊；不規則形請人工量測")
        ratio = gt.area / rect.area if rect.area else 0
        put("shape", "方形" if ratio >= 0.8 else "不規則形", "地籍圖", f"界線面積占最小外接矩形 {ratio:.0%}（≥80% 視為方形）")
        if road is not None and road[3] <= 3.0:
            put("frontage", "單面臨街", "地籍圖＋路網", "界線緊鄰道路，先填單面臨街；路角地、雙面臨街請人工確認")
        elif road is not None:
            notes.append(f"宗地界線距最近道路 {road[3]:.0f} m，臨街情形未推定，請人工填載")
    elif not real:
        notes.append("宗地幾何為合成示意，面積、寬深、形狀、臨街情形不推定，請依清冊填載")
    if road is not None:
        name, _line, props, dist = road
        try:
            from shapely.ops import nearest_points

            from .geo import to_wgs84
            from .terrain import SOURCE as TERRAIN_SOURCE
            from .terrain import parcel_terrain
            rp = to_wgs84(nearest_points(_line, gt)[0])
            tr = parcel_terrain(g, rp)
        except Exception:  # noqa: BLE001
            tr = None
        if tr:
            put("terrain", tr["value"], TERRAIN_SOURCE, tr["note"])
        hw = (props.get("highway") or "").lower()
        rt = HIGHWAY_TO_ROAD_TYPE.get(hw)
        if rt:
            put("road_type", rt, "路網", f"最近道路「{name}」為路網之{HIGHWAY_LABELS.get(hw, hw)} → {rt}（手冊 p.23 5(1) 依實際出入道路，請確認）")
        width, wsrc = _road_width(props)
        fr = parcel.get("front_road") or {}
        if overwrite or _blank(fr.get("name")) or "front_road" in derived:
            parcel["front_road"] = {"name": name, "width_m": round(width, 1) if width is not None else fr.get("width_m")}
            derived["front_road"] = {"source": "路網", "note": f"最近道路（距 {dist:.0f} m）" + (f"；寬度{wsrc}" if width is not None else "；寬度未知，請依實際量測（手冊 p.23 5(2)）")}
            filled.append("front_road")
    else:
        notes.append(f"{road_max_m:.0f} m 內沒有有名道路，道路種類與面前道路未推定")
    # 計畫道路：都市計畫圖道路用地量寬度（比路網等級預設準）；宗地不鄰道路用地 → 面臨現有巷道（土管但書用）
    if zoning is not None and len(zoning):
        try:
            from .planned_road import SOURCE as PLANNED_SRC
            from .planned_road import planned_road_frontage
            pr = planned_road_frontage(g, zoning, roads)
        except Exception:  # noqa: BLE001
            pr = None
        fr = parcel.get("front_road") or {}
        if pr and (overwrite or "front_road" in derived or _blank(fr.get("name"))):
            if pr["kind"] == "計畫道路" and pr.get("width_m") is not None:
                name = pr["names"][0] if pr["names"] else (fr.get("name") or "")
                parcel["front_road"] = {**fr, "name": name, "width_m": pr["width_m"], "kind": "計畫道路"}
                derived["front_road"] = {"source": PLANNED_SRC, "note": pr["note"]}
                if "front_road" not in filled:
                    filled.append("front_road")
            elif pr["kind"] == "現有巷道":
                parcel["front_road"] = {**fr, "kind": "現有巷道"}
                d0 = derived.get("front_road") or {"source": "路網", "note": ""}
                derived["front_road"] = {"source": d0.get("source", "路網"), "note": (d0.get("note", "") + "；" if d0.get("note") else "") + pr["note"]}
    sp = _street_parking(g, parcel, store)
    if sp:
        put("street_parking", sp["value"], sp["source"], sp["note"])
    if zoning is not None and len(zoning):
        hit = zoning.at((centroid(g).x, centroid(g).y))
        if hit:
            put("zoning", hit["zone"], hit.get("source") or "使用分區圖", "分區圖只到主分區；基準表若以「第X種」判定，請補細分區")
        else:
            notes.append("使用分區圖沒有涵蓋此位置，使用分區未推定")
    # 行政條件：細分區（實價登錄）、法定建蔽率／容積率、禁限建預設
    from .admin import fill_parcel_admin
    filled += fill_parcel_admin(parcel, district=district or "", overwrite=overwrite)
    return {"filled": filled, "notes": notes}


def _major_zone(polygon: Any, zoning) -> str | None:
    """街廓內面積最大的使用分區（道路用地等不列入）；沒有分區圖 → None。"""
    if zoning is None or not len(zoning):
        return None
    poly = as_shape(polygon)
    areas: dict[str, float] = {}
    for f in zoning.within_bbox(poly.bounds):
        z = (f.get("properties") or {}).get("zone")
        if not z or "道路" in z:
            continue
        inter = as_shape(f["geometry"]).intersection(poly)
        if not inter.is_empty:
            areas[z] = areas.get(z, 0.0) + to_twd97(inter).area
    if areas:
        return max(areas.items(), key=lambda kv: kv[1])[0]
    hit = zoning.at(poly.centroid)
    return hit["zone"] if hit else None


SOURCE_LABELS = {"cadastre_file": "地籍圖", "twland": "開放地籍查詢（推定）", "section_map": "地價區段圖", "nlsc_api": "國土測繪中心地籍查詢", "synthetic": "依清冊面積合成", "estimate_osm_block": "路網推估街廓（草稿）", "address_estimate": "依門牌路段推定位置（示意）"}


def generate_from_lot(data: dict, *, parcel_id: str, manual_point: list[float] | None, overwrite: bool,
                      regional, individual, resolve_geometries, roads=None, zoning=None, store=None, osrm=None, walk_graph=None,
                      parcel_changed: bool = False) -> dict[str, Any]:
    """
    整條鏈；resolve_geometries(data, manual_points, overwrite) 由呼叫端提供（地籍圖檔／NLSC／人工點）。
    parcel_changed：呼叫端已先把新地號存進案件時用它告知「換了地號」（後端比不出差異）。
    """
    from .bootstrap import block_from_roads, describe_range
    from .service import fill_case
    from .survey_draft import draft_section_survey

    steps: list[dict[str, Any]] = []
    subject = data["subject_parcel"]
    pid = (parcel_id or subject.get("parcel_id") or "").strip()
    changed = parcel_changed or (bool(pid) and pid != (subject.get("parcel_id") or ""))
    if pid:
        subject["parcel_id"] = pid
        if _blank(subject.get("address")):
            subject["address"] = f"{data['case'].get('district') or ''}{pid}"
    ow = overwrite or changed
    if changed:                                   # 換地號：舊界線與所有推定值作廢
        for k in ("geometry", "geometry_source", "geometry_note"):
            subject.pop(k, None)
        keep = {"parcel_id": (subject.get("derived") or {}).get("parcel_id")}      # 系統選取的比準地本身不能清
        for f in list((subject.get("derived") or {}).keys()):
            if f != "parcel_id":
                subject[f] = None
        subject["derived"] = {k: v for k, v in keep.items() if v}
    if not pid:
        steps.append({"step": "地號", "ok": False, "note": "請先填比準地地號（例如「金美段489地號」）"})
        return {"data": data, "steps": steps, "parcel_changed": changed}

    # 1. 幾何
    rep = resolve_geometries(data, {pid: manual_point} if manual_point else {}, ow)
    r = (rep or {}).get(pid) or {}
    if subject.get("geometry") is None:
        steps.append({"step": "地籍界線", "ok": False,
                      "note": f"{r.get('note') or '找不到此地號的界線'}。請「匯入地籍圖」（含此地號），或在圖上「設定比準地位置」後再產生；其餘步驟未執行"})
        return {"data": data, "steps": steps, "parcel_changed": changed}
    steps.append({"step": "地籍界線", "ok": True, "note": r.get("note") or subject.get("geometry_note") or SOURCE_LABELS.get(subject.get("geometry_source") or "", subject.get("geometry_source"))})

    # 2. 宗地屬性
    d = derive_parcel_attributes(subject, roads=roads, zoning=zoning, overwrite=ow, district=data["case"].get("district") or "", store=store)
    steps.append({"step": "宗地屬性", "ok": bool(d["filled"]), "note": ("推定 " + "、".join(field_label(f) for f in d["filled"]) if d["filled"] else "未推定任何欄位") + ("；" + "；".join(d["notes"]) if d["notes"] else ""),
                  "filled": d["filled"]})

    # 3. 區段範圍
    sid = subject.get("section_id") or next(iter(data.get("sections") or {}), None)
    if not sid:
        sid = "P001-00"
        subject["section_id"] = sid
    sec = data.setdefault("sections", {}).setdefault(sid, {"section_id": sid, "range_desc": "", "survey": {}})
    src = sec.get("geometry_source")
    if sec.get("geometry") is None or (ow and src in (None, "estimate_osm_block")):
        res = None
        if (sec.get("range_desc") or "").strip():                       # 有四至文字：先依路名圍面（題目給的區段範圍）
            r_ = section_from_range_text(sec, roads, zoning)
            if r_["ok"]:
                from shapely.geometry import shape as _shape
                if _shape(sec["geometry"]).buffer(0.0005).contains(centroid(subject["geometry"])):
                    steps.append({"step": "區段範圍", "ok": True, "note": r_["note"]})
                    res = "done"
                else:
                    for k in ("geometry", "geometry_source", "geometry_note", "status"):
                        sec.pop(k, None)
                    steps.append({"step": "區段範圍（四至）", "ok": False, "note": "依四至圍出的面不含比準地，改用路網推估街廓；請確認四至或地籍"})
        if res == "done":
            pass
        else:
            c = centroid(subject["geometry"])
            res = block_from_roads([(c.x, c.y)], roads) if roads is not None and getattr(roads, "items", None) else None
        if res and res != "done":
            z = _major_zone(res["geometry"], zoning)
            rng = describe_range(res["geometry"], roads, zoning=z, section_id=sid)
            sec["geometry"], sec["geometry_source"], sec["status"] = res["geometry"], "estimate_osm_block", "draft"
            sec["geometry_note"] = f"依比準地位置由路網推估之街廓（邊界道路：{'、'.join(res['bounding_roads'])}），需估價人員確認"
            if ow or _blank(sec.get("range_desc")):
                sec["range_desc"] = rng["range_desc"]
            steps.append({"step": "區段範圍", "ok": True, "note": f"路網推估街廓 {res['area_m2']:,.0f} m²，邊界道路 {'、'.join(res['bounding_roads'])}；四至草稿已填（草稿）"})
        elif res != "done":
            steps.append({"step": "區段範圍", "ok": False, "note": "路網圍不出包含比準地的街廓；請匯入地價區段圖或在圖上推估區段範圍"})
    else:
        steps.append({"step": "區段範圍", "ok": True, "note": f"沿用既有範圍（{SOURCE_LABELS.get(src or '', src) or '勘查表／區段圖'}）"})
    # 2b. 比較標的宗地屬性（已有界線者）與比準地建蔽率／容積率退回區段勘查表值
    comp_notes = []
    for c_ in data.get("comparables") or []:
        if c_.get("geometry") is not None and c_.get("geometry_source") in REAL_SOURCES:
            dc = derive_parcel_attributes(c_, roads=roads, zoning=zoning, overwrite=False, district=data["case"].get("district") or "", store=store)
            if dc["filled"]:
                comp_notes.append(f"{c_.get('parcel_id')}：推定 {'、'.join(field_label(f) for f in dc['filled'])}")
    if comp_notes:
        steps.append({"step": "比較標的宗地屬性", "ok": True, "note": "；".join(comp_notes)})
    lc_ = ((sec.get("survey") or {}).get("land_control") or {})
    for pf, sf in (("bcr_pct", "bcr"), ("far_pct", "far")):
        if _blank(subject.get(pf)) and lc_.get(sf) is not None:
            subject[pf] = lc_[sf]
            subject.setdefault("derived", {})[pf] = {"source": "區段勘查表", "note": f"比準地無分區細目可查（{subject.get('zoning') or '—'}），依所在區段勘查表填載值 {lc_[sf]}% 推定"}

    # 3b. 其他區段（比較標的所在區段）：有四至文字、沒有多邊形 → 由路名圍面（草稿）
    other_notes = []
    for osid, osec in (data.get("sections") or {}).items():
        if osid == sid or osec.get("geometry") is not None or not (osec.get("range_desc") or "").strip():
            continue
        r_ = section_from_range_text(osec, roads, zoning)
        other_notes.append(f"{osid}：{'已圍出' if r_['ok'] else '圍不出'}（{r_['note'][:60]}）")
    if other_notes:
        steps.append({"step": "其他區段範圍", "ok": True, "note": "；".join(other_notes)})

    # 4. 勘查表（有範圍的每個區段都推算；比準地區段帶比準地）
    from .admin import fill_section_admin
    for osid, osec in (data.get("sections") or {}).items():
        if osec.get("geometry") is None:
            if osid == sid:
                steps.append({"step": "勘查表", "ok": False, "note": "沒有區段範圍，略過"})
            continue
        try:
            sd = draft_section_survey(osec, regional, store=store, zoning=zoning, roads=roads, osrm=osrm, walk_graph=walk_graph, overwrite=ow, subject=subject if osid == sid else None)
            adm = fill_section_admin(osec, district=data["case"].get("district") or "", overwrite=ow)
            sd["filled"] = list(sd["filled"]) + adm
            n_manual = len(osec.get("survey_provenance", {}).get("manual") or sd.get("manual") or {})
            steps.append({"step": f"勘查表 {osid}" if osid != sid else "勘查表", "ok": True, "note": f"推算 {len(sd['filled'])} 個欄位、建議值 {len(sd['suggestions'])} 項、需人工填載 {n_manual} 項" + ("；" + "；".join(sd["warnings"]) if sd.get("warnings") else "")})
        except Exception as e:  # noqa: BLE001 - 推算失敗不擋其他步驟
            steps.append({"step": f"勘查表 {osid}", "ok": False, "note": f"推算失敗：{e}"})

    # 5. 設施距離
    try:
        f = fill_case(data, regional=regional, individual=individual, overwrite=ow, store=store, osrm=osrm, walk_graph=walk_graph if walk_graph is not None else "auto")
        steps.append({"step": "設施距離", "ok": True, "note": "已量測比準地與區段之設施距離" + ("；" + "；".join(f["warnings"]) if f["warnings"] else "")})
    except Exception as e:  # noqa: BLE001
        steps.append({"step": "設施距離", "ok": False, "note": f"量測失敗：{e}"})
    return {"data": data, "steps": steps, "parcel_changed": changed}


# ---------------------------------------------------------------- 無地號入口：區段範圍文字 → 區段多邊形 → 自動選比準地

ROAD_RE = re.compile(r"([一-鿿A-Za-z0-9]{1,12}(?:大道|路|街|巷|弄))")            # 貪婪：「潭興街107巷21弄」整個抓，不是只抓「潭興街」
SIDE_RE = re.compile(r"[北南東西]側至([一-鿿A-Za-z0-9]{1,12}?(?:大道|路|街|巷|弄))")
SPLIT_RE = re.compile(r"[，,、；;。\s（）()]|及|與|和|由|所圍|以[北南東西]|[北南東西]側至|之")


def road_names_from_text(text: str) -> list[str]:
    """四至文字抓路名：優先「北側至○○路」句型；否則先以標點與連接詞切詞，再取以路／街／巷結尾的詞。"""
    names = SIDE_RE.findall(text or "")
    if not names:
        for tok in SPLIT_RE.split(text or ""):
            m = ROAD_RE.search(tok.strip())
            if m:
                names.append(m.group(1))
    out: list[str] = []
    for n in names:
        n = re.sub(r"^(?:沿|自|從|經)", "", n)                       # 「沿潭興街以西」→ 潭興街
        if n and n not in out:
            out.append(n)
    return out


def section_from_range_text(section: dict, roads, zoning=None) -> dict[str, Any]:
    """區段範圍文字 → 多邊形（草稿）。回傳 {"ok", "note", "names", "missing"}。"""
    from .bootstrap import section_from_roads
    text = section.get("range_desc") or ""
    names = road_names_from_text(text)
    if not names:
        return {"ok": False, "note": "區段範圍文字裡找不到路名（需「北側至○○路」或含路／街／巷名）", "names": [], "missing": []}
    if roads is None or not getattr(roads, "items", None):
        return {"ok": False, "note": "沒有路網資料", "names": names, "missing": []}
    known = set(roads.names())
    present = [n for n in names if n in known or any(k.startswith(n) for k in known)]
    missing = [n for n in names if n not in present]
    res = section_from_roads(present, roads) if len(present) >= 3 else None
    if not res and len(present) >= 2:
        # 四條路本身圍不成封閉環（中間還有其他路）→ 以這些路的幾何中心當提示點，用全部路網切街廓，取碰到最多指定路名的面
        from shapely.ops import unary_union

        from .bootstrap import block_from_roads
        from .geo import to_wgs84
        by_name: dict[str, Any] = {}
        for n, g, _p in roads.items:
            key = next((x for x in present if n == x or n.startswith(x)), None)
            if key:
                by_name.setdefault(key, []).append(to_twd97(g))
        segs = {k: unary_union(v) for k, v in by_name.items()}
        # 提示點：指定路名兩兩相交（或最近）之點 → 街廓應該包在這些角點之間；沒有交點時退回幾何中心
        pts = []
        keys = list(segs)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                inter = segs[a].intersection(segs[b])
                if not inter.is_empty:
                    pts.append(inter.centroid)
                elif segs[a].distance(segs[b]) <= 60:
                    from shapely.ops import nearest_points
                    pts.append(nearest_points(segs[a], segs[b])[0])
        if segs:
            centre = unary_union(pts).centroid if pts else unary_union(list(segs.values())).convex_hull.centroid
            hints = [to_wgs84(centre)] + [to_wgs84(q) for q in pts]
            blk = block_from_roads([(h.x, h.y) for h in hints], roads, extra_names=present)
            if blk:
                touched = [n for n in present if n in blk["bounding_roads"] or any(b.startswith(n) for b in blk["bounding_roads"])]
                if len(touched) >= 2:
                    res = {"geometry": blk["geometry"], "area_m2": blk["area_m2"], "touched": touched}
    if not res:
        return {"ok": False, "note": f"路名 {'、'.join(names)} 圍不出封閉街廓" + (f"（路網沒有 {'、'.join(missing)}）" if missing else "") + "；請在圖上推估區段範圍或匯入區段圖", "names": names, "missing": missing}
    section["geometry"], section["geometry_source"], section["status"] = res["geometry"], "estimate_osm_block", "draft"
    touched = res.get("touched") if isinstance(res.get("touched"), list) else present
    section["geometry_note"] = f"依區段範圍文字之路名（{'、'.join(present)}）由路網圍出街廓 {res['area_m2']:,.0f} m²（邊界碰到 {'、'.join(touched)}）" + (f"；路網沒有 {'、'.join(missing)}" if missing else "") + "，需估價人員確認"
    return {"ok": True, "note": section["geometry_note"], "names": names, "missing": missing, "area_m2": res["area_m2"]}


def pick_representative_parcel(section_geom: Any, provider, roads=None) -> dict[str, Any] | None:
    """
    查估辦法 §18：比準地就區段內具代表性之土地選取。系統規則：區段內（面積過半落在區段內）的宗地中，
    優先臨主要道路（距有名道路 ≤ 3 m）者，取面積最接近該群中位數者。回傳 {"parcel_id", "section", "lot", "geometry", "note"}。
    """
    from shapely.geometry import shape
    if provider is None or not getattr(provider, "index", None):
        return None
    sec = to_twd97(as_shape(section_geom))
    cands = []
    for (sname, lot), v in provider.index.items():
        try:
            g = to_twd97(shape(v["geometry"]))
        except Exception:  # noqa: BLE001, S112 - 壞幾何略過
            continue
        if g.area <= 0 or not g.intersects(sec) or g.intersection(sec).area < 0.5 * g.area:
            continue
        near_road = False
        if roads is not None and getattr(roads, "items", None):
            near_road = any(to_twd97(rg).distance(g) <= 3.0 for n, rg, _p in roads.items if not re.search(r"\d+巷|弄", n))
        cands.append((sname, lot, g, v["geometry"], near_road))
    if not cands:
        return None
    pool = [c for c in cands if c[4]] or cands
    areas = sorted(c[2].area for c in pool)
    med = areas[len(areas) // 2]
    sname, lot, g, geom, near = min(pool, key=lambda c: abs(c[2].area - med))
    lot_txt = lot.removesuffix("-0")
    return {"parcel_id": f"{sname}{lot_txt}地號", "section": sname, "lot": lot, "geometry": geom, "area_m2": round(g.area, 2),
            "note": f"系統依查估辦法 §18 於區段內 {len(cands)} 筆宗地中選取：{'臨道路 ' + str(len(pool)) + ' 筆，' if near else ''}面積 {g.area:.0f} m² 最接近中位數 {med:.0f} m²；請確認是否具代表性"}


def prepare_from_range(data: dict, *, roads=None, zoning=None, provider=None) -> list[dict[str, Any]]:
    """沒有地號時：區段範圍文字圍區段 → 自動選比準地。回傳步驟清單；成功後 subject_parcel.parcel_id 已填，可接 generate_from_lot。"""
    steps: list[dict[str, Any]] = []
    subject = data["subject_parcel"]
    sid = subject.get("section_id") or next(iter(data.get("sections") or {}), "P001-00")
    sec = data.setdefault("sections", {}).setdefault(sid, {"section_id": sid, "range_desc": "", "survey": {}})
    if sec.get("geometry") is None:
        r = section_from_range_text(sec, roads, zoning)
        steps.append({"step": "區段範圍（文字）", "ok": r["ok"], "note": r["note"]})
        if not r["ok"]:
            return steps
    else:
        steps.append({"step": "區段範圍（文字）", "ok": True, "note": "已有區段範圍多邊形，沿用"})
    pick = pick_representative_parcel(sec["geometry"], provider, roads)
    if not pick:
        steps.append({"step": "比準地選取", "ok": False, "note": "地籍圖內沒有落在此區段的宗地，無法自動選比準地；請匯入地籍圖或填地號"})
        return steps
    subject["parcel_id"] = pick["parcel_id"]
    subject["geometry"], subject["geometry_source"], subject["geometry_note"] = pick["geometry"], "cadastre_file", f"地籍圖：{pick['section']}{pick['lot']}"
    subject.setdefault("derived", {})["parcel_id"] = {"source": "系統選取（查估辦法 §18）", "note": pick["note"]}
    steps.append({"step": "比準地選取", "ok": True, "note": f"{pick['parcel_id']}：{pick['note']}"})
    return steps
