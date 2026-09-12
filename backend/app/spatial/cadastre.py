"""
地籍幾何：把「段＋地號」變成宗地多邊形（WGS84 GeoJSON），來源依可得性排序：

  1. FileCadastreProvider   需用土地人函送的地籍圖（GeoJSON / Shapefile）。查估辦法 §5、§20：預定徵收範圍地籍圖本來就是必送資料。
  2. NLSCCadastreProvider   國土測繪中心「地籍查詢API」（CAD_004 地號→座標；需申請，NLSC_API_KEY）。介面先留，規格文件拿到再填。
  3. synthesize_parcel_geometry  只有質心（UI 點圖）時，用清冊的面積／寬／深合成矩形，標 geometry_source=synthetic。

段代碼用 NLSC 開放 API（ListCounty / ListTown / ListLandSection，免申請）解析並快取到 data/cadastre/nlsc_codes.json。
每筆 parcel 填入 geometry 時同時寫 geometry_source 與 geometry_note，UI 必須顯示來源。
"""
from __future__ import annotations

import json
import math
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import Point, Polygon, mapping, shape

from .geo import as_shape, to_twd97, to_wgs84

NLSC_BASE = "https://api.nlsc.gov.tw/other"
CACHE_PATH = Path(__file__).resolve().parents[3] / "data" / "cadastre" / "nlsc_codes.json"


class CadastreError(RuntimeError):
    pass


class CadastreNotConfigured(CadastreError):
    pass


# ------------------------------------------------------------------ 地號正規化


def normalize_lot_no(lot: Any) -> str:
    """'489' / '489-1' / '0489-0001' / '489地號' / 489.0 → '489-0' / '489-1'。"""
    if lot is None:
        return ""
    s = str(lot).strip().replace("地號", "").replace("之", "-").replace("－", "-").replace("—", "-")
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", s)
    if not m:
        return s
    return f"{int(m.group(1))}-{int(m.group(2) or 0)}"


def split_parcel_id(parcel_id: str) -> tuple[str | None, str | None]:
    """'金美段489地號' / '新北市金山區金美段489-1地號' → ('金美段', '489-1')。"""
    m = re.search(r"([^\s市區鄉鎮縣]{1,10}段(?:[^\s]{1,6}小段)?)\s*(\d+(?:-\d+)?)", parcel_id or "")
    return (m.group(1), normalize_lot_no(m.group(2))) if m else (None, None)


# ------------------------------------------------------------------ NLSC 段代碼（開放 API）


class SectionCodes:
    def __init__(self, cache_path: Path = CACHE_PATH, client: httpx.Client | None = None, offline: bool = False):
        self.cache_path = cache_path
        self.client = client or httpx.Client(timeout=15)
        self.offline = offline
        self.cache: dict[str, Any] = {}
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")

    def _xml(self, path: str) -> ET.Element:
        if self.offline:
            raise CadastreNotConfigured(f"離線模式且快取沒有 {path}")
        r = self.client.get(f"{NLSC_BASE}/{path}")
        r.raise_for_status()
        return ET.fromstring(r.text)

    def counties(self) -> dict[str, str]:
        if "counties" not in self.cache:
            root = self._xml("ListCounty")
            self.cache["counties"] = {i.findtext("countyname"): i.findtext("countycode") for i in root.iter("countyItem")}
            self._save()
        return self.cache["counties"]

    def towns(self, county_code: str) -> dict[str, str]:
        key = f"towns/{county_code}"
        if key not in self.cache:
            root = self._xml(f"ListTown/{county_code}")
            self.cache[key] = {i.findtext("townname"): i.findtext("towncode") for i in root.iter("townItem")}
            self._save()
        return self.cache[key]

    def sections(self, county_code: str, town_code: str) -> dict[str, dict]:
        key = f"sections/{county_code}/{town_code}"
        if key not in self.cache:
            root = self._xml(f"ListLandSection/{county_code}/{town_code}")
            self.cache[key] = {i.findtext("sectstr"): {"code": i.findtext("sectcode"), "office": i.findtext("office"),
                                                       "office_name": i.findtext("officestr")} for i in root.iter("sectItem")}
            self._save()
        return self.cache[key]

    def resolve(self, county: str, town: str, section: str) -> dict[str, Any]:
        """('新北市','金山區','金美段') → {county_code:'F', town_code:'F25', section_code:'1027', office:'FD', ...}"""
        county = county.replace("台", "臺")
        cc = self.counties().get(county)
        if not cc:
            raise CadastreError(f"找不到縣市「{county}」")
        tc = self.towns(cc).get(town)
        if not tc:
            raise CadastreError(f"找不到鄉鎮市區「{town}」")
        secs = self.sections(cc, tc)
        s = secs.get(section) or next((v for k, v in secs.items() if k.startswith(section) or section.startswith(k)), None)
        if not s:
            raise CadastreError(f"{county}{town} 找不到段「{section}」")
        return {"county": county, "county_code": cc, "town": town, "town_code": tc, "section": section, **s}


