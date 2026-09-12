"""
下載內政部實價登錄批次資料（土地買賣），整理成比較標的搜尋用的 JSON。賽前跑一次；換地區只要換 --county。

用法：
  cd backend && python3 scripts/fetch_lvr.py --valuation 1140901            # 依估價基準日自動決定要抓哪幾季（前一年到基準日）
  python3 scripts/fetch_lvr.py --seasons 113S3,113S4,114S1,114S2,114S3 --county f
  python3 scripts/fetch_lvr.py --from-dir /path/with/zips                    # 已手動下載的 zip

來源：https://plvr.land.moi.gov.tw/DownloadOpenData（DownloadSeason?season=114S2&type=zip&fileName=lvr_landcsv.zip）
縣市代碼：a 臺北市、b 臺中市、c 基隆市、d 臺南市、e 高雄市、f 新北市、g 宜蘭縣、h 桃園市、i 嘉義市、j 新竹縣、k 苗栗縣、m 南投縣、n 彰化縣、o 新竹市、p 雲林縣、q 嘉義縣、t 屏東縣、u 花蓮縣、v 臺東縣、w 金門縣、x 澎湖縣、z 連江縣
輸出：data/lvr/<county>_land.json（每筆：id、district、target（土地／房地）、date(民國 YYYMMDD)、total_price、unit_price、total_area、zone、note、building（房地才有）、lots[{section, lot, area, zone, share, transfer}]）
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "lvr"
URL = "https://plvr.land.moi.gov.tw/DownloadSeason?season={season}&type=zip&fileName=lvr_landcsv.zip"
COUNTY_NAMES = {"a": "臺北市", "b": "臺中市", "c": "基隆市", "d": "臺南市", "e": "高雄市", "f": "新北市", "g": "宜蘭縣", "h": "桃園市",
                "i": "嘉義市", "j": "新竹縣", "k": "苗栗縣", "m": "南投縣", "n": "彰化縣", "o": "新竹市", "p": "雲林縣", "q": "嘉義縣",
                "t": "屏東縣", "u": "花蓮縣", "v": "臺東縣", "w": "金門縣", "x": "澎湖縣", "z": "連江縣"}


def seasons_for(valuation: str) -> list[str]:
    """估價基準日（民國 YYYMMDD）前一年到基準日所跨的季（查估辦法 §17 第2、3項最多用到前一年）。"""
    y, m = int(valuation[:3]), int(valuation[3:5])
    out = []
    for yy in (y - 1, y):
        for q in (1, 2, 3, 4):
            if (yy, q) < (y - 1, (m - 1) // 3 + 1) or (yy, q) > (y, (m - 1) // 3 + 1):
                continue
            out.append(f"{yy}S{q}")
    return out


def download(season: str, dest: Path) -> Path:
    p = dest / f"lvr_{season}.zip"
    if p.exists() and p.stat().st_size > 10000:
        return p
    print(f"下載 {season} …", end="", flush=True)
    with urllib.request.urlopen(URL.format(season=season), timeout=180) as r:
        p.write_bytes(r.read())
    print(f" {p.stat().st_size // 1024} KB")
    return p


def _rows(z: zipfile.ZipFile, name: str) -> list[list[str]]:
    if name not in z.namelist():
        return []
    text = z.read(name).decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    return rows[2:] if len(rows) > 2 else []          # 第 1 列中文欄名、第 2 列英文欄名


def parse_zip(path: Path, county: str, season: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with zipfile.ZipFile(path) as z:
        main = _rows(z, f"{county}_lvr_land_a.csv")
        lots = _rows(z, f"{county}_lvr_land_a_land.csv")
        for r in main:
            if len(r) < 28 or r[1] not in ("土地", "房地(土地+建物)", "房地(土地+建物)+車位"):   # 房地要扣建物成本（§13 第3、4款），只列候選不自動採用
                continue
            try:
                total = float(r[21] or 0)
                area = float(r[3] or 0)
            except ValueError:
                continue
            out[r[27]] = {"id": r[27], "season": season, "district": r[0], "target": r[1], "position": r[2], "total_area": area,
                          "zone": r[4], "nonurban_zone": r[5], "nonurban_use": r[6], "date": r[7], "counts": r[8],
                          "total_price": total, "unit_price": float(r[22] or 0), "note": r[26], "lots": [],
                          "building": {"area": float(r[15] or 0), "type": r[11], "material": r[13], "completed": r[14], "floors": r[10], "level": r[9],
                                       "main_area": float(r[28] or 0) if len(r) > 28 and r[28] else None} if r[1] != "土地" else None}
        for r in lots:
            if len(r) < 8 or r[0] not in out:
                continue
            try:
                share = f"{int(r[5])}/{int(r[4])}" if r[4] and r[5] else None
            except ValueError:
                share = None
            out[r[0]]["lots"].append({"section": r[1], "area": float(r[2] or 0), "zone": r[3], "share": share, "transfer": r[6], "lot_raw": r[7]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", default="f")
    ap.add_argument("--valuation", help="估價基準日（民國 YYYMMDD），自動決定季別")
    ap.add_argument("--seasons", help="逗號分隔，例如 113S3,113S4,114S1")
    ap.add_argument("--from-dir", help="已下載 zip 的資料夾（檔名 lvr_<season>.zip）")
    ap.add_argument("--out")
    a = ap.parse_args()
    seasons = a.seasons.split(",") if a.seasons else seasons_for(a.valuation) if a.valuation else None
    if not seasons:
        sys.exit("請給 --valuation 或 --seasons")
    cache = Path(a.from_dir) if a.from_dir else OUT_DIR / "zip"
    cache.mkdir(parents=True, exist_ok=True)
    out_path = Path(a.out) if a.out else OUT_DIR / f"{a.county}_land.json"
    records: dict[str, dict] = {}
    if out_path.exists():
        for rec in json.loads(out_path.read_text(encoding="utf-8")).get("records", []):
            records[rec["id"]] = rec
    for s in seasons:
        z = cache / f"lvr_{s}.zip"
        if not z.exists():
            z = download(s, cache)
        got = parse_zip(z, a.county, s)
        records.update(got)
        print(f"{s}: 土地交易 {len(got)} 筆")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"county": a.county, "county_name": COUNTY_NAMES.get(a.county, a.county), "seasons": sorted({r['season'] for r in records.values()}),
                                    "source": "內政部不動產交易實價查詢服務網 批次下載（DownloadOpenData）", "records": sorted(records.values(), key=lambda r: r["date"])},
                                   ensure_ascii=False), encoding="utf-8")
    print(f"→ {out_path}（{len(records)} 筆）")


if __name__ == "__main__":
    main()
