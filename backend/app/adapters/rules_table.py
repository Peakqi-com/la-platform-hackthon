"""
評價基準明細表 → rules/*.json。

輸入三種：
  PDF（地政局給的基準明細表範例那種版面）        parse_pdf()
  canonical 長表 CSV / xlsx（我們定義的交換格式）  parse_long_rows()
    欄：scope, group_name, item_no, item_name, level, condition, pct_優, pct_稍優, pct_普通, pct_稍劣, pct_劣, note
    一列 = 一個細項的一個「比準地等級」；pct_X = 比較標的等級為 X 時的修正率
  當天若拿到別種版面 → 只加一個 parse_xxx() 產出同樣的 RawItem[]，後面不動。

RawItem → build_ruleset()：
  1. 細項名稱對回內政部項目目錄（CATALOG；直排 PDF 抽出的字序會亂，用字元多重集/Jaccard 比對，再用順序備援）
  2. 備註欄判定條件文字 → criteria（未滿X / X以上 / X以上未滿Y / X以上或無 / 區段內有 / 有無 / 枚舉）
  3. 矯正矩陣 → 等距則只留 max_pct，否則帶完整 matrix
  4. 對 rules/moi_max_ranges.json 檢查上限；超過 → warning（不判錯）
  5. 推定（無設施時等級、嫌惡設施區段內等級）一律標 warning

數值不寫死：所有等級、修正率、級距都來自輸入表。
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.engine.rules import RULES_DIR

from .common import AdapterResult, char_jaccard, norm_label, norm_text, same_char_multiset, to_number

LEVEL_ORDER = ["優", "稍優", "普通", "稍劣", "劣"]
LEVEL_ORDER_EXT = ["極優", "優", "稍優", "普通", "稍劣", "劣", "極劣"]                 # 樹林表「其他影響因素」七級
LEVEL_RE = r"(極優|極劣|稍優|稍劣|普通|優|劣)"

# ------------------------------------------------------------------ 內政部項目目錄（附件 24/25 的項目結構，不含數值）


@dataclass(frozen=True)
class CatalogItem:
    group: str
    name: str
    field: str                       # survey_field 或 parcel_field
    kind: str                        # enum | bool | bands | distance | manual
    unit: str | None = None
    facility_types: tuple[str, ...] = ()
    item_no: int | None = None
    aliases: tuple[str, ...] = ()
    farther_is_better: bool = False


REGIONAL_CATALOG: list[CatalogItem] = [
    CatalogItem("土地使用管制", "都市計畫（內、外）", "land_control.urban_plan", "enum", aliases=("都市計畫內外",)),
    CatalogItem("土地使用管制", "使用分區(使用地類別)", "land_control.zoning", "enum", aliases=("使用分區（編定）", "使用分區﹝編定﹞")),
    CatalogItem("土地使用管制", "建蔽率", "land_control.bcr", "bands", "%"),
    CatalogItem("土地使用管制", "容積率", "land_control.far", "bands", "%"),
    CatalogItem("土地使用管制", "有無禁止建築", "land_control.building_prohibited", "bool"),
    CatalogItem("土地使用管制", "有無限制建築（整體開發、面積限制、高度限制……等）", "land_control.building_restricted", "bool", aliases=("有無限制建築",)),
    CatalogItem("交通運輸", "主要道路寬度", "transport.main_road_width_m", "bands", "m"),
    CatalogItem("交通運輸", "區段內道路平均寬度", "transport.avg_road_width_m", "bands", "m"),
    CatalogItem("交通運輸", "接近大型車站之程度", "transport.major_station", "distance", "m", ("hsr_station", "rail_station", "intercity_bus_station", "mrt_station")),
    CatalogItem("交通運輸", "站牌之接近程度或密集程度", "transport.bus_stop", "distance", "m", ("bus_stop",)),
    CatalogItem("交通運輸", "交流道之有無及接近交流道之程度", "transport.interchange", "distance", "m", ("highway_interchange",)),
    CatalogItem("交通運輸", "區段內道路規劃及闢建程度", "transport.road_development", "enum"),
    CatalogItem("自然條件", "日照", "natural.sunlight", "enum"),
    CatalogItem("自然條件", "景觀", "natural.view", "enum"),
    CatalogItem("自然條件", "傾斜度", "natural.slope", "enum"),
    CatalogItem("自然條件", "排水之良否", "natural.drainage", "enum", aliases=("保（排）水之良否", "排水良否")),
    CatalogItem("自然條件", "地勢", "natural.terrain", "enum"),
    CatalogItem("土地改良", "建築基地改良或其他改良", "improvement.building_site", "enum"),
    CatalogItem("公共建設", "接近學校之程度", "public.school", "distance", "m", ("school",)),
    CatalogItem("公共建設", "接近市場之程度（傳統市場、超級市場、超大型購物中心）", "public.market", "distance", "m", ("traditional_market", "supermarket", "hypermarket"), aliases=("接近市場之程度",)),
    CatalogItem("公共建設", "接近公園（里鄰公園、一般公園）、廣場、徒步區之程度", "public.park", "distance", "m", ("park", "plaza", "pedestrian_zone"), aliases=("接近公園、廣場、徒步區之程度",)),
    CatalogItem("公共建設", "接近觀光遊憩設施之程度", "public.tourism", "distance", "m", ("tourist_attraction",)),
    CatalogItem("公共建設", "停車場地之便利程度", "public.parking", "distance", "m", ("parking_lot",)),
    CatalogItem("公共建設", "接近服務性設施的程度", "public.service", "distance", "m", ("service_facility",)),
    CatalogItem("特殊設施", "電業設施及公用氣體燃料設施之有無及接近程度", "special.utility", "distance", "m", ("substation", "hv_tower", "gas_tank", "oil_tank", "gas_station"), farther_is_better=True),
    CatalogItem("特殊設施", "殯葬設施之有無及接近程度", "special.funeral", "distance", "m", ("cemetery", "funeral_home", "crematorium", "columbarium"), farther_is_better=True),
    CatalogItem("特殊設施", "廢棄物處理設施之有無及接近程度", "special.waste", "distance", "m", ("sewage_plant", "landfill", "incinerator"), farther_is_better=True),
    CatalogItem("環境污染", "水污染、噪音污染、廢氣污染、廢棄物污染等之有無及接近程度", "pollution.source", "distance", "m", ("pollution_source",), aliases=("環境污染之有無及接近程度",), farther_is_better=True),
    CatalogItem("工商活動", "百貨公司之有無、數量、接近程度", "commerce.department_store", "distance", "m", ("department_store",)),
    CatalogItem("工商活動", "金融機構之有無、數量、接近程度", "commerce.bank", "distance", "m", ("bank", "credit_union", "post_office_bank")),
    CatalogItem("工商活動", "娛樂設施之有無、數量、接近程度", "commerce.entertainment", "distance", "m", ("cinema", "entertainment")),
    CatalogItem("工商活動", "大型展示中心或觀光飯店之有無、數量、接近程度", "commerce.hotel", "distance", "m", ("exhibition_center", "tourist_hotel")),
    CatalogItem("工商活動", "顧客通行量之多寡", "commerce.foot_traffic", "enum"),
    CatalogItem("工商活動", "店舖之毗連狀態", "commerce.shop_ratio_pct", "bands", "%", aliases=("店鋪之毗連狀態",)),
    CatalogItem("其他影響因素", "其他影響因素", "other", "manual"),
]

INDIVIDUAL_CATALOG: list[CatalogItem] = [
    CatalogItem("宗地條件", "面積(M2)", "area_m2", "bands", "m2", item_no=7, aliases=("面積",)),
    CatalogItem("宗地條件", "寬度(M)", "width_m", "bands", "m", item_no=8, aliases=("寬度",)),
    CatalogItem("宗地條件", "深度(M)", "depth_m", "bands", "m", item_no=9, aliases=("深度",)),
    CatalogItem("宗地條件", "形狀", "shape", "enum", item_no=10),
    CatalogItem("宗地條件", "臨街情形", "frontage", "enum", item_no=11, aliases=("臨路情形",)),
    CatalogItem("宗地條件", "地勢", "terrain", "enum", item_no=12),
    CatalogItem("道路條件", "道路種類", "road_type", "enum", item_no=13),
    CatalogItem("道路條件", "面前道路寬度", "front_road_width_m", "bands", "m", item_no=14),
    CatalogItem("接近條件", "接近學校之程度", "school", "distance", "m", ("school",), item_no=15, aliases=("接近學校程度",)),
    CatalogItem("接近條件", "接近市場之程度", "market", "distance", "m", ("traditional_market", "supermarket", "hypermarket"), item_no=16, aliases=("接近市場程度",)),
    CatalogItem("接近條件", "接近公園、廣場之程度", "park", "distance", "m", ("park", "plaza"), item_no=17, aliases=("接近公園、廣場程度",)),
    CatalogItem("接近條件", "接近車站之程度", "station", "distance", "m", ("bus_stop", "rail_station", "mrt_station", "intercity_bus_station"), item_no=18, aliases=("接近車站程度",)),
    CatalogItem("接近條件", "接近商圈之程度", "commercial_district", "distance", "m", ("commercial_district",), item_no=19, aliases=("接近商圈程度",)),
    CatalogItem("周邊環境條件", "嫌惡設施(類型)", "nuisance", "distance", "m",
                ("cemetery", "funeral_home", "crematorium", "columbarium", "substation", "hv_tower", "gas_station", "gas_tank",
                 "incinerator", "landfill", "sewage_plant", "pollution_source"), item_no=20, aliases=("嫌惡設施之有無", "嫌惡設施"), farther_is_better=True),
    CatalogItem("周邊環境條件", "停車方便性", "street_parking", "enum", item_no=21),
    CatalogItem("行政條件", "使用分區或編定用地", "zoning", "enum", item_no=22, aliases=("使用分區或編定",)),
    CatalogItem("行政條件", "建蔽率(%)", "bcr_pct", "bands", "%", item_no=23, aliases=("建蔽率",)),
    CatalogItem("行政條件", "容積率(%)", "far_pct", "bands", "%", item_no=24, aliases=("容積率",)),
    CatalogItem("行政條件", "有無禁限建", "building_restricted", "bool", item_no=25),
    CatalogItem("其他", "其他", "other", "manual", item_no=6),
]

GROUP_ALIASES = {"環境汙染": "環境污染", "特殊設施環境汙染": "特殊設施", "其他": "其他影響因素"}

# ------------------------------------------------------------------ 中間表示


@dataclass
class RawItem:
    scope: str                                  # regional | individual
    group_name: str
    raw_name: str
    levels: list[str]                           # 比較標的等級（表頭），由優到劣
    matrix: dict[str, dict[str, float]]         # {比準地等級: {比較標的等級: pct}}
    conditions: dict[str, str] = field(default_factory=dict)   # {等級: 條件文字}
    note: str = ""                              # 「以…衡量」
    item_no: int | None = None
    max_pct_declared: float | None = None
    source_ref: str = ""                        # 例：PDF p2 block 3


# ------------------------------------------------------------------ PDF 解析


def _s(v: Any) -> str:
    return "" if v is None else unicodedata.normalize("NFKC", str(v)).replace("\n", "").strip()


def parse_pdf(src: str | Path | bytes) -> tuple[list[RawItem], dict[str, Any]]:
    """PyMuPDF find_tables → RawItem[]。回傳 (items, meta{land_use, titles})。"""
    import fitz

    doc = fitz.open(stream=src, filetype="pdf") if isinstance(src, (bytes, bytearray)) else fitz.open(str(src))
    items: list[RawItem] = []
    meta: dict[str, Any] = {"titles": [], "land_use": None, "pages": len(doc)}
    for pno, page in enumerate(doc, start=1):
        text = page.get_text("text")
        title = next((l.strip() for l in text.splitlines() if "評價基準明細表" in l), "")
        scope = "individual" if "個別因素" in text else ("regional" if "區域因素" in text else None)
        if title:
            meta["titles"].append(title)
            m = re.search(r"(住宅|商業|工業|農業|其他)用地", title)
            if m and not meta["land_use"]:
                meta["land_use"] = m.group(0)
        if scope is None:
            scope = items[-1].scope if items else "regional"
        group = items[-1].group_name if items and items[-1].scope == scope else ""
        for tb in page.find_tables().tables:
            rows = tb.extract()
            cur: RawItem | None = None
            blk = 0
            for r in rows:
                ncol = max(9, len(r))
                cells = [_s(c) for c in r] + [""] * (ncol - len(r))
                c0, c1, c2 = cells[0], cells[1], cells[2]
                note = next((c for c in reversed(cells[8:]) if c), "")   # 備註在第 9 欄之後最右邊有字的格（七級表為 11 欄）
                if re.fullmatch(r"[+\-−]?\d+(?:\.\d+)?", note.strip()):     # 七級表數字列的最右格是修正率，不是備註
                    note = ""
                if any(k in c2 for k in ("比凖地", "比準地", "基準", "目標區段")):       # 個別表「比準地／宗地」、區域表「基準區段／目標區段」
                    blk += 1
                    if c0 and "主要項目" not in c0:
                        group = c0
                    levels = [c for c in cells[3:] if c in LEVEL_ORDER_EXT]
                    cur = RawItem(scope, group, c1, levels, {}, note=note, source_ref=f"PDF p{pno} block{blk}")
                    items.append(cur)
                    if note:
                        _absorb_conditions(cur, note)
                    continue
                if cur is None:
                    continue
                if c2 in LEVEL_ORDER_EXT:
                    vals = cells[3:3 + len(cur.levels)]
                    cur.matrix[c2] = {lv: to_number(v) for lv, v in zip(cur.levels, vals)}
                    if to_number(c1) is not None:
                        cur.max_pct_declared = to_number(c1)
                    if note:
                        _absorb_conditions(cur, note)
                    continue
                if to_number(c1) is not None and not c2:
                    cur.max_pct_declared = to_number(c1)
                if note:
                    _absorb_conditions(cur, note)
        _fallback_conditions_from_text(items, text, pno)
    return items, meta


def _fallback_conditions_from_text(items: list[RawItem], page_text: str, pno: int) -> None:
    """備註格跨欄時 find_tables 只抓到第一句，等級條件掉了：從頁面純文字找該句之後的「優：…劣：…」補回。"""
    flat = unicodedata.normalize("NFKC", page_text).replace("\n", "")
    for it in items:
        if it.conditions or not it.note or f"p{pno} " not in it.source_ref:
            continue
        head = unicodedata.normalize("NFKC", it.note).replace("\n", "")[:12]
        i = flat.find(head)
        if i < 0:
            continue
        sents = [m.span() for m in re.finditer(r"以(?!上|下|內|外)[^:：]{4,40}?(?:衡量|制定|計算|判定)", flat)]   # 各項目的說明句
        prev_end = max([e for s_, e in sents if e <= i], default=0)
        next_start = min([s_ for s_, e in sents if s_ > i + len(head)], default=len(flat))
        window = flat[prev_end:next_start]                                   # 說明句前後、到鄰項說明句為止（直排表文字順序會前後散落）
        if "優:" in window or "優：" in window:
            _absorb_conditions(it, window)
            if it.conditions:
                it.note = (it.note or "") + "（等級條件由頁面文字補回，需確認）"


def _absorb_conditions(item: RawItem, text: str) -> None:
    """備註欄文字可能一格塞全部等級（優：…稍優：…），也可能一列一個。切開後填 conditions。"""
    t = unicodedata.normalize("NFKC", text).replace("\n", "")
    t = re.sub(r"(?<![\d.])2\s+(\d+(?:\.\d+)?)\s*m\s*(以上|以下|未滿)", r"\1m2\2", t)      # 上標 m² 被拆成「2 600m 以上」
    t = re.sub(r"(\d)\s*m\s*2(?=\s*(以上|以下|未滿|$|\s))", r"\1m2", t)
    parts = re.split(r"(?<![稍極])(?=(?:極優|極劣|稍優|稍劣|普通|優|劣)\s*[:：])", t)
    for p in parts:
        m = re.match(r"^" + LEVEL_RE + r"\s*[:：]\s*(.*)$", p.strip())
        if m:
            lv, cond = m.group(1), m.group(2).strip()
            if lv in item.conditions and cond and item.conditions[lv] != cond:
                item.conditions[lv] = item.conditions[lv] + " " + cond
            elif cond:
                item.conditions[lv] = cond


# ------------------------------------------------------------------ canonical 長表

LONG_COLUMNS = ["scope", "group_name", "item_no", "item_name", "level", "condition",
                "pct_優", "pct_稍優", "pct_普通", "pct_稍劣", "pct_劣", "note"]


def items_to_long_rows(items: list[RawItem]) -> list[dict[str, Any]]:
    rows = []
    for it in items:
        for lv in it.levels:
            row = {"scope": it.scope, "group_name": it.group_name, "item_no": it.item_no or "", "item_name": it.raw_name,
                   "level": lv, "condition": it.conditions.get(lv, ""), "note": it.note}
            for cl in LEVEL_ORDER:
                v = it.matrix.get(lv, {}).get(cl)
                row[f"pct_{cl}"] = "" if v is None else v
            rows.append(row)
    return rows


def write_long_csv(items: list[RawItem], dest: str | Path | io.StringIO) -> None:
    rows = items_to_long_rows(items)
    if isinstance(dest, io.StringIO):
        w = csv.DictWriter(dest, fieldnames=LONG_COLUMNS)
        w.writeheader()
        w.writerows(rows)
        return
    with open(dest, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LONG_COLUMNS)
        w.writeheader()
        w.writerows(rows)


def parse_long_rows(rows: list[dict[str, Any]]) -> list[RawItem]:
    items: list[RawItem] = []
    cur: RawItem | None = None
    for r in rows:
        r = {norm_text(k): v for k, v in r.items()}
        name = _s(r.get("item_name"))
        if not name:
            continue
        scope = _s(r.get("scope")) or ("individual" if _s(r.get("item_no")) else "regional")
        key = (scope, _s(r.get("group_name")), name)
        if cur is None or (cur.scope, cur.group_name, cur.raw_name) != key:
            cur = RawItem(scope, _s(r.get("group_name")), name, [], {}, note=_s(r.get("note")),
                          item_no=int(to_number(r.get("item_no"))) if to_number(r.get("item_no")) is not None else None,
                          source_ref=f"long row {len(items) + 1}")
            items.append(cur)
        lv = _s(r.get("level"))
        if lv not in LEVEL_ORDER:
            continue
        if lv not in cur.levels:
            cur.levels.append(lv)
        cur.matrix[lv] = {cl: to_number(r.get(f"pct_{cl}")) for cl in LEVEL_ORDER if to_number(r.get(f"pct_{cl}")) is not None}
        cond = _s(r.get("condition"))
        if cond:
            cur.conditions[lv] = cond
    for it in items:
        it.levels.sort(key=LEVEL_ORDER.index)
    return items


def read_long_csv(src: str | Path | bytes) -> list[RawItem]:
    text = src.decode("utf-8-sig") if isinstance(src, (bytes, bytearray)) else Path(src).read_text(encoding="utf-8-sig")
    return parse_long_rows(list(csv.DictReader(io.StringIO(text))))


def read_long_xlsx(src: str | Path | bytes) -> list[RawItem]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    header = [_s(h) for h in rows[0]]
    return parse_long_rows([dict(zip(header, r)) for r in rows[1:]])


# ------------------------------------------------------------------ 判定條件文法

_UNIT_RE = r"(m2|m²|㎡|km|m|公尺|米|%|％)?"
_N = r"(\d+(?:\.\d+)?)"


def _clean_cond(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)
    t = t.replace(",", "").replace("，", "").replace(" ", "").replace("M", "m").replace("公尺", "m").replace("㎡", "m2").replace("m²", "m2")
    return t


def parse_condition(text: str) -> dict[str, Any]:
    """
    單一等級的條件文字 → 結構。kind: range | in_section | bool | enum
    range: {"ranges": [{"min","max"}], "or_none": bool, "unit": "m|m2|%|None", "typo": bool}
    """
    raw = text
    t = _clean_cond(text)
    if re.fullmatch(r"區段內有.*", t):
        return {"kind": "in_section"}
    if t == "無" or re.fullmatch(r"無(禁止|限制|禁限|禁、限|禁限制).*建.*", t):
        return {"kind": "bool", "value": False}
    if t == "有" or re.fullmatch(r"有(禁止|限制|禁限|禁、限|禁限制).*建.*", t):
        return {"kind": "bool", "value": True}
    out: dict[str, Any] = {"kind": "range", "ranges": [], "or_none": False, "unit": None, "typo": False}

    def num(v: str, unit: str) -> float:
        x = float(v)
        u = unit or ""
        if u == "km":
            out["typo"] = True     # 基準表範例把 200m 打成 200km；一律視為 m 並 warning
        if u in ("m", "km", ""):
            out["unit"] = out["unit"] or ("m" if u else None)
        elif u == "m2":
            out["unit"] = "m2"
        elif u in ("%", "％"):
            out["unit"] = "%"
        return x

    m = re.match(r"^未滿" + _N + _UNIT_RE + r"或" + _N + _UNIT_RE + r"以上", t)
    if m:
        out["ranges"] = [{"max": num(m.group(1), m.group(2))}, {"min": num(m.group(3), m.group(4))}]
        return out
    m = re.match(r"^" + _N + _UNIT_RE + r"以上未滿" + _N + _UNIT_RE, t)
    if m:
        out["ranges"] = [{"min": num(m.group(1), m.group(2)), "max": num(m.group(3), m.group(4))}]
        return out
    m = re.match(r"^" + _N + _UNIT_RE + r"以下$", t)                       # 「50m2 以下」：含等於，視同未滿（邊界值極少見，列需確認）
    if m:
        out["ranges"] = [{"max": num(m.group(1), m.group(2))}]
        return out
    m = re.match(r"^未滿" + _N + _UNIT_RE + r"(或無)?", t)
    if m:
        out["ranges"] = [{"max": num(m.group(1), m.group(2))}]
        out["or_none"] = bool(m.group(3))
        return out
    m = re.match(r"^" + _N + _UNIT_RE + r"以上(或無)?", t)
    if m:
        out["ranges"] = [{"min": num(m.group(1), m.group(2))}]
        out["or_none"] = bool(m.group(3))
        return out
    m = re.match(r"^" + _N + _UNIT_RE + r"以內(或無)?", t)
    if m:
        out["ranges"] = [{"max": num(m.group(1), m.group(2))}]
        out["or_none"] = bool(m.group(3))
        return out
    return {"kind": "enum", "values": _expand_enum(raw)}


def _expand_enum(text: str) -> list[str]:
    """「農業區、保護區建地目」→ [農業區建地目, 保護區建地目, 原文]；「甲建、乙建」→ [甲建, 乙建, 原文]。"""
    t = unicodedata.normalize("NFKC", text).strip()
    parts = [p.strip() for p in re.split(r"[、,，/]", t) if p.strip()]
    if len(parts) <= 1:
        return [t]
    tail = parts[-1]
    out = []
    for p in parts[:-1]:
        if p[-1] in tail and not tail.startswith(p):
            suffix = tail[tail.index(p[-1]) + 1:]
            out.append(p + suffix)
        else:
            out.append(p)
    out.append(tail)
    if t not in out:
        out.append(t)
    return out


# ------------------------------------------------------------------ 建 ruleset


def _match_catalog(item: RawItem, catalog: list[CatalogItem], used: set[str], result: AdapterResult) -> CatalogItem | None:
    cands = [c for c in catalog if c.name not in used]
    raw = item.raw_name
    for c in cands:
        if any(same_char_multiset(raw, n) for n in (c.name, *c.aliases)):
            return c
    grp = GROUP_ALIASES.get(norm_label(item.group_name), item.group_name)
    scored = []
    for c in cands:
        best = max(char_jaccard(raw, n) for n in (c.name, *c.aliases))
        if norm_label(c.group) == norm_label(grp) or norm_label(c.group) in norm_label(item.group_name):
            best += 0.15
        scored.append((best, c))
    scored.sort(key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.45:
        if scored[0][0] < 0.75:
            result.warn(f"細項「{raw}」對到內政部項目「{scored[0][1].name}」（名稱不完全相同，請確認）")
        return scored[0][1]
    return None


def _order_fallback(item: RawItem, catalog: list[CatalogItem], used: set[str], result: AdapterResult) -> CatalogItem | None:
    grp = GROUP_ALIASES.get(norm_label(item.group_name), item.group_name)
    for c in catalog:
        if c.name in used:
            continue
        if norm_label(c.group) == norm_label(grp) or norm_label(c.group) in norm_label(item.group_name):
            result.warn(f"細項「{item.raw_name}」無法依名稱對應，依主要項目「{c.group}」內順序推定為「{c.name}」（需確認）")
            return c
    return None


def _build_criteria(item: RawItem, cat: CatalogItem | None, result: AdapterResult, rid: str) -> dict[str, Any]:
    conds = {lv: parse_condition(txt) for lv, txt in item.conditions.items() if txt}
    if not conds:
        result.warn(f"細項「{item.raw_name}」備註欄沒有判定條件，等級由估價師自填、系統不判定")
        return {"type": "manual"}
    kinds = {c["kind"] for c in conds.values()}
    kind_hint = cat.kind if cat else None
    if kinds <= {"bool"} and len(item.levels) == 2:
        true_lv = next((lv for lv, c in conds.items() if c["value"]), item.levels[-1])
        false_lv = next((lv for lv, c in conds.items() if not c["value"]), item.levels[0])
        return {"type": "boolean", "true_level": true_lv, "false_level": false_lv}
    if kinds <= {"range", "in_section"}:
        if any(c.get("typo") for c in conds.values()):
            result.warn(f"{rid} {item.raw_name}: 條件文字單位「km」疑為「m」誤植，已視為公尺（基準表本身疑點）")
        unit = next((c["unit"] for c in conds.values() if c.get("unit")), None) or (cat.unit if cat else None)
        is_distance = (kind_hint == "distance") if kind_hint in ("distance", "bands") else (unit == "m")
        bands = []
        none_level = None
        in_section_level = None
        for lv in item.levels:
            c = conds.get(lv)
            if not c:
                continue
            if c["kind"] == "in_section":
                in_section_level = lv
                continue
            for rg in c["ranges"]:
                bands.append({"level": lv, **rg})
            if c.get("or_none"):
                none_level = lv
        crit: dict[str, Any] = {"type": "distance" if is_distance else "bands"}
        if not is_distance:
            crit["unit"] = unit or "m"
        farther = _farther_is_better(item, conds)
        if is_distance and farther:
            crit["direction"] = "farther_is_better"
            crit["aggregate"] = "worst"
        if is_distance and none_level is None:
            none_level = item.levels[0] if farther else item.levels[-1]
            result.warn(f"{rid} {item.raw_name}: 基準表未寫「無設施」時的等級，推定為「{none_level}」（{'嫌惡設施無則最優' if farther else '無則最劣'}，需確認）")
        if none_level is not None:
            crit["none_level"] = none_level
        if is_distance and item.scope == "regional":
            if in_section_level is None:
                in_section_level = item.levels[-1] if farther else item.levels[0]
                result.warn(f"{rid} {item.raw_name}: 基準表未寫「區段內有」時的等級，推定為「{in_section_level}」（需確認）")
            crit["in_section_level"] = in_section_level
        elif in_section_level is not None:
            crit["in_section_level"] = in_section_level
        crit["bands"] = bands
        return crit
    if kinds <= {"enum", "bool"}:
        mapping: dict[str, str] = {}
        default = None
        for lv in item.levels:
            c = conds.get(lv)
            if not c:
                continue
            vals = c["values"] if c["kind"] == "enum" else (["有"] if c["value"] else ["無"])
            for v in vals:
                if re.fullmatch(r"其他.*", v):
                    default = lv
                else:
                    mapping.setdefault(v, lv)
        if not mapping:                                                   # 條件全是「其他影響因素極優／優…」這種主觀描述 → 人工判定
            return {"type": "manual", "conditions": item.conditions}
        crit = {"type": "enum", "map": mapping}
        if default:
            crit["default"] = default
        normalize = _zoning_normalize(mapping)
        if normalize:
            crit["normalize"] = normalize
        return crit
    result.warn(f"細項「{item.raw_name}」的條件文字同時有數值與文字，系統無法自動判定，等級由估價師自填")
    return {"type": "manual", "conditions": item.conditions}


def _zoning_normalize(mapping: dict[str, str]) -> dict[str, str]:
    out = {}
    for base in ("商業區", "住宅區", "工業區"):
        if base in mapping:
            for k in ("第一種", "第二種", "第三種", "第四種", "第五種"):
                out[f"{k}{base}"] = base
    return out


def _farther_is_better(item: RawItem, conds: dict[str, dict]) -> bool:
    """最優等級的距離下限 > 最劣等級的距離下限 → 愈遠愈好（嫌惡設施）。"""
    def lo(lv: str) -> float | None:
        c = conds.get(lv)
        if not c or c["kind"] != "range":
            return None
        mins = [r.get("min", 0.0) if "min" in r else 0.0 for r in c["ranges"]]
        maxs = [r.get("max") for r in c["ranges"] if "max" in r]
        return max(mins) if mins else (min(maxs) if maxs else None)
    best, worst = lo(item.levels[0]), lo(item.levels[-1])
    if best is None or worst is None:
        return False
    return best > worst


def _matrix_info(item: RawItem, result: AdapterResult, rid: str) -> tuple[float, dict | None]:
    vals = [abs(v) for row in item.matrix.values() for v in row.values() if v is not None]
    max_pct = max(vals) if vals else (item.max_pct_declared or 0.0)
    if item.max_pct_declared is not None and abs(item.max_pct_declared - max_pct) > 1e-6:
        result.warn(f"{rid} {item.raw_name}: 表上標示的最大修正率 {item.max_pct_declared} 與矩陣最大值 {max_pct} 不一致")
    n = len(item.levels)
    step = max_pct / (n - 1) if n > 1 else 0.0
    equi = True
    full: dict[str, dict[str, float]] = {}
    for si, s in enumerate(item.levels):
        full[s] = {}
        for ci, c in enumerate(item.levels):
            v = item.matrix.get(s, {}).get(c)
            if v is None:
                equi = False
                v = (ci - si) * step
            full[s][c] = float(v)
            if abs(v - (ci - si) * step) > 1e-6:
                equi = False
    return max_pct, (None if equi else full)


def load_moi() -> dict:
    return json.loads((RULES_DIR / "moi_max_ranges.json").read_text(encoding="utf-8"))


def _moi_check(rules: list[dict], scope: str, land_use: str | None, result: AdapterResult) -> None:
    moi = load_moi()
    if scope == "regional":
        table = (moi["regional"].get(land_use or "") or {})
        if not table:
            result.warn(f"內政部上限表沒有「{land_use}」的區域因素欄，略過上限檢查")
            return
        cols, items = table["columns"], table["items"]
        # 選違規最少的欄當作該表的用地細類
        best_col, best_viol = None, None
        for ci, col in enumerate(cols):
            viol = []
            for r in rules:
                lim = _moi_lookup(items, r["name"])
                if lim is not None and lim[ci] is not None and r["max_pct"] > lim[ci] + 1e-6:
                    viol.append(f"{r['id']} {r['name']} max {r['max_pct']} > 上限 {lim[ci]}")
            if best_viol is None or len(viol) <= len(best_viol):   # 同分取較後（較嚴）的欄
                best_col, best_viol = col, viol
        result.data.setdefault("meta", {})[f"{scope}_moi_column"] = best_col
        for v in best_viol or []:
            result.warn(f"超過內政部最大影響範圍（{best_col}）：{v}（需確認，不判錯）")
    else:
        table = moi["individual"]
        if land_use not in table["columns"]:
            result.warn(f"內政部個別因素上限表沒有「{land_use}」欄，略過上限檢查")
            return
        ci = table["columns"].index(land_use)
        for r in rules:
            lim = _moi_lookup(table["items"], f"{r.get('item_no')}.{r['name']}")
            if lim is not None and lim[ci] is not None and r["max_pct"] > lim[ci] + 1e-6:
                result.warn(f"超過內政部最大影響範圍（{land_use}）：{r['id']} {r['name']} max {r['max_pct']} > 上限 {lim[ci]}（需確認，不判錯）")


def _moi_lookup(items: dict[str, list], name: str) -> list | None:
    for k, v in items.items():
        if norm_label(k) == norm_label(name) or same_char_multiset(k, name):
            return v
    best = max(items.items(), key=lambda kv: char_jaccard(kv[0], name))
    return best[1] if char_jaccard(best[0], name) >= 0.6 else None


def build_ruleset(items: list[RawItem], *, scope: str, land_use: str | None, rules_id: str, source: str,
                  result: AdapterResult) -> dict[str, Any]:
    catalog = REGIONAL_CATALOG if scope == "regional" else INDIVIDUAL_CATALOG
    used: set[str] = set()
    group_order: list[str] = []
    resolved: list[tuple[RawItem, CatalogItem | None]] = []
    for it in items:
        cat = _match_catalog(it, catalog, used, result) or _order_fallback(it, catalog, used, result)
        if cat:
            used.add(cat.name)
        else:
            result.warn(f"細項「{it.raw_name}」（{it.group_name}）無法對應內政部項目，survey_field/parcel_field 需人工指定")
        resolved.append((it, cat))
        g = (cat.group if cat else GROUP_ALIASES.get(norm_label(it.group_name), it.group_name)) or "未分類"
        if g not in group_order:
            group_order.append(g)
    rules: list[dict[str, Any]] = []
    counters: dict[int, int] = {}
    for it, cat in resolved:
        g = (cat.group if cat else GROUP_ALIASES.get(norm_label(it.group_name), it.group_name)) or "未分類"
        gno = group_order.index(g) + 1
        item_no = it.item_no or (cat.item_no if cat else None)
        if scope == "individual" and item_no is not None:
            rid = f"I{item_no}"
        else:
            counters[gno] = counters.get(gno, 0) + 1
            rid = f"R{gno}-{counters[gno]}"
        max_pct, matrix = _matrix_info(it, result, rid)
        crit = _build_criteria(it, cat, result, rid)
        rule: dict[str, Any] = {"id": rid, "group": gno, "name": cat.name if cat else it.raw_name,
                                "levels": list(it.levels), "max_pct": max_pct, "criteria": crit}
        if item_no is not None:
            rule["item_no"] = item_no
        if matrix:
            rule["matrix"] = matrix
        if cat:
            rule["survey_field" if scope == "regional" else "parcel_field"] = cat.field
            if cat.facility_types and crit.get("type") == "distance":
                rule["facility_types"] = list(cat.facility_types)
        notes = []
        if it.note:
            notes.append(it.note)
        if cat is None or norm_label(cat.name) != norm_label(it.raw_name):
            notes.append(f"原表細項名稱：{it.raw_name}")
        notes.append(f"來源：{it.source_ref}")
        rule["note"] = "；".join(notes)
        rules.append(rule)
    if scope == "individual":
        rules.sort(key=lambda r: (r.get("item_no") is None, r.get("item_no") or 0))
    _moi_check(rules, scope, land_use, result)
    return {
        "$schema_note": "由 app/adapters/rules_table.py 自基準明細表轉出；數值皆來自輸入表，criteria 由備註欄條件文字解析。",
        "id": rules_id, "source": source, "land_use": land_use, "table": "5" if scope == "regional" else "4",
        "scope": scope, "groups": [{"no": i + 1, "name": g} for i, g in enumerate(group_order)], "rules": rules,
    }


# ------------------------------------------------------------------ 入口


def read_rules_table(src: str | Path | bytes, *, filename: str | None = None, land_use: str | None = None,
                     id_prefix: str | None = None, source: str | None = None) -> AdapterResult:
    """PDF / canonical CSV / canonical xlsx → AdapterResult(data={'rulesets': {scope: ruleset}, 'items': long rows, 'meta'})。"""
    result = AdapterResult(kind="rules_table", data={"rulesets": {}, "long_rows": [], "meta": {}})
    name = (filename or (str(src) if not isinstance(src, (bytes, bytearray)) else "")).lower()
    meta: dict[str, Any] = {}
    if name.endswith(".pdf") or (isinstance(src, (bytes, bytearray)) and src[:4] == b"%PDF"):
        items, meta = parse_pdf(src)
    elif name.endswith(".csv"):
        items = read_long_csv(src)
    elif name.endswith((".xlsx", ".xlsm")):
        items = read_long_xlsx(src)
    else:
        result.warn("無法判斷基準表檔案格式（支援 .pdf / .csv / .xlsx）")
        return result
    land_use = land_use or meta.get("land_use")
    if not land_use:
        result.warn("無法從標題判斷用地別，內政部上限檢查略過；請指定 land_use")
    result.data["meta"] = meta | {"land_use": land_use, "item_count": len(items)}
    result.data["long_rows"] = items_to_long_rows(items)
    prefix = id_prefix or "custom"
    src_desc = source or (filename or (str(src) if not isinstance(src, (bytes, bytearray)) else "upload"))
    for scope in ("regional", "individual"):
        its = [i for i in items if i.scope == scope]
        if not its:
            continue
        rs = build_ruleset(its, scope=scope, land_use=land_use, rules_id=f"{prefix}_{scope}", source=src_desc, result=result)
        result.data["rulesets"][scope] = rs
    if not result.data["rulesets"]:
        result.warn("沒有解析出任何細項")
    return result.finalize()


if __name__ == "__main__":  # python -m app.adapters.rules_table <pdf|csv|xlsx> [--csv out.csv] [--json outdir]
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    ap.add_argument("--prefix", default="custom")
    a = ap.parse_args()
    res = read_rules_table(a.src, id_prefix=a.prefix)
    if a.csv:
        items, _ = parse_pdf(a.src) if a.src.lower().endswith(".pdf") else (read_long_csv(a.src), None)
        write_long_csv(items, a.csv)
    if a.json:
        for scope, rs in res.data["rulesets"].items():
            Path(a.json, f"{a.prefix}_{scope}.json").write_text(json.dumps(rs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"warnings": res.warnings, "meta": res.data["meta"]}, ensure_ascii=False, indent=2))
