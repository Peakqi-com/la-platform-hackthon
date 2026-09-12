"""
全區圖資的 SQLite 儲存（R-tree bbox 索引 + WKB），供路網／步行圖／使用分區依案件範圍局部載入。
全新北市 OSM 路網約 19 萬條 way、使用分區 3.4 萬面，整份讀進記憶體要 10 秒以上；改成查 bbox 才組物件。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from shapely import wkb
from shapely.geometry import mapping


class GeoDB:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.con = sqlite3.connect(self.path, check_same_thread=False)
        self.lock = threading.Lock()                     # FastAPI 同步端點在執行緒池並行，同一條連線要上鎖

    @classmethod
    def create(cls, path: str | Path) -> GeoDB:
        p = Path(path)
        if p.exists():
            p.unlink()
        db = cls(p)
        db.con.executescript(
            "CREATE TABLE feat (id INTEGER PRIMARY KEY, name TEXT, props TEXT, wkb BLOB);"
            "CREATE VIRTUAL TABLE idx USING rtree(id, minx, maxx, miny, maxy);"
            "CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);"
        )
        return db

    def write_many(self, rows: Iterable[tuple[str | None, dict, Any]], start_id: int = 1) -> int:
        """rows: (name, props, shapely geom WGS84)。回傳寫入筆數。"""
        cur = self.con.cursor()
        i = start_id
        n = 0
        batch_f, batch_i = [], []
        for name, props, geom in rows:
            if geom is None or geom.is_empty:
                continue
            minx, miny, maxx, maxy = geom.bounds
            batch_f.append((i, name, json.dumps(props, ensure_ascii=False), wkb.dumps(geom)))
            batch_i.append((i, minx, maxx, miny, maxy))
            i += 1
            n += 1
            if len(batch_f) >= 5000:
                cur.executemany("INSERT INTO feat VALUES (?,?,?,?)", batch_f)
                cur.executemany("INSERT INTO idx VALUES (?,?,?,?,?)", batch_i)
                batch_f, batch_i = [], []
        if batch_f:
            cur.executemany("INSERT INTO feat VALUES (?,?,?,?)", batch_f)
            cur.executemany("INSERT INTO idx VALUES (?,?,?,?,?)", batch_i)
        self.con.commit()
        return n

    def set_meta(self, k: str, v: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, v))
        self.con.commit()

    def meta(self, k: str) -> str | None:
        r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else None

    def count(self) -> int:
        with self.lock:
            return self.con.execute("SELECT count(*) FROM feat").fetchone()[0]

    def query(self, bbox: tuple[float, float, float, float]) -> list[dict]:
        """bbox=(minx, miny, maxx, maxy) WGS84 → GeoJSON features（properties 含 name）。"""
        minx, miny, maxx, maxy = bbox
        out = []
        with self.lock:
            rows = self.con.execute(
            "SELECT f.id, f.name, f.props, f.wkb FROM idx i JOIN feat f ON f.id = i.id WHERE i.maxx >= ? AND i.minx <= ? AND i.maxy >= ? AND i.miny <= ?",
            (minx, maxx, miny, maxy),
            ).fetchall()
        for _id, name, props, blob in rows:
            g = wkb.loads(blob)
            p = json.loads(props or "{}")
            if name is not None and "name" not in p:
                p["name"] = name
            out.append({"type": "Feature", "id": _id, "geometry": mapping(g), "properties": p, "_geom": g})
        return out

    def ensure_name_index(self) -> None:
        with self.lock:
            self.con.execute("CREATE INDEX IF NOT EXISTS idx_feat_name ON feat(name)")
            self.con.commit()

    def query_name(self, name: str, limit: int = 5000) -> list[tuple[int, str | None, dict, Any]]:
        """依 name 欄精確查（門牌：路名）。"""
        with self.lock:
            rows = self.con.execute("SELECT id, name, props, wkb FROM feat WHERE name = ? LIMIT ?", (name, limit)).fetchall()
        return [(r[0], r[1], json.loads(r[2] or "{}"), wkb.loads(r[3])) for r in rows]

    def query_geoms(self, bbox: tuple[float, float, float, float]) -> list[tuple[int, str | None, dict, Any]]:
        minx, miny, maxx, maxy = bbox
        with self.lock:
            rows = self.con.execute(
                "SELECT f.id, f.name, f.props, f.wkb FROM idx i JOIN feat f ON f.id = i.id WHERE i.maxx >= ? AND i.minx <= ? AND i.maxy >= ? AND i.miny <= ?",
                (minx, maxx, miny, maxy)).fetchall()
        return [(r[0], r[1], json.loads(r[2] or "{}"), wkb.loads(r[3])) for r in rows]
