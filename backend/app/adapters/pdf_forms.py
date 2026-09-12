"""
估價師填好的書表 PDF（表1 勘查表 / 表5-x 區域因素分析明細表 / 表4 比較法調查估價表）→ 內部 schema + Submitted。

策略（使用者決定：B 優先、A 備援）：
  1. 文字層優先：PyMuPDF find_tables() 直接讀格子（地政局範本是文字型 PDF），每個欄位 confidence = 1.0
  2. 掃描件／文字層抽不到表格 → pdf_forms_vision 走 app/llm provider 做 vision 抽取，欄位帶模型自報 confidence
  3. 兩邊都有：一致取高信心；不一致取文字層並 warning；只有一邊用那邊

回傳 AdapterResult(kind="pdf_forms")：
  data = {
    "case": {...}, "sections": {sid: Section}, "subject_parcel": Parcel, "comparables": [Comparable],
    "submitted": {"table1": {...}, "table5": {comp_no: {...verify_table5 的結構}}, "table4": {...verify_table4 的結構}},
    "pages": [{"page": n, "kind": "t1|t5|t4|map|other", "method": "text|vision|none"}],
  }
  信心值門檻（暫定）：< 0.6 → missing_fields；0.6–0.85 → warnings（UI 標黃）；≥ 0.85 接受。文字層一律 1.0。
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from app.engine.rules import RULES_DIR, RuleSet, load_ruleset

from .common import (
    AdapterResult,
    all_lines,
    annotate_facility_defaults,
    char_jaccard,
    guess_facility_type,
    is_garbage,
    make_facility,
    norm_label,
    norm_text,
    parse_count,
    parse_in_section,
    parse_named,
    selected_tokens,
    set_path,
    to_bool_有無,
    to_int_if_whole,
    to_number,
    to_text,
)

CONF_MISSING = 0.6
CONF_WARN = 0.85
SOURCE_T1 = "地價區段勘查表（估價師填）"
SOURCE_T4 = "比較法調查估價表（估價師填）"


# ------------------------------------------------------------------ 頁面分類


def classify_page(text: str) -> str:
    t = norm_text(text)
    if "勘查表" in t and ("表1" in t or "地價區段勘查表" in t):
        return "t1"
    if "區域因素分析明細表" in t:
        return "t5"
    if "比較法調查估價表" in t:
        return "t4"
    if any(k in t for k in ("區段略圖", "使用分區圖", "區段圖")):
        return "map"
    return "other"


def _cells(row: list) -> list[str]:
    return ["" if c is None else unicodedata.normalize("NFKC", str(c)).strip() for c in row]


def _is_group_label(s: str) -> bool:
    """直排的主要項目（'土\\n地\\n使\\n用'）：每段都是單字且 ≥3 段。"""
    segs = [x for x in re.split(r"[\n/]", s) if x.strip()]
    return len(segs) >= 3 and all(len(x.strip()) == 1 for x in segs)


def _flat(s: str) -> str:
    return re.sub(r"\s+", "", s.replace("\n", ""))


# ------------------------------------------------------------------ 表1

# norm_label(標籤) → (survey path, handler)
_T1_SIMPLE = {
    "都市計畫": ("land_control.urban_plan", "text"),
    "都市計畫內外": ("land_control.urban_plan", "text"),
    "使用分區": ("land_control.zoning", "text"),
    "建蔽率": ("land_control.bcr", "num"),
    "容積率": ("land_control.far", "num"),
    "有無禁止建築": ("land_control.building_prohibited", "bool"),
    "有無限制建築": ("land_control.building_restricted", "bool"),
    "區段內道路規劃及闢建程度": ("transport.road_development", "text"),
    "日照": ("natural.sunlight", "text"),
    "景觀": ("natural.view", "text"),
    "傾斜度": ("natural.slope", "text"),
    "保排水之良否": ("natural.drainage", "text"),
    "排水之良否": ("natural.drainage", "text"),
    "保水之良否": ("natural.drainage", "text"),
    "地勢": ("natural.terrain", "text"),
    "風勢": ("extra.wind", "text"),
    "土質": ("extra.soil", "text"),
    "接近聚落程度": ("extra.settlement", "text"),
    "接近運銷中心程度": ("extra.distribution_center", "text"),
    "接近消費市場程度": ("extra.consumer_market", "text"),
    "建築基地改良": ("improvement.building_site", "checks"),
    "農地改良": ("improvement.farmland", "checks"),
    "顧客之通行量": ("commerce.foot_traffic", "text"),
    "顧客通行量": ("commerce.foot_traffic", "text"),
    "店鋪之毗連狀態": ("commerce.shop_ratio_pct", "num"),
    "店舖之毗連狀態": ("commerce.shop_ratio_pct", "num"),
    "建築密度": ("extra.building_density", "text"),
    "建築型態": ("extra.building_type", "text"),
    "土地利用現況": ("extra.land_use_status", "checks"),
    "電力資源": ("extra.power", "text"),
    "產業用水及設施": ("extra.industrial_water", "text"),
}
# 單一設施（名稱：X ●本區段內 ○本區段外(距 M)）→ [Facility]
_T1_NAMED = {
    "觀光遊憩設施": ("public.tourism", "tourist_attraction"),
    "停車場地": ("public.parking", "parking_lot"),
    "接近服務性設施的程度": ("public.service", "service_facility"),
    "污廢水及廢棄物處理設施": ("extra.industrial_waste", None),
    "站牌": ("transport.bus_stop", "bus_stop"),
    "交流道": ("transport.interchange", "highway_interchange"),
    "百貨公司": ("commerce.department_store", "department_store"),
    "金融機構": ("commerce.bank", "bank"),
    "娛樂設施": ("commerce.entertainment", "entertainment"),
    "大型展示中心或觀光飯店": ("commerce.hotel", "tourist_hotel"),
    "變電所或高壓鐵塔": ("special.utility", "substation"),
    "瓦斯槽或儲油槽": ("special.utility", "gas_tank"),
}
# 多行勾選（● 國小 ●本區段內 …）→ [Facility]，行序對應 type
_T1_MULTI = {
    "大型車站": ("transport.major_station", ["hsr_station", "rail_station", "intercity_bus_station", "mrt_station"]),
    "學校": ("public.school", ["school", "school", "school", "school"]),
    "市場": ("public.market", ["traditional_market", "supermarket", "hypermarket"]),
    "公園廣場徒步區": ("public.park", ["park", "park", "plaza"]),
    "殯葬": ("special.funeral", ["cemetery", "funeral_home", "crematorium", "columbarium"]),
    "廢棄物處理": ("special.waste", ["sewage_plant", "landfill", "incinerator"]),
    "環境污染": ("pollution.source", ["pollution_source"] * 5),
}
_T1_SUBTYPE_LABEL = {"pollution.source": ["水污染", "噪音污染", "廢氣污染", "廢棄物污染", "其他污染"]}


def _is_known_label(c: str) -> bool:
    lab = norm_label(c)
    return (lab in _T1_SIMPLE or lab in _T1_NAMED or lab in _T1_MULTI or lab == "主要道路"
            or lab.startswith("區段內道路平均寬度"))


def parse_table1(page, result: AdapterResult) -> tuple[dict | None, dict[str, Any]]:
    """表1 → (Section, header{valuation_date, district})。"""
    tables = page.find_tables().tables
    if not tables:
        return None, {}
    rows = [_cells(r) for r in tables[0].extract()]
    text = page.get_text("text")
    header: dict[str, Any] = {}
    m = re.search(r"(新北市|臺北市|台北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|[一-鿿]{2,3}縣)([一-鿿]{1,3}(?:區|鄉|鎮|市))", text)
    if m:
        header["district"] = m.group(1) + m.group(2)
    survey: dict[str, Any] = {"land_control": {}, "transport": {}, "natural": {}, "public": {}, "special": {},
                              "pollution": {}, "commerce": {}, "other": None}
    section: dict[str, Any] = {"section_id": None, "range_desc": None, "survey": survey}
    level_nums: dict[str, dict] = {}
    seen_paths: set[str] = set()

    def get(path: str) -> Any:
        from .common import get_path
        return get_path(survey, path)

    def put(path: str, val: Any, lv: tuple[str, str]) -> None:
        set_path(survey, path, val)
        seen_paths.add(path)
        if lv[0].isdigit():
            level_nums[path] = {"num": int(lv[0]), "of": int(lv[1]) if lv[1].isdigit() else None}

    for row in rows:
        if not any(row):
            continue
        # 表頭列
        if "年" in row[0] and "期" in row[0]:
            for i, c in enumerate(row):
                if re.fullmatch(r"\d{7}", c):
                    header["valuation_date"] = c
                if "區段編號" in c and i + 1 < len(row):
                    section["section_id"] = next((x for x in row[i + 1:] if x), None)
                if "區段範圍" in c:
                    cand = next((x for x in row[i + 1:] if x and len(x.strip()) > 4 and not x.strip().startswith(("(公共", "（公共"))), None)
                    section["range_desc"] = _full_line(text, cand) if cand else None
            continue
        n = len(row)
        half = 9 if n >= 14 else n
        for lo, hi in ((0, half), (half, n)):
            seg = row[lo:hi]
            if not any(seg):
                continue
            lv = ("", "")
            label_i = None
            first_unknown = None
            for i, c in enumerate(seg):
                if not c:
                    continue
                if re.fullmatch(r"\d", c):
                    lv = (c, lv[1]) if not lv[0] else (lv[0], c)
                    continue
                if _is_known_label(c):
                    label_i = i
                    break
                if first_unknown is None and not _is_group_label(c) and not c[0] in "○●□■◯◉":
                    first_unknown = i
            if label_i is None:
                label_i = first_unknown
            if label_i is None:
                continue
            label_raw = seg[label_i]
            values = [c for c in seg[label_i + 1:] if c]
            _t1_dispatch(label_raw, values, lv, put, get, result)
    # 沒填的枚舉細項（住宅/工業才有的）→ None，不是缺
    for k in ("sunlight", "view", "slope"):
        survey["natural"].setdefault(k, None)
    survey["transport"].setdefault("interchange", [])
    survey["special"].setdefault("waste", [])
    survey["pollution"].setdefault("source", [])
    for k in ("department_store", "entertainment"):
        survey["commerce"].setdefault(k, [])
    section["level_numbers"] = level_nums
    for p in seen_paths:
        result.confidence[f"sections.{section['section_id']}.survey.{p}"] = 1.0
    return section, header


def _full_line(page_text: str, cell: str | None) -> str | None:
    """find_tables 的儲存格文字會在欄寬處截斷；用頁面全文把同一句補完整（下一行若是接續的括號也接上）。"""
    if not cell:
        return None
    head = cell.strip().replace("\n", "")[:10]
    lines = [ln.strip() for ln in page_text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.startswith(head):
            out = ln
            j = i + 1
            while (out.count("(") + out.count("（")) > (out.count(")") + out.count("）")) and j < len(lines):
                out += lines[j]
                j += 1
            out = out.replace("\n", "")
            return out if len(out) >= len(cell.strip().replace("\n", "")) else cell.strip().replace("\n", "")
    return cell.strip().replace("\n", "")


def _t1_dispatch(label_raw: str, values: list[str], lv: tuple[str, str], put, get, result: AdapterResult) -> None:
    lab = norm_label(label_raw)
    flat_label = _flat(label_raw)
    # 「區段內道路平均寬度 12 M」值在標籤裡
    if lab.startswith("區段內道路平均寬度"):
        put("transport.avg_road_width_m", {"value": to_int_if_whole(to_number(flat_label))}, lv)
        return
    if lab == "主要道路":
        joined = "/".join(values)
        name = parse_named(joined)
        w = re.search(r"寬度\s*[:：]\s*([\d.,]+)", joined)
        put("transport.main_road_width_m", {"name": name, "value": to_int_if_whole(to_number(w.group(1))) if w else None}, lv)
        return
    if lab in _T1_SIMPLE:
        path, kind = _T1_SIMPLE[lab]
        v = "/".join(values)
        if kind == "num":
            put(path, to_int_if_whole(to_number(v)), lv)
        elif kind == "bool":
            put(path, to_bool_有無(v), lv)
        elif kind == "checks":
            put(path, selected_tokens(v) or (to_text(v) if "□" not in v and "○" not in v else None), lv)
        else:
            put(path, to_text(v) if to_text(v) not in (None, "無") else (None if v.strip() in ("", "無") else to_text(v)), lv)
        return
    if lab in _T1_NAMED:
        path, ftype = _T1_NAMED[lab]
        v = "/".join(values)
        facs = []
        entries = [e for e in re.split(r"(?=名稱)", v) if e.strip()] if v.count("名稱") > 1 else [v]
        for line in entries:
            if "名稱" not in line and "本區段" not in line:
                continue
            name = parse_named(line)
            in_sec, dist = parse_in_section(line)
            extra = {}
            cnt = parse_count(line)
            if cnt is not None:
                extra["count"] = cnt
            if name is None and dist is None:
                continue
            f = make_facility(name, dist, ftype=guess_facility_type(name, ftype), in_section=in_sec, source=SOURCE_T1, extra=extra)
            if f:
                facs.append(f)
        if lab == "站牌":
            dm = re.search(r"密集程度.*?[●◉■]\s*(非常密集|密集|不密集)", v)
            if dm and facs:
                facs[0]["density"] = dm.group(1)
        if path.startswith("special.utility"):
            put(path, (get(path) or []) + facs, lv)
        else:
            put(path, facs, lv)
        return
    if lab in _T1_MULTI:
        path, types = _T1_MULTI[lab]
        # 值可能分成兩格：勾選清單 + 名稱清單（殯葬/廢棄物/環境污染）；或一格多行（大型車站/學校/市場/公園）
        name_cell = next((c for c in values if "名稱" in c), None)
        facs = []
        if name_cell is not None:
            lines = all_lines(name_cell)
            for i, line in enumerate(lines):
                name = parse_named(line)
                in_sec, dist = parse_in_section(line)
                if name is None and dist is None:
                    continue
                ft = types[i] if i < len(types) else types[-1]
                extra = {}
                sub = _T1_SUBTYPE_LABEL.get(path)
                if sub and i < len(sub):
                    extra["subtype"] = sub[i]
                facs.append(make_facility(name, dist, ftype=guess_facility_type(name, ft) if ft == "pollution_source" or ft.endswith("station") else ft,
                                          in_section=in_sec, source=SOURCE_T1, extra=extra))
        else:
            lines = all_lines("/".join(values))
            for i, line in enumerate(lines):
                if not line or line[0] not in "●◉■":
                    continue
                body = line[1:].strip()
                m = re.match(r"^(.*?)\s*[○●◯◉]\s*本區段內", body)
                name = m.group(1).strip() if m else body.split("○")[0].strip()
                name = re.sub(r"^無", "", name).strip()
                in_sec, dist = parse_in_section(body)
                if not name or name.startswith("無"):
                    continue
                ft = types[i] if i < len(types) else types[-1]
                facs.append(make_facility(name, dist, ftype=guess_facility_type(name, ft), in_section=in_sec, source=SOURCE_T1))
        facs = [f for f in facs if f]
        put(path, facs, lv)
        return
    # 未知標籤 → extra
    if values:
        result.warn(f"表1 未對應的欄位「{flat_label}」，放到 survey.extra")
        put(f"extra.{flat_label}", "/".join(values), lv)


# ------------------------------------------------------------------ 表5


def _find_rule(rs: RuleSet, name: str):
    n = norm_label(name)
    for r in rs.rules:
        if norm_label(r.name) == n:
            return r
    best = max(rs.rules, key=lambda r: char_jaccard(r.name, name))
    return best if char_jaccard(best.name, name) >= 0.6 else None


def _norm_level(rule, s: str) -> str | None:
    s = s.strip()
    if not s:
        return None
    if s in rule.levels:
        return s
    c = rule.criteria
    if c.get("type") == "boolean":
        b = to_bool_有無(s)
        if b is True:
            return c["true_level"]
        if b is False:
            return c["false_level"]
    return s


def parse_table5(page, regional: RuleSet, result: AdapterResult) -> dict[int, dict]:
    """表5 → {comp_no: {"section_id", "subject_section_id", "levels": {...}, "group_subtotals": {...}, "total_pct"}}。"""
    tables = page.find_tables().tables
    if not tables:
        return {}
    rows = [_cells(r) for r in tables[0].extract()]
    text = page.get_text("text")
    case_no = _case_no(text)
    comp_cols = [(4, 5, 6), (7, 8, 9), (10, 11, 12)]
    comps: dict[int, dict] = {}
    comp_ids: dict[int, int | None] = {}
    subject_sec = None
    group_no = 0
    for row in rows:
        c0 = row[0]
        mg = re.search(r"\((\d)\)", c0)
        if mg:
            group_no = int(mg.group(1))
        if c0.startswith("案號") or "實例編號" in "|".join(row[4:6]):
            for k, (a, b, c) in enumerate(comp_cols):
                txt = row[b] if b < len(row) else ""
                m = re.search(r"(\d+)", txt)
                comp_ids[k] = int(m.group(1)) if m else None
            continue
        if c0.startswith("地價區段"):
            subject_sec = row[2] or None
            for k, (a, b, c) in enumerate(comp_cols):
                if comp_ids.get(k) is not None:
                    comps[comp_ids[k]] = {"section_id": row[a] or None, "subject_section_id": subject_sec, "levels": {},
                                          "group_subtotals": {}, "total_pct": None}
            continue
        if c0.startswith(("主要項目", "備註")) or row[1] in ("全案", "比準地或各比較標的"):
            continue
        if "小計" in row[1] or "小計" in c0:
            nums = [to_number(x) for x in row[2:] if x and to_number(x) is not None]
            for k, cid in comp_ids.items():
                if cid is not None and k < len(nums):
                    comps[cid]["group_subtotals"][str(group_no)] = nums[k]
            continue
        if "總修正數" in c0 or row[1].startswith("=("):
            nums = [to_number(x) for x in row[2:] if x and to_number(x) is not None]
            for k, cid in comp_ids.items():
                if cid is not None and k < len(nums):
                    comps[cid]["total_pct"] = nums[k]
            continue
        name = row[1]
        if not name:
            continue
        rule = _find_rule(regional, name)
        if rule is None:
            result.warn(f"區域因素分析表細項「{_flat(name)}」在本案評價基準明細表沒有對應項目，未比對")
            continue
        s_num, s_lv = row[2], _norm_level(rule, row[3])
        for k, (a, b, c) in enumerate(comp_cols):
            cid = comp_ids.get(k)
            if cid is None or cid not in comps:
                continue
            c_lv = _norm_level(rule, row[b]) if b < len(row) else None
            if not row[a] and not c_lv and not row[c]:
                continue
            comps[cid]["levels"][rule.id] = {
                "subject": s_lv, "comparable": c_lv,
                "subject_num": int(s_num) if s_num.isdigit() else None,
                "comparable_num": int(row[a]) if row[a].isdigit() else None,
                "pct": to_number(row[c]),
            }
    for cid, d in comps.items():
        d["case_no"] = case_no
        for rid in d["levels"]:
            result.confidence[f"submitted.table5.{cid}.levels.{rid}"] = 1.0
    return comps


def _case_no(text: str) -> str | None:
    m = re.search(r"案號\s*[:：]\s*([0-9A-Za-z\-–]+)", unicodedata.normalize("NFKC", text))
    return m.group(1).replace("–", "-") if m else None


# ------------------------------------------------------------------ 表4


def _cond_value(a: str, b: str, c: str) -> Any:
    """(名稱, 數值, 單位) 或純量。"""
    if b and to_number(b) is not None:
        return {"name": a or None, "num": to_int_if_whole(to_number(b)), "unit": c}
    v = "/".join(x for x in (a, b, c) if x)
    return v.strip() or None


def parse_table4(page, individual: RuleSet, result: AdapterResult) -> dict[str, Any]:
    tables = page.find_tables().tables
    if not tables:
        return {}
    rows = [_cells(r) for r in tables[0].extract()]
    text = unicodedata.normalize("NFKC", page.get_text("text"))
    out: dict[str, Any] = {"case_no": _case_no(text), "valuation_date": None, "subject": {}, "comparables": {},
                           "submitted": {"comparables": {}, "subject_comparison_price": None}, "notes": {}}
    m = re.search(r"估價基準日\s*[:：]\s*(\d{7})", text) or re.search(r"^\s*(\d{7})\s*$", text, re.MULTILINE)
    if m:
        out["valuation_date"] = m.group(1)
    blocks = [(6, 7, 8, 9), (10, 11, 12, 13), (14, 15, 16, 17)]   # (name, num, unit, pct)
    comp_ids: dict[int, int | None] = {}
    subj = out["subject"]
    fill_date = re.search(r"填寫日期\s*[:：]\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", text)
    if fill_date:
        y, mo, d = fill_date.groups()
        out["fill_date"] = f"{int(y)}-{int(mo):02d}-{int(d):02d}"

    def comp(k: int) -> dict | None:
        cid = comp_ids.get(k)
        if cid is None:
            return None
        return out["comparables"].setdefault(cid, {"comp_no": cid, "items": {}})

    def sub(k: int) -> dict | None:
        cid = comp_ids.get(k)
        if cid is None:
            return None
        return out["submitted"]["comparables"].setdefault(cid, {"individual": {}})

    for row in rows:
        r = row + [""] * (18 - len(row))
        label = (r[0] + "|" + r[1] + "|" + r[2])
        if "全案" in (r[0].strip(), r[1].strip()):                      # 放最前面：全案備註常含「比準地所在區段…」，不能被當成表頭列；標籤可能在第 1 或第 2 欄
            li = 0 if r[0].strip() == "全案" else 1
            out["notes"]["case"] = next((x.strip() for x in r[li + 1:] if x and x.strip()), None)
            continue
        if "宗地流水號" in label or "比準地" in r[3]:
            subj["serial_no"] = r[5] or None
            for k, (a, b, c, p) in enumerate(blocks):
                seg = r[a:p + 1]
                num = next((to_number(x) for x in seg if x and re.fullmatch(r"\d+", x)), None)
                comp_ids[k] = int(num) if num is not None else None
            continue
        if r[0].startswith(("0基本資料", "0 基本資料")) or (r[0][:1] == "0" and "基本" in r[0]):
            subj["address"] = r[3] or None
            for k, (a, b, c, p) in enumerate(blocks):
                if r[a]:
                    cid = comp_ids.get(k)
                    if cid is None:
                        comp_ids[k] = k + 1
                        result.warn(f"表4 比較標的{k + 1} 沒有實例編號，依欄位順序給 {k + 1}")
                    comp(k)["address"] = r[a]
            continue
        if r[0].startswith("土地正常單價"):
            for k, (a, b, c, p) in enumerate(blocks):
                if r[a] and comp(k) is not None:
                    comp(k)["normal_unit_price"] = to_number(r[a])
            continue
        if r[0].startswith("交易日期"):
            for k, (a, b, c, p) in enumerate(blocks):
                if comp(k) is None:
                    continue
                if r[a]:
                    comp(k)["transaction_date"] = _norm_date(r[a])
                if r[p]:
                    sub(k)["date_adjustment_pct"] = to_number(r[p])
            continue
        if r[0].startswith("調整至估價基準日"):
            for k, (a, b, c, p) in enumerate(blocks):
                if r[a] and comp(k) is not None:
                    sub(k)["price_at_valuation_date"] = to_number(r[a])
            continue
        if r[0].startswith("地價區段"):
            subj["section_id"] = r[3] or None
            for k, (a, b, c, p) in enumerate(blocks):
                if comp(k) is None:
                    continue
                if r[a]:
                    comp(k)["section_id"] = r[a]
                if r[p]:
                    sub(k)["regional_adjustment_pct"] = to_number(r[p])
            continue
        mi = re.match(r"^(\d{1,2})\s*(.*)$", r[2]) or re.match(r"^(\d{1,2})\s*(.*)$", r[1])
        if mi and int(mi.group(1)) in range(6, 26):
            item = int(mi.group(1))
            subj.setdefault("items", {})[item] = _cond_value(r[3], r[4], r[5])
            for k, (a, b, c, p) in enumerate(blocks):
                if comp(k) is None:
                    continue
                comp(k)["items"][item] = _cond_value(r[a], r[b], r[c])
                pv = r[p]
                if pv:
                    sub(k)["individual"][str(item)] = "-" if pv in ("-", "－") else to_number(pv)
            continue
        if r[1] == "合計" or r[0] == "合計":
            for k, (a, b, c, p) in enumerate(blocks):
                if r[a] and sub(k) is not None:
                    sub(k)["individual_total_pct"] = to_number(r[a])
            continue
        if "絕對值加總" in r[1]:
            for k, (a, b, c, p) in enumerate(blocks):
                if sub(k) is None:
                    continue
                if r[a]:
                    sub(k)["abs_sum_pct"] = to_number(r[a])
                if r[c]:
                    sub(k)["similarity"] = r[c]
            continue
        if r[1].startswith("試算價格"):
            for k, (a, b, c, p) in enumerate(blocks):
                if sub(k) is None:
                    continue
                if r[a]:
                    sub(k)["trial_price"] = to_number(r[a])
                if r[c]:
                    sub(k)["weight_pct"] = to_number(r[c])
            continue
        if r[1].startswith("比準地比較價格"):
            v = next((to_number(x) for x in r[3:] if x and to_number(x) is not None), None)
            out["submitted"]["subject_comparison_price"] = v
            continue
        if r[1].startswith("比準地或各比較標的"):
            out["notes"]["subject"] = r[3] or None
            for k, (a, b, c, p) in enumerate(blocks):
                if r[a] and comp(k) is not None:
                    comp(k)["note"] = r[a]
            continue
    for cid, sub_d in out["submitted"]["comparables"].items():
        for k in sub_d.keys():  # noqa: SIM118
            result.confidence[f"submitted.table4.comparables.{cid}.{k}"] = 1.0
    return out


# ------------------------------------------------------------------ 表4 條件 → Parcel


def _norm_date(v: str) -> str:
    """「110年9月14日」「110/9/14」→「110.09.14」；已是點分格式就原樣。"""
    m = re.match(r"^\s*(\d{2,3})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?\s*$", v or "")
    return f"{int(m.group(1))}.{int(m.group(2)):02d}.{int(m.group(3)):02d}" if m else (v or "").strip()


def _parcel_from_t4(entry: dict, individual: RuleSet, result: AdapterResult, path: str, source: str) -> dict:
    items = entry.get("items", {})
    p: dict[str, Any] = {}
    addr = entry.get("address")
    p["address"] = addr
    m = re.search(r"([^\s市區鄉鎮縣]{1,8}段[\d、,，\-]+地號)", addr or "")
    p["parcel_id"] = m.group(1) if m else addr
    if p["parcel_id"] is None:
        result.missing(f"{path}.parcel_id")
    p["section_id"] = entry.get("section_id")
    for rule in sorted([r for r in individual.rules if r.item_no], key=lambda r: r.item_no):
        f = rule.parcel_field
        v = items.get(rule.item_no)
        if isinstance(v, dict) and is_garbage(v.get("name")):                                        # 單位格「M」、勾選符號被當成名稱 → 空
            v = {**v, "name": None}
            if v.get("num") is None:
                v = None
        elif isinstance(v, str) and is_garbage(v):
            v = None
        ctype = rule.criteria.get("type")
        if f == "front_road_width_m":
            if isinstance(v, dict):
                p["front_road"] = {"name": v.get("name"), "width_m": v.get("num")}
            elif v is None:
                p["front_road"] = None
                result.missing(f"{path}.front_road.width_m")
            else:
                p["front_road"] = {"name": None, "width_m": to_int_if_whole(to_number(v))} if to_number(v) is not None else {"name": v, "width_m": None}
            continue
        if ctype == "distance":
            facs = []
            if isinstance(v, dict):
                names = [x.strip() for x in re.split(r"[、;；/]", v.get("name") or "") if x.strip()]
                if not names:
                    names = [None]
                for i, nm in enumerate(names):
                    ft = guess_facility_type(nm, rule.facility_types[0] if rule.facility_types else None)
                    fac = make_facility(nm, v.get("num") if i == 0 else None, ftype=ft, source=source)
                    if fac:
                        facs.append(annotate_facility_defaults(fac, scope="individual", result=result, path=f"{path}.{f}"))
            elif isinstance(v, str) and v not in ("-", "無"):
                fac = make_facility(v, None, ftype=rule.facility_types[0] if rule.facility_types else None, source=source)
                facs.append(annotate_facility_defaults(fac, scope="individual", result=result, path=f"{path}.{f}"))
            if f == "nuisance":
                p[f] = facs
            else:
                p[f] = facs[0] if facs else None
            if v is None:
                result.missing(f"{path}.{f}")
            continue
        if isinstance(v, dict):
            v = v.get("num") if v.get("num") is not None else v.get("name")
        if ctype == "manual":
            p[f] = None if v in (None, "-", "－") else v
            continue
        if v in (None, ""):
            p[f] = None
            result.missing(f"{path}.{f}")
            continue
        if v in ("-", "－"):
            p[f] = None
            continue
        if ctype == "boolean":
            p[f] = to_bool_有無(v)
        elif ctype == "bands":
            p[f] = to_int_if_whole(to_number(v))
        else:
            p[f] = v
    return p


# ------------------------------------------------------------------ 主流程


SCOPE_ZH = {"regional": "區域因素", "individual": "個別因素"}


def ruleset_label(rid: str) -> str:
    """基準表 id → 給人看的名稱：示範表標「示範」，其餘取 source 第一段（括號前）；讀不到就回 id。"""
    from app.engine.rules import RULES_DIR
    try:
        d = json.loads((RULES_DIR / f"{rid}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return rid
    src = str(d.get("source") or d.get("name") or rid)
    short = re.split(r"[（(]", src, maxsplit=1)[0].strip() or rid
    return f"{short}（示範表）" if rid.startswith("demo_") else short


def pick_rulesets(land_use: str | None, result: AdapterResult, override: dict | None = None, district: str | None = None) -> tuple[RuleSet, RuleSet, dict]:
    ids = {"regional": None, "individual": None}
    if override:
        ids.update({k: v for k, v in override.items() if v})
    for scope in ("regional", "individual"):
        if ids[scope]:
            continue
        cands = []
        for p in sorted(RULES_DIR.glob(f"*_{scope}.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                result.warn(f"基準表 {p.name} 讀取失敗：{e}")
                continue
            if land_use is None or d.get("land_use") == land_use:
                cands.append((p.stem, d.get("district") or ""))
        # 同鄉鎮市區的表優先，其次正式表，示範表／上傳表最後
        cands.sort(key=lambda t: (not (district and t[1] and t[1] in district), t[0].startswith(("demo_", "uploaded_")), t[0]))
        cands = [t[0] for t in cands]
        if not cands:
            result.warn(f"找不到用地別「{land_use}」的{SCOPE_ZH[scope]}基準表，改用金山商業用地表對照細項名稱（僅供抽取，非審查依據）")
            cands = [f"jinshan_commercial_{scope}"]
        elif len(cands) > 1:
            result.warn(f"用地別「{land_use}」有 {len(cands)} 份{SCOPE_ZH[scope]}基準表，已採用「{ruleset_label(cands[0])}」；要換的話到「評價基準明細表」分頁選擇")
        ids[scope] = cands[0]
    return load_ruleset(ids["regional"]), load_ruleset(ids["individual"]), ids


def read_pdf_forms(src: str | Path | bytes, *, filename: str | None = None, use_vision: str = "auto",
                   provider=None, rulesets: dict | None = None, min_text_chars: int = 80) -> AdapterResult:
    """
    use_vision: "auto"（文字層抽不到表格的頁才用 vision）| "never" | "always"（兩邊都跑並交叉比對）
    provider:   app.llm.LLMProvider；None → 需要時 get_provider()
    """
    import fitz

    result = AdapterResult(kind="pdf_forms", data={"case": {}, "sections": {}, "subject_parcel": None, "comparables": [],
                                                   "submitted": {"table1": {}, "table5": {}, "table4": {}}, "pages": []})
    doc = fitz.open(stream=src, filetype="pdf") if isinstance(src, (bytes, bytearray)) else fitz.open(str(src))
    pages = [(i + 1, page, classify_page(page.get_text("text")), len(page.get_text("text").strip())) for i, page in enumerate(doc)]
    land_use = None
    district = None
    for _, page, kind, _n in pages:
        if kind in ("t5", "t1") and land_use is None:
            m = re.search(r"[（(](?:普通|高級)?(住宅|商業|工業|農業|其他)用地[)）]", page.get_text("text"))
            if m:
                land_use = m.group(1) + "用地"
        if district is None:
            m = re.search(r"(新北市|臺北市|台北市|桃園市|臺中市|台中市|臺南市|台南市|高雄市|[一-鿿]{2,3}縣)([一-鿿]{1,3}(?:區|鄉|鎮|市))", page.get_text("text"))
            if m:
                district = m.group(1) + m.group(2)
    if land_use is None and all(n < min_text_chars for *_x, n in pages):
        # 掃描件：頁面分類與用地別交給 vision（先用檔名/預設）
        pass
    regional, individual, ids = pick_rulesets(land_use, result, rulesets, district=district)
    ctx: dict[str, Any] = {"case": {"land_use": land_use, "rulesets": ids}, "sections": {}, "t5": {}, "t4": None}
    # 表5 備註「使用分區、建蔽率、容積率修正併同於比較法調查估價表宗地個別因素考量調整修正」→ 該三項在表5 免修正
    for _, page, kind, _n in pages:
        if kind != "t5":
            continue
        m = re.search(r"([^\n。]*(?:併同|免修正|不另修正)[^\n。]*)", page.get_text("text"))
        if not m:
            continue
        sentence = m.group(1).strip()
        skip = [ru.id for ru in regional.rules if any(k in sentence for k in {ru.name, ru.name.replace("（", "(").split("(")[0]} if len(k) >= 2)]
        if skip:
            ctx["case"]["regional_no_adjust"] = skip
            ctx["case"].setdefault("notes", {})["table5_case"] = sentence
            names = [ru.name for ru in regional.rules if ru.id in skip]
            result.warn(f"區域因素分析表備註載明免修正：{'、'.join(names)}（{sentence[:40]}…），該列填「-」不計入小計")
        break
    vision_pages: list[tuple[int, Any, str]] = []
    for pno, page, kind, nchars in pages:
        method = "none"
        text_ok = nchars >= min_text_chars and bool(page.find_tables().tables)
        if kind in ("t1", "t5", "t4") or (kind == "other" and not text_ok):
            if text_ok and use_vision != "always" and kind != "other":
                method = "text"
            elif use_vision == "never":
                if kind != "other":
                    result.warn(f"第 {pno} 頁（{kind}）沒有可用文字層，且 use_vision=never → 未抽取")
            else:
                method = "vision" if not text_ok else "text+vision"
                vision_pages.append((pno, page, kind))
            if method.startswith("text"):
                _text_layer(page, kind, ctx, result, regional, individual, pno)
        result.data["pages"].append({"page": pno, "kind": kind, "method": method, "chars": nchars})

    if vision_pages:
        from .pdf_forms_vision import run_vision
        run_vision(vision_pages, ctx, result, provider=provider, regional=regional, individual=individual)
        # vision 可能才知道用地別
        if ctx["case"].get("land_use") and ctx["case"]["land_use"] != land_use:
            regional, individual, ids = pick_rulesets(ctx["case"]["land_use"], result, rulesets)
            ctx["case"]["rulesets"] = ids
    _assemble(ctx, result, individual)
    _apply_confidence_policy(result)
    return result.finalize()


def _text_layer(page, kind: str, ctx: dict, result: AdapterResult, regional: RuleSet, individual: RuleSet, pno: int) -> None:
    if kind == "t1":
        sec, header = parse_table1(page, result)
        if sec:
            sid = sec["section_id"] or f"section_p{pno}"
            sec["section_id"] = sid
            ctx["sections"][sid] = sec
            ctx["case"].update({k: v for k, v in header.items() if v})
    elif kind == "t5":
        for cid, d in parse_table5(page, regional, result).items():
            if d.get("case_no"):
                ctx["case"].setdefault("case_no", d["case_no"])
            ctx["t5"][cid] = d
    elif kind == "t4":
        ctx["t4"] = parse_table4(page, individual, result)


def _assemble(ctx: dict, result: AdapterResult, individual: RuleSet) -> None:
    """ctx（文字層或 vision 填好的中間結構）→ result.data。"""
    case = ctx["case"]
    for sid, sec in ctx["sections"].items():
        for f_list in _iter_facility_lists(sec["survey"]):
            for f in f_list:
                annotate_facility_defaults(f, scope="regional", result=result, path=f"sections.{sid}")
        result.data["submitted"]["table1"][sid] = {"level_numbers": sec.pop("level_numbers", {})}
        result.data["sections"][sid] = sec
    for cid, d in ctx["t5"].items():
        result.data["submitted"]["table5"][cid] = d
    t4_data = ctx["t4"]
    if t4_data:
        if t4_data.get("case_no"):
            case.setdefault("case_no", t4_data["case_no"])
        if t4_data.get("valuation_date"):
            case.setdefault("valuation_date", t4_data["valuation_date"])
        if t4_data.get("fill_date"):
            case.setdefault("fill_date", t4_data["fill_date"])          # 案件層也留一份：書表拆檔時勘查表頁與表4頁分開讀，合併時才補得回 survey_date
            for sec in result.data["sections"].values():
                sec.setdefault("survey_date", t4_data["fill_date"])
        subj = _parcel_from_t4(t4_data["subject"], individual, result, "subject_parcel", SOURCE_T4)
        subj["serial_no"] = t4_data["subject"].get("serial_no")
        result.data["subject_parcel"] = subj
        comps = []
        for cid, entry in sorted(t4_data["comparables"].items()):
            i = len(comps)
            c = _parcel_from_t4(entry, individual, result, f"comparables[{i}]", SOURCE_T4)
            c["comp_no"] = cid
            c["normal_unit_price"] = entry.get("normal_unit_price")
            if c["normal_unit_price"] is None:
                result.missing(f"comparables[{i}].normal_unit_price")
            c["transaction_date"] = entry.get("transaction_date")
            sub = t4_data["submitted"]["comparables"].get(cid, {})
            da: dict[str, Any] = {}
            if sub.get("date_adjustment_pct") is not None:
                da["pct"] = sub["date_adjustment_pct"]
            note = entry.get("note")
            if note:
                da["note"] = note
                idx = re.findall(r"(\d{2},\d{3})\s*元", note)
                if len(idx) >= 2:
                    da["index_at_valuation"], da["index_at_transaction"] = to_number(idx[0]), to_number(idx[1])
            if "pct" not in da:
                result.missing(f"comparables[{i}].date_adjustment.pct")
            c["date_adjustment"] = da
            if sub.get("weight_pct") is not None:
                c["weight_pct"] = to_int_if_whole(sub["weight_pct"])
            comps.append(c)
        result.data["comparables"] = comps
        result.data["submitted"]["table4"] = t4_data["submitted"]
        result.data["notes"] = t4_data.get("notes", {})
    else:
        result.missing("subject_parcel")
        result.missing("comparables")
    if not result.data["sections"]:
        result.missing("sections")
    result.data["case"] = case


def _iter_facility_lists(survey: dict):
    for grp in ("transport", "public", "special", "pollution", "commerce"):
        for v in (survey.get(grp) or {}).values():
            if isinstance(v, list):
                yield v


def _apply_confidence_policy(result: AdapterResult) -> None:
    for path, c in list(result.confidence.items()):
        if c < CONF_MISSING:
            result.missing(path)
        elif c < CONF_WARN:
            result.warn(f"{path}: 抽取信心值 {c:.2f}，請人工確認")
