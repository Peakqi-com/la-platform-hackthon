"""
把 fetch_ntpc_zoning_rules.py 產出的 data/zoning_rules/merged.json 併入 rules/zoning_bcr_far.json 的 plans。

規則：
  - 只併「表格」或未標 check 的「句型」列；check=true 的列也寫入但帶 check 旗標（前端顯示需人工核對）。
  - 建蔽率 None 表示計畫書寫「依施行細則規定辦理」→ bcr_by_county=true，查表時由附表一補。
  - 已由人工核對過的計畫區（KEEP）不覆蓋，只補沒有的分區。
  - 每個分區記 source（來源附件＋公告日）與 page（PDF 頁），對應 docs/07「行政條件」列。
用法：python3 scripts/merge_zoning_rules.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "rules" / "zoning_bcr_far.json"
MERGED = ROOT / "data" / "zoning_rules" / "merged.json"
KEEP = {"金山都市計畫"}                       # 已逐格人工核對，不覆蓋

# 計畫區 → 鄉鎮市區（都市計畫範圍所在行政區；跨區者列全部，查表時以地址所在區對應）
PLAN_DISTRICTS: dict[str, list[str]] = {
    "八里(龍形地區)都市計畫": ["八里區"], "八里都市計畫": ["八里區"], "十分風景特定區計畫": ["平溪區"], "三芝都市計畫": ["三芝區"],
    "三重都市計畫": ["三重區"], "三峽都市計畫": ["三峽區"], "土城(頂埔地區)都市計畫": ["土城區"], "土城都市計畫": ["土城區"],
    "大漢溪北都市計畫": ["新莊區", "三重區", "板橋區", "五股區", "泰山區", "蘆洲區"], "大漢溪南都市計畫": ["板橋區", "土城區", "樹林區", "三峽區", "鶯歌區"],
    "中和都市計畫": ["中和區"], "五股都市計畫": ["五股區"], "北海岸風景特定區計畫": ["石門區", "三芝區", "金山區", "萬里區"], "平溪都市計畫": ["平溪區"],
    "永和都市計畫": ["永和區"], "石門都市計畫": ["石門區"], "石碇都市計畫": ["石碇區"], "汐止都市計畫": ["汐止區"], "坪林水源特定區計畫": ["坪林區"],
    "東北角海岸(含大溪海岸及頭城濱海)風景特定區計畫": ["貢寮區", "瑞芳區"], "林口特定區計畫": ["林口區", "龜山區", "八里區"],
    "板橋(浮洲地區)都市計畫": ["板橋區"], "板橋都市計畫": ["板橋區"], "金山都市計畫": ["金山區"], "泰山都市計畫": ["泰山區"],
    "烏來水源特定區計畫": ["烏來區"], "淡水(竹圍地區)都市計畫": ["淡水區"], "淡水都市計畫": ["淡水區"], "淡海新市鎮特定區計畫": ["淡水區"],
    "深坑都市計畫": ["深坑區"], "野柳風景特定區計畫": ["萬里區"], "新店(安坑地區)都市計畫": ["新店區"], "新店水源特定區計畫": ["新店區"],
    "新店都市計畫": ["新店區"], "新莊都市計畫": ["新莊區"], "瑞芳都市計畫": ["瑞芳區"], "萬里都市計畫": ["萬里區"],
    "臺北大學社區特定區計畫": ["三峽區", "樹林區"], "臺北水源特定區計畫": ["新店區", "烏來區", "石碇區", "坪林區", "雙溪區"], "臺北港特定區計畫": ["八里區"],
    "樹林(三多里地區)都市計畫": ["樹林區"], "樹林(山佳地區)都市計畫": ["樹林區"], "樹林都市計畫": ["樹林區"], "澳底都市計畫": ["貢寮區"],
    "龍壽、迴龍地區都市計畫": ["新莊區", "龜山區"], "雙溪都市計畫": ["雙溪區"], "蘆洲都市計畫": ["蘆洲區"], "鶯歌(鳳鳴地區)都市計畫": ["鶯歌區"], "鶯歌都市計畫": ["鶯歌區"],
}
# 同一行政區有多個計畫區時的查表優先序（主計畫在前；地區型計畫需由地籍／分區圖判斷，暫不自動命中）
PRIMARY = {"板橋區": "板橋都市計畫", "樹林區": "樹林都市計畫", "淡水區": "淡水都市計畫", "新店區": "新店都市計畫", "八里區": "八里都市計畫",
           "土城區": "土城都市計畫", "鶯歌區": "鶯歌都市計畫", "三峽區": "三峽都市計畫", "萬里區": "萬里都市計畫", "平溪區": "平溪都市計畫",
           "三重區": "三重都市計畫", "新莊區": "新莊都市計畫", "五股區": "五股都市計畫", "泰山區": "泰山都市計畫", "蘆洲區": "蘆洲都市計畫",
           "金山區": "金山都市計畫", "石門區": "石門都市計畫", "三芝區": "三芝都市計畫", "瑞芳區": "瑞芳都市計畫", "貢寮區": "澳底都市計畫",
           "林口區": "林口特定區計畫", "烏來區": "烏來水源特定區計畫", "坪林區": "坪林水源特定區計畫", "石碇區": "石碇都市計畫", "雙溪區": "雙溪都市計畫"}

NOISE = re.compile(r"^(?:[\d.]+|惟|為|之|內|以原|調高|改編分區|現況已超出|計畫範圍內之|部分|部份|業|用區及|建蔽率容積率備註|部分土石方資源堆置場)")


def clean_book(name: str) -> str:
    """附件檔名 → 書名：去掉副檔名、流水號前綴、日期前綴與「核定實施」之類的檔名尾巴。"""
    n = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    n = re.sub(r"^\d{1,2}[.\-_]\s*", "", n)                        # 01-、03.
    n = re.sub(r"^\d{7}[\-_]?(?:核定實施[\-_]?)?", "", n)            # 1091110-核定實施-
    n = re.sub(r"[\-_]?(?:核定實施|土管要點|土管|FF|\+\d+)$", "", n)
    n = n.replace("(用印版)", "").strip("-_ ")
    return n or name


def clean_zone(z: str) -> str | None:
    z = z.replace("（", "(").replace("）", ")").strip()
    if NOISE.match(z) or len(z) < 3:
        return None
    return z


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    merged = json.loads(MERGED.read_text(encoding="utf-8"))
    plans = rules.setdefault("plans", {})
    sources = rules.setdefault("sources", {})
    added = skipped = 0
    for plan, rec in merged.items():
        if plan not in PLAN_DISTRICTS:
            print("! 未知計畫區", plan)
            continue
        entry = plans.setdefault(plan, {"districts": PLAN_DISTRICTS[plan], "zones": {}})
        # 只有主計畫直接以行政區命中；地區型計畫（括號）的行政區只有在該區沒有主計畫時才命中
        entry["districts"] = [d for d in PLAN_DISTRICTS[plan] if PRIMARY.get(d, plan) == plan]
        if not entry["districts"]:
            entry["districts_secondary"] = PLAN_DISTRICTS[plan]          # 子計畫區：主計畫沒有該分區時才查，結果標 check
        if rec.get("deferred_to_county"):
            entry["deferred_to_county"] = True
            entry["deferred_note"] = f"該計畫土地使用分區管制要點通盤檢討已配合施行細則刪除建蔽率、容積率規定（「{rec['deferred_to_county'][:60]}…」），依施行細則附表一"
        srcs = [s for s in rec.get("sources", []) if s.get("status") == "ok"]
        if srcs and plan not in KEEP:                      # 人工核對過的計畫區來源說明不覆寫
            sources[plan] = f"{plan}土地使用分區管制要點：" + "；".join(f"{clean_book(s['book'])}（新北市政府城鄉發展局公告 {s['date']}）" for s in srcs)
        for zone, v in rec.get("zones", {}).items():
            zc = clean_zone(zone)
            if not zc or not v.get("far"):
                skipped += 1
                continue
            if plan in KEEP and zc in entry["zones"]:
                continue
            entry["zones"][zc] = {
                "bcr": v["bcr"], "far": v["far"],
                "bcr_by_county": v["bcr"] is None,
                "check": bool(v.get("check")),
                "note": f"{plan}土地使用分區管制要點（{v['source']}，PDF 第 {v['page']} 頁，{v['kind']}）" + ("；抽取數值不唯一：" + "、".join(v["variants"]) if v.get("variants") else ""),
            }
            added += 1
    rules["$schema_note"] = rules.get("$schema_note", "") + " plans[].zones[].bcr_by_county=true 表示計畫書寫「建蔽率依施行細則規定辦理」，查表時由 county_default 補；check=true 表示抽取數值不唯一，需人工核對。"
    print(f"併入 {added} 分區，略過 {skipped}；計畫區 {len(plans)}")
    if not a.dry:
        RULES.write_text(json.dumps(rules, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print("→", RULES)


if __name__ == "__main__":
    main()
