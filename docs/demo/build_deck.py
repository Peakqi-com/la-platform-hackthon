"""決賽簡報產生器：docs/11_deck_plan.md 的 30 頁 → PowerPoint 16:9。
配色比照網站（暖橘主色、米白底、深灰字）；封面與段落頁用主辦 KV 深藍。圖片來自 deck_img/。
執行：cd docs/demo && python3 build_deck.py → AI輔助不動產估價案件審查_簡報.pptx
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
IMG = HERE / "deck_img"
OUT = HERE / "AI輔助不動產估價案件審查_簡報.pptx"

ORANGE = RGBColor(0xEA, 0x58, 0x0C)
ORANGE_D = RGBColor(0x9A, 0x34, 0x12)
CREAM = RGBColor(0xFF, 0xF7, 0xED)
CREAM_D = RGBColor(0xFF, 0xED, 0xD5)
INK = RGBColor(0x1F, 0x29, 0x37)
GREY = RGBColor(0x64, 0x74, 0x8B)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
NAVY = RGBColor(0x0A, 0x16, 0x57)
NAVY_L = RGBColor(0x14, 0x24, 0x7A)
CYAN = RGBColor(0x5C, 0xE1, 0xE6)
PINK = RGBColor(0xF2, 0xA7, 0xD8)
FONT = "Microsoft JhengHei"

W, H = Inches(13.333), Inches(7.5)
prs = Presentation()
prs.slide_width, prs.slide_height = W, H
BLANK = prs.slide_layouts[6]
page_no = 0


def _font(run, size, color=INK, bold=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1.5)
    s.shadow.inherit = False
    return s


def text(slide, x, y, w, h, lines, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15):
    """lines: str 或 [(文字, size, color, bold)]；字串裡的換行分段。"""
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    items = lines if isinstance(lines, list) else [(lines, size, color, bold)]
    first = True
    for it in items:
        t, sz, col, bd = (it + (size, color, bold))[:4] if isinstance(it, tuple) else (it, size, color, bold)
        for seg in str(t).split("\n"):
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.alignment = align
            p.line_spacing = spacing
            r = p.add_run()
            r.text = seg
            _font(r, sz, col, bd)
    return tb


def bullets(slide, x, y, w, h, items, size=15, color=INK, gap=6):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05)
    first = True
    for it in items:
        head, body = (it if isinstance(it, tuple) else (None, it))
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        p.space_after = Pt(gap)
        p.line_spacing = 1.12
        r = p.add_run()
        r.text = "•  "
        _font(r, size, ORANGE, True)
        if head:
            r = p.add_run()
            r.text = head + "　"
            _font(r, size, ORANGE_D, True)
        r = p.add_run()
        r.text = body
        _font(r, size, color)
    return tb


def picture(slide, name, x, y, w, h, border=True):
    """等比放進框內（置中），可加細框。"""
    p = IMG / name
    iw, ih = Image.open(p).size
    s = min(w / iw, h / ih)
    pw, ph = int(iw * s), int(ih * s)
    px, py = x + (w - pw) // 2, y + (h - ph) // 2
    if border:
        rect(slide, px - Emu(12000), py - Emu(12000), pw + Emu(24000), ph + Emu(24000), WHITE, line=RGBColor(0xE5, 0xD5, 0xC0))
    return slide.shapes.add_picture(str(p), px, py, pw, ph)


def caption(slide, x, y, w, t):
    text(slide, x, y, w, Inches(0.35), t, size=11, color=GREY)


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


def footer(slide, dark=False):
    global page_no
    page_no += 1
    col = CYAN if dark else GREY
    text(slide, Inches(0.5), H - Inches(0.42), Inches(8), Inches(0.3), "AI 輔助不動產估價案件審查　｜　AI城市起風", size=10, color=col)
    text(slide, W - Inches(1.2), H - Inches(0.42), Inches(0.7), Inches(0.3), str(page_no), size=10, color=col, align=PP_ALIGN.RIGHT)


def content_slide(title, section, body_items=None, image=None, layout="split", cap=None, note=None, image2=None, size=15):
    """layout: split（左字右圖）｜wide（上字下圖）｜text（純文字）｜two（左右兩圖）"""
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, W, H, CREAM)
    rect(s, Inches(0.5), Inches(0.42), Inches(0.12), Inches(0.62), ORANGE)
    text(s, Inches(0.75), Inches(0.35), Inches(9.5), Inches(0.8), title, size=26, bold=True)
    text(s, W - Inches(4.3), Inches(0.5), Inches(3.8), Inches(0.4), section, size=12, color=ORANGE_D, align=PP_ALIGN.RIGHT)
    top = Inches(1.3)
    if layout == "split":
        if body_items:
            bullets(s, Inches(0.6), top, Inches(4.9), Inches(5.5), body_items, size=size)
        if image:
            picture(s, image, Inches(5.7), top, Inches(7.1), Inches(5.3))
            if cap:
                caption(s, Inches(5.7), Inches(6.65), Inches(7.1), cap)
    elif layout == "wide":
        if body_items:
            bullets(s, Inches(0.6), top, Inches(12.1), Inches(1.5), body_items, size=size, gap=2)
        if image:
            picture(s, image, Inches(0.6), Inches(2.85), Inches(12.1), Inches(3.9))
            if cap:
                caption(s, Inches(0.6), Inches(6.75), Inches(12.1), cap)
    elif layout == "two":
        if body_items:
            bullets(s, Inches(0.6), top, Inches(12.1), Inches(1.3), body_items, size=size, gap=2)
        picture(s, image, Inches(0.6), Inches(2.7), Inches(6.0), Inches(4.0))
        picture(s, image2, Inches(6.8), Inches(2.7), Inches(6.0), Inches(4.0))
        if cap:
            caption(s, Inches(0.6), Inches(6.75), Inches(12.1), cap)
    else:
        if body_items:
            bullets(s, Inches(0.6), top, Inches(12.1), Inches(5.5), body_items, size=size + 1, gap=10)
    footer(s)
    if note:
        notes(s, note)
    return s


def section_slide(num, title, sub):
    s = prs.slides.add_slide(BLANK)
    rect(s, 0, 0, W, H, NAVY)
    rect(s, 0, H - Inches(0.9), W, Inches(0.9), NAVY_L)
    text(s, Inches(0.9), Inches(2.0), Inches(3), Inches(1.6), num, size=72, color=CYAN, bold=True)
    text(s, Inches(0.9), Inches(3.5), Inches(11), Inches(1.2), title, size=40, color=WHITE, bold=True)
    text(s, Inches(0.95), Inches(4.6), Inches(11), Inches(0.8), sub, size=18, color=PINK)
    footer(s, dark=True)
    return s


def box(slide, x, y, w, h, title, body="", fill=NAVY_L, line=CYAN, tcol=WHITE, bcol=PINK, tsize=15, bsize=11):
    b = rect(slide, x, y, w, h, fill, line=line, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    b.adjustments[0] = 0.12
    tf = b.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Inches(0.08)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    _font(r, tsize, tcol, True)
    if body:
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = body
        _font(r2, bsize, bcol)
    return b


def arrow(slide, x1, y1, x2, y2, color=CYAN):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x1, y1, x2, y2)
    c.line.color.rgb = color
    c.line.width = Pt(2.25)
    ln = c.line._get_or_add_ln()
    from pptx.oxml.ns import qn
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    return c


# ───────────────────────────── 1 封面
s = prs.slides.add_slide(BLANK)
kv = Image.open(HERE / "assets" / "kv_webtitle.jpg")
kw, kh = kv.size
target = W / H
cw = int(kh * target)
kv.crop((0, 0, min(cw, kw), kh)).save(IMG / "kv_169.jpg")
s.shapes.add_picture(str(IMG / "kv_169.jpg"), 0, 0, W, H)
rect(s, 0, Inches(5.05), W, Inches(2.45), RGBColor(0x06, 0x0E, 0x3A))
text(s, Inches(0.7), Inches(5.15), Inches(9.5), Inches(0.9), "AI 輔助不動產估價案件審查", size=36, color=WHITE, bold=True)
text(s, Inches(0.7), Inches(5.95), Inches(9.5), Inches(0.5), "土地徵收補償市價查估・估價案件審查輔助系統", size=18, color=CYAN)
text(s, Inches(0.7), Inches(6.5), Inches(9.5), Inches(0.5), "新北市政府地政局命題　｜　2026 新北市 AI 智慧城市黑客松競賽", size=13, color=PINK)
text(s, W - Inches(4.6), Inches(5.25), Inches(4.0), Inches(0.6), "隊名　AI城市起風", size=20, color=WHITE, bold=True, align=PP_ALIGN.RIGHT)
text(s, W - Inches(4.6), Inches(5.9), Inches(4.0), Inches(0.5), "吳昭奇　洪湛閎　丁家麒", size=16, color=CYAN, align=PP_ALIGN.RIGHT)
page_no += 1

# ───────────────────────────── 2 痛點（命題文件原句）
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, CREAM)
rect(s, Inches(0.5), Inches(0.42), Inches(0.12), Inches(0.62), ORANGE)
text(s, Inches(0.75), Inches(0.35), Inches(9.5), Inches(0.8), "現況與痛點（引自地政局命題文件）", size=26, bold=True)
text(s, W - Inches(4.3), Inches(0.5), Inches(3.8), Inches(0.4), "為什麼", size=12, color=ORANGE_D, align=PP_ALIGN.RIGHT)
q = rect(s, Inches(0.6), Inches(1.3), Inches(7.2), Inches(2.0), CREAM_D)
text(s, Inches(0.8), Inches(1.4), Inches(6.9), Inches(1.9),
     "「審查人員須人工比對多張表單（如地價區段勘查表、影響地價區域因素分析明細表、比較法調查估價表），逐項核算距離、級距、修正率與加總結果，不僅作業時間長，且容易因人工判讀或抄填錯誤影響審查品質。」",
     size=15, color=ORANGE_D)
bullets(s, Inches(0.6), Inches(3.5), Inches(7.2), Inches(3.2), [
    ("痛點 1", "估價書表涉及表單眾多，人工逐項比對耗時且易發生疏漏。"),
    ("痛點 2", "區域因素與個別因素需依不同用地類別基準明細表判定，人工判讀一致性不易維持。"),
    ("痛點 3", "修正率加總及跨表抄填（如區域因素總修正數）容易出現計算或填載錯誤。"),
    ("預期成果", "透過 AI 輔助完成估價書填寫流程；降低人工審查時間與錯誤率，提升效率與一致性。"),
], size=15)
picture(s, "template_p1.png", Inches(8.1), Inches(1.3), Inches(2.4), Inches(3.4))
picture(s, "template_p3.png", Inches(10.6), Inches(1.3), Inches(2.4), Inches(3.4))
picture(s, "problem_statement.png", Inches(8.1), Inches(4.85), Inches(4.9), Inches(1.9))
caption(s, Inches(8.1), Inches(4.6), Inches(4.9), "上：查估書表範本第 1、3 頁　下：命題文件")
footer(s)
notes(s, "痛點原句來自命題文件。強調：表單多、基準表因案而異、跨表抄填。")

# ───────────────────────────── 3 一句話 + 四步驟（深藍圖）
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
text(s, Inches(0.7), Inches(0.5), Inches(12), Inches(0.8), "我們做什麼", size=30, color=WHITE, bold=True)
text(s, Inches(0.7), Inches(1.3), Inches(12), Inches(1.2),
     "把「勘查表事實 → 優劣等級 → 修正率 → 加總 → 跨表抄填」這條鏈自動化，並反向審查：\n比對估價師填的表與規則算出的表，逐條指出不一致並引用依據。沒有書表時，只給地號也能先產出一版。",
     size=17, color=PINK)
steps = [("① 輸入資料", "送審書表 PDF／年期與地號\n／評價基準明細表"), ("② 產出書表", "依基準表判等級、修正率\n與價格鏈，重算六頁書表"),
         ("③ 審查", "逐格比對填載值與核算值\n標出不符與依據，承辦裁決"), ("④ 輸出", "書表 Excel／PDF、意見書\nWord／PDF、三張圖說")]
x0, y0, bw, bh, gap = Inches(0.7), Inches(3.2), Inches(2.75), Inches(1.9), Inches(0.35)
for i, (t, b) in enumerate(steps):
    x = x0 + i * (bw + gap)
    box(s, x, y0, bw, bh, t, b, tsize=20, bsize=13)
    if i < 3:
        arrow(s, x + bw, y0 + bh // 2, x + bw + gap, y0 + bh // 2)
ins = [("送審書表 PDF", "估價單位送來的六頁書表"), ("範例", "相符／含填載錯誤／僅勘查表"), ("年期＋地號", "沒有書表時一鍵產出")]
for i, (t, b) in enumerate(ins):
    box(s, Inches(0.7) + i * Inches(4.15), Inches(5.6), Inches(3.8), Inches(1.0), "入口：" + t, b, fill=NAVY, line=PINK, tsize=15, bsize=11)
footer(s, dark=True)

# ───────────────────────────── 段落：設計原則
section_slide("01", "設計原則與資料基礎", "數字可追溯、推定不判錯、資料在本機")

content_slide("四個不可違反的原則", "設計原則", [
    ("① 規則引擎確定性", "每一個等級與修正率都指回基準表 JSON 的某一格；語言模型不碰數字。"),
    ("② 算式對回法源", "每條算式對回土地徵收補償市價查估辦法條號、作業手冊印刷頁碼（docs/07 對照表）。"),
    ("③ 推定只標「需確認」", "圖資推定值與範本本身疑點一律「需確認」，不判錯；估價師填值優先。"),
    ("④ 資料在本機", "路網、設施、分區、實價登錄、指數全部預先下載，不依賴外部 API；底圖瓦片有快取。"),
], image="rule_cell.png", cap="評價基準明細表判定條件與修正矩陣格位：每個修正率都能點回這裡", size=15,
    note="規則引擎是確定性的；語言模型只做文件抽取與意見書潤飾。")

content_slide("法規與規則來源", "設計原則", [
    ("查估辦法", "土地徵收補償市價查估辦法 §5、§7、§13、§17、§18、§19、§20、§21。"),
    ("作業手冊", "土地徵收補償市價查估作業手冊，頁碼校正到印刷頁；p.100–102 官方算例當第二組驗收。"),
    ("技術規則", "不動產估價技術規則為一般規定，與查估辦法衝突時依查估辦法（§25、§26、§27、§48–§67、§98、§100 已對照）。"),
    ("第四號公報", "估價師公會全聯會第四號公報 113.12.11：建物成本、耐用年數、殘價率。"),
    ("基準表與上限", "評價基準明細表是資料不是程式，換區換用地別只換 JSON；內政部評價基準表上限只提醒。"),
    ("建蔽率容積率", "施行細則附表一、附表三＋各計畫區土管要點自動抽取（48 個計畫區）。"),
], image="input_rules.png", cap="評價基準明細表分頁：匯入地政局 PDF 自動解析成規則", size=14)

content_slide("圖資與開放資料", "設計原則", [
    ("底圖", "國土測繪中心通用版電子地圖與段籍圖（瓦片快取，金山一帶離線可用）。"),
    ("路網與設施", "OpenStreetMap 全新北市路網、步行圖、95,696 筆設施、367 萬筆門牌。"),
    ("分區與地籍", "城鄉局都市計畫使用分區；地籍圖匯入圖檔或預載。"),
    ("市場", "內政部實價登錄、都市地價指數、新北市營造工程物價指數。"),
    ("環境", "水利署淹水潛勢、環境部列管污染源、經濟部商圈、交通局路邊停車格、高公局交流道、中油加油站。"),
    ("每筆距離帶來源", "資料集名稱、量測方式（步行／直線）、起點約定，畫面與書表都看得到。"),
], image="map_interactive.png", cap="地圖互動檢視：右側每筆接近條件標來源與量測方式", size=14)

# ───────────────────────────── 段落：案件總覽與入口
section_slide("02", "案件總覽與三種入口", "送審書表 PDF／年期與地號／範例")

content_slide("案件總覽：承辦的儀表板", "案件總覽", [
    ("五個數字", "全部案件、審查中、待處理不符項、產出已過期、已完成。"),
    ("兩張入口卡", "審查送審書表（拖 PDF）、一鍵建案（依地號產生書表）。"),
    ("案件清單", "審查結果、比較價格、產出是否最新、最後操作、依狀態給「下一步」按鈕。"),
    ("封存取代刪除", "資料與紀錄都保留，可復原。"),
    ("操作身分", "左下填姓名與角色，寫進操作紀錄與意見書落款。"),
], image="home_top.png", cap="案件總覽首頁", size=15)

content_slide("入口 A：上傳送審書表 PDF", "案件總覽", [
    ("拖進六頁 PDF", "文字層直接讀取；掃描件走影像辨識。"),
    ("先預覽再建案", "每頁辨識到哪一表、案號、比準地、比較標的件數、缺漏欄位、低信心欄位、提醒。"),
    ("建立案件並開始審查", "建案同時補地籍界線與區段範圍，直接進審查頁。"),
    ("範本實測", "六頁範本文字層還原 99%，缺漏 0、低信心 0。"),
], image="import_preview.png", cap="辨識結果預覽", size=15)

content_slide("入口 B：一鍵建案（依地號產生書表）", "案件總覽", [
    ("只填五格", "案號、估價基準日、鄉鎮市區、比準地地號、用地別。"),
    ("約 30 秒", "地籍界線 → 宗地屬性推定 → 區段範圍（路網推估街廓）→ 勘查表 28 欄 → 設施距離 → 實價登錄比較標的 3 件。"),
    ("沒有地號也行", "填區段範圍文字，系統圍出區段並依 §18 選比準地。"),
    ("估價師從「改」開始", "推定值全部標示，不是從空白填起。"),
], image="onekey_form.png", cap="一鍵建案表單", size=15)

content_slide("入口 C：範例與其他可上傳的資料", "案件總覽", [
    ("範例一", "金山區 P002-00 地價區段，送審書表填載與系統核算相符。"),
    ("範例二", "同一案但含填載錯誤：看不符項、承辦裁決與意見書。"),
    ("範例三", "僅有年期、區段編號、區段範圍的勘查表，由圖資推算其餘欄位。"),
    ("還能上傳", "宗地個別因素清冊 xlsx、買賣實例 xlsx、評價基準明細表 PDF／CSV／JSON、地籍圖（GeoJSON／KML／GML／SHP zip）、地價區段圖。"),
    ("匯入規則", "依地號併入、只覆蓋有值欄位、對不到的回報。"),
], image="home_list.png", cap="案件清單：狀態、審查結果、比較價格、產出、最後操作、下一步", size=14)

# ───────────────────────────── 段落：① 輸入資料
section_slide("03", "① 輸入資料", "案件與地價區段／宗地條件與買賣實例／評價基準明細表")

content_slide("案件與地價區段", "① 輸入資料", [
    ("案件", "案號、基準日、估價師簽章欄、填寫日期、比準地地號、用地別、適用基準表。"),
    ("地價區段", "區段編號、範圍文字、勘查日期；範圍多邊形與比準地位置。"),
    ("位置與設施距離", "匯入地價區段圖、匯入地籍圖、補上送審書表 PDF、重新量測設施距離。"),
    ("替代方式", "沒有圖檔時：點圖推估街廓、人工標定設施，結果標示為草稿。"),
    ("依地號產生", "可選擇是否覆寫已填值。"),
], image="input_case.png", cap="案件與地價區段分頁", size=15)

content_slide("填寫結果清單：每個欄位從哪裡來", "① 輸入資料", [
    ("四種狀態", "資料（匯入或填載）、量測（圖資量出）、推定（系統規則）、空白（需人工填載）。"),
    ("來源與說明", "每列寫資料集名稱與推定理由，例如「最小外接矩形與面前道路平行之邊」。"),
    ("一眼看缺什麼", "頂端統計：資料 4、量測 39、推定 52、空白 12。"),
    ("推定門檻公開", "全部寫在 docs/07，讓人能質疑。"),
], image="fill_report.png", cap="一鍵建案後的填寫結果清單", size=15)

content_slide("宗地條件與買賣實例", "① 輸入資料", [
    ("比準地 19 欄", "面積、寬深、形狀、臨街、地勢、道路、接近條件、嫌惡設施、停車、分區、建蔽容積、禁限建。"),
    ("比較標的三欄並排", "與比準地逐欄對照；可匯入清冊與實例 xlsx，填好再匯入。"),
    ("實價登錄自動選取", "§17 蒐集期間、§19 同區段→同鄉鎮→鄰近鄉鎮；期間外參考案例需理由。"),
    ("含建物實例", "第四號公報成本法推定建物成本：每坪營造施工費 × 坪數 × 定額折舊 × 營造工程物價指數，標需確認。"),
    ("期日調整", "都市地價指數依日期內插；無地籍界線時依門牌定位、可點圖設定。"),
], image="input_parcels.png", cap="宗地條件與買賣實例分頁", size=14)

content_slide("評價基準明細表", "① 輸入資料", [
    ("內建", "金山商業用地區域／個別因素基準表（逐格核對）、示範住宅用地（非官方）。"),
    ("匯入", "地政局基準表 PDF／CSV／JSON → 自動解析成規則 JSON；細項對回內政部項目目錄。"),
    ("檢查", "超過內政部評價基準表上限只提醒；備註欄條件文字用文法解析。"),
    ("套用", "點名稱看細項與矩陣，「套用至本案」。"),
], image="table1_compare.png", cap="對照檢視：勘查表每格的判定條件與等級", size=15)

content_slide("勘查表推定規則（28 欄哪些能推）", "① 輸入資料", [
    ("土地使用管制", "都市計畫內外、使用分區、建蔽率容積率（土管要點）、禁限建（預設無）。"),
    ("交通", "主要道路與平均路寬（路網）、大型車站、站牌、交流道、道路闢建程度（計畫道路 × 現況路網）。"),
    ("自然", "排水（淹水潛勢 24h 350mm）、地勢（衛星測高高程）。"),
    ("設施", "市場、公園、觀光、停車場、電業、殯葬、廢棄物、污染源、百貨、金融、娛樂、飯店。"),
    ("工商", "店舖毗連狀態、顧客通行量（OSM 店舖密度）、商圈（清冊圍面）。"),
    ("停車方便性", "交通局路邊停車格 50 m 內，或面前道路寬 ≥ 8 m（系統門檻，非法規）。"),
], image="generated_sheet.png", cap="一鍵建案產出的地價區段勘查表", size=14)

# ───────────────────────────── 段落：② 產出書表
section_slide("04", "② 產出書表", "規則引擎／六頁書表／三張圖說／地圖")

# 價格鏈圖（深藍）
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
text(s, Inches(0.7), Inches(0.4), Inches(12), Inches(0.8), "規則引擎：等級 → 修正率 → 價格鏈", size=28, color=WHITE, bold=True)
chain = [("勘查表事實", "距離、寬度、面積…"), ("優劣等級", "基準表判定條件"), ("修正率", "矩陣查格"), ("小計／總修正數", "手冊 p.49"),
         ("區域因素調整", "帶入比較法調查估價表"), ("個別因素差異率", "手冊 p.52"), ("試算價格", "辦法 §17、§18"),
         ("權重", "絕對值加總排名 50/30/20"), ("比較價格", "手冊 p.53"), ("比準地地價", "辦法 §21 尾數")]
bw, bh = Inches(2.3), Inches(1.0)
for i, (t, b) in enumerate(chain):                     # 蛇行：第一列左→右，第二列右→左
    r, c = divmod(i, 5)
    col = c if r == 0 else 4 - c
    x = Inches(0.7) + col * Inches(2.5)
    y = Inches(1.6) + r * Inches(1.6)
    box(s, x, y, bw, bh, t, b, tsize=14, bsize=10)
    if c < 4:
        if r == 0:
            arrow(s, x + bw, y + bh // 2, x + bw + Inches(0.2), y + bh // 2)
        else:
            arrow(s, x, y + bh // 2, x - Inches(0.2), y + bh // 2)
xc = Inches(0.7) + 4 * Inches(2.5) + bw // 2
arrow(s, xc, Inches(1.6) + bh, xc, Inches(3.2), color=PINK)
bullets(s, Inches(0.7), Inches(4.6), Inches(12), Inches(2.3), [
    ("驗收 1", "地政局範本：表 5-2 每個等級、表 4 每個差異率、13.00%、比較價格 212,958 元/m² 全部重現。"),
    ("驗收 2", "作業手冊 p.100–102 官方算例。"),
    ("不寫死", "基準表、上限、量測方式都是 JSON；當天換區、換用地別不改程式。"),
], size=14, color=WHITE)
footer(s, dark=True)

content_slide("六頁書表預覽：照範本版面", "② 產出書表", [
    ("頁序", "地價區段勘查表、影響地價區域因素分析明細表、比較法調查估價表、地價區段略圖、地價使用分區圖、地價區段圖。"),
    ("同一份版面", "Excel、畫面預覽、PDF 都從同一張工作表格線畫出來。"),
    ("列印", "六頁 PDF，A4 直式與 A3 橫式混排不裁切。"),
    ("審查標記", "可疊上不符與需確認的格位標記。"),
], image="sheets_preview.png", cap="書表預覽第 1 頁", size=15)

content_slide("三張圖說", "② 產出書表", [
    ("地價區段略圖", "區段範圍、比準地、比較標的、道路、段籍圖底圖，比例尺 1:1800，估價師簽章欄。"),
    ("地價使用分區圖", "使用分區色塊與區段範圍。"),
    ("地價區段圖", "設施位置與量測路線。"),
    ("A3 橫式 PNG", "進 Excel 圖說工作表與意見書附圖。"),
], image="mapA_sketch.png", cap="地價區段略圖（上傳送審書表的案件）", size=15)

content_slide("地圖互動檢視", "② 產出書表", [
    ("三張圖切換", "區段略圖、使用分區圖、地價區段圖。"),
    ("點設施看距離線", "步行路徑或直線，與書表填載值對照。"),
    ("接近條件清單", "每筆標來源（送審書表抽取／量測）與量測方式。"),
    ("比較標的位置", "沒有地籍界線時可點圖設定。"),
], image="map_interactive.png", cap="地圖互動檢視", size=15)

# ───────────────────────────── 段落：③ 審查
section_slide("05", "③ 審查", "逐項比對／承辦裁決／審查意見書")

content_slide("逐項比對：每一列都有依據", "③ 審查", [
    ("七個審查重點", "i 勘查表 → vii 跨表抄填，對應作業手冊審查重點。"),
    ("每列欄位", "結果、書表、位置、估價單位填載、系統核算、說明、依據、追溯、承辦裁決。"),
    ("依據", "查估辦法條號或手冊頁碼，例如「手冊 p.49 (六)3(3)」。"),
    ("追溯", "「看基準表格位」跳到判定條件與矩陣格位。"),
    ("分組與篩選", "全案／各比較標的；僅不符、僅需確認、僅備註。"),
], image="mismatch_rows.png", cap="範例二：5 項不符、1 項需確認", size=14)

content_slide("需確認與不符分開", "③ 審查", [
    ("範本案結果", "全部相符＋1 項需確認。"),
    ("需確認的例子", "道路種類最大修正率 8% 超過內政部個別因素評價基準表上限 5%，是範本本身疑點，不判錯。"),
    ("推定值", "系統推定的距離、等級一律只列需確認。"),
    ("不符", "只有估價單位填載值與規則核算值不一致才列不符。"),
], image="review_confirm_row.png", cap="範例一：需確認列的說明與依據", size=15)

content_slide("承辦裁決與操作紀錄", "③ 審查", [
    ("兩種裁決", "接受填載（經審酌採估價單位之值，填理由）、維持不符（請估價單位補正）。"),
    ("寫進意見書", "裁決、理由、裁決人都進意見書逐條意見。"),
    ("操作紀錄", "時間、操作者、動作、內容；建案、重新產生、裁決、匯出全部留痕。"),
    ("產出過期", "輸入改動後產出標「已過期」，裁決對不到新不符項標過期。"),
], image="decisions_log.png", cap="承辦裁決欄與操作紀錄", size=15)

content_slide("審查意見書", "③ 審查", [
    ("結論", "相符／需確認／不符請補正後再送審。"),
    ("核算摘要", "各比較標的區域因素調整、個別因素合計、試算價格、權重；比準地比較價格與地價。"),
    ("逐條意見", "[F-001] 書表、格位、填載值、核算值、依據、承辦裁決（裁決人）。"),
    ("附件與落款", "三張圖說；落款用操作身分。"),
    ("輸出", "Word、PDF；語言模型潤飾預設關閉，開啟時守門（標籤齊、沒有新數字，否則退回原句）。"),
], image="opinion.png", cap="範例二的審查意見書", size=14)

# ───────────────────────────── 段落：④ 輸出
section_slide("06", "④ 輸出與案件管理", "一列多格式／案件生命週期")

content_slide("輸出", "④ 輸出", [
    ("下載全部", "一個 zip：書表、意見書、三張圖、清冊、實例。"),
    ("查估書表", "Excel 六張工作表（三表＋三圖）、PDF 照範本頁序。"),
    ("審查意見書", "Word、PDF。"),
    ("三張圖說", "PNG A3。"),
    ("可再匯入", "宗地個別因素清冊、買賣實例 xlsx 填好可再匯入。"),
], image="export.png", cap="輸出頁", size=15)

content_slide("案件生命週期", "④ 輸出", [
    ("狀態", "草稿 → 審查中 → 已完成，在案件列切換。"),
    ("輸入與產出時間", "輸入最後修改、產出最後產生；不一致標「產出已過期」，按「重新產生書表」。"),
    ("重置", "清空重填，或回到原始輸入（保留匯入的地籍圖與區段圖）。"),
    ("另存新案", "同一輸入試不同基準表。"),
    ("封存與復原", "清單勾「已封存」可復原。"),
], image="home_list.png", cap="案件清單與狀態", size=15)

# ───────────────────────────── 段落：技術與部署
section_slide("07", "技術與部署", "依「黑客松競賽環境規範與限制」")

# 架構圖
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
text(s, Inches(0.7), Inches(0.4), Inches(12), Inches(0.8), "系統架構", size=28, color=WHITE, bold=True)
box(s, Inches(0.7), Inches(1.5), Inches(3.4), Inches(1.6), "前端 Next.js", "書表預覽、地圖（Leaflet）、審查、\n輸出；一頁一主鍵", tsize=16, bsize=11)
box(s, Inches(4.9), Inches(1.5), Inches(3.6), Inches(1.6), "後端 FastAPI", "engine 規則引擎／spatial 空間／market 市場\n／report 報表／maps 圖說／adapters 匯入", tsize=16, bsize=11)
box(s, Inches(9.3), Inches(1.5), Inches(3.4), Inches(1.6), "Amazon Bedrock", "只做意見書潤飾與掃描件辨識\n（守門檢查；可切 mock）", fill=NAVY, line=PINK, tsize=16, bsize=11)
arrow(s, Inches(4.1), Inches(2.3), Inches(4.9), Inches(2.3))
arrow(s, Inches(8.5), Inches(2.3), Inches(9.3), Inches(2.3), color=PINK)
box(s, Inches(0.7), Inches(3.6), Inches(12.0), Inches(1.5), "本機資料層（不依賴外部 API）",
    "規則 JSON（基準表、上限、量測方式、土管要點、建物成本、物價指數）｜案件 JSON 與操作紀錄｜SQLite R-tree 全區圖資依案件範圍局部載入（路網、步行圖、設施、門牌、分區）｜實價登錄、地價指數、淹水潛勢、地籍圖｜底圖瓦片快取",
    tsize=16, bsize=11)
arrow(s, Inches(6.7), Inches(3.1), Inches(6.7), Inches(3.6))
bullets(s, Inches(0.7), Inches(5.4), Inches(12), Inches(1.6), [
    ("測試", "157 個自動測試：範本驗收、手冊算例、adapter、輸出、API。"),
    ("隔離不確定性", "當天資料格式不明只改 adapter；帳號權限不明只改 deploy。"),
], size=14, color=WHITE)
footer(s, dark=True)

# 部署圖
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
text(s, Inches(0.7), Inches(0.4), Inches(12), Inches(0.8), "AWS 部署（依競賽規範）", size=28, color=WHITE, bold=True)
box(s, Inches(0.7), Inches(1.5), Inches(2.4), Inches(1.3), "使用者", "評審／承辦瀏覽器\nHTTPS", fill=NAVY, line=PINK, tsize=15, bsize=11)
box(s, Inches(3.9), Inches(1.5), Inches(5.4), Inches(1.3), "EC2 標準型（us-east-1）", "Caddy 443 → Next.js 3000 ／ FastAPI 8000（本機）\nSecurity Group 只開 443／80", tsize=15, bsize=11)
box(s, Inches(10.1), Inches(1.5), Inches(2.6), Inches(1.3), "Amazon Bedrock", "< 1 RPS，只開通用到的模型", fill=NAVY, line=PINK, tsize=15, bsize=11)
arrow(s, Inches(3.1), Inches(2.15), Inches(3.9), Inches(2.15))
arrow(s, Inches(9.3), Inches(2.15), Inches(10.1), Inches(2.15), color=PINK)
box(s, Inches(3.9), Inches(3.2), Inches(5.4), Inches(1.0), "EBS 資料卷約 2 GB", "圖資、實價登錄、規則、案件；S3 若用只做私有備份", tsize=14, bsize=11)
arrow(s, Inches(6.6), Inches(2.8), Inches(6.6), Inches(3.2))
bullets(s, Inches(0.7), Inches(4.5), Inches(12), Inches(2.5), [
    ("區域", "us-east-1／us-west-2 指定區域。"),
    ("執行個體", "Standard 系列（規範允許 256 vCPU），不用 GPU、不做模型訓練。"),
    ("安全", "不建立對外全開的 Security Group；不開公開 S3；機密走環境變數與 .gitignore，repo 私有。"),
    ("資料", "不上傳個人資料；實價登錄為去識別化公開資料，操作身分用職稱。"),
    ("時程", "deploy/runbook_ec2.md 30 分鐘從零到可用，不用 docker。"),
], size=14, color=WHITE)
footer(s, dark=True)

content_slide("限制與後續", "技術與部署", [
    ("收益法", "查估辦法 §14 未實作（實價登錄無收益資料），列人工填寫。"),
    ("樓層別效用比率", "第四號公報無表，區分所有建物由估價師填。"),
    ("地籍圖", "現用匯入圖檔或預載；正式版需國土測繪中心地籍 API（地政局名義申請）。"),
    ("土管要點", "48 個計畫區自動抽取，8 個抓不到表退回施行細則附表一，多表不一致標需人工核對。"),
    ("推定門檻", "勘查表推定規則為系統自訂，待地政局確認後調整。"),
    ("底圖", "國土測繪中心瓦片在境外主機的連線需確認；金山一帶已快取可離線。"),
], layout="text", size=15)

# ───────────────────────────── 30 結語
s = prs.slides.add_slide(BLANK)
rect(s, 0, 0, W, H, NAVY)
text(s, Inches(0.7), Inches(0.4), Inches(12), Inches(0.8), "Demo 與結語", size=28, color=WHITE, bold=True)
text(s, Inches(0.7), Inches(1.15), Inches(12), Inches(0.6), "估價單位送來什麼就逐格核算；沒送也能先產一版；每個數字都能點回法源。", size=18, color=PINK)
for i, (t, img, cap_) in enumerate([("場景一　送審書表 → 逐格核算", "review_pass.png", "上傳 PDF，10 秒進審查"),
                                    ("場景二　填載錯誤 → 裁決 → 意見書", "opinion.png", "5 項不符，承辦裁決寫進意見書"),
                                    ("場景三　地號 → 一鍵產出", "fill_report.png", "30 秒產出勘查表與比較標的")]):
    x = Inches(0.7) + i * Inches(4.15)
    text(s, x, Inches(1.9), Inches(3.9), Inches(0.5), t, size=15, color=CYAN, bold=True)
    picture(s, img, x, Inches(2.4), Inches(3.9), Inches(3.0), border=False)
    text(s, x, Inches(5.45), Inches(3.9), Inches(0.4), cap_, size=12, color=PINK)
qr = rect(s, W - Inches(2.2), Inches(5.6), Inches(1.5), Inches(1.5), NAVY_L, line=CYAN)
text(s, W - Inches(2.2), Inches(6.05), Inches(1.5), Inches(0.6), "QR code\n（部署網址）", size=11, color=CYAN, align=PP_ALIGN.CENTER)
text(s, Inches(0.7), Inches(6.2), Inches(9), Inches(0.5), "隊名 AI城市起風　吳昭奇・洪湛閎・丁家麒", size=14, color=WHITE)
footer(s, dark=True)

prs.save(OUT)
print("saved", OUT, "slides", len(prs.slides))
