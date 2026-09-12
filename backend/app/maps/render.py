"""
圖說 → PNG（純 PIL，不用瀏覽器）。三張圖用同一組圖層（layers.case_layers 的輸出）：
  sketch  區段略圖：sections + parcels + roads
  zoning  使用分區圖：zoning + sections
  section 地價區段圖：sections + parcels + facilities + distance_lines
底圖：國土測繪中心 WMTS EMAP（可關；抓不到就白底，圖上註明）。字型：依序找 MAP_FONT 環境變數、macOS PingFang／STHeiti、Linux Noto CJK／文泉驛；都沒有就不畫中文標籤並在圖上註明。
"""
from __future__ import annotations

import io
import itertools
import math
import os
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

MODES: dict[str, list[str]] = {"sketch": ["cadastre", "section_map", "sections", "parcels", "roads"], "zoning": ["zoning", "section_map", "sections"], "section": ["cadastre", "section_map", "sections", "parcels", "facilities", "distance_lines"]}
MODE_TITLE = {"sketch": "地價區段略圖", "zoning": "地價使用分區圖", "section": "地價區段圖"}
SCALES = (1000, 1500, 1800, 2000, 2500, 3000, 4000, 5000, 6000, 8000, 10000)
PRINT_W_MM = 277.0     # A4 橫式可印寬；比例尺依「圖寬 px 印成 277 mm」換算
TILE_URL = "https://wmts.nlsc.gov.tw/wmts/{layer}/default/GoogleMapsCompatible/{z}/{y}/{x}"
TILE_LAYERS = ("EMAP", "LANDSECT")     # 電子地圖底圖、段籍圖（段界與段名，透明疊圖）
TILE_DIR = Path(os.environ.get("TILE_CACHE") or Path(__file__).resolve().parents[3] / "data" / "tiles")
FONT_CANDIDATES = [os.environ.get("MAP_FONT") or "", "/System/Library/Fonts/PingFang.ttc", "/System/Library/Fonts/STHeiti Light.ttc",
                   "/System/Library/Fonts/Hiragino Sans GB.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"]


def _font(size: int):
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            try:
                return ImageFont.truetype(p, size), True
            except OSError:
                continue
    return ImageFont.load_default(), False


# ------------------------------------------------------------------ 投影（Web Mercator，配合 WMTS 瓦片）

def _merc(lon: float, lat: float) -> tuple[float, float]:
    x = (lon + 180.0) / 360.0
    s = math.sin(math.radians(lat))
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    return x, y


class _View:
    def __init__(self, bbox: tuple[float, float, float, float], size: tuple[int, int], pad: int = 24, fixed_scale: bool = True, print_w_mm: float = PRINT_W_MM):
        self.w, self.h = size
        x0, y0 = _merc(bbox[0], bbox[3])
        x1, y1 = _merc(bbox[2], bbox[1])
        span = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        self.center_lat = (bbox[1] + bbox[3]) / 2
        self.scale = min((self.w - 2 * pad) / span[0], (self.h - 2 * pad) / span[1])
        self.denominator = None
        if fixed_scale:
            # 換成範本式比例尺：取能放下的最小標準比例尺（1:1800 放得下就用 1:1800）
            mm_per_px = print_w_mm / self.w
            need = self.m_per_px() * 1000 / mm_per_px
            self.denominator = next((d for d in SCALES if d >= need - 1e-6), SCALES[-1])
            mpp = self.denominator * mm_per_px / 1000
            self.scale = 40075016.686 * math.cos(math.radians(self.center_lat)) / mpp
        self.ox = (self.w - span[0] * self.scale) / 2 - x0 * self.scale
        self.oy = (self.h - span[1] * self.scale) / 2 - y0 * self.scale
        self.zoom = max(1, min(19, math.floor(math.log2(self.scale / 256))))

    def px(self, lon: float, lat: float) -> tuple[float, float]:
        x, y = _merc(lon, lat)
        return x * self.scale + self.ox, y * self.scale + self.oy

    def m_per_px(self) -> float:
        return 40075016.686 * math.cos(math.radians(self.center_lat)) / self.scale


