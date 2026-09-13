"""
審查模式：拿估價師填的表（submitted）和引擎算的表（computed）比對，產出 findings。

每條 finding 對應作業手冊 p.11-13 審查重點的條號：
  iii  勘查表細項等級是否依基準明細表填列
  v    買賣實例交易日期在蒐集期間內（查估辦法 §17）；總價與實價登錄相符；正常單價計算（§13）
  vi   表5 等級須與勘查表一致、修正百分比須依基準明細表
  vii  表4 區域因素調整率 = 表5 總修正數；個別因素差異率依基準明細表；權重是否合邏輯（技術規則 §27）
  x    宗地條件與清冊一致；尾數計算
  p.53 (十二) 比準地比較價格四捨五入至個位數

severity: error（數字/等級不符）、warn（推定規則、四捨五入 ±1、需人工確認）、info
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .rules import RuleSet
from .tables import Table4, Table5, date_adjustment_from_index

PRICE_TOL = 1.0      # 元；範本中間值帶小數再四捨五入，容許 ±1
PCT_TOL = 0.005      # 百分點


@dataclass
class Finding:
    severity: str          # error | warn | info
    checklist: str         # 手冊審查重點條號
    table: str             # "表5" | "表4" | "表1"
    location: str          # 例如 "比較標的1 / 14 面前道路寬度"
    submitted: str | None
    computed: str | None
    message: str
    basis: str | None = None   # 依據：基準表哪一格
    rule_id: str | None = None  # 定位：表5 細項 id（R2-1）／G1 小計／TOTAL
    item_no: int | None = None  # 定位：表4 欄位編號；0=價格鏈上段、99=合計以下、100=比準地比較價格
    comp_no: int | None = None  # 定位：比較標的
    kind: str = "mismatch"      # mismatch=填載與核算不符；gap=資料缺口（沒有可比對的填載）；inferred=依系統推定值核算（降為需確認）

    def to_dict(self) -> dict:
        return asdict(self)


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _num(v) -> float | None:
    """送審表抽取值 → 數字；None／空白／「-」／「免」等非數字 → None（呼叫端決定要不要出 warn），絕不丟例外。"""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(",", "").replace("％", "").replace("%", "")
    if t in ("", "-", "—", "－"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _unparsable(v) -> bool:
    """有填但不是數字（例如「免」「無」）。"""
    return v not in (None, "", "-", "—", "－") and _num(v) is None


def verify_table5(computed: Table5, submitted: dict, comp_no: int | None = None) -> list[Finding]:
    """
    submitted 結構（來自表5抽取）：
      {"levels": {rule_id: {"subject": "優", "comparable": "劣", "pct": 0.0}}, "group_subtotals": {"1": 0.0,...}, "total_pct": 0.0}
    """
    out: list[Finding] = []
    sub_levels = submitted.get("levels", {})
    for row in computed.rows:
        s = sub_levels.get(row.rule_id)
        if s is None:
            continue
        loc = f"比較標的區段 {computed.comparable_section} / {row.name}"
        if row.subject_level and s.get("subject") and s["subject"] != row.subject_level:
            out.append(Finding("error", "vi", "表5", loc, s["subject"], row.subject_level,
                               "比準地區段優劣等級與勘查表事實對照基準表結果不符", f"{row.rule_id} 判定條件", rule_id=row.rule_id, comp_no=comp_no))
        if row.comparable_level and s.get("comparable") and s["comparable"] != row.comparable_level:
            out.append(Finding("error", "vi", "表5", loc, s["comparable"], row.comparable_level,
                               "比較標的區段優劣等級與勘查表事實對照基準表結果不符", f"{row.rule_id} 判定條件", rule_id=row.rule_id, comp_no=comp_no))
        sp = _num(s.get("pct"))
        if _unparsable(s.get("pct")):
            out.append(Finding("warn", "vi", "表5", loc, str(s.get("pct")), _fmt(row.pct), "修正百分比填載值無法解析為數字，請人工核對", rule_id=row.rule_id, comp_no=comp_no))
        elif row.pct is not None and sp is not None and abs(sp - row.pct) > PCT_TOL:
            out.append(Finding("error", "vi", "表5", loc, _fmt(sp), _fmt(row.pct),
                               "修正百分比與基準表矩陣不符", f"{row.rule_id} 矩陣[{row.subject_level}][{row.comparable_level}]", rule_id=row.rule_id, comp_no=comp_no))
        for i in row.issues:
            out.append(Finding("warn", "iii", "表5", loc, None, None, i, rule_id=row.rule_id, comp_no=comp_no))
    for g, v in computed.group_subtotals.items():
        sv = _num(submitted.get("group_subtotals", {}).get(str(g)))
        if sv is not None and abs(sv - v) > PCT_TOL:
            out.append(Finding("error", "vi", "表5", f"百分比小計 ({g})", _fmt(sv), _fmt(v), "小計加總錯誤", "手冊 p.49 (六)3(3)、表式：小計＝該主要項目各細項修正百分比之和", rule_id=f"G{g}", comp_no=comp_no))
    st = _num(submitted.get("total_pct"))
    if st is not None and abs(st - computed.total_pct) > PCT_TOL:
        out.append(Finding("error", "vi", "表5", "影響地價區域因素總修正數", _fmt(st), _fmt(computed.total_pct), "總修正數加總錯誤", "手冊 p.49 (六)3(3)(4)：總修正數＝各主要項目小計之和，帶入比較法調查估價表區域因素調整", rule_id="TOTAL", comp_no=comp_no))
    return out


def verify_table4(computed: Table4, submitted: dict) -> list[Finding]:
    """
    submitted 結構（來自表4抽取）：
      {"comparables": {comp_no: {"date_adjustment_pct":2.0, "price_at_valuation_date":188459, "regional_adjustment_pct":0.0,
                                 "individual": {"7":0.0,...}, "individual_total_pct":13.0, "abs_sum_pct":15.0,
                                 "similarity":"普通", "weight_pct":100, "trial_price":212958}},
       "subject_comparison_price": 212958}
    """
    out: list[Finding] = []
    weights: list[tuple[int, float | None, float]] = []        # (comp_no, 估價師權重, 絕對值加總)

    def chk(key: str, label: str, comp_val: float | None, item_no: int, comp_no: int, msg: str, basis: str | None = None, tol: float = PCT_TOL) -> None:
        if key not in s:
            return
        v = _num(s[key])
        if _unparsable(s[key]):
            out.append(Finding("warn", "vii", "表4", f"{pre} / {label}", str(s[key]), _fmt(comp_val), f"{label}填載值無法解析為數字，請人工核對", item_no=item_no, comp_no=comp_no))
        elif v is not None and comp_val is not None and abs(v - comp_val) > tol:
            out.append(Finding("error", "vii", "表4", f"{pre} / {label}", _fmt(v), _fmt(comp_val), msg, basis, item_no=item_no, comp_no=comp_no))

    for comp in computed.comparables:
        s = submitted.get("comparables", {}).get(comp.comp_no) or submitted.get("comparables", {}).get(str(comp.comp_no))
        if not s:
            continue
        pre = f"比較標的{comp.comp_no}"
        chk("regional_adjustment_pct", "區域因素調整百分率", comp.regional_adjustment_pct, 0, comp.comp_no,
            "與影響地價區域因素分析明細表之總修正數不符（跨表抄填）", "影響地價區域因素分析明細表 總修正數")
        chk("price_at_valuation_date", "調整至估價基準日單價", comp.price_at_valuation_date, 0, comp.comp_no,
            "土地正常單價×(1+期日調整率) 計算不符", tol=PRICE_TOL)
        sub_ind = s.get("individual", {})
        ind_blank = not any(v not in (None, "", "—") for v in (sub_ind or {}).values())   # 個別因素整欄空白＝待填，不是估價師選擇不修正
        for row in comp.rows:
            sv = sub_ind.get(str(row.item_no))
            loc = f"{pre} / {row.item_no} {row.name}"
            if row.pct is None:
                if sv not in (None, "-", "", "—"):
                    out.append(Finding("warn", "vii", "表4", loc, _fmt(sv), "-", "引擎判為免修正，估價師填了差異率；請確認並於備註敘明", item_no=row.item_no, comp_no=comp.comp_no))
                continue
            if sv in (None, "-", "", "—"):
                if ind_blank:
                    continue
                if abs(row.pct) > PCT_TOL:      # 核算 0% 時填「-」視為相符，不列
                    out.append(Finding("warn", "vii", "表4", loc, "-", _fmt(row.pct),
                                       f"估價師填「-」未修正此項，但依基準表核算差異率為 {_fmt(row.pct)}%（比準地{row.subject_level or '—'}／比較標的{row.comparable_level or '—'}）",
                                       f"item {row.item_no} 矩陣[{row.subject_level}][{row.comparable_level}]", item_no=row.item_no, comp_no=comp.comp_no))
                continue
            svn = _num(sv)
            if svn is None:
                out.append(Finding("warn", "vii", "表4", loc, str(sv), _fmt(row.pct), "差異率填載值無法解析為數字，請人工核對", item_no=row.item_no, comp_no=comp.comp_no))
                continue
            if abs(svn - row.pct) > PCT_TOL:
                out.append(Finding("error", "vii", "表4", loc, _fmt(svn), _fmt(row.pct),
                                   "差異率與個別因素基準表矩陣不符",
                                   f"item {row.item_no} 矩陣[{row.subject_level}][{row.comparable_level}]", item_no=row.item_no, comp_no=comp.comp_no))
            for i in row.issues:
                out.append(Finding("warn", "x", "表4", loc, None, None, i, item_no=row.item_no, comp_no=comp.comp_no))
        chk("individual_total_pct", "合計", comp.individual_total_pct, 99, comp.comp_no, "個別因素合計加總錯誤")
        chk("abs_sum_pct", "調整百分率絕對值加總", comp.abs_sum_pct, 99, comp.comp_no, "絕對值加總錯誤")
        if s.get("similarity") and comp.similarity and s["similarity"] != comp.similarity:
            out.append(Finding("warn", "vii", "表4", f"{pre} / 價格形成因素相近程度", s["similarity"], comp.similarity, "與絕對值加總排名不一致（手冊 p.53 範例）", item_no=99, comp_no=comp.comp_no))
        chk("trial_price", "試算價格", comp.trial_price, 99, comp.comp_no, "調整至基準日單價×(1+區域)×(1+個別) 計算不符", tol=PRICE_TOL)
        if "weight_pct" in s:
            if _unparsable(s["weight_pct"]):
                out.append(Finding("warn", "vii", "表4", f"{pre} / 比較標的權重", str(s["weight_pct"]), None, "權重填載值無法解析為數字，請人工核對", item_no=99, comp_no=comp.comp_no))
            weights.append((comp.comp_no, _num(s["weight_pct"]), comp.abs_sum_pct))
    # 權重：合計須為 100%；權重高低應與絕對值加總排名一致（手冊 p.53 (十一)、不動產估價技術規則 §27）
    given = [(n, w, a) for n, w, a in weights if w is not None]
    if given and len(given) == len(computed.comparables):
        total = sum(w for _n, w, _a in given)
        if abs(total - 100.0) > 0.01:
            out.append(Finding("error", "vii", "表4", "比較標的權重合計", _fmt(total), "100.00", "各比較標的權重合計不等於 100%，比準地比較價格無法成立",
                               "手冊 p.53 (十一)、不動產估價技術規則 §27", item_no=99))
        ranked = sorted(given, key=lambda x: x[2])                     # 絕對值加總小者相近程度較高，權重應較大
        if any(ranked[i][1] < ranked[i + 1][1] - 1e-6 for i in range(len(ranked) - 1)):
            out.append(Finding("warn", "vii", "表4", "比較標的權重", "、".join(f"標的{n} {w:g}%" for n, w, _a in given), "依絕對值加總由小到大遞減",
                               "權重高低與調整百分率絕對值加總之排名不一致；技術規則 §27 另容許考量資料可信度，請於備註敘明理由", "手冊 p.53 (十一)、技術規則 §27", item_no=99))
    sp = _num(submitted.get("subject_comparison_price"))
    if _unparsable(submitted.get("subject_comparison_price")):
        out.append(Finding("warn", "p.53(十二)", "表4", "比準地比較價格", str(submitted.get("subject_comparison_price")), _fmt(computed.subject_comparison_price), "比準地比較價格填載值無法解析為數字，請人工核對", item_no=100))
    elif sp is not None and computed.subject_comparison_price is not None and abs(sp - computed.subject_comparison_price) > PRICE_TOL:
        out.append(Finding("error", "p.53(十二)", "表4", "比準地比較價格", _fmt(sp), _fmt(computed.subject_comparison_price), "加權平均或尾數四捨五入不符", item_no=100))
    return out


# ---------------------------------------------------------------- 基準明細表 vs 內政部最大影響範圍（手冊 p.49–50 (七)3、p.52–53 (八)1、附件24/25 p.149–154）


def verify_rulesets(regional: RuleSet | None, individual: RuleSet | None) -> list[Finding]:
    """
    每次核算都檢查案件用的基準明細表 max_pct 是否超過內政部附件24／25 上限。
    超過者列 warn「需確認」不判錯（例如金山商業個別因素表 13 道路種類 8% > 5%，疑點 D）；
    上限表沒有該用地別或對不到項目名稱時略過。
    """
    from app.adapters.rules_table import _moi_lookup, load_moi
    out: list[Finding] = []
    moi = load_moi()
    if regional is not None:
        table = (moi["regional"].get(regional.land_use or "") or {})
        if table:
            cols, items = table["columns"], table["items"]
            best: tuple[str, list[tuple]] | None = None
            for ci, col in enumerate(cols):
                viol = []
                for r in regional.rules:
                    lim = _moi_lookup(items, r.name)
                    if lim is not None and lim[ci] is not None and r.max_pct > lim[ci] + 1e-6:
                        viol.append((r, lim[ci]))
                if best is None or len(viol) <= len(best[1]):   # 違規最少的欄當作該表的用地細類，同分取較嚴的欄
                    best = (col, viol)
            if best:
                for r, lim in best[1]:
                    out.append(Finding("warn", "vi", "表5", r.name, _fmt(float(r.max_pct)), _fmt(float(lim)),
                                       f"基準明細表最大修正率超過內政部區域因素評價基準表「{best[0]}」上限，需確認（不判錯）",
                                       "手冊 p.49–50 (七)3、附件24（手冊 p.149–153）", rule_id=r.id))
    if individual is not None:
        table = moi["individual"]
        if individual.land_use in table["columns"]:
            ci = table["columns"].index(individual.land_use)
            for r in individual.rules:
                lim = _moi_lookup(table["items"], f"{r.item_no}.{r.name}")
                if lim is not None and lim[ci] is not None and r.max_pct > lim[ci] + 1e-6:
                    out.append(Finding("warn", "vii", "表4", f"{r.item_no} {r.name}", _fmt(float(r.max_pct)), _fmt(float(lim[ci])),
                                       f"基準明細表最大修正率超過內政部個別因素評價基準表「{individual.land_use}」上限，需確認（不判錯）",
                                       "手冊 p.52–53 (八)1、附件25（手冊 p.154）", item_no=r.item_no))
    return out


# ---------------------------------------------------------------- 買賣實例（審查重點 v；查估辦法 §13、§17、§19）

INDEX_PCT_TOL = 0.05     # 期日調整率與指數比的容差（百分點）；範本 2.037% 填 2.00%，估價師取整需於備註敘明


def _roc(s: str) -> tuple[int, int, int] | None:
    import re
    if not s:
        return None
    t = str(s).replace("年", ".").replace("月", ".").replace("日", "").replace("/", ".").replace("-", ".")
    m = re.match(r"^\s*(\d{2,3})\.(\d{1,2})\.(\d{1,2})\s*$", t) or re.match(r"^\s*(\d{3})(\d{2})(\d{2})\s*$", t)
    if not m:
        return None
    d = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    try:
        _ord(d)                                  # 114.13.01、114.02.30 之類 → 視為無法解析，交給呼叫端出 warn
    except ValueError:
        return None
    return d


def _ord(d: tuple[int, int, int]) -> int:
    import datetime
    y, m, dd = d
    return datetime.date(y + 1911, m, dd).toordinal()


def _year_before(d: tuple[int, int, int]) -> int:
    """估價基準日前一年（ordinal）；2/29 基準日退到前一年 2/28（查估辦法 §17 第3項放寬上限）。"""
    import datetime
    y, m, dd = d
    try:
        return datetime.date(y + 1910, m, dd).toordinal()
    except ValueError:
        return datetime.date(y + 1910, m, 28).toordinal()


def collection_window(valuation_date: str) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
    """
    查估辦法 §17 第2項：估價基準日 9/1 → 案例蒐集期間當年 3/2～9/1；3/1 → 前一年 9/2～當年 3/1。
    其他基準日 → None（需人工確認）。
    """
    v = _roc(valuation_date)
    if not v:
        return None
    y, m, d = v
    if (m, d) == (9, 1):
        return (y, 3, 2), (y, 9, 1)
    if (m, d) == (3, 1):
        return (y - 1, 9, 2), (y, 3, 1)
    return None


_WIDEN_RE = re.compile(r"第\s*17\s*條\s*第\s*3\s*項|§\s*17\s*第\s*3\s*項|擴大[^。]{0,20}蒐集期間")


def _notes_text(data_or_case: dict | None) -> str:
    """案件裡所有備註文字（全案、比準地、各比較標的；表5 全案說明）串成一段，供核對「是否已於備註敘明」。"""
    out: list[str] = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    d = data_or_case or {}
    walk(d.get("notes"))
    walk((d.get("case") or {}).get("notes"))
    for c in d.get("comparables") or []:
        walk(c.get("note"))
    return "\n".join(out)


def verify_comparables(case: dict, comparables: list[dict], notes_text: str = "") -> list[Finding]:
    out: list[Finding] = []
    widen_stated = bool(_WIDEN_RE.search(notes_text or "") or _WIDEN_RE.search(_notes_text({"case": case})))
    n = len(comparables)
    if n == 0:
        out.append(Finding("error", "vii", "表4", "比較標的", "0", "1~3", "未選取比較標的", "查估辦法 §19 第1項第1款", kind="gap"))
    elif n > 3:
        out.append(Finding("warn", "vii", "表4", "比較標的", str(n), "1~3", "比較標的超過三件，與查估辦法 §19「一至三件」不符，請確認", "查估辦法 §19 第1項第1款"))
    vdate = case.get("valuation_date")
    win = collection_window(vdate) if vdate else None
    vd = _roc(vdate) if vdate else None
    if vdate and win is None:
        out.append(Finding("warn", "v", "表4", "估價基準日", str(vdate), "9/1 或 3/1",
                           "估價基準日非 9 月 1 日或 3 月 1 日，案例蒐集期間依查估辦法 §17 原則需人工確認", "查估辦法 §17 第2項"))
    for c in comparables:
        pre = f"比較標的{c.get('comp_no')}"
        td = _roc(c.get("transaction_date"))
        if td and vd:
            sel = c.get("selection") or {}
            ref_note = f"；本件為蒐集期間外參考案例（手冊 p.77 問答四），理由：{sel.get('reason')}" if sel.get("out_of_window") and sel.get("reason") else ""
            if _ord(td) > _ord(vd):
                out.append(Finding("error", "v", "表4", f"{pre} / 交易日期", c.get("transaction_date"), f"≤ {vdate}",
                                   "交易日期晚於估價基準日" + ref_note, "查估辦法 §17"))
            elif win and not (_ord(win[0]) <= _ord(td) <= _ord(win[1])):
                if _ord(td) >= _year_before(vd):
                    rng = f"{win[0][0]}.{win[0][1]:02d}.{win[0][2]:02d}～{win[1][0]}.{win[1][1]:02d}.{win[1][2]:02d}"
                    if widen_stated:
                        out.append(Finding("info", "v", "表4", f"{pre} / 交易日期", c.get("transaction_date"), rng,
                                           "交易日期在原則蒐集期間外、估價基準日前一年內；備註已敘明依查估辦法 §17 第3項擴大蒐集期間之理由",
                                           "查估辦法 §17 第2、3項"))
                    else:
                        out.append(Finding("warn", "v", "表4", f"{pre} / 交易日期", c.get("transaction_date"), rng,
                                           "交易日期在原則蒐集期間外、估價基準日前一年內：依查估辦法 §17 第3項放寬者，應於備註敘明無適當實例之理由",
                                           "查估辦法 §17 第2、3項"))
                else:
                    out.append(Finding("error", "v", "表4", f"{pre} / 交易日期", c.get("transaction_date"), "估價基準日前一年內",
                                       "交易日期超過估價基準日前一年，逾查估辦法 §17 放寬上限" + ref_note, "查估辦法 §17 第3項"))
        elif not td:
            out.append(Finding("warn", "v", "表4", f"{pre} / 交易日期", str(c.get("transaction_date")), None, "交易日期缺漏或格式無法解析"))
        elif not vd:
            out.append(Finding("warn", "v", "表4", "估價基準日", str(vdate), None, "估價基準日格式無法解析（民國年.月.日），無法核對蒐集期間"))
        da = c.get("date_adjustment") or {}
        if _num(da.get("pct")) is not None and _num(da.get("index_at_valuation")) and _num(da.get("index_at_transaction")):
            calc = date_adjustment_from_index(_num(da["index_at_valuation"]), _num(da["index_at_transaction"]))
            if abs(calc - _num(da["pct"])) > INDEX_PCT_TOL:
                out.append(Finding("warn", "v", "表4", f"{pre} / 調整百分率", _fmt(_num(da["pct"])), _fmt(calc),
                                   "期日調整率與地價指數比計算值不符；取整或採其他指數者應於備註敘明", "手冊 p.50 (四)、問答八"))
        src = c.get("source") or {}
        if _num(src.get("price_total")) and _num(c.get("area_m2")) and _num(c.get("normal_unit_price")):
            calc_unit = _num(src["price_total"]) / _num(c["area_m2"])
            if abs(calc_unit - _num(c["normal_unit_price"])) > 1.0:
                out.append(Finding("info", "v", "表4", f"{pre} / 土地正常單價", _fmt(_num(c["normal_unit_price"])), _fmt(calc_unit),
                                   "正常單價 ≠ 總價÷面積：若地上有建物須依 §13 第3、4款扣除建物成本，或屬特殊情況依 §7、§8 修正，請對照買賣實例調查估價表",
                                   "查估辦法 §13"))
    return out


# ---------------------------------------------------------------- 推定值不判錯（約束：系統推定的觀測值只能出「需確認」）

INFER_PARCEL_KEY = {"front_road_width_m": "front_road"}     # 清冊欄位 → parcel.derived 的鍵（其餘同名）


def inferred_keys(data: dict, regional: RuleSet, individual: RuleSet) -> set[tuple]:
    """哪些 (表, 比較標的, 細項) 的核算觀測值來自系統推定：
    表4：比準地或該比較標的的 parcel.derived 有該欄位（面積、寬深、形狀、臨街、地勢、道路、路寬、停車、分區、建蔽、容積、禁限建）；
    表5：比準地區段或該比較標的區段的 survey_provenance.suggestions 有該欄位，或 filled 內非設施距離的欄位（分區、路寬、闢建、排水、地勢、店舖）。
    設施距離是依設施資料庫與路網「量測」，不算推定。"""
    keys: set[tuple] = set()
    subject = data.get("subject_parcel") or {}
    comps = data.get("comparables") or []
    sections = data.get("sections") or {}

    def parcel_inferred(p: dict) -> set[str]:
        return set((p.get("derived") or {}).keys())

    def section_inferred(sec: dict | None) -> set[str]:
        if not sec:
            return set()
        prov = sec.get("survey_provenance") or {}
        dist = {r.survey_field for r in regional.rules if r.criteria.get("type") == "distance"}
        return set((prov.get("suggestions") or {}).keys()) | {f for f in (prov.get("filled") or []) if f not in dist}

    subj_p = parcel_inferred(subject)
    subj_s = section_inferred(sections.get(subject.get("section_id") or ""))
    for c in comps:
        n = c.get("comp_no")
        cp = parcel_inferred(c) | subj_p
        for r in individual.rules:
            if r.item_no and r.parcel_field and INFER_PARCEL_KEY.get(r.parcel_field, r.parcel_field) in cp:
                keys.add(("表4", n, r.item_no))
        cs = section_inferred(sections.get(c.get("section_id") or "")) | subj_s
        for r in regional.rules:
            if r.survey_field and r.survey_field in cs:
                keys.add(("表5", n, r.id))
    return keys


def soften_inferred(findings: list[Finding], keys: set[tuple]) -> list[Finding]:
    """推定值算出的等級／差異率／修正率與填載不同 → 降為 warn，並註明是依推定值核算。"""
    for f in findings:
        if f.severity != "error":
            continue
        k = ("表4", f.comp_no, f.item_no) if f.table == "表4" else ("表5", f.comp_no, f.rule_id) if f.table == "表5" else None
        if k in keys:
            f.severity, f.kind = "warn", "inferred"
            f.message = "依系統推定值核算，需人工確認：" + f.message
    return findings


def verify_admin_consistency(data: dict) -> list[Finding]:
    """宗地建蔽率／容積率（表4 第 23、24 項）與所在區段勘查表土地使用管制欄不一致 → 需確認。
    同一分區兩者理應相同；不同時常見原因是計畫書但書（面臨道路未達 N 公尺者容積率上限較低）或勘查表抄錯。法定值定義：手冊 p.51 (六)4；行政條件：查估辦法 §20。"""
    out: list[Finding] = []
    sections = data.get("sections") or {}
    district = (data.get("case") or {}).get("district") or ""
    try:
        from app.spatial.admin import plan_provisos
        provisos = plan_provisos(district)
    except Exception:  # noqa: BLE001
        provisos = []
    parcels: list[tuple[str, int | None, dict]] = [("比準地", None, data.get("subject_parcel") or {})]
    parcels += [(f"比較標的{c.get('comp_no')}", c.get("comp_no"), c) for c in (data.get("comparables") or [])]
    for label, comp_no, p in parcels:
        lc = ((sections.get(p.get("section_id") or "") or {}).get("survey") or {}).get("land_control") or {}
        derived = p.get("derived") or {}
        for field, key, item_no, name in (("bcr_pct", "bcr", 23, "建蔽率(%)"), ("far_pct", "far", 24, "容積率(%)")):
            pv, sv = _num(p.get(field)), _num(lc.get(key))
            if pv is None or sv is None or abs(pv - sv) <= PCT_TOL:
                continue
            msg = f"宗地{name[:3]} {pv:g}% 與所在區段（{p.get('section_id') or '—'}）勘查表 {sv:g}% 不一致，請確認何者為該宗地之法定值"
            hint = "；".join(x.get("note", "") for x in provisos if key == "far" and (p.get("zoning") or "").split(":")[-1] in (x.get("zones") or []))
            if hint:
                msg += f"（計畫書但書可能為差異原因：{hint[:80]}…）"
            elif derived.get(field, {}).get("note"):
                msg += f"（宗地值來源：{str(derived[field].get('source', ''))[:40]}）"
            out.append(Finding("warn", "vii", "表4", f"{label} / {item_no} {name}", _fmt(sv), _fmt(pv), msg,
                               "手冊 p.51 (六)4 法定容積率；查估辦法 §20 行政條件", item_no=item_no, comp_no=comp_no,
                               kind="inferred" if field in derived else "mismatch"))
    return out


def verify_income(data: dict, result: dict) -> list[Finding]:
    """收益法（選用）審查：手冊 p.12 審查重點 viii（收益實例租金與實價登錄相符、推估過程、總費用、土地及建物收益資本化率符合技術規則 §43）、
    ix（比準地地價估計表之權重與決定理由、尾數）；查估辦法 §7、§8（特殊情況調整）、§17（租金形成日期與蒐集期間）。"""
    res = result.get("income")
    if not res:
        return []
    out: list[Finding] = []
    exs = (data.get("income") or {}).get("examples") or []
    tbl = "表2"
    if not exs:
        out.append(Finding("warn", "viii", tbl, "收益實例", "0", "3", "收益法已啟用但未選收益實例（手冊 p.37 (五)1(1)：以蒐集 3 件為原則）", "查估辦法 §14；手冊 p.37", kind="gap"))
    elif len(exs) != 3:
        out.append(Finding("info", "viii", tbl, "收益實例", str(len(exs)), "3", f"收益實例 {len(exs)} 件；手冊以蒐集 3 件為原則，不足者宜於備註敘明", "手冊 p.37 (五)1(1)"))
    vdate = (data.get("case") or {}).get("valuation_date") or ""
    win = collection_window(vdate) if vdate else None
    vd = _roc(vdate) if vdate else None
    widen = bool(_WIDEN_RE.search(_notes_text(data)))
    rent_idx: dict | None = None
    for ex in exs:
        pre = f"收益實例{ex.get('example_no')}"
        td = _roc(ex.get("rent_date"))
        if td and vd:
            if _ord(td) > _ord(vd) or _ord(td) < _year_before(vd):
                out.append(Finding("error", "viii", tbl, f"{pre} / 租金形成日期", str(ex.get("rent_date")), "估價基準日前一年內",
                                   "租金形成日期逾查估辦法 §17 第3項放寬上限（估價基準日前一年內）或晚於估價基準日", "查估辦法 §17 第2、3項"))
            elif win and not (_ord(win[0]) <= _ord(td) <= _ord(win[1])) and not widen:
                out.append(Finding("warn", "viii", tbl, f"{pre} / 租金形成日期", str(ex.get("rent_date")), None,
                                   "租金形成日期在原則蒐集期間外、估價基準日前一年內：依查估辦法 §17 第3項放寬者，應於備註敘明無適當實例之理由", "查估辦法 §17 第2、3項"))
        if ex.get("flags") and not float(ex.get("situation_pct") or 0):
            out.append(Finding("warn", "viii", tbl, f"{pre} / 情況調整", "0", None,
                               f"收益實例備註顯示特殊情況（{'；'.join(ex['flags'])[:60]}），未作情況調整；請依查估辦法 §7、§8 調整並於修正說明欄敘明", "查估辦法 §7、§8；手冊 p.38 (8)ii"))
        if ex.get("lvr_id"):
            if rent_idx is None:
                try:
                    from app.market.rent import load_rent
                    rent_idx = {r["id"]: r for r in load_rent().get("records", [])}
                except Exception:  # noqa: BLE001 - 租賃資料缺檔不擋審查
                    rent_idx = {}
            rr = rent_idx.get(ex["lvr_id"])
            tot, ref = _num(ex.get("total_rent")), (rr or {}).get("rent_ex_park") or (rr or {}).get("total_rent")
            if rr and tot is not None and ref and abs(tot - float(ref)) > 1:
                out.append(Finding("warn", "viii", tbl, f"{pre} / 總租金", _fmt(tot), _fmt(float(ref)),
                                   "收益實例租金與實價登錄不符；實際成交案例之收益面積與租金應與實價登錄相符，有調整者應於修正說明欄敘明", "手冊 p.12 審查重點 viii"))
    lc, bc, dep = res.get("land_cap_rate_pct"), res.get("building_cap_rate_pct"), res.get("deposit_rate_pct")
    if lc is not None and dep is not None and lc < dep:
        out.append(Finding("warn", "viii", tbl, "土地收益資本化率", _fmt(float(lc)), f"≥ {dep}",
                           "土地收益資本化率低於一年期定存利率；技術規則 §43 第1款風險溢酬法以定存等為基準加計風險，請確認決定理由", "技術規則 §43；手冊 p.12 審查重點 viii"))
    if lc is not None and bc is not None and bc <= lc:
        out.append(Finding("warn", "viii", tbl, "建物收益資本化率", _fmt(float(bc)), f"> {lc}",
                           "建物收益資本化率未高於土地收益資本化率（建物風險高於土地，宜高於）", "手冊 p.41 (七)2；技術規則 §43"))
    for s in res.get("issues") or []:
        out.append(Finding("info", "viii", tbl, "收益法", None, None, s, "查估辦法 §14；手冊 p.37～41", kind="gap"))
    for s in (result.get("land_price_decision") or {}).get("issues") or []:
        out.append(Finding("warn" if "理由" in s else "info", "ix", "表14", "比準地地價估計表", None, None, s, "手冊 p.8 五(二)3、4；p.12 審查重點 ix"))
    return out


def collect_findings(regional: RuleSet, individual: RuleSet, data: dict, result: dict,
                     submitted_table5: dict | None, submitted_table4: dict | None) -> list[dict]:
    """一案的全部審查結果（各端點共用）：比較標的與蒐集期間 → 基準表上限 → 表5／表4 逐格比對 → 推定值降級 → 無送審書表時 error 一律標資料缺口。"""
    findings: list[Finding] = list(verify_comparables(data["case"], data.get("comparables") or [], _notes_text(data))) + list(verify_rulesets(regional, individual))
    t5s = submitted_table5 or {}
    for comp_no, t5 in result["table5"].items():
        sub = t5s.get(comp_no) or t5s.get(str(comp_no))
        if sub:
            findings += verify_table5(t5, sub, comp_no)
    if submitted_table4:
        findings += verify_table4(result["table4"], submitted_table4)
    findings += verify_admin_consistency(data)
    findings += verify_income(data, result)
    soften_inferred(findings, inferred_keys(data, regional, individual))
    if not (submitted_table4 or t5s):
        for f in findings:
            if f.severity == "error":
                f.kind = "gap"
    return [f.to_dict() for f in findings]
