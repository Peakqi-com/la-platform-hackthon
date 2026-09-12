"""
書表格線：把 openpyxl 工作表轉成「格子清單」（含合併、樣式），給前端書表預覽畫成 HTML，也給 reportlab 畫成 PDF。
版面只有一份來源（xlsx.py／xlsx_table1.py 照範本寫的工作表），Excel、預覽、PDF 三者一致。
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.worksheet.worksheet import Worksheet

CHAR_PX = 7.2          # Excel 欄寬（字元數）→ 像素
PT_PX = 4 / 3          # 點 → 像素
DEFAULT_ROW_PT = 15.0
FONT_DIR = Path(__file__).resolve().parents[1] / "fonts"
FONT_CANDIDATES = [(os.environ.get("PDF_FONT") or "", 0), (str(FONT_DIR / "wqy-microhei.ttc"), 0), ("/System/Library/Fonts/PingFang.ttc", 0),
                   ("/System/Library/Fonts/STHeiti Light.ttc", 0), ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0),
                   ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0), ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 0)]


def _fmt_value(v: Any, number_format: str | None) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "有" if v else "無"
    if isinstance(v, (int, float)) and number_format:
        nf = number_format
        if '"%"' in nf:
            return f"{v:.2f}%"
        if '" %"' in nf:
            return f"{v:.2f} %"
        if "#,##0" in nf:
            return f"{v:,.0f}"
        if "0.00" in nf:
            return f"{v:.2f}"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def sheet_grid(ws: Worksheet) -> dict[str, Any]:
    """一張工作表 → {title, orientation, cols[px], rows[px], cells[{r,c,rs,cs,v,b,size,fill,h,v_align,border}]}。"""
    if ws.print_area:
        area = ws.print_area if isinstance(ws.print_area, str) else ws.print_area[0]
        c1, r1, c2, r2 = range_boundaries(area.replace("$", "").split("!")[-1])
    else:
        c1, r1, c2, r2 = 1, 1, ws.max_column, ws.max_row
    merged: dict[tuple[int, int], tuple[int, int]] = {}
    covered: set[tuple[int, int]] = set()
    for rng in ws.merged_cells.ranges:
        mc1, mr1, mc2, mr2 = rng.min_col, rng.min_row, rng.max_col, rng.max_row
        merged[(mr1, mc1)] = (mr2 - mr1 + 1, mc2 - mc1 + 1)
        for r in range(mr1, mr2 + 1):
            for c in range(mc1, mc2 + 1):
                if (r, c) != (mr1, mc1):
                    covered.add((r, c))
    cols = []
    for c in range(c1, c2 + 1):
        w = ws.column_dimensions[get_column_letter(c)].width
        cols.append(round((w if w else 8.43) * CHAR_PX + 5))
    rows = []
    for r in range(r1, r2 + 1):
        h = ws.row_dimensions[r].height
        rows.append(round((h if h else DEFAULT_ROW_PT) * PT_PX))
    cells = []
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            if (r, c) in covered:
                continue
            cell = ws.cell(row=r, column=c)
            rs, cs = merged.get((r, c), (1, 1))
            v = _fmt_value(cell.value, cell.number_format)
            has_border = bool(cell.border and cell.border.left and cell.border.left.style)
            fill = None
            if cell.fill and cell.fill.fill_type == "solid" and cell.fill.fgColor and cell.fill.fgColor.rgb and isinstance(cell.fill.fgColor.rgb, str):
                rgb = cell.fill.fgColor.rgb[-6:]
                if rgb.upper() not in ("000000", "FFFFFF"):
                    fill = "#" + rgb
            if not v and not has_border and not fill:
                continue
            cells.append({"r": r - r1, "c": c - c1, "rs": rs, "cs": cs, "v": v, "b": bool(cell.font and cell.font.bold),
                          "size": float(cell.font.size or 9) if cell.font else 9.0, "fill": fill,
                          "h": (cell.alignment.horizontal if cell.alignment and cell.alignment.horizontal else ("right" if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool) else "left")),
                          "va": (cell.alignment.vertical if cell.alignment and cell.alignment.vertical else "center"),
                          "wrap": bool(cell.alignment and cell.alignment.wrap_text), "border": has_border})
    # 沒框線的文字（標題、簽章欄）比照 Excel 溢到右側空格：把 colspan 延伸到下一個有內容的格子為止，預覽與 PDF 才不會互相疊字
    occupied = {(c["r"], c["c"]) for c in cells if c["v"] or c["border"] or c["fill"]}
    for cell in cells:
        if cell["border"] or not cell["v"] or cell["cs"] != 1 or cell["rs"] != 1:
            continue
        span = 1
        while cell["c"] + span < len(cols) and (cell["r"], cell["c"] + span) not in occupied and (r1 + cell["r"], c1 + cell["c"] + span) not in covered:
            span += 1
        cell["cs"] = span
        cell["wrap"] = False
    orient = ws.page_setup.orientation if ws.page_setup.orientation in ("portrait", "landscape") else ("portrait" if sum(cols) < 760 else "landscape")   # 工作表有指定就照指定（表1、表5 直式）
    return {"title": ws.title, "orientation": orient, "cols": cols, "rows": rows, "cells": cells}


def workbook_grids(wb) -> list[dict[str, Any]]:
    return [sheet_grid(ws) for ws in wb.worksheets if not getattr(ws, "_images", None)]


# ------------------------------------------------------------------ PDF（reportlab）

_font_name: str | None = None


def pdf_font() -> str:
    """找一個能嵌入的 TrueType 中文字型（TTC 也可）；找不到就退回 Helvetica（中文會變方塊，PDF 上註明）。"""
    global _font_name
    if _font_name:
        return _font_name
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for path, idx in FONT_CANDIDATES:
        if path and Path(path).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", path, subfontIndex=idx))
                _font_name = "CJK"
                return _font_name
            except (OSError, ValueError, TypeError):   # 字型檔壞掉就試下一個
                continue
    _font_name = "Helvetica"
    return _font_name


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth
    out: list[str] = []
    for para in str(text).split("\n"):
        line = ""
        for ch in para:
            if stringWidth(line + ch, font, size) > width and line:
                out.append(line)
                line = ch
            else:
                line += ch
        out.append(line)
    return out


def _cell_lines(cell: dict, width_px: float, font: str) -> list[str]:
    """與繪製時同樣的換行規則（單位：px，縮放前）。"""
    fs = cell["size"] * PT_PX * 0.92
    pad = 2
    if cell["border"] and (cell["wrap"] or cell["cs"] == 1 or "\n" in cell["v"]):
        return _wrap(cell["v"], font, fs, width_px - 2 * pad)
    return str(cell["v"]).split("\n")


def _autofit_rows(g: dict[str, Any], font: str) -> list[float]:
    """Excel 會依換行內容自動長高列，openpyxl 讀不到；這裡照文字行數把列高補足（合併格不夠的高度加到最後一列）。"""
    rows = [float(h) for h in g["rows"]]
    cols = g["cols"]
    for cell in g["cells"]:
        if not cell["v"]:
            continue
        w = sum(cols[cell["c"]:cell["c"] + cell["cs"]])
        lines = _cell_lines(cell, w, font)
        need = len(lines) * cell["size"] * PT_PX * 0.92 * 1.18 + 4
        r0, rs = cell["r"], cell["rs"]
        avail = sum(rows[r0:r0 + rs])
        if need > avail:
            rows[r0 + rs - 1] += need - avail
    return rows


def grids_to_pdf(grids: list[dict[str, Any]], figures: list[tuple[str, str, bytes]] | None = None, *, footer: str = "") -> bytes:
    """每張表一頁（A4，依 orientation），列高先依內容補足再縮放到整頁可見；圖說每張一頁。"""
    from reportlab.lib.pagesizes import A3, A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    font = pdf_font()
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    margin = 28
    for g in grids:
        size = landscape(A4) if g["orientation"] == "landscape" else A4
        c.setPageSize(size)
        pw, ph = size
        g = {**g, "rows": _autofit_rows(g, font)}
        total_w, total_h = sum(g["cols"]), sum(g["rows"])
        s = min((pw - 2 * margin) / max(total_w, 1), (ph - 2 * margin - 14) / max(total_h, 1))
        x0, y0 = margin, ph - margin
        xs = [x0]
        for w in g["cols"]:
            xs.append(xs[-1] + w * s)
        ys = [y0]
        for h in g["rows"]:
            ys.append(ys[-1] - h * s)
        for cell in g["cells"]:
            x1, x2 = xs[cell["c"]], xs[cell["c"] + cell["cs"]]
            yt, yb = ys[cell["r"]], ys[cell["r"] + cell["rs"]]
            if cell["fill"]:
                c.setFillColor(cell["fill"])
                c.rect(x1, yb, x2 - x1, yt - yb, stroke=0, fill=1)
            if cell["border"]:
                c.setStrokeColorRGB(0, 0, 0)
                c.setLineWidth(0.5)
                c.rect(x1, yb, x2 - x1, yt - yb, stroke=1, fill=0)
            if cell["v"]:
                fs = max(cell["size"] * s * PT_PX * 0.92, 4)
                c.setFont(font, fs)
                c.setFillColorRGB(0, 0, 0)
                pad = 2 * s
                lines = [ln for ln in _cell_lines(cell, sum(g["cols"][cell["c"]:cell["c"] + cell["cs"]]), font)]
                lh = fs * 1.18
                block_h = lh * len(lines)
                if cell["va"] == "top":
                    ty = yt - pad - fs
                elif cell["va"] == "bottom":
                    ty = yb + pad + block_h - fs
                else:
                    ty = (yt + yb) / 2 + block_h / 2 - fs * 0.95
                for ln in lines:
                    if cell["h"] == "center":
                        c.drawCentredString((x1 + x2) / 2, ty, ln)
                    elif cell["h"] == "right":
                        c.drawRightString(x2 - pad, ty, ln)
                    else:
                        c.drawString(x1 + pad, ty, ln)
                    ty -= lh
        if footer:
            c.setFont(font, 7)
            c.setFillColorRGB(0.35, 0.35, 0.35)
            c.drawString(margin, margin / 2, footer + ("" if font == "CJK" else "  (no CJK font: Chinese may not render)"))
        c.showPage()
    for _mode, _title, png in figures or []:
        # 圖說頁：PNG 本身已是整頁版面（render_page_png，A3 橫式，含標題／比例尺／估價師欄），照範本第 4–6 頁用 A3 橫式滿版放
        img = ImageReader(io.BytesIO(png))
        iw, ih = img.getSize()
        size = landscape(A3) if iw / ih > 1.2 and iw >= 2000 else landscape(A4)
        c.setPageSize(size)
        pw, ph = size
        if size == landscape(A3):
            c.drawImage(img, 0, 0, pw, ph)
        else:
            s = min((pw - 2 * margin) / iw, (ph - 2 * margin) / ih)
            c.drawImage(img, (pw - iw * s) / 2, (ph - ih * s) / 2, iw * s, ih * s)
        c.showPage()
    c.save()
    return buf.getvalue()
