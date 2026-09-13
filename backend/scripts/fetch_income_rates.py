"""
收益法用的兩份公開序列 → rules/：
  rules/deposit_rates.json：中央銀行「五大銀行存放款利率歷史月資料」（data.gov.tw 10359，A13Rate.csv）→ 每月五大銀行一年期定存（固定）平均、指數房貸（機動）平均。
    用途：押租金運用收益（手冊 p.39 表2「一年期定存利率」）、風險溢酬法基準（技術規則 §43 第1款：考慮銀行定期存款利率）、成本法資本利息（技術規則 §63）。
  rules/cpi_rent.json：行政院主計總處「消費者物價指數（房租）銜接表」（cpisplrent.xls，民國110年=100）→ 每月全國房租指數。
    用途：收益實例租金調整至估價基準日（查估辦法 §17 第1項、手冊 p.39 (10) 價格日期調整）。

  SSL_CERT_FILE=$(python3 -m certifi) python3 scripts/fetch_income_rates.py
"""
from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "rules"
A13 = "https://www.cbc.gov.tw/public/data/OpenData/A13Rate.csv"
CPI = "https://ws.dgbas.gov.tw/001/Upload/463/relfile/10315/2279/cpisplrent.xls"


def _get(url: str) -> bytes:
    """先用 urllib；政府網站憑證鏈不完整（ws.dgbas.gov.tw）驗不過時改用系統 curl（macOS 鑰匙圈／系統憑證庫）。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
            return r.read()
    except urllib.error.URLError:
        import subprocess
        return subprocess.run(["curl", "-sSL", "-m", "60", "-A", "Mozilla/5.0", url], check=True, capture_output=True).stdout


def _avg(vals: list[float]) -> float | None:
    return round(sum(vals) / len(vals), 4) if vals else None


def deposit_rates(raw: bytes) -> dict:
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    h = rows[0]
    i_ym, i_dep, i_mort = h.index("年月"), h.index("定存利率-一年期-固定"), h.index("指數房貸-機動") if "指數房貸-機動" in h else None
    dep: dict[str, list[float]] = {}
    mort: dict[str, list[float]] = {}
    for r in rows[1:]:
        if len(r) <= i_dep or not r[i_ym].strip():
            continue
        ym = r[i_ym].strip().zfill(5)
        try:
            dep.setdefault(ym, []).append(float(r[i_dep]))
        except ValueError:
            pass
        if i_mort is not None and i_mort < len(r):
            try:
                mort.setdefault(ym, []).append(float(r[i_mort]))
            except ValueError:
                pass
    return {"source": "中央銀行 五大銀行存放款利率歷史月資料（政府資料開放平臺 10359）", "url": A13, "fetched": datetime.now(tz=UTC).date().isoformat(),
            "unit": "年利率 %；鍵為民國年月 YYYMM；值為當月各行平均", "note": "五大銀行：97年11月後為臺銀、土銀、合庫、一銀、華銀",
            "deposit_1y_fixed": {k: _avg(v) for k, v in sorted(dep.items())}, "mortgage_index_floating": {k: _avg(v) for k, v in sorted(mort.items()) if v}}


def cpi_rent(raw: bytes) -> dict:
    import xlrd
    sh = xlrd.open_workbook(file_contents=raw).sheet_by_name("CPI-房租類")
    series: dict[str, float] = {}
    for i in range(sh.nrows):
        v = sh.row_values(i)
        try:
            y = int(float(v[0]))
        except (TypeError, ValueError):
            continue
        for m in range(1, 13):
            try:
                series[f"{y:03d}{m:02d}"] = float(v[m])
            except (TypeError, ValueError):
                continue
    return {"source": "行政院主計總處 消費者物價指數（1.房租）銜接表", "url": CPI, "base": "民國110年=100", "fetched": datetime.now(tz=UTC).date().isoformat(),
            "unit": "指數；鍵為民國年月 YYYMM", "series": dict(sorted(series.items()))}


def main() -> None:
    d = deposit_rates(_get(A13))
    (RULES / "deposit_rates.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("deposit_rates.json", len(d["deposit_1y_fixed"]), "個月；111.09 一年期定存", d["deposit_1y_fixed"].get("11109"))
    c = cpi_rent(_get(CPI))
    (RULES / "cpi_rent.json").write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("cpi_rent.json", len(c["series"]), "個月；111.09 房租指數", c["series"].get("11109"))


if __name__ == "__main__":
    main()
