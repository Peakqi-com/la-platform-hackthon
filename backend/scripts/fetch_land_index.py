"""
內政部地政司「都市地價指數」半年報 → rules/land_price_index.json（期日調整用）。

報告附錄三／四／五「全國都市土地各期平均區段地價對基期平均區段地價百分比」按鄉鎮市區列出住宅區／商業區／工業區
最近 11 期（每期計算日 3/31、9/30；基期 112.3.31＝100）。一份最新報告就含完整序列。

用法：cd backend && python3 scripts/fetch_land_index.py [--period 114H2] [--pdf 已下載.pdf]
來源：https://pip.moi.gov.tw/Publicize/Info/E1020（檔名 <年>H1|H2_market.pdf）
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "rules"
URL = "https://pip.moi.gov.tw/Upload/sys/cityprice/{period}_market.pdf"
ZONES = {"住宅區": "附錄三", "商業區": "附錄四", "工業區": "附錄五"}
# 直轄市／縣市的鄉鎮市區（報告依縣市順序列出；同名區用縣市順序判斷）
NTPC = ["板橋區", "三重區", "中和區", "永和區", "新莊區", "新店區", "樹林區", "鶯歌區", "三峽區", "淡水區", "汐止區", "瑞芳區", "土城區", "蘆洲區",
        "五股區", "泰山區", "林口區", "深坑區", "石碇區", "坪林區", "三芝區", "石門區", "八里區", "平溪區", "雙溪區", "貢寮區", "金山區", "萬里區", "烏來區"]
TPE = ["松山區", "信義區", "大安區", "中山區", "中正區", "大同區", "萬華區", "文山區", "南港區", "內湖區", "士林區", "北投區"]
ROW = re.compile(r"^([一-鿿]{1,4}(?:區|鄉|鎮|市))\s+((?:-?[\d.]+|-)(?:\s+(?:-?[\d.]+|-)){5,})\s*$")


def download(period: str, dest: Path) -> Path:
    p = dest / f"{period}_market.pdf"
    if p.exists():
        return p
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE          # pip.moi.gov.tw 憑證鏈在部分機器驗證失敗
    with urllib.request.urlopen(URL.format(period=period), timeout=180, context=ctx) as r:
        p.write_bytes(r.read())
    return p


def parse(pdf: Path) -> dict:
    import pypdf
    r = pypdf.PdfReader(str(pdf))
    dates: list[str] | None = None
    series: dict[str, dict[str, list[float | None]]] = {}
    for page in r.pages:
        t = page.extract_text() or ""
        m = re.search(r"(附錄[三四五]) 全國都市土地各期平均區段地價對基期平均區段地價百分比 － (住宅區|商業區|工業區)", t)
        if not m:
            continue
        zone = m.group(2)
        head = re.search(r"((?:\d{3}\.\d{1,2}\.\d{1,2}\s*\*?\s*){5,})", t)
        if head:
            ds = re.findall(r"(\d{3})\.(\d{1,2})\.(\d{1,2})", head.group(1))
            dates = [f"{y}.{int(mm):02d}.{int(dd):02d}" for y, mm, dd in ds]
        county_state = {"ntpc_seen": False, "tpe_seen": False}
        for line in t.splitlines():
            mm = ROW.match(line.strip())
            if not mm:
                continue
            name, vals = mm.group(1), mm.group(2).split()
            nums = [None if v == "-" else float(v) for v in vals]
            if name in NTPC and not county_state["tpe_seen"]:
                county = "新北市"
                county_state["ntpc_seen"] = True
            elif name in TPE and county_state["ntpc_seen"]:
                county = "臺北市"
                county_state["tpe_seen"] = True
            else:
                county = ""
            key = f"{county}{name}" if county else name
            series.setdefault(key, {})[zone] = nums
    if not dates:
        sys.exit("找不到期別表頭")
    return {"dates": dates, "series": series}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="114H2")
    ap.add_argument("--pdf")
    a = ap.parse_args()
    pdf = Path(a.pdf) if a.pdf else download(a.period, ROOT / "data" / "lvr")
    d = parse(pdf)
    n_period = 65 - ((114 - int(a.period[:3])) * 2 + (1 if a.period.endswith("H1") else 0))   # 第65期＝114H2
    out = {"$schema_note": "期日調整用都市地價指數：各鄉鎮市區各使用分區「各期平均區段地價對基期平均區段地價百分比」（基期 112.3.31＝100）。"
                           "查估辦法 §17 第1項、手冊 p.50 (四)：得以地價指數調整至估價基準日。engine/tables.date_adjustment_from_index 以兩期指數比計算，"
                           "交易日與基準日落在兩期之間者依日期線性內插（app/market/index.py）。",
           "source": f"內政部地政司 都市地價指數 第{n_period}期（{a.period}）報告 附錄三／四／五", "url": URL.format(period=a.period),
           "base": "112.03.31 = 100", "period_no_latest": n_period, "dates": d["dates"], "zones": list(ZONES), "series": d["series"]}
    p = RULES / "land_price_index.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ntpc = {k: v for k, v in d["series"].items() if k.startswith("新北市")}
    print(f"→ {p}：{len(d['series'])} 個鄉鎮市區（新北市 {len(ntpc)}），期別 {d['dates'][0]}～{d['dates'][-1]}")
    print("金山區：", d["series"].get("新北市金山區"))


if __name__ == "__main__":
    main()
