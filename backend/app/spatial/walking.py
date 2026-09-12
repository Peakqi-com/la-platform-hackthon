"""
輕量步行路徑（OSRM 的備援）：把 OSM highway 線段接成圖，Dijkstra 算最短路徑長度。

  用途：這台機器沒有 docker 跑不了 OSRM；EC2 上有 OSRM 時 measure_distance 仍優先用 OSRM，
        沒有時用這個（measure 仍記「walking」，provenance.router = "osm_graph"），再沒有才退回直線 ×1.3。
  範圍：一個鄉鎮的路網（金山 1,729 條 way）建圖不到一秒；全台請用 OSRM。
  foot profile 近似：排除 motorway/trunk（含 link）、foot=no、access=private/no；其餘皆可走。
"""
from __future__ import annotations

import heapq
import json
import math
import os
from itertools import pairwise
from pathlib import Path
from typing import Any

from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .geo import as_shape, to_twd97

NO_FOOT = {"motorway", "motorway_link", "trunk", "trunk_link"}
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


class WalkGraph:
    def __init__(self, features: list[dict], grid: float = 0.05):
        self.grid = grid
        lines = []
        for f in features:
            p = f.get("properties") or {}
            hw = (p.get("highway") or "").lower()
            if hw in NO_FOOT or p.get("foot") == "no" or p.get("access") in ("private", "no"):
                continue
            g = shape(f["geometry"])
            if g.geom_type == "LineString" and len(g.coords) >= 2:
                lines.append(to_twd97(g))
        self.adj: dict[tuple[float, float], list[tuple[tuple[float, float], float]]] = {}
        self.segments: list[LineString] = []
        if lines:
            noded = unary_union(lines)                      # 在交叉點打斷
            parts = list(noded.geoms) if noded.geom_type == "MultiLineString" else [noded]
            for part in parts:
                cs = list(part.coords)
                for a, b in pairwise(cs):
                    na, nb = self._key(a), self._key(b)
                    if na == nb:
                        continue
                    d = math.dist(a, b)
                    self.adj.setdefault(na, []).append((nb, d))
                    self.adj.setdefault(nb, []).append((na, d))
                    self.segments.append(LineString([a, b]))
        self.tree = STRtree(self.segments) if self.segments else None

    def __getstate__(self):
        d = self.__dict__.copy()
        d.pop("tree", None)
        d.pop("_sssp_cache", None)
        d["segments"] = [list(sg.coords) for sg in self.segments]
        return d

    def __setstate__(self, d):
        self.__dict__.update(d)
        self.segments = [LineString(c) for c in d["segments"]]
        self.tree = STRtree(self.segments) if self.segments else None

    def _key(self, c) -> tuple[float, float]:
        return (round(c[0] / self.grid) * self.grid, round(c[1] / self.grid) * self.grid)

    @classmethod
    def from_geojson(cls, path: str | Path) -> WalkGraph:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["features"])

    def __len__(self) -> int:
        return len(self.segments)

    def snap(self, pt: Point) -> tuple[int, Point, float]:
        """最近路段 → (segment index, 投影點, 到路的直線距離)。"""
        i = int(self.tree.nearest(pt))
        seg = self.segments[i]
        proj = seg.interpolate(seg.project(pt))
        return i, proj, pt.distance(proj)

    def route_distance_m(self, a: Any, b: Any, max_snap_m: float = 300.0) -> dict[str, Any]:
        """
        步行距離 = 起點到路 + 路網最短路徑 + 路到終點。回傳 {"distance_m", "snap_a_m", "snap_b_m", "path_m"}。
        找不到路徑（不連通）→ raise ValueError。
        """
        if not self.tree:
            raise ValueError("步行路網為空")
        pa, pb = to_twd97(as_shape(a)), to_twd97(as_shape(b))
        if pa.geom_type != "Point":
            pa = pa.centroid
        if pb.geom_type != "Point":
            pb = pb.centroid
        ia, qa, da = self.snap(pa)
        ib, qb, db = self.snap(pb)
        if da > max_snap_m or db > max_snap_m:
            raise ValueError(f"起點或終點離路網超過 {max_snap_m} m（{da:.0f} / {db:.0f}）")
        # 虛擬節點：投影點接到所在路段兩端
        sa, sb = self.segments[ia], self.segments[ib]
        a_ends = [(self._key(c), math.dist((qa.x, qa.y), c)) for c in sa.coords]
        b_ends = {self._key(c): math.dist((qb.x, qb.y), c) for c in sb.coords}
        if ia == ib:
            path = qa.distance(qb)
        else:
            dist = self._sssp(ia, qa, a_ends)            # 同一起點（比準地／區段）到很多設施：單源最短路徑算一次，之後每個目標 O(1)
            cands = [dist[n] + d for n, d in b_ends.items() if n in dist]
            path = min(cands) if cands else None
            if path is None:
                raise ValueError("路網不連通")
        return {"distance_m": path + da + db, "path_m": path, "snap_a_m": da, "snap_b_m": db,
                "snap_a": [qa.x, qa.y], "snap_b": [qb.x, qb.y]}

    SSSP_MAX_M = 12_000.0      # 單源最短路徑只算到 12 km（設施搜尋半徑 10 km 以內）
    SSSP_CACHE_N = 16

    def _sssp(self, seg_idx: int, q, starts: list[tuple[tuple[float, float], float]]) -> dict[tuple[float, float], float]:
        key = (seg_idx, round(q.x, 1), round(q.y, 1))
        cache = self.__dict__.setdefault("_sssp_cache", {})
        if key in cache:
            return cache[key]
        dist: dict[tuple[float, float], float] = {}
        pq: list[tuple[float, tuple[float, float]]] = []
        for n, d in starts:
            heapq.heappush(pq, (d, n))
        while pq:
            d, n = heapq.heappop(pq)
            if n in dist:
                continue
            if d > self.SSSP_MAX_M:
                break
            dist[n] = d
            for m, w in self.adj.get(n, []):
                if m not in dist:
                    heapq.heappush(pq, (d + w, m))
        if len(cache) >= self.SSSP_CACHE_N:
            cache.pop(next(iter(cache)))
        cache[key] = dist
        return dist

    def _dijkstra(self, starts: list[tuple[tuple[float, float], float]], targets: dict[tuple[float, float], float]) -> float | None:
        dist: dict[tuple[float, float], float] = {}
        pq: list[tuple[float, tuple[float, float]]] = []
        for n, d in starts:
            heapq.heappush(pq, (d, n))
        best: float | None = None
        while pq:
            d, n = heapq.heappop(pq)
            if n in dist:
                continue
            dist[n] = d
            if n in targets:
                cand = d + targets[n]
                best = cand if best is None else min(best, cand)
            if best is not None and d > best:
                break
            for m, w in self.adj.get(n, []):
                if m not in dist:
                    heapq.heappush(pq, (d + w, m))
        return best