# ------------------------------------------------------------------ 地籍圖檔


class FileCadastreProvider:
    """
    地籍圖 GeoJSON（或 pyshp 可讀的 Shapefile）→ {(段, 地號): geometry}。
    欄位名稱因來源而異，用 section_field / lot_field 指定；段可以是段名或段代碼；地號接受 489 / 489-1 / 04890001 等寫法。
    """
    name = "cadastre_file"

    def __init__(self, features: Iterable[dict], *, section_field: str = "段名", lot_field: str = "地號",
                 section_code_field: str | None = None, source: str = "需用土地人地籍圖"):
        self.index: dict[tuple[str, str], dict] = {}
        self.source = source
        self.sections: set[str] = set()
        for f in features:
            props = f.get("properties") or {}
            sec = str(props.get(section_field) or "").strip()
            code = str(props.get(section_code_field) or "").strip() if section_code_field else ""
            lot = _lot_from_props(props.get(lot_field))
            if not lot or not (sec or code):
                continue
            geom = f["geometry"]
            for key in filter(None, (sec, code)):
                self.index[(key, lot)] = {"geometry": geom, "properties": props}
                self.sections.add(key)

    @classmethod
    def from_geojson(cls, path: str | Path, **kw) -> FileCadastreProvider:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["features"], **kw)

    @classmethod
    def from_shapefile(cls, path: str | Path, *, src_epsg: int = 3826, **kw) -> FileCadastreProvider:
        try:
            import shapefile  # pyshp
        except ImportError as e:
            raise CadastreNotConfigured("讀 Shapefile 需要 pyshp：pip install pyshp") from e
        from pyproj import Transformer
        from shapely.ops import transform
        tr = Transformer.from_crs(f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
        feats = []
        with shapefile.Reader(str(path), encoding="utf-8") as sf:
            for sr in sf.shapeRecords():
                g = shape(sr.shape.__geo_interface__)
                if src_epsg != 4326:
                    g = transform(tr.transform, g)
                feats.append({"type": "Feature", "geometry": mapping(g), "properties": sr.record.as_dict()})
        return cls(feats, **kw)

    def lookup(self, section: str, lot_no: str) -> dict | None:
        hit = self.index.get((section, normalize_lot_no(lot_no)))
        if hit is None:
            for (sec, lot), v in self.index.items():
                if lot == normalize_lot_no(lot_no) and (sec.startswith(section) or section.startswith(sec)):
                    hit = v
                    break
        return hit

    def __len__(self) -> int:
        return len({id(v) for v in self.index.values()})


def _lot_from_props(v: Any) -> str:
    """地籍圖常見 8 碼地號 '04890000' → '489-0'。"""
    if v is None:
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{int(s[:4])}-{int(s[4:])}"
    return normalize_lot_no(s)


# ------------------------------------------------------------------ NLSC 地籍查詢 API（需申請）


class NLSCCadastreProvider:
    """CAD_004 地號 → 座標。規格文件與金鑰要向國土測繪中心申請（(04)2252-2966#256）。拿到後填 endpoint 與參數。"""
    name = "nlsc_api"

    def __init__(self, api_key: str | None = None, endpoint: str | None = None):
        self.api_key = api_key or os.environ.get("NLSC_API_KEY")
        self.endpoint = endpoint or os.environ.get("NLSC_CAD_ENDPOINT")

    def lookup(self, section_code: str, lot_no: str) -> dict | None:
        if not self.api_key or not self.endpoint:
            raise CadastreNotConfigured("國土測繪中心地籍查詢API（CAD_004）需申請金鑰與規格：設定 NLSC_API_KEY、NLSC_CAD_ENDPOINT")
        raise CadastreNotConfigured("NLSC CAD_004 介接尚未依規格文件實作（拿到 API 文件後補）")


# ------------------------------------------------------------------ 合成幾何（只有質心時）


def synthesize_parcel_geometry(centroid: Any, area_m2: float | None, width_m: float | None = None,
                               depth_m: float | None = None, bearing_deg: float = 0.0) -> Polygon:
    """
    以質心為中心合成矩形：有寬深 → width × depth（面積不足時等比放大到 area）；只有面積 → 正方形。
    bearing_deg = 寬邊（臨路面）的方位角（0 = 正北），沒有就正北。回傳 WGS84 Polygon。
    """
    c = as_shape(centroid)
    if c.geom_type != "Point":
        c = c.centroid
    if width_m and depth_m:
        w, d = float(width_m), float(depth_m)
        if area_m2 and w * d < float(area_m2) * 0.8:
            k = math.sqrt(float(area_m2) / (w * d))
            w, d = w * k, d * k
    elif area_m2:
        w = d = math.sqrt(float(area_m2))
    else:
        w = d = 10.0
    th = math.radians(bearing_deg)
    cx, cy = to_twd97(c).x, to_twd97(c).y
    pts = []
    for sx, sy in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)):
        x = cx + sx * math.cos(th) - sy * math.sin(th)
        y = cy + sx * math.sin(th) + sy * math.cos(th)
        pts.append((x, y))
    return to_wgs84(Polygon(pts))


