"""
內政部實價登錄「租賃」資料（lvr_landcsv.zip 內 <county>_lvr_land_c.csv、_c_land.csv）→ data/lvr/<county>_rent.json，收益法收益實例用。

  python3 scripts/fetch_lvr_rent.py --valuation 1110901          # 依估價基準日決定季別（沿用 fetch_lvr 的 zip 快取，缺的季別才下載）
  python3 scripts/fetch_lvr_rent.py --seasons 110S3,110S4,111S1,111S2,111S3

來源：https://plvr.land.moi.gov.tw/DownloadOpenData（與買賣同一個季別 zip）。
法源：查估辦法 §14（收益實例依技術規則第三章第二節）、§17（收益實例租金調整至估價基準日、蒐集期間）；手冊 p.37–39 收益法調查估價表
（收益實例以 3 件為原則、租金型態含實價登錄租金）。租賃實價登錄只涵蓋經紀業與包租業經手之案件，非全部租約。
欄位依表頭名稱對應（早期季別欄位較少）。每筆：id、season、district、target、position、land_area、zone、date（民國 YYYMMDD）、level、floors、btype、use、
material、completed、building_area、furnished、total_rent、unit_rent（元/m²/月，扣除車位租金與車位面積後自算）、park_rent、park_area、note、lots[{section, area, zone, lot_raw}]。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_lvr import COUNTY_NAMES, OUT_DIR, download, seasons_for

TARGETS = ("土地", "租賃房屋", "租賃房屋+車位", "建物", "房地(土地+建物)", "房地(土地+建物)+車位")


def _table(z: zipfile.ZipFile, name: str) -> tuple[list[str], list[list[str]]]:
    if name not in z.namelist():
        return [], []
    rows = list(csv.reader(io.StringIO(z.read(name).decode("utf-8-sig", errors="replace"))))
    return (rows[0], rows[2:]) if rows else ([], [])


def _f(v: str) -> float | None:
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def parse_rent_zip(path: Path, county: str, season: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with zipfile.ZipFile(path) as z:
        h, body = _table(z, f"{county}_lvr_land_c.csv")
        hl, lots = _table(z, f"{county}_lvr_land_c_land.csv")
        ix = {k: i for i, k in enumerate(h)}

        def g(r: list[str], *keys: str) -> str:
            for k in keys:
                if k in ix and ix[k] < len(r):
                    return r[ix[k]].strip()
            return ""
        for r in body:
            target = g(r, "交易標的")
            if target not in TARGETS:
                continue
            total = _f(g(r, "總額元"))
            if not total:
                continue
            land_area = _f(g(r, "土地面積平方公尺", "土地移轉總面積平方公尺")) or 0.0
            b_area = _f(g(r, "建物總面積平方公尺", "建物移轉總面積平方公尺")) or 0.0
            park_rent = _f(g(r, "車位總額元")) or 0.0
            park_area = _f(g(r, "車位面積平方公尺", "車位移轉總面積平方公尺")) or 0.0
            if target == "土地":
                area, rent = land_area, total
                basis = "總額 ÷ 土地面積"
            else:
                area = b_area - park_area if park_area and b_area > park_area else b_area
                rent = total - park_rent if park_rent and total > park_rent else total
                basis = "（總額 − 車位總額）÷（建物總面積 − 車位面積）" if park_rent or park_area else "總額 ÷ 建物總面積"
            unit = round(rent / area, 1) if area else None
            rid = g(r, "編號")
            out[rid] = {"id": rid, "season": season, "district": g(r, "鄉鎮市區"), "target": target, "position": g(r, "土地位置建物門牌", "土地區段位置建物區段門牌"),
                        "land_area": land_area, "zone": g(r, "都市土地使用分區"), "nonurban_zone": g(r, "非都市土地使用分區"), "nonurban_use": g(r, "非都市土地使用編定"),
                        "date": g(r, "租賃年月日"), "level": g(r, "租賃層次"), "floors": g(r, "總樓層數"), "btype": g(r, "建物型態"), "use": g(r, "主要用途"),
                        "material": g(r, "主要建材"), "completed": g(r, "建築完成年月"), "building_area": b_area, "furnished": g(r, "有無附傢俱"),
                        "total_rent": total, "rent_ex_park": rent, "unit_rent": unit, "unit_basis": basis, "park_rent": park_rent, "park_area": park_area,
                        "note": g(r, "備註"), "lease_type": g(r, "出租型態"), "lease_period": g(r, "租賃期間"), "service": g(r, "租賃住宅服務"), "lots": []}
        li = {k: i for i, k in enumerate(hl)}
        for r in lots:
            rid = r[li["編號"]] if "編號" in li and li["編號"] < len(r) else ""
            if rid not in out:
                continue
            out[rid]["lots"].append({"section": r[li.get("土地位置", 1)] if li.get("土地位置", 1) < len(r) else "",
                                     "area": _f(r[li.get("土地移轉面積平方公尺", 2)]) or 0.0, "zone": r[li.get("使用分區或編定", 3)],
                                     "lot_raw": r[li["地號"]] if "地號" in li and li["地號"] < len(r) else ""})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", default="f")
    ap.add_argument("--valuation")
    ap.add_argument("--seasons")
    ap.add_argument("--from-dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    seasons = a.seasons.split(",") if a.seasons else seasons_for(a.valuation) if a.valuation else None
    if not seasons:
        sys.exit("請給 --valuation 或 --seasons")
    cache = Path(a.from_dir) if a.from_dir else OUT_DIR / "zip"
    cache.mkdir(parents=True, exist_ok=True)
    out_path = Path(a.out) if a.out else OUT_DIR / f"{a.county}_rent.json"
    records: dict[str, dict] = {}
    if out_path.exists():
        for rec in json.loads(out_path.read_text(encoding="utf-8")).get("records", []):
            records[rec["id"]] = rec
    for s in seasons:
        z = cache / f"lvr_{s}.zip"
        if not z.exists():
            z = download(s, cache)
        got = parse_rent_zip(z, a.county, s)
        records.update(got)
        print(f"{s}: 租賃 {len(got)} 筆（土地 {sum(1 for r in got.values() if r['target'] == '土地')}）")
    out_path.write_text(json.dumps({"county": a.county, "county_name": COUNTY_NAMES.get(a.county, a.county), "seasons": sorted({r['season'] for r in records.values()}),
                                    "source": "內政部不動產交易實價查詢服務網 批次下載（DownloadOpenData）租賃資料；僅含經紀業及包租業經手之租賃案件",
                                    "records": sorted(records.values(), key=lambda r: r["date"])}, ensure_ascii=False), encoding="utf-8")
    print(f"→ {out_path}（{len(records)} 筆）")


if __name__ == "__main__":
    main()
