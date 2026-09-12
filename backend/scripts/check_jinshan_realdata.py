"""
真實資料自洽檢查（不是驗收測試）：用範本表4 比準地的四個距離（金山國小 150、金山市場 30、中山溫泉公園 190、金山區公所站 80）
在 OSM POI 上反推比準地位置，看殘差多大、各項落在哪個級距。範本沒給地籍座標，所以只能這樣間接對。

  python scripts/check_jinshan_realdata.py ../data/poi_osm_jinshan.sqlite
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from app.engine.rules import grade, load_ruleset
from app.spatial import geo
from app.spatial.poi import POIStore

TEMPLATE = {  # 範本表4 比準地欄
    "school": ("金山國小", 150), "traditional_market": ("金山第一市場", 30), "park": ("中山溫泉公園", 190), "bus_stop": ("金山區公所", 80),
}


def main(db: str) -> None:
    st = POIStore.from_sqlite(db)
    targets = {}
    for t, (name, d) in TEMPLATE.items():
        cands = [p for p in st.by_types([t]) if name[:4] in (p.name or "")]
        if not cands:
            print(f"× POI 庫沒有 {t} 「{name}」"); continue
        targets[t] = (cands[0], d)
        print(f"✓ {t:20} {cands[0].name} ({cands[0].lon:.5f}, {cands[0].lat:.5f})  範本距離 {d} m")
    if len(targets) < 3:
        print("可對照的設施不足三個，無法反推位置"); return
    # 以市場為中心做 5 m 網格搜尋，最小化距離殘差平方和
    c = next(iter(targets.values()))[0].geom.centroid
    best = None
    for dx in range(-400, 401, 5):
        for dy in range(-400, 401, 5):
            q = geo.offset_point(c.x, c.y, dx, dy)
            err = sum((geo.straight_distance_m(q, p.geom) - d) ** 2 for p, d in targets.values())
            if best is None or err < best[0]:
                best = (err, q)
    err, q = best
    print(f"\n反推比準地位置 ≈ ({q.x:.5f}, {q.y:.5f})，RMS 殘差 {(err / len(targets)) ** 0.5:.0f} m（直線距離；範本可能是步行距離）")
    ind = load_ruleset("jinshan_commercial_individual")
    rule_of = {"school": "I15", "traditional_market": "I16", "park": "I17", "bus_stop": "I18"}
    for t, (p, d) in targets.items():
        got = geo.straight_distance_m(q, p.geom)
        r = ind.by_id(rule_of[t])
        print(f"  {r.name:12} 範本 {d:4} m → {grade(r, {'distance_m': d}):3}   OSM 直線 {got:5.0f} m → {grade(r, {'distance_m': got}):3}")
    for t in ("cemetery", "gas_station", "substation", "bank", "tourist_hotel", "intercity_bus_station", "parking_lot"):
        near = st.nearest(q, [t], k=2)
        print(f"  最近 {t:22}", ", ".join(f"{p.name or '(無名)'} {d:.0f} m" for p, d in near) or "無")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../data/poi_osm_jinshan.sqlite")