# ------------------------------------------------------------------ 整合


def resolve_parcel_geometry(parcel: dict, *, file_provider: FileCadastreProvider | None = None,
                            nlsc: NLSCCadastreProvider | None = None, manual_point: Any = None,
                            section_codes: SectionCodes | None = None, district: str | None = None,
                            overwrite: bool = False) -> dict[str, Any]:
    """
    依序嘗試：地籍圖檔 → NLSC API → 質心合成。成功時寫 parcel.geometry / geometry_source / geometry_note。
    回傳 {"ok": bool, "source": str|None, "note": str}。
    """
    if parcel.get("geometry") is not None and not overwrite and parcel.get("geometry_source") not in (None, "synthetic"):
        return {"ok": True, "source": parcel.get("geometry_source"), "note": "已有幾何，未覆寫"}
    sec, lot = split_parcel_id(parcel.get("parcel_id") or parcel.get("address") or "")
    notes: list[str] = []
    if file_provider is not None and sec and lot:
        hit = file_provider.lookup(sec, lot)
        if hit:
            parcel["geometry"] = hit["geometry"]
            parcel["geometry_source"] = file_provider.name
            parcel["geometry_note"] = f"{file_provider.source}：{sec}{lot}"
            return {"ok": True, "source": file_provider.name, "note": parcel["geometry_note"]}
        notes.append(f"地籍圖檔沒有 {sec}{lot}")
    if nlsc is not None and sec and lot:
        try:
            code = None
            if section_codes is not None and district:
                m = re.match(r"^(.*?[市縣])(.*?[區鄉鎮市])$", district)
                if m:
                    code = section_codes.resolve(m.group(1), m.group(2), sec)["code"]
            hit = nlsc.lookup(code or sec, lot)
            if hit:
                parcel["geometry"] = hit["geometry"]
                parcel["geometry_source"] = nlsc.name
                parcel["geometry_note"] = "國土測繪中心地籍查詢API"
                return {"ok": True, "source": nlsc.name, "note": parcel["geometry_note"]}
        except CadastreError as e:
            notes.append(str(e))
    if manual_point is not None:
        poly = synthesize_parcel_geometry(manual_point, parcel.get("area_m2"), parcel.get("width_m"), parcel.get("depth_m"))
        parcel["geometry"] = mapping(poly)
        parcel["geometry_source"] = "synthetic"
        parcel["geometry_note"] = (f"以人工指定質心＋清冊面積 {parcel.get('area_m2')} m²（寬 {parcel.get('width_m')}／深 {parcel.get('depth_m')}）合成矩形，"
                                   "非地籍圖，距離結果需確認")
        return {"ok": True, "source": "synthetic", "note": parcel["geometry_note"]}
    return {"ok": False, "source": None, "note": "；".join(notes) or "沒有地籍圖檔、NLSC API 或人工質心可用"}