# ------------------------------------------------------------------ 底圖瓦片

def _ssl_context():
    """python.org 版 Python 常沒帶系統憑證；有 certifi 就用它，否則用預設。"""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def tile_bytes(z: int, x: int, y: int, timeout: float = 4.0, layer: str = "EMAP") -> bytes | None:
    """一塊瓦片：先看 data/tiles 快取，沒有才向國土測繪中心抓並存下。互動地圖（/api/tiles）與 PNG 繪圖共用。EMAP 沿用舊路徑，其他圖層放子目錄。"""
    if layer not in TILE_LAYERS:
        return None
    p = (TILE_DIR if layer == "EMAP" else TILE_DIR / layer) / str(z) / f"{x}_{y}.png"
    if p.exists():
        return p.read_bytes()
    try:
        req = urllib.request.Request(TILE_URL.format(layer=layer, z=z, x=x, y=y), headers={"User-Agent": "ntpc-appraisal-review/0.3"})
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as r:
            data = r.read()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return data
    except (OSError, ValueError):   # 網路、逾時、憑證：沒有這格
        return None


def tile_cache_status() -> dict:
    """快取瓦片數與涵蓋的鄉鎮市區（取 z=16 瓦片中心點對區界，最多抽 300 片），首頁狀態列用。"""
    import math

    files = list(TILE_DIR.rglob("*.png")) if TILE_DIR.exists() else []
    districts: set[str] = set()
    try:
        from shapely.geometry import Point

        from app.spatial.area import _districts
        dl = _districts()
        picked = [f for f in files if f.parent.name == "16"][:300] or [f for f in files if f.parent.name.isdigit()][:300]
        for f in picked:
            try:                                             # 版面：data/tiles/{z}/{x}_{y}.png
                z = int(f.parent.name)
                x, y = (int(t) for t in f.stem.split("_"))
            except (ValueError, IndexError):
                continue
            n = 2 ** z
            lon = (x + 0.5) / n * 360.0 - 180.0
            lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
            pt = Point(lon, lat)
            d = next((nm for nm, g in dl if g.contains(pt)), None)
            if d:
                districts.add(d)
    except Exception:  # noqa: BLE001, S110 - 沒有區界檔就不標
        pass
    return {"path": str(TILE_DIR), "tiles": len(files), "districts": sorted(districts)}


def _tile(z: int, x: int, y: int, timeout: float, layer: str = "EMAP") -> Image.Image | None:
    data = tile_bytes(z, x, y, timeout, layer)
    if data is None:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except (OSError, ValueError):   # 壞圖：這格留白
        return None


def _draw_basemap(img: Image.Image, v: _View, timeout: float, layer: str = "EMAP") -> bool:
    n = 2 ** v.zoom
    tile_px = v.scale / n
    # 圖面左上角對應的 mercator 座標
    mx0, my0 = (0 - v.ox) / v.scale, (0 - v.oy) / v.scale
    mx1, my1 = (v.w - v.ox) / v.scale, (v.h - v.oy) / v.scale
    ok = 0
    for tx in range(math.floor(mx0 * n), math.ceil(mx1 * n)):
        for ty in range(math.floor(my0 * n), math.ceil(my1 * n)):
            if not (0 <= tx < n and 0 <= ty < n):
                continue
            t = _tile(v.zoom, tx, ty, timeout, layer)
            if t is None:
                continue
            px, py = tx / n * v.scale + v.ox, ty / n * v.scale + v.oy
            size = max(1, round(tile_px))
            img.alpha_composite(t.resize((size, size)), (round(px), round(py)))
            ok += 1
    return ok > 0


# ------------------------------------------------------------------ 幾何繪製

