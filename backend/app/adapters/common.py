"""
input adapter 共用工具。

所有 adapter 回傳 AdapterResult：
  data            轉成內部 schema（docs/03）的資料；缺的欄位不猜，留 None
  missing_fields  缺欄位清單（路徑字串，例如 "parcels[0].width_m"），讓 UI 補
  warnings        推定、格式疑點、被正規化的值
  confidence      {路徑: 0~1}；文字層/Excel 直接讀到 = 1.0，LLM 抽取用模型自報值

「-」與空白的差別（表7 慣例）：
  「-」  = 估價師/需用土地人明示免填（免修正），data 存 None，不列 missing
  空白   = 沒填，data 存 None，列進 missing_fields
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

# ------------------------------------------------------------------ 結果容器

DASH_VALUES = {"-", "－", "—", "–", "─"}
NONE_WORDS = {"無", "none", "null", "n/a", "na"}


@dataclass
class AdapterResult:
    kind: str
    data: Any
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        self.finalize()
        d = asdict(self)
        d.pop("stats", None)
        return d

    def count(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    def finalize(self) -> AdapterResult:
        """把逐筆統計收斂成一則 warning（避免每個設施各發一條）。"""
        n = self.stats.pop("assumed_measure", 0)
        if n:
            self.warn(f"共 {n} 筆設施距離未載明量測方式與起點，已依系統預設（各設施的慣用量測方式，自宗地起算）帶入並標「需人工確認」")
        return self

    def warn(self, msg: str) -> None:
        if msg not in self.warnings:
            self.warnings.append(msg)

    def missing(self, path: str) -> None:
        if path not in self.missing_fields:
            self.missing_fields.append(path)


class Missing:
    """哨兵：欄位在來源中不存在或空白（≠ 明示「-」）。"""
    _inst: Missing | None = None

    def __new__(cls):
        if cls._inst is None:
            cls._inst = super().__new__(cls)
        return cls._inst

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING = Missing()

# ------------------------------------------------------------------ 字串正規化


def norm_text(s: Any) -> str:
    """全形→半形、去空白/換行/常見標點，供標籤比對。"""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = re.sub(r"[\s　]+", "", s)
    s = s.replace("（", "(").replace("）", ")").replace("，", ",").replace("、", ",").replace("．", ".")
    s = s.replace("：", ":").replace("；", ";")
    return s.lower()


def norm_label(s: Any) -> str:
    """標籤比對用：norm_text 後再去掉括號內容、標點、前導編號。"""
    t = norm_text(s)
    t = re.sub(r"\([^)]*\)", "", t)
    t = re.sub(r"^[0-9]+[.．、]?", "", t)
    t = re.sub(r"[^0-9a-z一-鿿%]", "", t)
    return t


def char_jaccard(a: str, b: str) -> float:
    """字元集合 Jaccard；用來對付 PDF 直排文字抽出來字序亂掉的細項名稱。"""
    sa, sb = set(norm_label(a)), set(norm_label(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def same_char_multiset(a: str, b: str) -> bool:
    return sorted(norm_label(a)) == sorted(norm_label(b))


# ------------------------------------------------------------------ 值的解析

_NUM_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


_GARBAGE_RE = re.compile(r"^[\s○●◎□■△▲×✓✔\-—－_/]*$|^(?:M|m|M\)|公尺|%|％|㎡|M2)$")


def is_garbage(v: Any) -> bool:
    """書表／範本裡的勾選符號與單位格（○ ● □ M ㎡ %）被當成值 → 視為空。"""
    if isinstance(v, str):
        return bool(_GARBAGE_RE.match(v.strip()))
    if isinstance(v, dict):
        vals = [x for x in v.values() if x not in (None, "")]
        return bool(vals) and all(isinstance(x, str) and is_garbage(x) for x in vals)
    return False


def is_blank(v: Any) -> bool:
    return v is None or v is MISSING or (isinstance(v, str) and v.strip() == "")


def is_dash(v: Any) -> bool:
    return isinstance(v, str) and v.strip() in DASH_VALUES


def to_number(v: Any) -> float | None:
    """'1,020' → 1020.0；'70%' → 70.0；'18 M' → 18.0；'無'/'-'/空白 → None。"""
    if v is None or v is MISSING:
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    s = unicodedata.normalize("NFKC", str(v)).strip()
    if not s or s in DASH_VALUES or s.lower() in NONE_WORDS:
        return None
    m = _NUM_RE.search(s.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def to_int_if_whole(x: float | None) -> float | int | None:
    if x is None:
        return None
    return int(x) if float(x).is_integer() else x


def to_bool_有無(v: Any) -> bool | None:
    """有/是/Y/true → True；無/否/N/false → False；其他 → None。"""
    if v is None or v is MISSING:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = norm_text(v)
    if not s or s in DASH_VALUES:
        return None
    if s.startswith(("有", "是", "y", "true", "1")):
        return True
    if s.startswith(("無", "否", "n", "false", "0")):
        return False
    return None


def to_text(v: Any) -> str | None:
    if v is None or v is MISSING:
        return None
    s = str(v).strip()
    if not s or s in DASH_VALUES:
        return None
    return s


def roc_date(v: Any) -> str | None:
    """民國日期正規化成 'YYY.MM.DD'（範本表4 交易日期格式）。接受 114.05.28 / 114-05-28 / 1140528 / 114年5月28日。"""
    if v is None or v is MISSING:
        return None
    if hasattr(v, "year"):  # datetime
        return f"{v.year - 1911}.{v.month:02d}.{v.day:02d}"
    s = unicodedata.normalize("NFKC", str(v)).strip()
    if not s:
        return None
    m = re.match(r"^(\d{2,3})[.\-/年](\d{1,2})[.\-/月](\d{1,2})日?$", s)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        return f"{y}.{mo:02d}.{d:02d}"
    m = re.match(r"^(\d{3})(\d{2})(\d{2})$", s)
    if m:
        return f"{int(m.group(1))}.{m.group(2)}.{m.group(3)}"
    return s


# ------------------------------------------------------------------ 勘查表常見片語

_RADIO_ON = "●◉■☑√✓"
_RADIO_OFF = "○◯□☐"
_DIST_RE = re.compile(r"距\s*([\d,\.]+)?\s*(?:M|m|公尺|米)?\s*\)?")


def parse_in_section(text: str) -> tuple[bool | None, float | None]:
    """
    解析「○本區段內 ●本區段外(距 120 M)」→ (in_section=False, 120)
    「●本區段內 ○本區段外(距 M)」→ (True, None)；兩個都沒勾 → (None, distance or None)
    """
    if not text:
        return None, None
    t = unicodedata.normalize("NFKC", text)
    in_sec: bool | None = None
    m_in = re.search(r"([" + _RADIO_ON + _RADIO_OFF + r"])\s*本區段內", t)
    m_out = re.search(r"([" + _RADIO_ON + _RADIO_OFF + r"])\s*本區段外", t)
    if m_in and m_in.group(1) in _RADIO_ON:
        in_sec = True
    elif m_out and m_out.group(1) in _RADIO_ON:
        in_sec = False
    dist = None
    md = _DIST_RE.search(t)
    if md and md.group(1):
        dist = to_number(md.group(1))
    return in_sec, dist


def parse_named(text: str) -> str | None:
    """「名稱：金山變電所 ○本區段內 …」→ '金山變電所'；名稱為「無」→ None。"""
    if not text:
        return None
    t = unicodedata.normalize("NFKC", text)
    m = re.search(r"名稱\s*[:：]\s*([^○●◯◉□■\n/]+?)(?:\s+數量|\s*[○●◯◉□■]|\s*$|\s*/)", t)
    name = m.group(1).strip() if m else None
    if name is None:
        return None
    name = re.sub(r"\s+", "", name)
    if not name or name.startswith("無"):
        return None
    return name


def parse_count(text: str) -> int | None:
    m = re.search(r"數量\s*[:：]\s*(\d+)", unicodedata.normalize("NFKC", text or ""))
    return int(m.group(1)) if m else None


def selected_lines(text: str) -> list[str]:
    """把多行勾選文字拆行，只留開頭是實心符號的行（去掉符號）。"""
    out = []
    for line in re.split(r"[\n/]", unicodedata.normalize("NFKC", text or "")):
        line = line.strip()
        if line and line[0] in _RADIO_ON:
            out.append(line[1:].strip())
    return out


def selected_tokens(text: str) -> list[str]:
    """「○商業用 ○住宅用 ●住商混合/○空地」→ ['住商混合']；同一行多個勾選也抓得到。"""
    return [t.strip() for t in re.findall(r"[●◉■☑√✓]\s*([^○●◯◉□■☐☑\n/]+)", unicodedata.normalize("NFKC", text or "")) if t.strip()]


def all_lines(text: str) -> list[str]:
    return [l.strip() for l in re.split(r"[\n/]", unicodedata.normalize("NFKC", text or "")) if l.strip()]


# ------------------------------------------------------------------ Facility 建構

FACILITY_KEYWORDS: list[tuple[str, str]] = [
    # (關鍵字, facility_measurement.json 的 type)
    ("高鐵", "hsr_station"), ("火車", "rail_station"), ("臺鐵", "rail_station"), ("台鐵", "rail_station"),
    ("捷運", "mrt_station"), ("輕軌", "mrt_station"), ("客運", "intercity_bus_station"),
    ("站牌", "bus_stop"), ("公車", "bus_stop"),
    ("交流道", "highway_interchange"),
    ("傳統市場", "traditional_market"), ("零售市場", "traditional_market"), ("市場", "traditional_market"),
    ("超級市場", "supermarket"), ("超市", "supermarket"), ("購物中心", "hypermarket"), ("量販", "hypermarket"),
    ("徒步區", "pedestrian_zone"), ("廣場", "plaza"), ("公園", "park"),
    ("停車", "parking_lot"),
    ("國小", "school"), ("國中", "school"), ("高中", "school"), ("大學", "school"), ("學校", "school"), ("學院", "school"),
    ("商圈", "commercial_district"), ("老街", "tourist_attraction"), ("景點", "tourist_attraction"),
    ("農會", "bank"), ("銀行", "bank"), ("郵局", "post_office_bank"), ("信用合作社", "credit_union"),
    ("百貨", "department_store"), ("電影", "cinema"), ("飯店", "tourist_hotel"), ("酒店", "tourist_hotel"), ("展示中心", "exhibition_center"),
    ("公墓", "cemetery"), ("墓", "cemetery"), ("殯儀", "funeral_home"), ("火葬", "crematorium"), ("火化", "crematorium"),
    ("納骨", "columbarium"), ("靈骨", "columbarium"),
    ("變電", "substation"), ("鐵塔", "hv_tower"), ("高壓", "hv_tower"), ("瓦斯", "gas_tank"), ("儲油", "oil_tank"),
    ("加油", "gas_station"), ("中油", "gas_station"), ("台亞", "gas_station"), ("全國加油", "gas_station"),
    ("焚化", "incinerator"), ("掩埋", "landfill"), ("垃圾", "landfill"), ("污水", "sewage_plant"), ("汙水", "sewage_plant"),
    ("污染", "pollution_source"), ("汙染", "pollution_source"),
]


def guess_facility_type(name: str | None, default: str | None = None) -> str | None:
    if not name:
        return default
    for kw, t in FACILITY_KEYWORDS:
        if kw in name:
            return t
    return default


def make_facility(name: str | None, distance_m: float | None, *, ftype: str | None = None,
                  in_section: bool | None = None, source: str = "manual",
                  origin: str | None = None, measure: str | None = None, extra: dict | None = None) -> dict | None:
    """
    組 Facility。measure/origin 缺時不在這裡猜；由 annotate_facility_defaults() 依 facility_measurement.json 補預設並標 assumed。
    """
    if isinstance(name, str) and is_garbage(name):
        name = None
    if name is None and distance_m is None and in_section is None:
        return None
    f: dict[str, Any] = {"name": name}
    t = ftype or guess_facility_type(name)
    if t:
        f["type"] = t
    if in_section is not None:
        f["in_section"] = in_section
    if distance_m is not None:
        f["distance_m"] = to_int_if_whole(distance_m)
    if measure:
        f["measure"] = measure
    if origin:
        f["origin"] = origin
    f["source"] = source
    if extra:
        f.update(extra)
    return f


_FM_CACHE: dict | None = None


def facility_measurement() -> dict:
    global _FM_CACHE
    if _FM_CACHE is None:
        import json

        from app.engine.rules import RULES_DIR
        _FM_CACHE = json.loads((RULES_DIR / "facility_measurement.json").read_text(encoding="utf-8"))
    return _FM_CACHE


def annotate_facility_defaults(f: dict | None, *, scope: str, result: AdapterResult, path: str) -> dict | None:
    """
    表單/清冊上抄來的距離不會寫量測方式。依使用者決定（B 案）：
    measure 依 facility_measurement.json 帶預設、origin 依 scope 慣例、標 assumed=true 並發 warning，不列 missing。
    """
    if not f:
        return f
    fm = facility_measurement()
    ft = f.get("type")
    assumed = []
    if "measure" not in f:
        mode = (fm["facility_types"].get(ft) or {}).get("mode") if ft else None
        f["measure"] = mode or "unspecified"
        assumed.append("measure")
    if "origin" not in f:
        f["origin"] = "section_boundary" if scope == "regional" else "parcel_centroid"
        assumed.append("origin")
    if assumed:
        f["assumed"] = True
        if f.get("distance_m") is not None:
            result.count("assumed_measure")
    return f


# ------------------------------------------------------------------ 路徑工具


def set_path(d: dict, dotted: str, value: Any) -> None:
    cur = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def get_path(d: Any, dotted: str) -> Any:
    cur = d
    for p in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list) and p.isdigit():
            cur = cur[int(p)] if int(p) < len(cur) else None
        else:
            return None
    return cur


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """巢狀 dict/list → {dotted path: leaf}；測試用來算欄位還原率。"""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def leaf_equal(a: Any, b: Any, tol: float = 1e-6) -> bool:
    """葉值比較：數字容差、字串正規化後比、布林照值。"""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= tol
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        fa, fb = to_number(a), to_number(b)
        return fa is not None and fb is not None and abs(fa - fb) <= tol
    return norm_text(a) == norm_text(b)


# ------------------------------------------------------------------ 表格式欄位規格（表7 / 買賣實例 共用）


@dataclass
class FieldSpec:
    key: str                     # 平面 key（assemble 時再組成巢狀 schema）
    labels: tuple[str, ...]      # 可接受的欄名（會 norm_label）
    kind: str = "text"           # text | num | pct | bool | date | int
    item_no: int | None = None
    group: str | None = None  # 表7 左側主要項目文字
    required: bool = False       # 缺了要列 missing_fields

    def matches(self, label: Any) -> bool:
        nl = norm_label(label)
        if not nl:
            return False
        for cand in self.labels:
            if nl == norm_label(cand):
                return True
        return False


def parse_by_kind(kind: str, raw: Any) -> Any:
    if raw is MISSING:
        return MISSING
    if is_blank(raw):
        return MISSING
    if is_dash(raw):
        return None
    if kind in ("num", "pct"):
        return to_int_if_whole(to_number(raw))
    if kind == "int":
        n = to_number(raw)
        return int(n) if n is not None else None
    if kind == "bool":
        return to_bool_有無(raw)
    if kind == "date":
        return roc_date(raw)
    return to_text(raw)


def _cell(ws, r: int, c: int) -> Any:
    v = ws.cell(row=r, column=c).value
    return v


def detect_layout(ws, specs: Iterable[FieldSpec], key_field: str) -> str:
    """
    'transposed' = 表7 官方版面（欄位是列、記錄是欄）；'long' = 一列一筆。
    判斷：前 4 欄裡沿列往下命中的標籤數 vs 單一列裡命中的標籤數，多者勝；都 < 3 → 無法辨識。
    """
    specs = list(specs)
    max_r = min(ws.max_row, 80)
    max_c = min(ws.max_column, 80)
    col_hits = 0
    for r in range(1, max_r + 1):
        if any(any(s.matches(_cell(ws, r, c)) for s in specs) for c in range(1, min(4, max_c) + 1)):
            col_hits += 1
    row_hits = 0
    for r in range(1, max_r + 1):
        hits = sum(1 for c in range(1, max_c + 1) if any(s.matches(_cell(ws, r, c)) for s in specs))
        row_hits = max(row_hits, hits)
    if max(col_hits, row_hits) < 3:
        raise ValueError("無法辨識表格版面：找不到欄位標籤（需含「宗地流水號」等列標籤或一列表頭）")
    return "transposed" if col_hits >= row_hits else "long"


def read_records(ws, specs: list[FieldSpec], key_field: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    """
    回傳 (records, layout, unknown_labels)。每筆 record = {spec.key: raw or MISSING}。
    transposed：標籤在前 4 欄任一格；記錄欄 = 標籤欄右側、在任一標籤列有值的欄。
    long：表頭列 = 命中最多的那一列；之後每列一筆，連續 3 列空白就停。
    """
    layout = detect_layout(ws, specs, key_field)
    unknown: list[str] = []
    max_r, max_c = ws.max_row, ws.max_column
    if layout == "transposed":
        label_rows: list[tuple[int, FieldSpec]] = []
        label_cols: set[int] = set()
        for r in range(1, max_r + 1):
            for c in range(1, min(4, max_c) + 1):
                v = _cell(ws, r, c)
                if is_blank(v):
                    continue
                spec = next((s for s in specs if s.matches(v)), None)
                if spec:
                    label_rows.append((r, spec))
                    label_cols.add(c)
                    break
                if isinstance(v, str) and len(norm_label(v)) >= 2 and not re.fullmatch(r"\d+", norm_label(v)):
                    unknown.append(v.strip())
        first_rec_col = max(label_cols) + 1
        rec_cols = [c for c in range(first_rec_col, max_c + 1)
                    if any(not is_blank(_cell(ws, r, c)) for r, _ in label_rows)]
        records: list[dict[str, Any]] = [{} for _ in rec_cols]
        for r, spec in label_rows:
            for i, c in enumerate(rec_cols):
                raw = _cell(ws, r, c)
                if spec.key in records[i] and records[i][spec.key] is not MISSING:
                    continue
                records[i][spec.key] = MISSING if is_blank(raw) else raw
        for rec in records:
            for s in specs:
                rec.setdefault(s.key, MISSING)
        return records, layout, sorted(set(unknown))
    # long
    best_r, best_hits = None, 0
    for r in range(1, min(max_r, 60) + 1):
        hits = sum(1 for c in range(1, max_c + 1) if any(s.matches(_cell(ws, r, c)) for s in specs))
        if hits > best_hits:
            best_r, best_hits = r, hits
    colmap: dict[int, FieldSpec] = {}
    for c in range(1, max_c + 1):
        v = _cell(ws, best_r, c)
        if is_blank(v):
            continue
        s = next((s for s in specs if s.matches(v)), None)
        if s:
            colmap[c] = s
        else:
            unknown.append(str(v).strip())
    records = []
    blank_run = 0
    for r in range(best_r + 1, max_r + 1):
        row = {s.key: (MISSING if is_blank(_cell(ws, r, c)) else _cell(ws, r, c)) for c, s in colmap.items()}
        if all(v is MISSING for v in row.values()):
            blank_run += 1
            if blank_run >= 3:
                break
            continue
        blank_run = 0
        for s in specs:
            row.setdefault(s.key, MISSING)
        records.append(row)
    return records, layout, sorted(set(unknown))