def point_geojson(lon: float, lat: float) -> dict:
    return mapping(Point(lon, lat))


# ------------------------------------------------------------------ KML / GML（國土測繪中心地籍圖 API MAP_001／MAP_002 的回傳格式）


def parse_kml_gml(content: bytes) -> list[dict]:
    """
    KML（Placemark／Polygon／ExtendedData）或 GML（featureMember／Polygon／posList）→ GeoJSON features（WGS84）。
    座標若是 TWD97（數值 > 1000）自動轉 WGS84。屬性照原名保留，段名／地號欄由上層自動辨認。
    """
    root = ET.fromstring(content)
    feats: list[dict] = []

    def _local(tag: str) -> str:
        return tag.split("}")[-1]

    def _coords_text_to_ring(txt: str, swap_axis: bool = False) -> list[list[float]]:
        nums = [float(v) for v in re.split(r"[\s,]+", txt.strip()) if v]
        if not nums:
            return []
        # KML: lon,lat[,alt] 三元或二元；GML posList：x y 成對
        step = 3 if (len(nums) % 3 == 0 and len(nums) % 2 != 0) else 2
        pts = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - step + 1, step)]
        if swap_axis:
            pts = [(b, a) for a, b in pts]
        if pts and (abs(pts[0][0]) > 1000 or abs(pts[0][1]) > 1000):     # TWD97 公尺 → 經緯度
            pts = [(p.x, p.y) for p in (to_wgs84(Point(x, y)) for x, y in pts)]
        return [[x, y] for x, y in pts]

    for el in root.iter():
        name = _local(el.tag)
        if name not in ("Placemark", "featureMember", "member"):
            continue
        props: dict[str, Any] = {}
        rings: list[list[list[float]]] = []
        for sub in el.iter():
            t = _local(sub.tag)
            if t == "SimpleData" and sub.get("name"):
                props[sub.get("name")] = (sub.text or "").strip()
            elif t == "Data" and sub.get("name"):
                v = sub.find("{*}value")
                props[sub.get("name")] = (v.text if v is not None and v.text else "").strip()
            elif t == "coordinates" and sub.text:
                rings.append(_coords_text_to_ring(sub.text))
            elif t == "posList" and sub.text:
                rings.append(_coords_text_to_ring(sub.text, swap_axis=(sub.get("srsDimension") is None and "4326" in (root.get("srsName") or ""))))
            elif t == "name" and sub.text and "name" not in props:
                props["name"] = sub.text.strip()
        # GML 屬性：featureMember 下第一層子元素的純文字子節點
        if name in ("featureMember", "member"):
            for child in el:
                for attr in child:
                    if len(attr) == 0 and attr.text and attr.text.strip() and _local(attr.tag) not in props:
                        props[_local(attr.tag)] = attr.text.strip()
        rings = [r for r in rings if len(r) >= 4]
        if not rings:
            continue
        geom = {"type": "Polygon", "coordinates": [rings[0]]} if len(rings) == 1 else {"type": "MultiPolygon", "coordinates": [[r] for r in rings]}
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    return feats
