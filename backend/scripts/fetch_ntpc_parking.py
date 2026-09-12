"""
新北市交通局「路邊停車空位查詢」（data.gov.tw 122901；每格經緯度、車格類型、收費）→ data/sources/ntpc_roadside_parking.csv。
之後 scripts/build_poi_ntpc.py 會把它併進設施庫（type=roadside_parking），停車方便性推定用。
用法：python3 scripts/fetch_ntpc_parking.py
"""
from __future__ import annotations

import csv
import subprocess
from pathlib import Path

URL = "https://data.ntpc.gov.tw/api/datasets/54a507c4-c038-41b5-bf60-bbecb9d052c6/csv/file"
OUT = Path(__file__).resolve().parents[2] / "data" / "sources" / "ntpc_roadside_parking.csv"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-s", "-L", "-m", "300", "-o", str(OUT), URL], check=True)
    with open(OUT, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ok = sum(1 for r in rows if r.get("latitude") and r.get("longitude"))
    print(f"{len(rows)} 格（有座標 {ok}）→ {OUT}")


if __name__ == "__main__":
    main()
