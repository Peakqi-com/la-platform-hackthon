"""
沒有地籍界線的比較標的：用實價登錄門牌的路名，對到該行政區的路網，取路段中點當「推定位置」。
只用來圍區段草稿、量設施距離、推地勢與分區；面積用實價登錄土地面積合成示意範圍，寬深形狀仍留人工。
結果一律 geometry_source=address_estimate，畫面與書表標推定。
"""
from __future__ import annotations

import re
from typing import Any

from shapely.ops import unary_union

from .area import district_geom, pad_bbox

FULL2HALF = str.maketrans("０１２３４５６７８９", "0123456789")
ROAD_RE = re.compile(r"([一-鿿A-Za-z0-9]{1,10}?(?:大道|路|街|巷|弄))")
DISTRICT_RE = re.compile(r"(新北市)?([一-鿿]{1,3}區)")


def parse_address(position: str, default_district: str | None) -> dict[str, Any]:
    """「新北市三芝區智成街２之１號二樓」→ {district: 三芝區, road: 智成街, lane, number}。"""
    s = (position or "").translate(FULL2HALF).replace("台", "臺")
    m = DISTRICT_RE.search(s)
    district = m.group(2) if m else ((default_district or "").replace("新北市", "") or None)
    rest = s[m.end():] if m else s
    roads = ROAD_RE.findall(rest)
    road = None
    for r in roads:
        if r.endswith(("巷", "弄")):
            continue
        road = r
        break
    lane = next((r for r in roads if r.endswith("巷")), None)
    num = re.search(r"(\d+)(?:之\d+)?號", rest)
    return {"district": district, "road": road, "lane": lane, "number": int(num.group(1)) if num else None, "text": s}


_addr_db = None


def address_db():
    """data/osm/addresses.sqlite（OSM addr:street＋addr:housenumber，新北一帶 367 萬筆）；沒有就 None。"""
    global _addr_db
    if _addr_db is None:
        import os
        from pathlib import Path

        from .geodb import GeoDB
        path = os.environ.get("ADDRESS_DB") or str(Path(__file__).resolve().parents[3] / "data" / "osm" / "addresses.sqlite")
        if Path(path).exists():
            _addr_db = GeoDB(path)
            _addr_db.ensure_name_index()
        else:
            _addr_db = False
    return _addr_db or None


def point_from_housenumber(a: dict, dg) -> dict[str, Any] | None:
    """門牌點：同路名、同行政區內找相同號數（含「之」前的號）；沒有就取號數最接近且同奇偶側的門牌，並註明。"""
    db = address_db()
    if db is None or a.get("number") is None:
        return None
    street = a["road"] if not a.get("lane") else f"{a['road']}{a['lane']}"
    rows = [r for r in db.query_name(street) if dg.buffer(0.002).contains(r[3])]
    if not rows and a.get("lane"):
        rows = [r for r in db.query_name(a["road"]) if dg.buffer(0.002).contains(r[3])]
    if not rows:
        return None
    n = a["number"]
    exact = [r for r in rows if r[2].get("number") == n]
    if exact:
        pt = exact[0][3]
        return {"lon": float(pt.x), "lat": float(pt.y), "kind": "exact", "note": f"門牌 {street}{exact[0][2].get('housenumber')} 之定位點（OpenStreetMap 門牌）"}
    same_side = [r for r in rows if (r[2].get("number", 0) - n) % 2 == 0] or rows
    near = min(same_side, key=lambda r: abs(r[2].get("number", 0) - n))
    pt = near[3]
    return {"lon": float(pt.x), "lat": float(pt.y), "kind": "nearest", "note": f"無 {street}{n} 號門牌點，取同側最近門牌 {near[2].get('housenumber')} 號之定位點（OpenStreetMap 門牌）"}


def point_from_address(position: str, default_district: str | None, get_roads) -> dict[str, Any] | None:
    """回 {"lon","lat","note","district","road","kind"}；順序：門牌點 → 路段中點；都對不到 → None。get_roads(bbox) 由呼叫端給。"""
    a = parse_address(position, default_district)
    if not a["road"] or not a["district"]:
        return None
    dg = district_geom(a["district"])
    if dg is None:
        return None
    hn = point_from_housenumber(a, dg)
    if hn:
        return {**hn, "district": a["district"], "road": a["road"], "note": f"依實價登錄門牌「{a['text']}」：{hn['note']}（非地籍界線）"}
    roads = get_roads(pad_bbox(dg.bounds, 500.0))
    cands = []
    for name in ([a["lane"]] if a["lane"] else []) + [a["road"]]:
        if not name:
            continue
        full = f"{a['road']}{name}" if name.endswith(("巷", "弄")) and not name.startswith(a["road"]) else name
        segs = [g for g in roads.named(full, exact=True) if dg.buffer(0.002).intersects(g)]
        if not segs:
            segs = [g for g in roads.named(name, exact=False) if dg.buffer(0.002).intersects(g)]
        if segs:
            cands = segs
            used = full
            break
    if not cands:
        return None
    line = unary_union(cands)
    # 沒有門牌定位資料：取整條路的幾何中心，再投影到路上
    c = line.centroid
    pt = line.interpolate(line.project(c)) if line.geom_type == "LineString" else min((g.interpolate(g.project(c)) for g in getattr(line, "geoms", [line])), key=lambda p: p.distance(c))
    return {"lon": float(pt.x), "lat": float(pt.y), "district": a["district"], "road": used, "kind": "road_mid",
            "note": f"依實價登錄門牌「{a['text']}」對到{a['district']}路網「{used}」，取該路段中點為推定位置（門牌資料沒有這一號，非地籍界線）"}