def _rings(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Polygon":
        return [c[0]] if c else []
    if t == "MultiPolygon":
        return [poly[0] for poly in c if poly]
    return []


def _lines(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "LineString":
        return [c]
    if t == "MultiLineString":
        return list(c)
    return []


def _points(geom: dict) -> list[tuple[float, float]]:
    t, c = geom.get("type"), geom.get("coordinates")
    if t == "Point":
        return [tuple(c)]
    if t == "MultiPoint":
        return [tuple(p) for p in c]
    if t in ("Polygon", "MultiPolygon"):
        pts = [p for r in _rings(geom) for p in r]
        if pts:
            return [(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))]
    return []


def _hex(color: str | None, alpha: int, default=(200, 200, 200)) -> tuple[int, int, int, int]:
    if color and color.startswith("#") and len(color) in (4, 7):
        c = color[1:]
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha)
    return (*default, alpha)


def _dashed(draw: ImageDraw.ImageDraw, pts: list[tuple[float, float]], fill, width: int, dash: int = 10, gap: int = 6) -> None:
    on = True
    for (x0, y0), (x1, y1) in itertools.pairwise(pts):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg == 0:
            continue
        d = 0.0
        while d < seg:
            step = dash if on else gap
            e = min(seg, d + step)
            if on:
                draw.line([(x0 + (x1 - x0) * d / seg, y0 + (y1 - y0) * d / seg), (x0 + (x1 - x0) * e / seg, y0 + (y1 - y0) * e / seg)], fill=fill, width=width)
            d = e
            on = not on


def _text_bg(draw, xy, text, font, fill=(20, 20, 20, 255), bg=(255, 255, 255, 210)):
    box = draw.textbbox(xy, text, font=font)
    draw.rectangle((box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1), fill=bg)
    draw.text(xy, text, font=font, fill=fill)


LEGEND = {"sketch": [("紅虛線 地價區段範圍", (210, 0, 0)), ("紅面 比準地", (229, 83, 61)), ("藍面 比較標的", (31, 119, 180)), ("灰線 道路", (110, 110, 110))],
          "zoning": [("色塊 使用分區", (150, 150, 150)), ("紅虛線 地價區段範圍", (210, 0, 0))],
          "section": [("紅虛線 地價區段範圍", (210, 0, 0)), ("紅面 比準地", (229, 83, 61)), ("藍面 比較標的", (31, 119, 180)), ("黃點 區段設施", (242, 199, 68)),
                      ("綠點 宗地接近設施", (87, 185, 107)), ("綠線 步行距離", (42, 157, 143)), ("橘線 直線距離", (231, 111, 81))]}


def _ring_area(ring: list) -> float:
    """經緯度環的面積（鞋帶公式，度²；只用來排序圖例，不換算成 m²）。"""
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def zoning_legend(layers: dict[str, Any], limit: int = 16) -> list[tuple[str, tuple[int, int, int]]]:
    """使用分區圖的圖例：圖上出現的每種分區各一格（名稱＋色塊），依面積由大到小，最多 limit 種；其餘併成「其他分區」。"""
    area: dict[str, float] = {}
    color: dict[str, str] = {}
    for f in (layers.get("zoning") or {}).get("features", []):
        z = f.get("properties", {}).get("zone") or "未分類"
        color.setdefault(z, f["properties"].get("color") or "#dddddd")
        area[z] = area.get(z, 0.0) + sum(_ring_area(r) for r in _rings(f["geometry"]))
    order = sorted(area, key=lambda z: -area[z])
    out = [(z, _legend_swatch(color[z])) for z in order[:limit]]
    if len(order) > limit:
        out.append((f"其他分區（{len(order) - limit} 種）", _legend_swatch("#dddddd")))
    return out


ZONING_ALPHA = 120     # 圖上分區色塊的透明度（疊在底圖上）


