"""
表1（地價區段勘查表，見 xlsx_table1.py）、表5（影響地價區域因素分析明細表）與 表4（比較法調查估價表）→ Excel，版面照地政局範本（docs/reference/查估書表範本.pdf 第 2、3 頁）。

慣例：
- 數字寫「值」不寫公式（使用者決定）：openpyxl 讀回即可驗證，不依賴 Excel 重算。
- 百分比以「百分點」存（5.0 = 5%），數字格式 0.00"%" 顯示成 5.00%，和引擎/fixture 單位一致。
- 免修正項目寫字串「-」，不是 0。
- 二級布林細項（有無禁止建築…）照範本顯示「無／有」，不顯示「優／劣」。
- 字型標楷體；沒裝字型只影響外觀。
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.engine.rules import RULES_DIR, Rule, RuleSet, load_ruleset
from app.engine.tables import Table4, Table5, run_case

FONT = "標楷體"
_thin = Side(style="thin", color="000000")
BORDER = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
HEAD_FILL = PatternFill("solid", fgColor="FFFFCC")
PCT = '0.00"%"'
PCT_SPACE = '0.00" %"'
MONEY = "#,##0"
MAX_COMPS = 3


def _ruleset_table_no(rs: RuleSet) -> str:
    p = RULES_DIR / f"{rs.id}.json"
    if p.exists():
        try:
            return str(json.loads(p.read_text(encoding="utf-8")).get("table") or "5")
        except (OSError, json.JSONDecodeError):
            return "5"
    return "5"


def _cell(ws: Worksheet, r: int, c: int, v: Any = None, *, fmt: str | None = None, align=CENTER, bold=False,
          fill=None, size=9) -> None:
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = Font(name=FONT, size=size, bold=bold)
    cell.alignment = align
    cell.border = BORDER
    if fmt:
        cell.number_format = fmt
    if fill:
        cell.fill = fill


def _merge(ws: Worksheet, r1: int, c1: int, r2: int, c2: int, v: Any = None, **kw) -> None:
    _cell(ws, r1, c1, v, **kw)
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            ws.cell(row=r, column=c).border = BORDER
    if (r1, c1) != (r2, c2):
        ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def level_label(rule: Rule, level: str | None) -> str | None:
    if level is None:
        return None
    c = rule.criteria
    if c.get("type") == "boolean":
        return "有" if level == c.get("true_level") else "無"
    return level


# ------------------------------------------------------------------ 表5


def write_table5(ws: Worksheet, tables: dict[int, Table5], rs: RuleSet, case: dict, meta: dict) -> None:
    land_use = case.get("land_use") or rs.land_use
    comps = sorted(tables.items())[:MAX_COMPS]
    ws.title = f"表{_ruleset_table_no(rs)}"
    widths = [9, 30, 4, 7] + [4, 7, 9] * MAX_COMPS
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    _cell(ws, 1, 1, f"表{_ruleset_table_no(rs)}  影響地價區域因素分析明細表（{land_use}）", align=LEFT, bold=True, size=14)
    ws.cell(row=1, column=1).border = Border()
    _merge(ws, 2, 1, 2, 2, f"案號：{case.get('case_no', '')}", align=LEFT, fill=HEAD_FILL)
    _merge(ws, 2, 3, 2, 4, "比準地", fill=HEAD_FILL)
    _merge(ws, 3, 1, 3, 2, "地價區段號", fill=HEAD_FILL)
    subject_sec = comps[0][1].subject_section if comps else case.get("subject_section_id", "")
    _merge(ws, 3, 3, 3, 4, subject_sec)
    _merge(ws, 4, 1, 4, 1, "主要項目", fill=HEAD_FILL)
    _merge(ws, 4, 2, 4, 2, "修正細項", fill=HEAD_FILL)
    _merge(ws, 4, 3, 4, 4, "優劣等級", fill=HEAD_FILL)
    labels = meta.get("comp_labels") or {}
    for k in range(MAX_COMPS):
        c0 = 5 + 3 * k
        comp_no, t5 = comps[k] if k < len(comps) else (None, None)
        _cell(ws, 2, c0, f"比較\n標的{k + 1}", fill=HEAD_FILL)
        _merge(ws, 2, c0 + 1, 2, c0 + 2, f"實例編號 {labels.get(comp_no, comp_no) if comp_no is not None else ''}", fill=HEAD_FILL)
        _merge(ws, 3, c0, 3, c0 + 2, t5.comparable_section if t5 else "")
        _merge(ws, 4, c0, 4, c0 + 1, "優劣等級", fill=HEAD_FILL)
        _cell(ws, 4, c0 + 2, "修正百分比", fill=HEAD_FILL)
    r = 5
    rows_by_rule = {}
    for comp_no, t5 in comps:
        rows_by_rule[comp_no] = {row.rule_id: row for row in t5.rows}
    group_nos = sorted(rs.groups)
    for g in group_nos:
        rules = [ru for ru in rs.rules if ru.group == g]
        start = r
        for ru in rules:
            _cell(ws, r, 2, ru.name, align=LEFT)
            srow = rows_by_rule[comps[0][0]].get(ru.id) if comps else None
            if srow and not ru.is_manual:
                _cell(ws, r, 3, srow.subject_num)
                _cell(ws, r, 4, level_label(ru, srow.subject_level))
            else:
                _cell(ws, r, 3)
                _cell(ws, r, 4)
            for k in range(MAX_COMPS):
                c0 = 5 + 3 * k
                if k < len(comps):
                    row = rows_by_rule[comps[k][0]].get(ru.id)
                    if row and not ru.is_manual:
                        _cell(ws, r, c0, row.comparable_num)
                        _cell(ws, r, c0 + 1, level_label(ru, row.comparable_level))
                        _cell(ws, r, c0 + 2, row.pct if row.pct is not None else "-", fmt="0.00")
                        continue
                for cc in range(c0, c0 + 3):
                    _cell(ws, r, cc)
            r += 1
        # 小計列
        _cell(ws, r, 2, "百分比小計", align=LEFT, fill=HEAD_FILL)
        _cell(ws, r, 3)
        _cell(ws, r, 4)
        for k in range(MAX_COMPS):
            c0 = 5 + 3 * k
            v = comps[k][1].group_subtotals.get(g) if k < len(comps) else None
            _merge(ws, r, c0, r, c0 + 2, v if v is not None else "", fmt=PCT_SPACE)
        _merge(ws, start, 1, r, 1, f"{rs.groups[g]}({g})", fill=HEAD_FILL)
        r += 1
    formula = "=" + "+".join(f"({g})" for g in group_nos)
    _cell(ws, r, 1, "影響地價\n區域因素\n總修正數", fill=HEAD_FILL)
    _cell(ws, r, 2, formula, align=LEFT, fill=HEAD_FILL)
    _cell(ws, r, 3)
    _cell(ws, r, 4)
    for k in range(MAX_COMPS):
        c0 = 5 + 3 * k
        v = comps[k][1].total_pct if k < len(comps) else None
        _merge(ws, r, c0, r, c0 + 2, v if v is not None else "", fmt=PCT_SPACE)
    ws.row_dimensions[r].height = 40
    r += 1
    notes = meta.get("notes") or {}
    _merge(ws, r, 1, r + 1, 1, "備註欄", fill=HEAD_FILL)
    _cell(ws, r, 2, "比準地或各比較標的", fill=HEAD_FILL)
    _merge(ws, r, 3, r, 4, notes.get("subject") or "", align=LEFT)
    for k in range(MAX_COMPS):
        c0 = 5 + 3 * k
        comp_no = comps[k][0] if k < len(comps) else None
        _merge(ws, r, c0, r, c0 + 2, (notes.get("comparables") or {}).get(str(comp_no), "") if comp_no is not None else "", align=LEFT)
    longest = max([len(notes.get("subject") or "")] + [len(v or "") for v in (notes.get("comparables") or {}).values()] + [0])
    ws.row_dimensions[r].height = min(220, max(36, 12 * (longest // 18 + 1)))          # 依最長備註估行數（每行約 18 字、12pt），PDF 與預覽照此列高縮放
    r += 1
    _cell(ws, r, 2, "全案", fill=HEAD_FILL)
    _merge(ws, r, 3, r, 4 + 3 * MAX_COMPS, notes.get("case") or "", align=LEFT)
    ws.row_dimensions[r].height = 48
    r += 2
    ws.cell(row=r, column=4 + 3 * MAX_COMPS - 3, value=f"不動產估價師：{meta.get('appraiser', '')}").font = Font(name=FONT, size=10)
    ws.page_setup.orientation = "portrait"          # 範本第 2 頁為直式
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"A1:{get_column_letter(4 + 3 * MAX_COMPS)}{r}"


# ------------------------------------------------------------------ 表4


def _disp(v: Any) -> Any:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "有" if v else "無"
    if isinstance(v, list):
        names = [x.get("name") for x in v if isinstance(x, dict) and x.get("name")]
        return "、".join(names) if names else "-"
    if isinstance(v, dict):
        return v.get("name") or v.get("value") or "-"
    return v


def _num_of(v: Any) -> float | None:
    if isinstance(v, dict):
        for k in ("distance_m", "width_m", "value"):
            if v.get(k) is not None:
                return v[k]
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v[0].get("distance_m")
    return None


def write_table4(ws: Worksheet, t4: Table4, rs: RuleSet, case: dict, subject: dict, comparables: list[dict], meta: dict) -> None:
    ws.title = "表4"
    comps = t4.comparables[:MAX_COMPS]
    comp_data = {c["comp_no"]: c for c in comparables}
    labels = meta.get("comp_labels") or {}
    widths = [5, 6, 22, 14, 6, 4] + [14, 6, 4, 8] * MAX_COMPS
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    last_col = 6 + 4 * MAX_COMPS
    _cell(ws, 1, 1, "表4  比較法調查估價表", align=LEFT, bold=True, size=14)
    ws.cell(row=1, column=1).border = Border()
    ws.cell(row=1, column=7, value=f"估價基準日：{case.get('valuation_date', '')}").font = Font(name=FONT, size=10)
    ws.cell(row=1, column=last_col - 4, value=f"案號：{case.get('case_no', '')}").font = Font(name=FONT, size=10)
    _merge(ws, 2, 1, 3, 3, "調整項目", fill=HEAD_FILL)
    _merge(ws, 2, 4, 2, 6, f"比準地：宗地流水號  {subject.get('serial_no') or '-'}", fill=HEAD_FILL)
    _merge(ws, 3, 4, 3, 6, "條件", fill=HEAD_FILL)
    blocks = []
    for k in range(MAX_COMPS):
        c0 = 7 + 4 * k
        blocks.append(c0)
        comp = comps[k] if k < len(comps) else None
        _merge(ws, 2, c0, 2, c0 + 1, f"比較標的{k + 1}", fill=HEAD_FILL)
        _merge(ws, 2, c0 + 2, 2, c0 + 3, f"實例編號：{labels.get(comp.comp_no, comp.comp_no) if comp else ''}", fill=HEAD_FILL)
        _merge(ws, 3, c0, 3, c0 + 2, "條件", fill=HEAD_FILL)
        _cell(ws, 3, c0 + 3, "差異率", fill=HEAD_FILL)

    def head(r: int, a: str, b: str | None = None) -> None:
        if b is None:
            _merge(ws, r, 1, r, 3, a, align=LEFT, fill=HEAD_FILL)
        else:
            _merge(ws, r, 1, r, 2, a, align=LEFT, fill=HEAD_FILL)
            _cell(ws, r, 3, b, fill=HEAD_FILL)

    def comp_cells(r: int, fn, pct_fn=None, fmt: str | None = None, pct_fmt: str = PCT) -> None:
        for k, c0 in enumerate(blocks):
            comp = comps[k] if k < len(comps) else None
            v = fn(comp) if comp else ""
            _merge(ws, r, c0, r, c0 + 2, v, fmt=fmt)
            pv = pct_fn(comp) if (comp and pct_fn) else ""
            _cell(ws, r, c0 + 3, pv, fmt=pct_fmt)

    r = 4
    head(r, "0基本資料")
    _merge(ws, r, 4, r, 6, subject.get("address") or subject.get("parcel_id") or "")
    comp_cells(r, lambda c: comp_data.get(c.comp_no, {}).get("address") or c.parcel_id)
    r += 1
    head(r, "土地正常單價")
    _merge(ws, r, 4, r, 6, "")
    comp_cells(r, lambda c: c.normal_unit_price, fmt=MONEY)
    r += 1
    head(r, "交易日期", "調整百分率")
    _merge(ws, r, 4, r, 6, "")
    comp_cells(r, lambda c: comp_data.get(c.comp_no, {}).get("transaction_date") or "", lambda c: c.date_adjustment_pct)
    r += 1
    head(r, "調整至估價基準日單價(元/M2)")
    _merge(ws, r, 4, r, 6, "")
    comp_cells(r, lambda c: c.price_at_valuation_date, fmt=MONEY)   # 保留小數（範本 188,459 是由 184,763.4 算出，見 docs/02 疑點 4）
    r += 1
    head(r, "地價區段", "區域因素調整百分率")
    _merge(ws, r, 4, r, 6, subject.get("section_id") or "")
    comp_cells(r, lambda c: c.section_id, lambda c: c.regional_adjustment_pct)
    r += 1
    items_start = r
    rows_by_item = {c.comp_no: {row.item_no: row for row in c.rows} for c in comps}
    groups = {}
    for ru in sorted([x for x in rs.rules if x.item_no and not x.is_manual], key=lambda x: x.item_no):
        groups.setdefault(ru.group, []).append(ru)
    for g, rules in sorted(groups.items()):
        gstart = r
        for ru in rules:
            _cell(ws, r, 3, f"{ru.item_no}{ru.name}", align=LEFT)
            _value_cells(ws, r, 4, ru, _subject_obs(ru, subject))      # 顯示值取自宗地資料（含設施名稱），修正率取自引擎
            for k, c0 in enumerate(blocks):
                if k < len(comps):
                    row = rows_by_item[comps[k].comp_no].get(ru.item_no)
                    _value_cells(ws, r, c0, ru, _subject_obs(ru, comp_data.get(comps[k].comp_no, {})))
                    _cell(ws, r, c0 + 3, row.pct if (row and row.pct is not None) else "-", fmt=PCT)
                else:
                    _merge(ws, r, c0, r, c0 + 2, "")
                    _cell(ws, r, c0 + 3, "")
            r += 1
        _merge(ws, gstart, 2, r - 1, 2, f"{g}\n{rs.groups.get(g, '')}", fill=HEAD_FILL)
    manual = [x for x in rs.rules if x.is_manual]
    for ru in manual:
        _merge(ws, r, 2, r, 3, f"{ru.item_no}{ru.name}", align=LEFT, fill=HEAD_FILL)
        _merge(ws, r, 4, r, 6, _disp(subject.get(ru.parcel_field)))
        for k, c0 in enumerate(blocks):
            if k < len(comps):
                row = rows_by_item[comps[k].comp_no].get(ru.item_no)
                _merge(ws, r, c0, r, c0 + 2, _disp(row.comparable_value if row else None))
                _cell(ws, r, c0 + 3, row.pct if (row and row.pct is not None) else "-", fmt=PCT)
            else:
                _merge(ws, r, c0, r, c0 + 2, "")
                _cell(ws, r, c0 + 3, "")
        r += 1
    _merge(ws, items_start, 1, r - 1, 1, "個\n別\n因\n素\n調\n整", fill=HEAD_FILL)
    _merge(ws, r, 2, r, 3, "合計", fill=HEAD_FILL)
    _merge(ws, r, 4, r, 6, "")
    for k, c0 in enumerate(blocks):
        _merge(ws, r, c0, r, c0 + 3, comps[k].individual_total_pct if k < len(comps) else "", fmt=PCT)
    r += 1
    pstart = r
    _merge(ws, r, 2, r, 3, "調整百分率絕對值加總", align=LEFT, fill=HEAD_FILL)
    _merge(ws, r, 4, r, 6, "價格形成因素之相近程度", fill=HEAD_FILL)
    for k, c0 in enumerate(blocks):
        _merge(ws, r, c0, r, c0 + 1, comps[k].abs_sum_pct if k < len(comps) else "", fmt=PCT)
        _merge(ws, r, c0 + 2, r, c0 + 3, comps[k].similarity if k < len(comps) else "")
    r += 1
    _merge(ws, r, 2, r, 3, "試算價格", align=LEFT, fill=HEAD_FILL)
    _merge(ws, r, 4, r, 6, "比較標的權重", fill=HEAD_FILL)
    for k, c0 in enumerate(blocks):
        _merge(ws, r, c0, r, c0 + 1, round(comps[k].trial_price) if k < len(comps) else "", fmt=MONEY)
        _merge(ws, r, c0 + 2, r, c0 + 3, comps[k].weight_pct if k < len(comps) else "", fmt='0"%"')
    r += 1
    _merge(ws, r, 2, r, 6, "比準地比較價格", fill=HEAD_FILL)
    _merge(ws, r, 7, r, last_col, t4.subject_comparison_price, fmt=MONEY)
    _merge(ws, pstart, 1, r, 1, "比\n較\n價\n格", fill=HEAD_FILL)
    r += 1
    notes = meta.get("notes") or {}
    nstart = r
    _merge(ws, r, 2, r, 3, "比準地或各比較標的", fill=HEAD_FILL)
    _merge(ws, r, 4, r, 6, notes.get("subject") or "", align=LEFT)
    for k, c0 in enumerate(blocks):
        comp = comps[k] if k < len(comps) else None
        txt = ""
        if comp:
            txt = (notes.get("comparables") or {}).get(str(comp.comp_no)) or (comp_data.get(comp.comp_no, {}).get("date_adjustment") or {}).get("note") or ""
        _merge(ws, r, c0, r, c0 + 3, txt, align=LEFT)
    longest4 = max([len(notes.get("subject") or "")] + [len(v or "") for v in (notes.get("comparables") or {}).values()] + [0])
    ws.row_dimensions[r].height = min(200, max(60, 12 * (longest4 // 30 + 1)))
    r += 1
    _merge(ws, r, 2, r, 3, "全案", fill=HEAD_FILL)
    _merge(ws, r, 4, r, last_col, notes.get("case") or "", align=LEFT)
    ws.row_dimensions[r].height = 80
    _merge(ws, nstart, 1, r, 1, "備\n註\n欄", fill=HEAD_FILL)
    r += 1
    sig = [(1, f"填寫日期：{meta.get('fill_date', '')}"), (4, "承辦員："), (7, "課（股）長："), (11, "主任（局、處長）："),
           (last_col - 3, f"不動產估價師：{meta.get('appraiser', '')}")]
    for c, txt in sig:
        ws.cell(row=r, column=c, value=txt).font = Font(name=FONT, size=10)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_area = f"A1:{get_column_letter(last_col)}{r}"


def _subject_obs(ru: Rule, parcel: dict) -> Any:
    if ru.parcel_field == "front_road_width_m":
        return parcel.get("front_road")
    return parcel.get(ru.parcel_field)


def _value_cells(ws: Worksheet, r: int, c0: int, ru: Rule, v: Any) -> None:
    """條件欄三格：設施/道路 → 名稱 | 數值 | M；其他 → 合併一格。"""
    num = _num_of(v)
    ctype = ru.criteria.get("type")
    if num is not None and (ctype == "distance" or ru.parcel_field == "front_road_width_m"):
        _cell(ws, r, c0, _disp(v))
        _cell(ws, r, c0 + 1, num, fmt="0")
        _cell(ws, r, c0 + 2, "M")
        return
    if v is None:
        _merge(ws, r, c0, r, c0 + 2, "-")
        return
    if ru.parcel_field in ("bcr_pct", "far_pct") and isinstance(v, (int, float)):
        _merge(ws, r, c0, r, c0 + 2, v, fmt='0"%"')
        return
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        _merge(ws, r, c0, r, c0 + 2, v, fmt="0.##" if isinstance(v, float) and not float(v).is_integer() else "0")
        return
    _merge(ws, r, c0, r, c0 + 2, _disp(v))


# ------------------------------------------------------------------ 入口


def build_workbook(data: dict, *, meta: dict | None = None, regional: RuleSet | None = None,
                   individual: RuleSet | None = None, figures: list[tuple[str, str, bytes]] | None = None) -> Workbook:
    """data = 內部 schema 案件（fixtures 的結構，不含 expected）。內部跑引擎後產出兩張工作表。"""
    meta = meta or {}
    rs_ids = data["case"].get("rulesets") or {}
    regional = regional or load_ruleset(rs_ids.get("regional", "jinshan_commercial_regional"))
    individual = individual or load_ruleset(rs_ids.get("individual", "jinshan_commercial_individual"))
    result = run_case(regional, individual, data)
    case = dict(data["case"])
    case.setdefault("land_use", regional.land_use)
    from .xlsx_table1 import write_table1
    wb = Workbook()
    ws1 = wb.active
    subject_sid = data["subject_parcel"].get("section_id")
    sections = data.get("sections") or {}
    section = sections.get(subject_sid) or next(iter(sections.values()), {"section_id": subject_sid, "survey": {}})
    write_table1(ws1, section, case, regional, meta | {"level_numbers": (meta.get("table1_level_numbers") or {}).get(subject_sid, {})})
    # 比較標的所在區段各一張勘查表（實務上比準地＋每個比較標的區段都要勘查表；決賽題目就是四張）
    order = [c.get("section_id") for c in data.get("comparables") or []] + list(sections)
    done = {section.get("section_id")}
    for sid in order:
        if not sid or sid in done or sid not in sections:
            continue
        done.add(sid)
        wsx = wb.create_sheet()
        write_table1(wsx, sections[sid], case, regional, meta | {"level_numbers": (meta.get("table1_level_numbers") or {}).get(sid, {})})
        wsx.title = f"表1 {sid}"[:31]
    ws5 = wb.create_sheet()
    write_table5(ws5, result["table5"], regional, case, meta)
    ws4 = wb.create_sheet()
    write_table4(ws4, result["table4"], individual, case, data["subject_parcel"], data["comparables"], meta)
    for _mode, title, png in figures or []:
        write_figure(wb.create_sheet(title[:31]), title, png, case)
    return wb


def write_figure(ws, title: str, png: bytes, case: dict) -> None:
    """一張圖說一張工作表（範本第 4–6 頁）。頁式 PNG（A3 橫式整頁，含標題與估價師欄）直接放 A1、A3 橫式一頁；舊式 4:3 圖則加標題列。"""
    from openpyxl.drawing.image import Image as XLImage
    img = XLImage(io.BytesIO(png))
    page_style = img.width / max(img.height, 1) > 1.2 and img.width >= 2000
    if page_style:
        img.width, img.height = 1190, 842
        ws.add_image(img, "A1")
        ws.page_setup.paperSize = ws.PAPERSIZE_A3
        ws.page_margins.left = ws.page_margins.right = ws.page_margins.top = ws.page_margins.bottom = 0.2
    else:
        ws["A1"] = f"{title}　案號 {case.get('case_no', '')}　估價基準日 {case.get('valuation_date', '')}"
        ws["A1"].font = Font(bold=True, size=14)
        img.width, img.height = 960, 720
        ws.add_image(img, "A3")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def export_xlsx(data: dict, dest: str | Path | io.BytesIO, *, meta: dict | None = None) -> Workbook:
    wb = build_workbook(data, meta=meta)
    wb.save(dest)
    return wb