_graph: WalkGraph | None = None
_db = None
_cache: dict = {}
CACHE_N = 4


def walk_db():
    global _db
    if _db is None:
        path = os.environ.get("WALK_DB") or str(DATA_DIR / "osm" / "walk.sqlite")
        if Path(path).exists():
            from .geodb import GeoDB
            _db = GeoDB(path)
        else:
            _db = False
    return _db or None


DISTRICT_PAD_M = 2500.0
WALK_CACHE_DIR = DATA_DIR / "osm" / "walk_cache"


def _district_key(b) -> tuple[str, tuple] | None:
    """要的範圍若整個落在某鄉鎮市區外擴 2.5 km 的框內，就用該區的步行圖（鍵穩定、可存磁碟、跨案件共用）。"""
    from shapely.geometry import Point

    from .area import _districts, pad_bbox
    c = Point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
    for name, g in _districts():
        if g.contains(c):
            db_ = pad_bbox(g.bounds, DISTRICT_PAD_M)
            if db_[0] <= b[0] and db_[1] <= b[1] and db_[2] >= b[2] and db_[3] >= b[3]:
                return name, db_
            return None
    return None


def _load_or_build(key: str, bbox, db) -> WalkGraph:
    import pickle
    f = WALK_CACHE_DIR / f"{key}.pkl"
    if f.exists():
        try:
            with open(f, "rb") as fh:
                return pickle.load(fh)
        except Exception:  # noqa: BLE001, S110 - 快取壞了就重建
            pass
    g = WalkGraph(db.query(bbox))
    try:
        WALK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(f, "wb") as fh:
            pickle.dump(g, fh, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception:  # noqa: BLE001, S110 - 存不了快取就算了
        pass
    return g


def get_walk_graph(bbox=None, *, data: dict | None = None, pad_m: float = 5000.0) -> WalkGraph | None:
    """全區 walk.sqlite 存在時依範圍建局部步行圖：範圍落在某鄉鎮市區內就用該區的圖（記憶體＋磁碟快取），否則依 bbox 建；沒有全區檔用整份 GeoJSON。"""
    global _graph
    db = walk_db()
    if db is not None:
        from .area import bbox_key, case_bbox
        b = bbox or case_bbox(data, pad_m=pad_m)
        if b is None:
            return None
        dk = _district_key(b)
        k = ("d", dk[0]) if dk else bbox_key(b)
        if k not in _cache:
            if len(_cache) >= CACHE_N:
                _cache.pop(next(iter(_cache)))
            _cache[k] = _load_or_build(f"d_{dk[0]}", dk[1], db) if dk else WalkGraph(db.query(k))
        g = _cache[k]
        return g if len(g) else None
    if _graph is None:
        path = os.environ.get("WALK_GRAPH_GEOJSON") or str(DATA_DIR / "walk_graph_jinshan.geojson")
        _graph = WalkGraph.from_geojson(path) if Path(path).exists() else WalkGraph([])
    return _graph if len(_graph) else None


def set_walk_graph(g: WalkGraph | None) -> None:
    global _graph, _db
    _graph = g
    _db = False
    _cache.clear()
