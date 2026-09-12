"""預建各鄉鎮市區的步行圖快取（data/osm/walk_cache/d_<區>.pkl），部署後跑一次，量測就不必等建圖。用法：python3 scripts/prebuild_walk.py [區名...]"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.spatial.area import _districts, pad_bbox
from app.spatial.walking import DISTRICT_PAD_M, _load_or_build, walk_db

NTPC = {"板橋區", "三重區", "中和區", "永和區", "新莊區", "新店區", "土城區", "蘆洲區", "樹林區", "汐止區", "鶯歌區", "三峽區", "淡水區", "瑞芳區", "五股區", "泰山區", "林口區",
        "深坑區", "石碇區", "坪林區", "三芝區", "石門區", "八里區", "平溪區", "雙溪區", "貢寮區", "金山區", "萬里區", "烏來區"}
want = set(sys.argv[1:]) or NTPC
db = walk_db()
for name, g in _districts():
    if name not in want:
        continue
    t = time.time()
    wg = _load_or_build(f"d_{name}", pad_bbox(g.bounds, DISTRICT_PAD_M), db)
    print(f"{name}: {len(wg):,} 段 {time.time() - t:.1f} s", flush=True)