def _legend_swatch(hex_color: str) -> tuple[int, int, int]:
    """圖例色塊要和圖上看到的一樣：圖上是色塊以 ZONING_ALPHA 疊在（近白的）底圖上，所以圖例也用同樣透明度混白。"""
    r, g, b, _a = _hex(hex_color, 255)
    a = ZONING_ALPHA / 255
    return (round(r * a + 255 * (1 - a)), round(g * a + 255 * (1 - a)), round(b * a + 255 * (1 - a)))


def _render(layers: dict[str, Any], mode: str, *, highlight: str | None, size: tuple[int, int], basemap: bool, tile_timeout: float,
            subject_section: str, view_pad_m: float, print_w_mm: float) -> tuple[Image.Image, dict[str, Any]]:
    """地圖本體（底圖、圖層、圖上標籤），不含標題／圖例／比例尺文字。回 (RGBA 影像, {denominator, has_base, cjk, m_per_px, k})。
    k = 圖寬相對 1200 px 的倍率，字級與線寬跟著放大，印成大圖時不會變細小。"""
    if mode not in MODES:
        raise ValueError(f"mode 須為 {list(MODES)}")
    bbox = layers.get("bbox")
    if not bbox:
        raise ValueError("案件沒有任何幾何（區段、宗地或設施），無法產圖")
    # 取景用「緊貼幾何＋view_pad_m」，圖層（分區、路網）則裁到較大的 bbox，避免圖上出現裁切邊框
    if layers.get("tight_bbox"):
        from app.spatial.geo import offset_point
        t = layers["tight_bbox"]
        p1, p2 = offset_point(t[0], t[1], -view_pad_m, -view_pad_m), offset_point(t[2], t[3], view_pad_m, view_pad_m)
        bbox = (p1.x, p1.y, p2.x, p2.y)
    w, h = size
    k = max(1.0, w / 1200)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    v = _View(tuple(bbox), (w, h), print_w_mm=print_w_mm)
    has_base = _draw_basemap(img, v, tile_timeout) if basemap else False
    if basemap and mode != "zoning":
        _draw_basemap(img, v, tile_timeout, "LANDSECT")     # 段籍圖：段界與段名（範本略圖／區段圖底圖有段界）
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f_small, cjk = _font(round(14 * k))
    f_label, _ = _font(round(15 * k))
    P = v.px
    show = MODES[mode]
    fc = lambda k: (layers.get(k) or {}).get("features", [])

    if "zoning" in show:
        for f in fc("zoning"):
            col = _hex(f["properties"].get("color"), ZONING_ALPHA)
            for ring in _rings(f["geometry"]):
                d.polygon([P(*p) for p in ring], fill=col, outline=(90, 90, 90, 200))
    if "cadastre" in show:
        for f in fc("cadastre"):
            for ring in _rings(f["geometry"]):
                d.polygon([P(*p) for p in ring], outline=(120, 120, 120, 190))
    if "roads" in show:
        for f in fc("roads"):
            for ln in _lines(f["geometry"]):
                d.line([P(*p) for p in ln], fill=(110, 110, 110, 170), width=round(2 * k))
    if "section_map" in show:
        for f in fc("section_map"):
            for ring in _rings(f["geometry"]):
                pts = [P(*p) for p in ring]
                _dashed(d, pts + pts[:1], (120, 60, 60, 170), round(2 * k))
    if "sections" in show:
        for f in fc("sections"):
            for ring in _rings(f["geometry"]):
                pts = [P(*p) for p in ring]
                d.polygon(pts, fill=(220, 0, 0, 22))
                _dashed(d, pts + pts[:1], (210, 0, 0, 255), round(4 * k))
    if "parcels" in show:
        for f in fc("parcels"):
            subj = f["properties"].get("role") == "subject"
            col = (229, 83, 61) if subj else (31, 119, 180)
            rings = _rings(f["geometry"])
            for ring in rings:
                d.polygon([P(*p) for p in ring], fill=(*col, 110), outline=(*col, 255), width=round(3 * k))
            for pt in _points(f["geometry"]) if not rings else []:
                x, y = P(*pt)
                rr = round(8 * k)
                d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(*col, 220), outline=(40, 40, 40, 255), width=round(2 * k))
    if "distance_lines" in show:
        for f in fc("distance_lines"):
            pr = f["properties"]
            hl = highlight and pr.get("field", "").endswith(highlight)
            col = (42, 157, 143, 255) if pr.get("measure") == "walking" else (231, 111, 81, 255)
            pts = [P(*p) for ln in _lines(f["geometry"]) for p in ln]
            if pr.get("measure") == "straight_estimated":
                _dashed(d, pts, col, round((5 if hl else 2) * k), 6, 5)
            else:
                d.line(pts, fill=col, width=round((5 if hl else 2) * k))
    if "facilities" in show:
        for f in fc("facilities"):
            pr = f["properties"]
            hl = highlight and pr.get("field", "").endswith(highlight)
            fill = (242, 199, 68) if pr.get("scope") == "regional" else (87, 185, 107)
            for ring in _rings(f["geometry"]):
                d.polygon([P(*p) for p in ring], fill=(*fill, 90), outline=(50, 50, 50, 200))
            for pt in _points(f["geometry"]):
                x, y = P(*pt)
                r = round((10 if hl else 6) * k)
                d.ellipse((x - r, y - r, x + r, y + r), fill=(*fill, 240), outline=(30, 30, 30, 255), width=round(2 * k))
    img.alpha_composite(ov)

    # 標籤（需要中文字型）
    d = ImageDraw.Draw(img)
    if cjk and "cadastre" in show and (v.denominator or 0) <= 3000:
        f_lot, _ = _font(round(10 * k))
        for f in fc("cadastre"):
            pts = [p for r in _rings(f["geometry"]) for p in r]
            if pts:
                cx, cy = P(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                if 0 < cx < w and 0 < cy < h:
                    lab = str(f["properties"].get("lot") or "")
                    d.text((cx - 4 * len(lab), cy - 6), lab, font=f_lot, fill=(60, 60, 60, 255))
    if cjk and "section_map" in show:
        own = {f["properties"].get("section_id") for f in fc("sections")}
        for f in fc("section_map"):
            sid = f["properties"].get("section_id")
            if not sid or sid in own:      # 沒編號不標；本案區段由下方 sections 標（含「徵收地」），不重複
                continue
            pts = [p for r in _rings(f["geometry"]) for p in r]
            if pts:
                cx, cy = P(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                if 0 < cx < w and 0 < cy < h:
                    _text_bg(d, (cx - 20, cy - 8), f"區段 {sid}", f_small, fill=(110, 50, 50, 255))
    if cjk:
        if "sections" in show:
            for f in fc("sections"):
                pts = [p for r in _rings(f["geometry"]) for p in r]
                if pts:
                    xy = [P(*p) for p in pts]
                    cx, by = sum(x for x, _ in xy) / len(xy), max(y for _, y in xy)     # 區段標籤放多邊形正下方（範本亦標在區段外側），不與比準地標籤重疊
                    sid = f["properties"].get("section_id", "")
                    _text_bg(d, (cx - 40 * k, min(by + 6 * k, h - 24 * k)), f"區段 {sid}" + ("（徵收地）" if sid and sid == subject_section else ""), f_label, fill=(180, 0, 0, 255))
        if "parcels" in show:
            for f in fc("parcels"):
                for pt in _points(f["geometry"]):
                    x, y = P(*pt)
                    pr = f["properties"]
                    lab = f"實例編號 {pr.get('comp_no')}：{pr.get('parcel_id') or ''}" if pr.get("role") == "comparable" else pr.get("label", "")
                    _text_bg(d, (x + 10, y - 8), lab, f_small)
        if "facilities" in show:
            for f in fc("facilities"):
                pr = f["properties"]
                hl = highlight and pr.get("field", "").endswith(highlight)
                if hl or pr.get("scope") == "individual":
                    for pt in _points(f["geometry"]):
                        x, y = P(*pt)
                        _text_bg(d, (x + 9, y + 4), pr.get("label") or pr.get("name") or "", f_small)
        if "zoning" in show:
            seen = set()
            for f in fc("zoning"):
                z = f["properties"].get("zone")
                if z in seen:
                    continue
                pts = [p for r in _rings(f["geometry"]) for p in r]
                if pts:
                    seen.add(z)
                    cx, cy = P(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                    if 0 < cx < w and 0 < cy < h:
                        d.text((cx, cy), z, font=f_small, fill=(40, 40, 40, 255))

    return img, {"denominator": v.denominator, "has_base": has_base, "cjk": cjk, "m_per_px": v.m_per_px(), "k": k}


def render_png(layers: dict[str, Any], mode: str = "section", *, title: str = "", subtitle: str = "", highlight: str | None = None,
               size: tuple[int, int] = (1200, 900), basemap: bool = True, tile_timeout: float = 4.0, district: str = "",
               subject_section: str = "", appraiser: str = "", view_pad_m: float = 120.0, page: bool = False) -> bytes:
    """layers = case_layers() 的輸出；highlight = 設施欄位名（如 school、transport.station），該欄位的設施與量測線加粗。
    page=True → 照《查估書表範本》第 4–6 頁的版面（A3 橫式白底、標題置中、比例尺與區段範圍圖例、圖置中、右下不動產估價師）。"""
    if page:
        return render_page_png(layers, mode, title=title, subtitle=subtitle, highlight=highlight, basemap=basemap, tile_timeout=tile_timeout,
                               district=district, subject_section=subject_section, appraiser=appraiser)
    img, info = _render(layers, mode, highlight=highlight, size=size, basemap=basemap, tile_timeout=tile_timeout,
                        subject_section=subject_section, view_pad_m=view_pad_m, print_w_mm=PRINT_W_MM)
    w, h = img.size
    k, cjk, has_base = info["k"], info["cjk"], info["has_base"]
    d = ImageDraw.Draw(img)
    f_small, _ = _font(round(14 * k))
    f_label, _ = _font(round(15 * k))
    f_title, _ = _font(round(22 * k))
    # 標題、圖例、比例尺、出處
    head = title or f"{district}土地徵收市價查估{MODE_TITLE[mode]}"
    _text_bg(d, (12, 10), head if cjk else "map", f_title, bg=(255, 255, 255, 235))
    if subtitle and cjk:
        _text_bg(d, (12, 40), subtitle, f_small)
    if cjk:
        sc = f"比例尺：1：{info['denominator']}" if info["denominator"] else ""
        _text_bg(d, (w - 250, 12), f"{sc}（A4 橫式）", f_label)
        _text_bg(d, (w - 250, 40), f"不動產估價師：{appraiser or '　　　　　　'}", f_label)
    legend = LEGEND[mode] if mode != "zoning" else [LEGEND["zoning"][1], *zoning_legend(layers)]
    if cjk:
        rows = min(len(legend), 9)          # 分區種類多時排兩欄
        y0 = h - 24 * rows - 40
        for i, (text, col) in enumerate(legend):
            cx, y = 14 + (i // rows) * 190, y0 + (i % rows) * 24
            d.rectangle((cx, y + 3, cx + 16, y + 17), fill=(*col, 255), outline=(60, 60, 60, 255))
            _text_bg(d, (cx + 22, y), text, f_small)
    _scale_bar(d, info["m_per_px"], (w - 30, h - 40), f_small)
    attr = _attribution(has_base, basemap, cjk)
    _text_bg(d, (12, h - 24), attr, f_small, fill=(70, 70, 70, 255))
    return _encode(img)


def _scale_bar(d: ImageDraw.ImageDraw, mpp: float, right_bottom: tuple[int, int], font, k: float = 1.0) -> None:
    """比例尺線段（取 50/100/200/500/1000 m 中印出來不短於 120 px×k 者），右下角對齊 right_bottom。"""
    for meters in (50, 100, 200, 500, 1000):
        if meters / mpp >= 120 * k:
            break
    bar = meters / mpp
    x1, y1 = right_bottom
    d.rectangle((x1 - bar, y1 - 6 * k, x1, y1), fill=(20, 20, 20, 255))
    d.text((x1 - bar, y1 - 28 * k), f"{meters} m", font=font, fill=(20, 20, 20, 255))


def _attribution(has_base: bool, basemap: bool, cjk: bool) -> str:
    attr = "底圖 © 國土測繪中心 EMAP" if has_base else ("底圖未載入（離線）" if basemap else "無底圖")
    attr2 = "路網 © OpenStreetMap contributors；分區：新北市城鄉發展局" if cjk else ""
    foot = (attr + "；" + attr2) if cjk else ("basemap NLSC" if has_base else "no basemap")
    if not cjk:
        foot += " (no CJK font: labels omitted)"
    return foot


def _encode(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.convert("RGB").quantize(256).save(out, format="PNG", optimize=True)
    return out.getvalue()


# 範本第 4–6 頁：A3 橫式（420×297 mm）；圖面 300×225 mm 置中，標題置中、左上比例尺與區段範圍圖例、右下不動產估價師
PAGE_DPI = 150
PAGE_MM = (420.0, 297.0)
PAGE_MAP_MM = (300.0, 225.0)


def render_page_png(layers: dict[str, Any], mode: str = "section", *, title: str = "", subtitle: str = "", highlight: str | None = None,
                    basemap: bool = True, tile_timeout: float = 4.0, district: str = "", subject_section: str = "", appraiser: str = "",
                    view_pad_m: float = 60.0, dpi: int = PAGE_DPI) -> bytes:
    """照《查估書表範本》第 4–6 頁版面組成一整頁 PNG（A3 橫式，dpi 解析度）。比例尺依「圖面印成 300 mm 寬」換算，標準比例尺（1:1800…）。"""
    mm = lambda v: round(v * dpi / 25.4)
    pt = lambda v: max(8, round(v * dpi / 72))
    PW, PH = mm(PAGE_MM[0]), mm(PAGE_MM[1])
    MW, MH = mm(PAGE_MAP_MM[0]), mm(PAGE_MAP_MM[1])
    img, info = _render(layers, mode, highlight=highlight, size=(MW, MH), basemap=basemap, tile_timeout=tile_timeout,
                        subject_section=subject_section, view_pad_m=view_pad_m, print_w_mm=PAGE_MAP_MM[0])
    cjk, k = info["cjk"], info["k"]
    page = Image.new("RGB", (PW, PH), (255, 255, 255))
    d = ImageDraw.Draw(page)
    f_title, _ = _font(pt(26))
    f_label, _ = _font(pt(15))
    f_small, _ = _font(pt(10))
    f_tiny, _ = _font(pt(8))
    black, grey = (0, 0, 0), (90, 90, 90)
    # 標題置中
    head = title or f"{district}土地徵收市價查估{MODE_TITLE[mode]}"
    if cjk:
        tw = d.textlength(head, font=f_title)
        d.text(((PW - tw) / 2, mm(16)), head, font=f_title, fill=black)
    else:
        d.text((mm(20), mm(16)), "map", font=f_title, fill=black)
    # 左上：比例尺＋區段範圍圖例（範本：略圖／區段圖紅框、分區圖藍框）
    x, y = (PW - MW) // 2, mm(34)
    if cjk:
        sc = f"比例尺：1：{info['denominator']}" if info["denominator"] else "比例尺：—"
        d.text((x, y), sc, font=f_label, fill=black)
        x2 = x + d.textlength(sc, font=f_label) + mm(12)
        box_col = (40, 60, 200) if mode == "zoning" else (210, 0, 0)
        d.rectangle((x2, y + mm(0.5), x2 + mm(9), y + mm(6)), outline=box_col, width=max(2, round(dpi / 60)))
        d.text((x2 + mm(11), y), "區段範圍", font=f_label, fill=box_col)
    # 圖置中，細黑框
    mx, my = (PW - MW) // 2, mm(46)
    page.paste(img.convert("RGB"), (mx, my))
    d.rectangle((mx - 1, my - 1, mx + MW, my + MH), outline=black, width=max(1, round(dpi / 100)))
    # 圖內右下比例尺線段
    _scale_bar(ImageDraw.Draw(page), info["m_per_px"], (mx + MW - mm(6), my + MH - mm(6)), f_small, k)
    # 圖下：其他圖例（範本只有區段範圍；本系統多了比準地／比較標的／設施，放圖下一列）
    if cjk:
        # 圖下最多兩列（每列 5 mm），放不下的分區併成「其他分區（N 種）」；不和頁尾的案件資訊、簽章欄重疊
        entries = LEGEND[mode][1:] if mode != "zoning" else zoning_legend(layers, limit=40)
        row_h, gap, sw = mm(5), mm(8), mm(6.5)
        width = lambda t: sw + d.textlength(t, font=f_small) + gap
        rows: list[list[tuple[str, tuple[int, int, int]]]] = [[]]
        used = 0.0
        placed = 0
        for text, col in entries:
            wtext = width(text)
            if used + wtext > MW:
                if len(rows) == 2:
                    break
                rows.append([])
                used = 0.0
            rows[-1].append((text, col))
            used += wtext
            placed += 1
        rest = len(entries) - placed
        if rest:
            other = (f"其他分區（{rest} 種）", (221, 221, 221))
            if used + width(other[0]) > MW and rows[-1]:
                rows[-1].pop()                                       # 讓位給「其他」
            rows[-1].append(other)
        ly = my + MH + mm(2.5)
        for row in rows:
            lx = mx
            for text, col in row:
                d.rectangle((lx, ly + mm(0.8), lx + mm(5), ly + mm(4)), fill=col, outline=(60, 60, 60))
                d.text((lx + sw, ly), text, font=f_small, fill=black)
                lx += width(text)
            ly += row_h
    # 底部：左＝案件資訊與出處；右＝不動產估價師（同一列，在圖例下方）
    if cjk:
        if subtitle:
            d.text((mx, PH - mm(9.5)), subtitle, font=f_small, fill=grey)
        d.text((mx, PH - mm(5)), _attribution(info["has_base"], basemap, cjk), font=f_tiny, fill=grey)
        sig = f"不動產估價師：{appraiser or ''}"
        d.text((mx + MW - d.textlength(sig, font=f_label) - (0 if appraiser else mm(30)), PH - mm(10.5)), sig, font=f_label, fill=black)
    return _encode(page)


def case_figures(data: dict, *, basemap: bool = True, highlight: str | None = None, appraiser: str = "", page: bool = False) -> list[tuple[str, str, bytes]]:
    """一次產三張：[(mode, 標題, png)]。page=True → 範本頁式（書表 PDF／Excel／預覽用）。"""
    from app.maps.layers import case_layers
    from app.maps.zoning import get_zoning_store
    from app.spatial.roads_store import get_roads
    layers = case_layers(data, zoning=get_zoning_store(), roads=get_roads(data=data), pad_m=900.0)
    case = data.get("case") or {}
    sid = data.get("subject_parcel", {}).get("section_id", "")
    sub = f"案號 {case.get('case_no', '')}　估價基準日 {case.get('valuation_date', '')}　區段 {sid}"
    return [(m, MODE_TITLE[m], render_png(layers, m, subtitle=sub, basemap=basemap, highlight=highlight if m == "section" else None,
                                           district=case.get("district", ""), subject_section=sid, appraiser=appraiser, page=page)) for m in MODES]
