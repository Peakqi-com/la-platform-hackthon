"""
新北市各都市計畫區「土地使用分區管制要點」建蔽率／容積率：從城鄉發展局「都市計畫公告」抓最新核定計畫書，抽出各分區數值，
輸出 data/zoning_rules/extracted.json 供人工核對，再手動併入 rules/zoning_bcr_far.json 的 plans。

流程：
  1. 公告列表（home.jsp?id=0c69de209c17e5c4，POST page=N，約 29 頁、2018 年起）→ 標題含「通盤檢討」＋「細部計畫」（全本土管要點）或「管制要點」（單點修訂）
  2. 對應到城鄉資訊查詢平台的 49 個計畫區名稱（GetCityPlanList）
  3. 每個計畫區取最新一份「全本」計畫書 PDF（檔名含 書／計畫書／核定實施，不取公告與圖）；沒有全本就取最新單點修訂並標 partial
  4. 抽文字，找「○○區…建蔽率…％…容積率…％」句型與表格列，記頁碼與原句
限制：公告只有 2018 年以後；更早的通檢要靠平台「都市計畫書圖查詢」（geturbancourse，2026-09-10 其後端無法連線）或人工。
用法：cd backend && python3 scripts/fetch_ntpc_zoning_rules.py [--plans 板橋,三重] [--max-mb 80]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "zoning_rules"
LIST_URL = "https://www.planning.ntpc.gov.tw/home.jsp?id=0c69de209c17e5c4"
BASE = "https://www.planning.ntpc.gov.tw/"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
OP = urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX))

ZONE_RE = r"(第[一二三四五六七八九十]+種[^\s，、。；:：%％]{1,8}區|[^\s，、。；:：%％「」()（）]{1,10}?(?:住宅區|商業區|工業區|專用區|旅館區|風景區|保護區|農業區|文教區|行政區|保存區|用地))"


def crawl_list(pages: int = 40) -> list[dict]:
    items = []
    for page in range(1, pages + 1):
        data = urllib.parse.urlencode({"page": page, "keyword": "", "qptdate": "", "qdldate": ""}).encode()
        s = html.unescape(OP.open(urllib.request.Request(LIST_URL, data=data), timeout=60).read().decode("utf-8", "ignore"))
        rows = re.findall(r'<a href="(home\.jsp\?id=0c69de209c17e5c4&act=[^"]+dataserno=[^"]+)" title="([^"]+)">(.*?)</a>', s, re.DOTALL)
        if not rows:
            break
        for href, title, inner in rows:
            d = re.search(r'class="date[^"]*">\s*([\d\-]+)', inner)
            items.append({"href": href, "title": title.strip(), "date": d.group(1) if d else ""})
        time.sleep(0.2)
    return items


def plan_variants(name: str) -> list[str]:
    base = re.sub(r"(都市計畫|特定區計畫)$", "", name)
    base = base.replace("（", "(").replace("）", ")")
    v = [name, base + "細部計畫", base + "主要計畫", base + "都市計畫", base + "特定區計畫", base + "特定區細部計畫"]
    inner = re.findall(r"\(([^)]+)\)", base)
    if inner:                         # 八里(龍形地區) → 八里(龍形地區)細部計畫、新店安坑地區都市計畫
        flat = base.replace("(", "").replace(")", "")
        v += [flat + "細部計畫", flat + "都市計畫", flat + "主要計畫"]
    else:                             # 泰山 → 泰山(既有發展地區)細部計畫、淡海新市鎮特定區第一期細部計畫
        v += [base + "(", base + "第一期", base + "第二期"]
    return sorted(set(v), key=len, reverse=True)


def match_plan(title: str, plans: list[dict]) -> dict | None:
    t = title.replace("（", "(").replace("）", ")")
    best = None
    for p in plans:
        for v in plan_variants(p["PLAN_NAME"]):
            if v in t and (best is None or len(v) > best[1]):
                best = (p, len(v))
    return best[0] if best else None


def attachments(href: str) -> list[dict]:
    s = html.unescape(OP.open(BASE + href, timeout=60).read().decode("utf-8", "ignore"))
    atts = re.findall(r'href="(/uploaddowndoc\?dis=anounce&file=([^"&]+)&filedisplay=([^"&]+)[^"]*)"', s)
    return [{"url": BASE.rstrip("/") + a[0], "file": a[1], "name": urllib.parse.unquote(a[2])} for a in atts]


def pick_book(atts: list[dict]) -> dict | None:
    def score(a):
        n = a["name"]
        if re.search(r"公告|函|紀錄|圖冊|圖\.pdf|圖\)|計畫圖|-圖", n):
            return -1
        return 3 if re.search(r"土管|管制要點", n) else 2 if re.search(r"計畫書|書\.pdf|書n|書\(|書-|核定實施|用印", n) else 1 if n.lower().endswith(".pdf") else 0
    cands = sorted(atts, key=score, reverse=True)
    return cands[0] if cands and score(cands[0]) > 0 else None


def download(a: dict, dest: Path, max_mb: float) -> Path | None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    with OP.open(a["url"], timeout=300) as r:
        data = r.read(int(max_mb * 1024 * 1024) + 1)
    if len(data) > max_mb * 1024 * 1024:
        return None
    dest.write_bytes(data)
    return dest


HEADER_RE = re.compile(r"土地使用\s*分區\s*(?:種類)?\s*建蔽\s*率\s*容積\s*率|分區\s*建蔽率\s*容積率|建蔽率\s*容積率\s*備註")
NUM_RE = re.compile(r"^(\d{1,3}(?:\.\d+)?)[%％]$")
STOP_RE = re.compile(r"^(?:[(（][一二三四五六七八九十]+[)）]|[一二三四五六七八九十]+、|註[:：]?|備註[:：]|依指定現有巷道|說明[:：])")
_ORD = r"第[一二三四五六七八九十]+(?:之[一二三四五])?種"
_SPECIAL = (r"(?:" + _ORD + r")?(?:宗教|醫院|社區中心|產業|社會福利(?:事業|設施)?|郵政|加油站|教育休閒|漁業|港埠|文化創意產業特定|殯葬|"
            r"電信|工商|農產品批發|客運|轉運|物流|車站|捷運|機關|學校|公用事業|體育|觀光|遊憩|溫泉|休閒|廣播電視|石油|油庫|自來水|電力|"
            r"環保|資源回收|污水處理|焚化爐|新市鎮|會展|文化|藝術|科技|研究|批發|市場|停車|水岸|生態|軍事|國防|眷村|殯儀|墓地|納骨|老人|"
            r"長照|托育|社福|醫療|衛生|療養|特定|再發展|工業|商業|住宅|旅館|農業|保護|風景|文教|行政|保存|海洋|漁港|遊艇|港灣|軌道|鐵路|運動|公園|"
            r"綠地|河濱|物流倉儲|倉儲|加工|經貿|創新|農漁|農特產|生技|資訊|媒體|影視|智慧|無線|數位|園區|校園)")
_LAND = (r"(?:機關|學校|社教|市場|零售市場|批發市場|加油站|停車場|變電所|墓地|抽水站|環保設施|環保|公園|綠地|廣場|兒童遊樂場|體育場|"
         r"鄰里公園兼兒童遊樂場|公園兼兒童遊樂場|自來水|電信|郵政|港埠|河道|溝渠|水利|殯葬|殯儀館|污水處理廠|污水處理|垃圾|焚化|醫療|衛生|"
         r"公用事業|鐵路|捷運|車站|轉運站|客運|電力|瓦斯|油管|廣播|電視|警察|消防|國防|保護|農業|高速公路|公路|加油站|社會福利(?:設施)?|"
         r"公園兼社會福利設施|文[中小大高][一二三四五六七八九十\d]{0,3}|[機市停園綠廣兒體變抽污殯加社郵電港學]\s?[一二三四五六七八九十\d]{1,3}|私立[^\s，、。；:：%％()（）]{2,8})")
ZONE_FULL_RE = re.compile(
    r"(?:" + _ORD + r"|[甲乙丙丁特]種|古蹟|歷史|海濱|景觀|一般|特定)?"
    r"(?:住宅區|商業區|工業區|旅館區|風景區|保護區|農業區|文教區|行政區|保存區|遊憩區|港埠區|遊樂區|" + _SPECIAL + r"(?:特定)?專用區|" + _LAND + r"用地)"
    r"(?:[(（][一二三四五六七八九十特附帶條件\d]{1,4}[)）])*"
)
DEFER_TOKENS = ("依施行", "依本施行", "細則規", "定辦理", "定辦理。", "細則規定辦理", "細則規定辦理。", "規定辦理", "規定辦理。", "施行細則規定辦理", "細則辦理", "依施行細則辦理")


def _items(seg: str) -> list[tuple[str, object]]:
    """把表格片段切成 (ZONE 名稱 | NUM 數值 | DEFER) 序列；分區名可能被直排切碎、也可能兩個分區黏在同一 token。"""
    out: list[tuple[str, object]] = []
    pending = ""
    for t in re.split(r"[\s⏎]+", seg):
        if not t:
            continue
        m = NUM_RE.match(t)
        if m:
            if pending:
                out += [("ZONE", z) for z in ZONE_FULL_RE.findall(pending)]
                pending = ""
            out.append(("NUM", int(float(m.group(1)))))
            continue
        if t.startswith(DEFER_TOKENS) or t in DEFER_TOKENS:
            if pending:
                out += [("ZONE", z) for z in ZONE_FULL_RE.findall(pending)]
                pending = ""
            out.append(("DEFER", None))
            continue
        if STOP_RE.match(t) and out:
            if pending:
                out += [("ZONE", z) for z in ZONE_FULL_RE.findall(pending)]
            return out
        pending += t
        if len(pending) > 40:       # 太長＝敘述文字，不是表格格位；只保留尾端
            zs = ZONE_FULL_RE.findall(pending)
            out += [("ZONE", z) for z in zs]
            pending = ""
    if pending:
        out += [("ZONE", z) for z in ZONE_FULL_RE.findall(pending)]
    return out


def _plaus_bcr(v: int) -> bool:
    return 5 <= v <= 90


def _plaus_far(v: int) -> bool:
    return 10 <= v <= 1200


def parse_table_v2(text: str, page: int) -> list[dict]:
    """「土地使用分區 建蔽率 容積率」表。分區名與數字依出現順序配對：
    1 分區 + 2 數 → 建蔽/容積；k 分區 + k 數（建蔽率欄合併為「依施行細則規定辦理」）→ 每分區只填容積；其餘標「需核對」。"""
    rows: list[dict] = []
    for h in HEADER_RE.finditer(text):
        seg = text[h.end():h.end() + 3500].replace("％", "%")
        items = _items(seg)
        i = 0
        while i < len(items):
            if items[i][0] != "ZONE":
                i += 1
                continue
            zones: list[str] = []
            while i < len(items) and items[i][0] == "ZONE":
                zones.append(str(items[i][1]))
                i += 1
            deferred = False
            nums: list[int] = []
            while i < len(items) and items[i][0] in ("NUM", "DEFER"):
                if items[i][0] == "DEFER":
                    deferred = True
                else:
                    nums.append(int(items[i][1]))  # type: ignore[arg-type]
                i += 1
            zones = list(dict.fromkeys(zones))
            if len(zones) > 1:
                cats = {"住宅區", "商業區", "工業區", "風景區", "用地"}
                zones = [z for z in zones if not (z in cats and any(o != z and o.endswith(z) for o in zones))]
            k, n = len(zones), len(nums)
            src = f"{'／'.join(zones)} {'依施行細則 ' if deferred else ''}{' '.join(f'{v}%' for v in nums)}".strip()
            if n == 0:
                continue
            if k == 1 and n == 2 and _plaus_bcr(nums[0]) and _plaus_far(nums[1]) and nums[1] >= nums[0] and not deferred:
                rows.append({"zone": zones[0], "bcr": nums[0], "far": nums[1], "page": page, "kind": "表格", "check": False, "text": src})
            elif k == n and all(_plaus_far(v) for v in nums) and (deferred or all(v >= 100 for v in nums)):
                for z, v in zip(zones, nums, strict=True):
                    rows.append({"zone": z, "bcr": None, "far": v, "page": page, "kind": "表格", "check": False, "text": src})
            elif k * 2 == n and all(_plaus_bcr(nums[j]) and _plaus_far(nums[j + 1]) for j in range(0, n, 2)) and not deferred:
                for j, z in enumerate(zones):
                    rows.append({"zone": z, "bcr": nums[2 * j], "far": nums[2 * j + 1], "page": page, "kind": "表格", "check": False, "text": src})
            elif k == 1 and n == 1 and _plaus_far(nums[0]):
                rows.append({"zone": zones[0], "bcr": None, "far": nums[0], "page": page, "kind": "表格", "check": not deferred, "text": src})
            else:
                rows.append({"zone": "／".join(zones), "bcr": None, "far": None, "page": page, "kind": "表格", "check": True, "text": src})
    return rows


DEFER_RE = re.compile(r"刪除[^。]{0,60}建蔽率[^。]{0,12}容積率[^。]{0,60}(?:重複|規定)")      # 「刪除土地使用分區、公共設施用地之建蔽率、容積率…重複性規定」


def detect_deferred(pdf: Path) -> str | None:
    """通盤檢討書寫「配合施行細則規定刪除…建蔽率、容積率…重複性規定」→ 該計畫區的建蔽率容積率已回歸施行細則附表一。回傳那句話。"""
    import pypdf
    try:
        r = pypdf.PdfReader(str(pdf))
        for page in r.pages[:60]:
            t = re.sub(r"\s+", "", page.extract_text() or "")
            m = DEFER_RE.search(t)
            if m:
                return m.group(0)[:120]
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def extract_rows(pdf: Path) -> list[dict]:
    import pypdf
    rows: list[dict] = []
    try:
        r = pypdf.PdfReader(str(pdf))
    except Exception as e:  # noqa: BLE001
        return [{"error": str(e)}]
    for i, page in enumerate(r.pages[:400]):
        t = page.extract_text() or ""
        if "建蔽率" not in t or "容積率" not in t:
            continue
        rows += parse_table_v2(t, i + 1)
        flat = re.sub(r"\s+", "", t)
        # 句型：○○區…建蔽率不得大於50%，容積率不得大於180%
        for m in re.finditer(r"(.{2,24}?)(?:之|內|的)?(?:建築物之)?建蔽率(?:不得大於|不得超過|為|以)?(\d{1,3})[%％][^。]{0,30}?容積率(?:不得大於|不得超過|為|以)?(\d{1,3})[%％]", flat):
            zs = ZONE_FULL_RE.findall(m.group(1))
            if not zs:
                continue
            zone = zs[-1]
            noisy = not m.group(1).endswith(zone)          # 分區名與「建蔽率」之間還夾著別的字 → 可能是敘述而非規定
            rows.append({"zone": zone, "bcr": int(m.group(2)), "far": int(m.group(3)), "page": i + 1, "kind": "句型", "check": noisy, "text": flat[max(0, m.start() - 10):m.end() + 30]})
    # 去重（同分區同數值）
    seen, out = set(), []
    for x in rows:
        k = (x.get("zone"), x.get("bcr"), x.get("far"))
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def merge_plan(rec: dict) -> dict:
    """（見下方本體）"""
    out = _merge_plan(rec)
    dq = next((s.get("deferred_to_county") for s in rec.get("sources", []) if s.get("deferred_to_county")), None)
    if dq:
        out["deferred_to_county"] = dq
    return out


def _merge_plan(rec: dict) -> dict:
    """同一計畫區、同一分區可能有多列（修正前後表、兩個來源）；優先「土管」來源、頁碼最前、無需核對者。
    建蔽率為 None 表示「依施行細則規定辦理」，由系統查附表一補。值不一致時全部列出並標 conflict。"""
    rows = [r for r in rec.get("rows", []) if "error" not in r and r.get("far")]
    by_zone: dict[str, list[dict]] = {}
    for r in rows:
        by_zone.setdefault(r["zone"], []).append(r)
    out: dict[str, dict] = {}
    for zone, lst in by_zone.items():
        lst.sort(key=lambda r: (0 if r["source"].startswith("土管") else 1, 1 if r.get("check") else 0, 0 if r["kind"] == "表格" else 1, r["page"]))
        best = lst[0]
        vals = {(r["bcr"], r["far"]) for r in lst}
        fars = {r["far"] for r in lst}
        bcrs = {r["bcr"] for r in lst if r["bcr"] is not None}
        bcr = best["bcr"]
        if bcr is None and len(bcrs) == 1 and len(fars) == 1:
            bcr = bcrs.pop()                     # 另一表已寫明建蔽率、容積率一致 → 採寫明者
        out[zone] = {"bcr": bcr, "far": best["far"], "page": best["page"], "kind": best["kind"], "source": best["source"],
                     "check": bool(best.get("check")) or len(fars) > 1 or len(bcrs) > 1,
                     "variants": sorted(f"{b if b is not None else '細則'}/{f}" for b, f in vals) if len(vals) > 1 else None}
    flagged = [r for r in rec.get("rows", []) if "error" not in r and not r.get("far") and r.get("check")]
    return {"sources": rec.get("sources", []), "zones": out, "unparsed": [{"page": r["page"], "text": r["text"], "source": r["source"]} for r in flagged]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", help="逗號分隔的計畫區關鍵字（例：板橋,三重），預設全部")
    ap.add_argument("--max-mb", type=float, default=80)
    ap.add_argument("--reuse-index", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    plans = json.loads((OUT / "cityplans.json").read_text(encoding="utf-8"))
    idx_p = OUT / "announcements.json"
    items = json.loads(idx_p.read_text(encoding="utf-8")) if a.reuse_index and idx_p.exists() else crawl_list()
    idx_p.write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
    want = [k.strip() for k in a.plans.split(",")] if a.plans else None
    cands: dict[str, list[dict]] = {}
    for it in items:
        t = it["title"]
        if re.search(r"公開展覽|公告徵求|撤銷|停止適用", t):
            continue
        full = ("通盤檢討" in t and ("細部計畫" in t or "特定區計畫" in t or "都市計畫" in t)) or ("管制要點" in t and "通盤檢討" in t) or bool(re.search(r"第[一二三四]階段", t))
        partial = "管制要點" in t or "細部計畫" in t
        if not (full or partial):
            continue
        p = match_plan(t, plans)
        if not p or (want and not any(w in p["PLAN_NAME"] for w in want)):
            continue
        cands.setdefault(p["PLAN_NAME"], []).append({**it, "full": full})
    results = []
    for name, lst in sorted(cands.items()):
        lst.sort(key=lambda x: x["date"], reverse=True)
        chosen = None
        pool = []
        for it in lst[:6]:                       # 最新 6 筆公告的附件都看：優先「土管要點」全文，其次全本通檢計畫書
            atts = attachments(it["href"])
            for a_ in atts:
                if re.search(r"土管|管制要點", a_["name"]) and not re.search(r"公告|紀錄|圖", a_["name"]):
                    pool.append((3, it["date"], it, a_))
            book = pick_book(atts)
            if book and it["full"]:
                pool.append((2, it["date"], it, book))
            time.sleep(0.2)
        picks: list[tuple[dict, dict]] = []
        if pool:
            pool.sort(key=lambda x: (x[0], x[1]), reverse=True)
            for score_ in (3, 2):
                for sc, _, it, book in pool:
                    if sc == score_ and not any(b["url"] == book["url"] for _, b in picks):
                        picks.append((it, book))
                        break
        chosen = picks[0][0] if picks else None
        rec = {"plan": name, "n_candidates": len(lst), "sources": [], "rows": [], "status": "no_book"}
        for it, book in picks:
            safe = re.sub(r"[^\w一-鿿]+", "_", name)[:30]
            tag = "土管" if re.search(r"土管|管制要點", book["name"]) and not it["full"] else "全本"
            dest = OUT / "pdf" / f"{safe}_{tag}_{it['date']}.pdf"
            src = {"title": it["title"], "date": it["date"], "full": it["full"], "href": it["href"], "book": book["name"], "kind": tag}
            try:
                p = download(book, dest, a.max_mb)
            except Exception as e:  # noqa: BLE001
                p = None
                src["status"] = f"download_error: {e}"
            if p:
                rows = extract_rows(p)
                for r_ in rows:
                    r_["source"] = f"{tag} {it['date']}"
                src["pdf"] = str(p.relative_to(ROOT))
                dq = detect_deferred(p)
                if dq:
                    src["deferred_to_county"] = dq
                src["status"] = "ok" if rows and "error" not in rows[0] else ("no_text_or_table" if not rows else "pdf_error")
                rec["rows"] += rows
            else:
                src.setdefault("status", "too_large")
            rec["sources"].append(src)
        good = [r_ for r_ in rec["rows"] if "error" not in r_]
        rec["status"] = "ok" if good else ("no_book" if not picks else "no_text_or_table")
        rec["n_check"] = sum(1 for r_ in good if r_.get("check"))
        rec["book"] = picks[0][1]["name"] if picks else None
        results.append(rec)
        print(f"{name}: {rec['status']}  候選 {len(lst)}  來源 {len(picks)}  {chosen['date'] if chosen else ''}  列 {len(rec['rows'])}  需核對 {rec['n_check']}")
    merged = {r["plan"]: merge_plan(r) for r in results}
    (OUT / "merged.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "extracted.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {OUT / 'extracted.json'}")


if __name__ == "__main__":
    main()
