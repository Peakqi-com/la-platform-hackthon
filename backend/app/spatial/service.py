"""POI 庫／OSRM 單例與整案填值入口（API 與測試共用）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.engine.rules import RuleSet, load_ruleset

from .osrm import OSRMClient
from .poi import POIStore
from .reference import fill_parcel, fill_section, select_reference_facilities
from .roads_store import roads_status
from .walking import get_walk_graph, walk_db

_store: POIStore | None = None
_osrm: OSRMClient | None = None
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


MANUAL_POI_PATH = DATA_DIR / "sources" / "manual_poi.geojson"


_store_path: str | None = None


def _walk_status() -> dict:
    db = walk_db()
    if db is not None:
        return {"mode": "sqlite", "path": db.path, "features": db.count()}
    return {"mode": "geojson", "segments": len(get_walk_graph() or []), "path": os.environ.get("WALK_GRAPH_GEOJSON") or str(DATA_DIR / "walk_graph_jinshan.geojson")}


def get_poi_store() -> POIStore:
    """POI_DB（預設 data/poi_ntpc.sqlite 全區，其次 data/poi_osm_jinshan.sqlite、data/poi.sqlite）＋ 人工標定 data/sources/manual_poi.geojson。"""
    global _store
    if _store is None:
        cands = [os.environ.get("POI_DB"), str(DATA_DIR / "poi_ntpc.sqlite"), str(DATA_DIR / "poi_osm_jinshan.sqlite"), str(DATA_DIR / "poi.sqlite")]
        path = next((c for c in cands if c and Path(c).exists()), None)
        global _store_path
        _store_path = path
        _store = POIStore.from_sqlite(path) if path else POIStore()
        if MANUAL_POI_PATH.exists():
            _store.merge(POIStore.from_geojson(MANUAL_POI_PATH, source="人工標定"))
    return _store


def add_manual_poi(ftype: str, name: str, lon: float, lat: float, *, note: str = "", by: str = "") -> dict:
    """UI 上人工標定一個設施（OSM／政府資料沒有的：金山變電所、福緣納骨堂、老街商圈…），立刻可用並寫進 manual_poi.geojson。"""
    import json

    from shapely.geometry import Point

    from .poi import POI
    store = get_poi_store()
    poi = POI(type=ftype, name=name, geom=Point(lon, lat), source="人工標定", source_id=f"manual/{name}",
              attrs={"note": note, "by": by})
    store.merge(POIStore([poi]))
    MANUAL_POI_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(MANUAL_POI_PATH.read_text(encoding="utf-8")) if MANUAL_POI_PATH.exists() else {"type": "FeatureCollection", "features": []}
    existing["features"] = [f for f in existing["features"] if f["properties"].get("source_id") != poi.source_id] + [poi.to_feature()]
    MANUAL_POI_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
    return poi.to_feature()


def set_poi_store(store: POIStore) -> None:
    global _store
    _store = store


def get_osrm() -> OSRMClient:
    global _osrm
    if _osrm is None:
        _osrm = OSRMClient()
    return _osrm


def set_osrm(client: OSRMClient) -> None:
    global _osrm
    _osrm = client


def status() -> dict[str, Any]:
    st = get_poi_store()
    return {"poi": {"count": len(st), "types": st.types(), "path": _store_path or ""},
            "osrm": get_osrm().status(), "walk_graph": _walk_status(), "roads": roads_status()}


def fill_case(data: dict, *, regional: RuleSet | None = None, individual: RuleSet | None = None,
              origin_mode_individual: str = "parcel_centroid", origin_mode_regional: str = "section_boundary",
              mode_overrides: dict[str, str] | None = None, overwrite: bool = False,
              store: POIStore | None = None, osrm: OSRMClient | None = None, walk_graph: Any = "auto") -> dict[str, Any]:
    """
    整案：先以比準地為 anchor 選案件層級參照設施（手冊 p.24 8(2)、p.51 (六)2(2)），
    再填比準地、各比較標的（同一參照設施）、各區段。沒有 geometry 的跳過並記 warnings。
    """
    store = store or get_poi_store()
    osrm = osrm or get_osrm()
    if walk_graph == "auto":
        walk_graph = get_walk_graph(data=data)
    rs = data["case"].get("rulesets") or {}
    regional = regional or load_ruleset(rs.get("regional", "jinshan_commercial_regional"))
    individual = individual or load_ruleset(rs.get("individual", "jinshan_commercial_individual"))
    warnings: list[str] = []
    prov: dict[str, Any] = {"parcels": {}, "sections": {}, "reference": {}}
    subject = data["subject_parcel"]
    rules = [r for r in individual.rules if r.criteria.get("type") == "distance" and r.parcel_field]
    reference = None
    if subject.get("geometry") is not None:
        from .distance import parcel_origin
        anchor = parcel_origin(subject["geometry"], origin_mode_individual)
        reference = select_reference_facilities(anchor, rules, store)
        prov["reference"] = {rid: [{"name": p.name, "type": p.type, "source": p.source} for p in pois] for rid, pois in reference.items()}
        r = fill_parcel(subject, individual, store, reference=reference, osrm=osrm, origin_mode=origin_mode_individual,
                        mode_overrides=mode_overrides, overwrite=overwrite, walk_graph=walk_graph)
        prov["parcels"][subject.get("parcel_id")] = r["provenance"]
    else:
        warnings.append(f"比準地 {subject.get('parcel_id')} 沒有位置或界線，個別因素距離未計算；參照設施改由各比較標的自選")
    for c in data.get("comparables", []):
        if c.get("geometry") is None:
            warnings.append(f"比較標的{c.get('comp_no')} {c.get('parcel_id')} 沒有位置或界線，距離未計算")
            continue
        r = fill_parcel(c, individual, store, reference=reference, osrm=osrm, origin_mode=origin_mode_individual,
                        mode_overrides=mode_overrides, overwrite=overwrite, walk_graph=walk_graph)
        prov["parcels"][c.get("parcel_id")] = r["provenance"]
    for sid, sec in (data.get("sections") or {}).items():
        if sec.get("geometry") is None:
            warnings.append(f"區段 {sid} 沒有範圍多邊形，區域因素距離未計算")
            continue
        anchor = subject.get("geometry") if origin_mode_regional == "subject_parcel" else None
        if origin_mode_regional == "subject_parcel" and anchor is None:
            warnings.append(f"區段 {sid}：量測起點設為比準地但比準地沒有位置，改用區段邊界")
        r = fill_section(sec, regional, store, osrm=osrm, origin_mode="section_boundary" if anchor is None else origin_mode_regional,
                         anchor=anchor, mode_overrides=mode_overrides, overwrite=overwrite, walk_graph=walk_graph)
        prov["sections"][sid] = r["provenance"]
    return {"data": data, "provenance": prov, "warnings": warnings, "osrm": osrm.status()}


def reload_all() -> dict:
    """換了 data/ 或 rules/ 的檔案後不必重啟：清掉所有程序級快取（設施庫、路網、步行圖、分區庫、實價登錄、地價指數、建蔽容積表、區界、淹水圖、量測方式表）。"""
    global _store, _store_path
    cleared = []
    _store, _store_path = None, None
    cleared.append("poi")
    try:
        from . import roads_store as RS
        RS._db, RS._roads = None, None
        RS._cache.clear()
        cleared.append("roads")
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        from . import walking as W
        W._db, W._graph = None, None
        W._cache.clear()
        cleared.append("walk_graph")
    except Exception:  # noqa: BLE001, S110
        pass
    for modname, names in (("app.maps.zoning", ["set_zoning_store"]), ("app.market.lvr", ["load_lvr", "_index"]), ("app.market.index", ["load_index"]),
                           ("app.spatial.admin", ["load_table", "_lvr_zone_index"]), ("app.spatial.area", ["_districts"]),
                           ("app.spatial.survey_draft", ["_flood_index"]), ("app.spatial.terrain", ["_cache"])):
        try:
            import importlib
            m = importlib.import_module(modname)
            for n in names:
                obj = getattr(m, n, None)
                if obj is None:
                    continue
                if n == "set_zoning_store":
                    obj(None)
                elif hasattr(obj, "cache_clear"):
                    obj.cache_clear()
                elif isinstance(obj, dict):
                    obj.clear()
            cleared.append(modname.rsplit(".", 1)[-1])
        except Exception:  # noqa: BLE001, S110
            pass
    try:
        from . import reference as R
        R._FM = None
        cleared.append("facility_measurement")
    except Exception:  # noqa: BLE001, S110
        pass
    return {"cleared": cleared, "data_files": data_file_times()}


def data_file_times() -> dict:
    """主要資料檔的修改時間（健康檢查用；換檔沒重載會看得出來）。"""
    import datetime
    rules = DATA_DIR.parent / "rules"
    files = {"設施庫": DATA_DIR / "poi_ntpc.sqlite", "路網": DATA_DIR / "osm" / "roads.sqlite", "步行圖": DATA_DIR / "osm" / "walk.sqlite",
             "使用分區": DATA_DIR / "zoning" / "ntpc_zoning.sqlite", "實價登錄": DATA_DIR / "lvr" / "f_land.json", "淹水潛勢": DATA_DIR / "flood" / "ntpc_24h350r.geojson",
             "地籍圖": DATA_DIR / "cadastre" / "default.geojson", "建蔽容積表": rules / "zoning_bcr_far.json", "地價指數": rules / "land_price_index.json"}
    out = {}
    for k, f in files.items():
        out[k] = datetime.datetime.fromtimestamp(f.stat().st_mtime, tz=datetime.UTC).astimezone().strftime("%Y-%m-%d %H:%M") if f.exists() else None
    return out
