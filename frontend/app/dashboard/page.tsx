"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCase } from "@/components/CaseContext";
import PageHeader from "@/components/PageHeader";
import { IOBadge } from "@/components/IO";
import { Btn, Card, Help, Modal } from "@/components/ui";
import { latestVdate, VDateSelect } from "@/components/vdate";
import { InputBadges, InputDetail } from "@/components/Inputs";
import { api, Any, fmtMoney, INPUT_KIND_LABEL, InputResult, LOW_CONF, STATUS_LABEL } from "@/lib/api";

const NTPC_DISTRICTS = ["金山區", "萬里區", "石門區", "三芝區", "淡水區", "八里區", "林口區", "五股區", "泰山區", "蘆洲區", "三重區", "新莊區", "板橋區", "中和區", "永和區", "土城區", "樹林區", "鶯歌區", "三峽區", "新店區", "深坑區", "石碇區", "坪林區", "烏來區", "汐止區", "瑞芳區", "平溪區", "雙溪區", "貢寮區"];
const EXAMPLES: { v: "template" | "tampered" | "residential" | "blank_survey" | "shulin"; title: string; desc: string }[] = [
  { v: "template", title: "範例一：金山區 P002-00 地價區段", desc: "送審書表填載與系統核算相符。" },
  { v: "tampered", title: "範例二：含填載錯誤之送審書表", desc: "同一案但等級與修正率抄錯，看不符項、承辦裁決與意見書。" },
  { v: "blank_survey", title: "範例三：僅有年期、區段編號、區段範圍之勘查表", desc: "由圖資推算勘查表其餘欄位。" },
  { v: "shulin", title: "範例四：樹林區普通住宅用地（四個區段、三個比較標的）", desc: "住宅用地基準表；勘查表與個別因素待圖資推算，可輸出地政局正式範本書表。" },
];
type NewMethod = "upload" | "lot" | "example";

/* 案件總覽（承辦／主管儀表）：路徑 /dashboard。根路徑 / 是首頁介紹頁（app/page.tsx）。 */
export default function Dashboard() {
  const router = useRouter();
  const { rec, loadDemo, loading, error, cases, loadCase, refreshList } = useCase();
  const [nc, setNc] = useState({ case_no: "", valuation_date: latestVdate(), district: "新北市金山區", land_use: "商業用地", section_id: "", range_desc: "", subject_parcel_id: "" });
  const [autoFill, setAutoFill] = useState(true);      // 建立後立即依地號產生（含實價登錄比較標的）
  const [lots, setLots] = useState<{ section: string; lot: string; parcel_id: string; district?: string | null }[]>([]);   // 預載地籍圖的地號清單（比準地下拉，依鄉鎮市區篩）
  const [manualLot, setManualLot] = useState(false);       // 地籍圖沒有的地號：改手動輸入
  useEffect(() => { api.cadastreLots().then((r) => setLots(r.lots || [])).catch(() => setLots([])); }, []);
  const [ncMsg, setNcMsg] = useState<string | null>(null);
  const [listMsg, setListMsg] = useState<string | null>(null);      // 封存／復原／刪除失敗提示
  const [health, setHealth] = useState<Any>(null);
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); }, []);
  const [q, setQ] = useState(""); const [stFilter, setStFilter] = useState("all"); const [showArchived, setShowArchived] = useState(false); const [sortBy, setSortBy] = useState<"opened" | "updated" | "case_no">("opened");
  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);   // 封存區「刪除」兩段式確認：第一次按 → 顯示確定／取消
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const [newOpen, setNewOpen] = useState(false);                 // 「＋ 新增案件」對話框
  const [method, setMethod] = useState<NewMethod | null>(null);   // 對話框第二步：上傳／依地號／範例
  function closeNew() { setNewOpen(false); setMethod(null); setUploads([]); setBatchMsg(null); setNcMsg(null); }

  /* 上傳輸入檔：一次可選多份，逐份辨識預覽；預設「合併為一個案件」（書表 PDF、清冊、實例、基準表、地籍圖、區段圖都併進同一案），也可每份各建一案或加到既有案件。 */
  type Upload = { id: string; file: File; filename: string; status: "queued" | "parsing" | "done" | "error"; error?: string; preview?: InputResult & { data?: Any; confidence?: Record<string, number> } };
  const GEO_EXT = /\.(geojson|kml|gml|xml|zip)$/i;
  const [uploads, setUploads] = useState<Upload[]>([]);
  const patchUpload = (id: string, patch: Partial<Upload>) => setUploads((l) => l.map((u) => (u.id === id ? { ...u, ...patch } : u)));
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [umode, setUmode] = useState<"one" | "each" | "existing">("one");
  const [targetCase, setTargetCase] = useState("");
  const [nf, setNf] = useState({ case_no: "", valuation_date: latestVdate(), district: "新北市金山區" });   // 沒有書表 PDF 時建案要的基本資料
  function previewOf(u: Upload, r: Any): Upload["preview"] {
    const d = r.data || {};
    const base = { filename: u.filename, kind: r.kind, kind_label: INPUT_KIND_LABEL[r.kind] || r.kind, missing: r.missing_fields || [], warnings: r.warnings || [], confidence: r.confidence || {}, data: d, pages: d.pages || [], summary: "" };
    if (r.kind === "pdf_forms") return { ...base, summary: `${d.case?.case_no || "案號未讀到"}；估價基準日 ${d.case?.valuation_date || "—"}；${d.case?.land_use || "—"}；比準地 ${d.subject_parcel?.parcel_id || "—"}；比較標的 ${d.comparables?.length ?? 0} 件；區域因素分析表 ${Object.keys(d.submitted?.table5 || {}).length} 件、比較法估價表 ${d.submitted?.table4?.comparables ? "有" : "無"}` };
    if (r.kind === "parcels" || r.kind === "comparables") return { ...base, summary: `讀取 ${d.parcels?.length ?? d.comparables?.length ?? 0} 筆，建案時依地號對到比準地與比較標的` };
    if (r.kind === "rules_table") return { ...base, summary: `基準表：${Object.keys(d.rulesets || {}).map((k) => (k === "regional" ? "區域因素" : "個別因素")).join("、") || "沒讀到"}，建案時匯入並套用至本案` };
    return base;
  }
  async function onUpload(files: FileList | File[] | null | undefined) {
    const list = Array.from(files || []); if (!list.length) return;
    const items: Upload[] = list.map((f, i) => ({ id: `${Date.now()}-${i}-${f.name}`, file: f, filename: f.name, status: "queued" }));
    setUploads((l) => [...l, ...items]); setBatchMsg(null); setBusy(true);
    try {
      for (const u of items) {   // 逐份辨識：掃描件走影像辨識較慢，避免同時打太多請求；辨識結果後端會快取，建案時不重跑
        if (GEO_EXT.test(u.filename)) { patchUpload(u.id, { status: "done", preview: { filename: u.filename, kind: "cadastre", kind_label: "地籍圖／地價區段圖", summary: "建案時依屬性欄位辨識是地籍圖（地號欄）或區段圖（區段編號欄）並併入" } }); continue; }
        patchUpload(u.id, { status: "parsing" });
        try { const r = await api.adapt(u.file, "auto", { use_vision: "auto" }); patchUpload(u.id, { status: "done", preview: previewOf(u, r) }); }
        catch (e: Any) { patchUpload(u.id, { status: "error", error: String(e.message || e) }); }
      }
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }
  const ready = uploads.filter((u) => u.status === "done");
  const hasPdf = ready.some((u) => u.preview?.kind === "pdf_forms");
  const needsForm = umode !== "existing" && !hasPdf;
  const canCreate = ready.length > 0 && !busy && (umode === "existing" ? !!targetCase : !needsForm || (!!nf.case_no.trim() && !!nf.valuation_date.trim()));
  async function createFromUploads() {
    if (!ready.length) return; setBusy(true); setBatchMsg(null);
    const files = ready.map((u) => u.file);
    const form = needsForm ? { case_no: nf.case_no.trim(), valuation_date: nf.valuation_date.trim(), district: nf.district } : {};
    try {
      if (umode === "existing") {
        const r = await api.addInputs(targetCase, files);
        const ok = r.results.filter((x) => !x.error && !x.skipped).length; const bad = r.results.filter((x) => x.error);
        await refreshList(); await loadCase(targetCase); closeNew();
        setListMsg(`已加入 ${ok} 份到「${r.record.name}」${bad.length ? `；失敗：${bad.map((x) => `${x.filename}（${x.error}）`).join("、")}` : ""}。`);
        router.push(`/input?tab=case&case=${encodeURIComponent(targetCase)}`);
        return;
      }
      if (umode === "each") {
        const made: string[] = []; const bad: string[] = [];
        for (const u of ready) {
          try { const r = await api.casesFromInputs([u.file], { ...form, use_vision: "auto" }); made.push(r.case.id); if (r.results[0]?.error) bad.push(`${u.filename}（${r.results[0].error}）`); }
          catch (e: Any) { bad.push(`${u.filename}（${String(e.message || e)}）`); }
        }
        await refreshList(); if (made.length) await loadCase(made[made.length - 1]); closeNew();
        setListMsg(`已建立 ${made.length} 件案件${bad.length ? `；有問題：${bad.join("、")}` : ""}。`);
        return;
      }
      const r = await api.casesFromInputs(files, { ...form, use_vision: "auto" });
      const bad = r.results.filter((x) => x.error);
      await refreshList(); await loadCase(r.case.id); closeNew();
      if (bad.length) setListMsg(`已建立「${r.case.name}」，但 ${bad.length} 份檔沒併入：${bad.map((x) => `${x.filename}（${x.error}）`).join("、")}。可到案件的「輸入檔」再加入。`);
      const review = !!(r.case.submitted_table4 || r.case.submitted_table5);
      router.push(review ? `/review?case=${encodeURIComponent(r.case.id)}` : `/input?tab=case&case=${encodeURIComponent(r.case.id)}`);
    } catch (e: Any) { setBatchMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  const lowConfOf = (u: Upload) => Object.values(u.preview?.confidence || {}).filter((v) => v < LOW_CONF).length;
  const shown = useMemo(() => {
    let l = cases.filter((c) => (showArchived ? c.archived : !c.archived) && (stFilter === "all" || c.status === stFilter) && (!q || String(c.name).includes(q) || String(c.case_no || "").includes(q) || String(c.subject_parcel_id || "").includes(q)));
    l = [...l].sort((a, b) => sortBy === "case_no" ? String(a.case_no || "").localeCompare(String(b.case_no || "")) : String(b[sortBy === "opened" ? "opened_at" : "updated_at"] || "").localeCompare(String(a[sortBy === "opened" ? "opened_at" : "updated_at"] || "")));
    return l;
  }, [cases, q, stFilter, sortBy, showArchived]);
  async function createBlank() {
    if (!nc.case_no.trim() || !nc.valuation_date.trim() || !nc.district.trim()) { setNcMsg("案號、估價基準日、鄉鎮市區為必填。"); return; }
    if (!nc.subject_parcel_id.trim() && !nc.range_desc.trim()) { setNcMsg("請填比準地地號；沒有地號時改填「區段範圍」文字，系統會圍出區段並依查估辦法 §18 自動選比準地。"); return; }
    setBusy(true); setNcMsg(null);
    try {
      const r = await api.newCase(nc);
      let report = "";
      if (autoFill && (nc.subject_parcel_id.trim() || nc.range_desc.trim())) {
        setNcMsg(nc.subject_parcel_id.trim() ? "已建立，依地號產生中（地籍界線 → 宗地屬性 → 區段範圍 → 勘查表 → 設施距離 → 比較標的）…" : "已建立，依區段範圍文字圍區段並選比準地中…");
        await api.fromLot(r.id, { parcel_id: nc.subject_parcel_id.trim(), parcel_changed: !!nc.subject_parcel_id.trim() });
        await api.generate(r.id); report = "&report=1";
      }
      await refreshList(); await loadCase(r.id); router.push(`/input?tab=case&case=${encodeURIComponent(r.id)}${report}`);
    }
    catch (e: Any) { setNcMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  const kpi = useMemo(() => ({
    total: cases.filter((c) => !c.archived).length,
    reviewing: cases.filter((c) => c.status === "reviewing").length,
    done: cases.filter((c) => c.status === "done").length,
    pending: cases.filter((c) => c.status !== "done" && c.has_submitted).reduce((a, c) => a + Math.max(0, (c.n_error ?? 0) - (c.n_accepted ?? 0)), 0),   // 只算有送審書表的案件；依地號產生的案件其 error 是資料缺口
    stale: cases.filter((c) => c.stale).length,
  }), [cases]);
  const fmtT = (t?: string | null) => (t ? String(t).replace("T", " ").slice(5, 16) : "—");
  /* 下一步：依案件現況逐層判斷 — 已完成 → 輸入不齊 → 產出未產生／已過期 → 審查結果與裁決進度 → 狀態。每個都附「為什麼」給 title。 */
  const nextStep = (c: Any): { href: string; label: string; why: string } => {
    const q = `case=${encodeURIComponent(c.id)}`;
    const nErr = c.n_error ?? 0, nWarn = c.n_warn ?? 0, open = Math.max(0, nErr - (c.n_accepted ?? 0));
    if (c.status === "done") return { href: `/export?${q}`, label: "下載全部", why: "案件已完成，輸出 Excel／PDF／意見書與圖說" };
    if (!c.subject_parcel_id) return { href: `/input?tab=case&${q}`, label: "補基本資料", why: "還沒有比準地" };
    if (c.n_comparables === 0 && !c.has_submitted) return { href: `/input?tab=parcels&${q}`, label: "補比較標的", why: "沒有買賣實例，無法算比較價格" };
    if (c.n_error === null || c.n_error === undefined) return { href: `/sheets?${q}`, label: "產生書表", why: "尚未產生書表" };
    if (c.stale) return { href: `/sheets?${q}`, label: "重新產生書表", why: "輸入改過，產出已過期" };
    if (!c.has_submitted) {   // 依地號產生：沒有送審書表可比對，只看資料缺口
      if (nErr > 0) return { href: `/input?tab=parcels&${q}`, label: `補資料缺口（${nErr}）`, why: "書表有欄位推不出來，需人工填載" };
      if (nWarn > 0) return { href: `/review?${q}`, label: `確認需確認項（${nWarn}）`, why: "系統判定不足的項目要人工確認" };
      return { href: `/export?${q}`, label: "輸出書表", why: "書表已產生且沒有缺口" };
    }
    if (c.status === "reviewing") {
      if (open > 0) return { href: `/review?${q}`, label: `處理不符項（${open}）`, why: "還有不符項未裁決" };
      return { href: `/review?${q}`, label: "完成審查", why: "不符項都裁決過了，可以把狀態改為已完成" };
    }
    if (nErr > 0) return { href: `/review?${q}`, label: `開始審查（${nErr} 不符）`, why: "送審書表與規則算出的結果有不一致" };
    if (nWarn > 0) return { href: `/review?${q}`, label: `確認需確認項（${nWarn}）`, why: "填載值相符，但有系統判定不足的項目要人工確認" };
    return { href: `/review?${q}`, label: "檢視審查結果", why: "送審書表與規則結果全部相符" };
  };
  const reviewCell = (c: Any) => {
    if (c.n_error === null || c.n_error === undefined) return <span className="text-slate-400">尚未產生</span>;
    if (!c.has_submitted) return <span className="text-slate-500">無送審書表{c.n_error ? <span className="text-red-700">・資料缺口 {c.n_error}</span> : ""}{c.n_warn ? <span className="text-amber-800">・需確認 {c.n_warn}</span> : ""}</span>;
    const open = Math.max(0, (c.n_error ?? 0) - (c.n_accepted ?? 0));
    if ((c.n_error ?? 0) === 0) return <span className="text-emerald-700">相符{c.n_warn ? `・${c.n_warn} 需確認` : ""}</span>;
    return <span><span className="text-red-700 font-medium">{c.n_error} 不符</span>{c.n_accepted ? <span className="text-slate-600">・已裁決 {c.n_accepted}</span> : null}{open ? <span className="text-amber-800">・待處理 {open}</span> : null}</span>;
  };
  const METHODS: { m: NewMethod; title: string; desc: string }[] = [
    { m: "upload", title: "上傳輸入檔", desc: "有估價單位送來的書表 PDF（可拆成多份）、清冊、實例、基準表、地籍圖、區段圖：一次選多份，辨識後合併成一個案件，直接開啟審查。" },
    { m: "lot", title: "依地號建案", desc: "沒有送審書表、只有年期與比準地地號：系統找地籍界線、推算勘查表、量測設施距離並產生書表。" },
    { m: "example", title: "載入範例", desc: "用內建的三個示範案看整套流程：相符、含填載錯誤、僅有勘查表基本欄位。" },
  ];
  const METHOD_TITLE: Record<NewMethod, string> = { upload: "上傳輸入檔", lot: "依地號建案", example: "載入範例" };
  return (
    <div>
      <PageHeader title="案件總覽" />
      {error && <div className="bg-red-50 border border-red-200 text-red-800 rounded p-3 text-sm mb-3">{error}</div>}

      <section className="bg-[#fff1e3] text-[#3b2314] border border-orange-200 rounded-xl px-6 py-5 mb-4">
        <div>
          <div className="flex-1 min-w-[20rem]">
            <div className="text-lg font-semibold">這套系統做什麼</div>
            <Help className="mt-1">估價單位送來土地徵收補償市價查估書表（各區段勘查表、區域因素分析明細表、比較法調查估價表與三張圖說），系統依評價基準明細表把三張表重算一份，逐格比對估價單位填載值與核算值，指出不符處並附查估辦法條號與作業手冊頁碼，最後產出審查意見書與正式書表。等級、修正率與價格全部由規則引擎依《土地徵收補償市價查估辦法》與作業手冊確定性計算，每一格都能對回基準明細表；AI（語言模型）只用於掃描件辨識與意見書文字潤飾，不參與數字。</Help>
            <div className="mt-3 flex flex-wrap items-stretch gap-2"><ol className="flex-1 min-w-[20rem] grid sm:grid-cols-4 gap-2 text-sm">
              {[["①", "輸入資料", "上傳送審書表 PDF，或填年期與地號一鍵建案；匯入該地區的評價基準明細表"], ["②", "產出書表", "依基準表判定等級、修正率與價格鏈，重算全部書表並預覽"], ["③", "審查", "逐格比對填載值與核算值，標出不符與依據；承辦逐項裁決、產生審查意見書"], ["④", "輸出", "下載正式書表 Excel／PDF、審查意見書 Word／PDF、三張圖說"]].map(([n, t, d]) => (
                <li key={n} className="bg-white border border-orange-200 rounded-lg px-3 py-2"><div className="font-semibold"><span className="text-orange-700 mr-1">{n}</span>{t}</div><div className="text-xs text-slate-700 mt-1">{d}</div></li>))}
            </ol>
            <div className="shrink-0 flex flex-col gap-2 w-56">
            <button onClick={async () => { await loadDemo("template"); router.push("/sheets"); }} disabled={loading} className="flex-1 min-h-[3rem] px-4 py-3 rounded-lg bg-white border border-orange-300 text-orange-900 font-semibold hover:bg-orange-50 disabled:opacity-50">{loading ? "載入中…" : "用範例看一遍 →"}</button>
          </div>
            </div>
            {health && (
              <div className="text-[11px] mt-3 flex flex-wrap gap-3">
                <span className={health.tiles?.tiles > 0 ? "text-emerald-700" : "text-amber-800"}>底圖快取：{health.tiles?.tiles > 0 ? `${health.tiles.tiles} 塊${health.tiles.districts?.length ? `（${health.tiles.districts.join("、")}離線可用，其他區需外網）` : "（離線可用）"}` : "無（需要外網）"}</span>
                <span className="text-slate-600">設施資料庫：{health.spatial?.poi?.count ?? "—"} 筆</span>
              </div>
            )}
          </div>
        </div>
      </section>

      {cases.length > 0 && (
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        {[["全部案件", kpi.total, ""], ["審查中", kpi.reviewing, "text-sky-800"], ["待處理不符項", kpi.pending, kpi.pending ? "text-red-700" : ""], ["產出已過期", kpi.stale, kpi.stale ? "text-amber-800" : ""], ["已完成", kpi.done, "text-emerald-700"]].map(([l, v, cls]) => (
          <div key={String(l)} className="bg-white border border-slate-200 rounded-lg px-4 py-3"><div className="text-xs text-slate-500">{l}</div><div className={`text-2xl font-semibold ${cls}`}>{v}</div></div>))}
      </div>)}

      <Card title={`案件清單（${cases.length}）`} right={<>
        <Btn onClick={() => { setMethod(null); setNewOpen(true); }} title="上傳送審書表、依地號建案或載入範例">＋ 新增案件</Btn>
        <input className="border rounded px-2 py-1 text-sm w-40" placeholder="搜尋案號／名稱／地號" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="border rounded px-2 py-1 text-sm" value={stFilter} onChange={(e) => setStFilter(e.target.value)}><option value="all">全部狀態</option>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select className="border rounded px-2 py-1 text-sm" value={sortBy} onChange={(e) => setSortBy(e.target.value as Any)}><option value="opened">最近開啟</option><option value="updated">最近修改</option><option value="case_no">案號</option></select>
        <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />已封存（{cases.filter((c) => c.archived).length}）</label></>}>
        {listMsg && <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2 mb-2 flex items-center gap-2">{listMsg}<button className="underline text-xs" onClick={() => setListMsg(null)}>關閉</button></div>}
        {shown.length === 0 ? <div className="text-sm text-slate-500">{cases.length ? "沒有符合條件的案件" : "尚無案件。按「＋ 新增案件」上傳送審書表、依地號建案或載入範例。"}</div> : (
          <div className="overflow-x-auto"><table className="grid"><thead><tr><th className="min-w-[14rem]">案件</th><th className="whitespace-nowrap">狀態</th><th className="whitespace-nowrap" title="這一案輸入了哪些資料：實色＝已輸入（滑過看來源檔），淡灰＝尚未">輸入資料</th><th className="whitespace-nowrap">審查結果</th><th className="whitespace-nowrap">比較價格</th><th className="whitespace-nowrap">產出</th><th className="whitespace-nowrap">最後操作</th><th className="whitespace-nowrap w-1">下一步</th></tr></thead>
            <tbody>{shown.map((c) => { const ns = nextStep(c); return (<tr key={c.id} className={rec?.id === c.id ? "selected" : ""}>
              <td><button className="font-medium text-left underline decoration-dotted hover:text-[#c2410c]" title="開啟案件（從 ① 輸入資料開始）" onClick={async () => { await loadCase(c.id); router.push(`/input?tab=case&case=${encodeURIComponent(c.id)}`); }}>{c.name}</button><div className="text-xs text-slate-500">{c.case_no}・基準日 {c.valuation_date || "—"}・比準地 {c.subject_parcel_id || "—"}・比較標的 {c.n_comparables} 件{c.has_submitted ? "・有送審書表" : ""}</div></td>
              <td className="whitespace-nowrap"><span className={`rounded px-1.5 py-0.5 text-xs ${c.status === "done" ? "bg-emerald-100 text-emerald-800" : c.status === "reviewing" ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-700"}`}>{STATUS_LABEL[c.status] || c.status}</span></td>
              <td className="text-xs min-w-[12rem]"><InputBadges summary={c.inputs_summary} />{c.inputs_summary?.n ? <div className="text-slate-500 mt-0.5">{c.inputs_summary.n} 份輸入檔</div> : null}</td>
              <td className="text-xs whitespace-nowrap">{reviewCell(c)}</td>
              <td className="text-xs text-right font-mono whitespace-nowrap">{c.comparison_price ? `${fmtMoney(c.comparison_price)} 元/m²` : "—"}</td>
              <td className="text-xs whitespace-nowrap">{c.stale ? <span className="text-amber-800">已過期</span> : c.generated_at ? <span className="text-emerald-700">最新</span> : "—"}<div className="text-slate-500">{fmtT(c.generated_at)}</div></td>
              <td className="text-xs whitespace-nowrap">{c.last_action ? <>{c.last_action.actor}<div className="text-slate-500">{c.last_action.action}・{fmtT(c.last_action.at)}</div></> : "—"}</td>
              <td className="text-xs"><div className="flex flex-wrap items-center gap-x-2 gap-y-1"><Link href={ns.href} onClick={() => loadCase(c.id)} title={ns.why}><Btn title={ns.why}>{ns.label}</Btn></Link>{c.archived ? <>
                <button className="text-orange-800 underline" onClick={async () => { try { await api.archiveCase(c.id, true); await refreshList(); } catch (e: Any) { setListMsg(`復原失敗：${String(e?.message || e)}`); } }}>復原</button>
                {pendingDelete === c.id
                  ? <div className="mt-1 whitespace-normal max-w-[13rem] bg-red-50 border border-red-200 rounded px-2 py-1"><div className="text-red-800 mb-1">確定刪除？資料與匯入檔案會移除，操作紀錄保留，無法復原。</div>
                      <button className="px-2 py-0.5 rounded bg-red-600 text-white" onClick={async () => { try { await api.deleteCase(c.id); setPendingDelete(null); const list = await refreshList(); if (rec?.id === c.id) { if (list.length) await loadCase(list[0].id); else window.location.reload(); } } catch (e: Any) { setListMsg(`刪除失敗：${String(e?.message || e)}`); } }}>確定刪除</button>
                      <button className="px-2 py-0.5 rounded border border-slate-300 bg-white ml-1" onClick={() => setPendingDelete(null)}>取消</button></div>
                  : <button className="text-red-700 underline" title="永久刪除此案件的資料與匯入檔案（操作紀錄保留）" onClick={() => setPendingDelete(c.id)}>刪除</button>}
              </> : <button className="text-slate-400 hover:text-amber-800 underline" title="封存：從清單隱藏，資料與紀錄保留，可復原" onClick={async () => { try { await api.archiveCase(c.id); await refreshList(); } catch (e: Any) { setListMsg(`封存失敗：${String(e?.message || e)}`); } }}>封存</button>}</div></td>
            </tr>); })}</tbody></table></div>
        )}
      </Card>

      {newOpen && (
        <Modal title={method ? `新增案件：${METHOD_TITLE[method]}` : "新增案件"} onClose={closeNew}
          back={method ? <button type="button" className="text-sm text-slate-600 hover:text-[#c2410c] underline decoration-dotted" onClick={() => { setMethod(null); setUploads([]); setBatchMsg(null); setNcMsg(null); }}>← 換方式</button> : undefined}>
          {!method && (
            <div>
              <div className="text-xs text-slate-600 mb-3">三種方式都會建立一個新案件，差別只在資料從哪裡來。</div>
              <div className="grid sm:grid-cols-3 gap-3">
                {METHODS.map((x) => (
                  <button key={x.m} type="button" onClick={() => setMethod(x.m)} className="text-left rounded-lg border border-slate-200 hover:border-[#ea580c] hover:bg-orange-50 px-4 py-4 flex flex-col gap-1 min-h-[9rem]">
                    <div className="font-semibold">{x.title}</div><div className="text-xs text-slate-600">{x.desc}</div><div className="text-xs text-[#c2410c] mt-auto pt-2">選擇此方式 →</div>
                  </button>))}
              </div>
            </div>
          )}

          {method === "upload" && (
            <div>
              <div className={`rounded-lg border-2 border-dashed px-4 py-4 flex flex-col items-center justify-center text-center transition ${drag ? "border-[#ea580c] bg-orange-50" : "border-orange-300 bg-orange-50/30"} ${uploads.length ? "min-h-[5rem]" : "min-h-[8rem]"}`}
                onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                onDrop={(e) => { e.preventDefault(); setDrag(false); onUpload(e.dataTransfer.files); }}>
                <div className="text-sm font-medium">{uploads.length ? "再拖其他檔案到這裡（同一案件）" : "把送審書表 PDF 與其他輸入檔拖到這裡（可一次多份）"}</div>
                <div className="text-xs text-slate-500 mt-1">或</div>
                <div className="mt-2"><Btn onClick={() => fileRef.current?.click()} disabled={busy} busy={busy}>⬆ 選擇檔案</Btn></div>
                <div className="text-[11px] text-slate-500 mt-1">書表 PDF（整份或拆成勘查表／表5／表4）、宗地清冊、買賣實例 xlsx、評價基準明細表、地籍圖、地價區段圖。選檔時按住 Shift／⌘ 可多選。</div>
                <input ref={fileRef} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.json,.geojson,.kml,.gml,.xml,.zip" hidden onChange={(e) => onUpload(e.target.files)} />
              </div>
              {!uploads.length && (
                <ol className="mt-3 grid grid-cols-3 gap-2 text-xs">
                  {[["1", "辨識每份檔", "書表走文字層或影像辨識；清冊、實例、基準表、圖檔各自判斷種類"], ["2", "預覽辨識結果", "每份的頁面、案件、缺漏與信心值"], ["3", "合併成一個案件", "書表依區段與實例編號聯集，清冊補宗地屬性，基準表直接套用；建立後開啟審查"]].map(([n, t, d]) => (
                    <li key={n} className="rounded-md bg-slate-50 border border-slate-200 px-2 py-1.5"><div className="font-medium"><span className="text-orange-700 mr-1">{n}</span>{t}</div><div className="text-[11px] text-slate-500 mt-0.5">{d}</div></li>))}
                </ol>
              )}
              {uploads.length > 0 && (
                <div className="mt-3">
                  <div className="text-sm font-semibold mb-1">辨識結果（{ready.length}／{uploads.length} 份）</div>
                  <ul className="space-y-2 max-h-[40vh] overflow-auto pr-1">
                    {uploads.map((u) => (
                      <li key={u.id} className={`rounded-md border px-3 py-2 ${u.status === "error" ? "border-red-200 bg-red-50/40" : "border-slate-200"}`}>
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-medium">{u.filename}</span>
                          {u.status === "queued" && <span className="text-xs text-slate-500">等待辨識</span>}
                          {u.status === "parsing" && <span className="text-xs text-orange-700 inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />辨識中…</span>}
                          {u.status === "done" && <span className="rounded px-1.5 py-0.5 text-xs bg-slate-100 text-slate-700">{u.preview?.kind_label}</span>}
                          {u.status === "done" && u.preview?.kind === "pdf_forms" && <span className="text-xs text-slate-500">缺漏 {u.preview.missing?.length ?? 0}・低信心 {lowConfOf(u)}・提醒 {u.preview.warnings?.length ?? 0}</span>}
                          {u.status !== "parsing" && <button className="ml-auto text-xs underline text-slate-600" onClick={() => setUploads((l) => l.filter((x) => x.id !== u.id))} disabled={busy}>移除</button>}
                        </div>
                        {u.status === "error" && <div className="text-red-700 text-xs mt-1">{u.error}</div>}
                        {u.status === "done" && u.preview && <div className="mt-1"><InputDetail e={u.preview} /></div>}
                      </li>))}
                  </ul>
                  <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm space-y-2">
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                      <label className="inline-flex items-center gap-1"><input type="radio" name="umode" checked={umode === "one"} onChange={() => setUmode("one")} />合併為一個案件（{ready.length} 份）</label>
                      <label className="inline-flex items-center gap-1"><input type="radio" name="umode" checked={umode === "each"} onChange={() => setUmode("each")} />每份各建一案</label>
                      <label className="inline-flex items-center gap-1"><input type="radio" name="umode" checked={umode === "existing"} onChange={() => setUmode("existing")} />加入到既有案件</label>
                      {umode === "existing" && <select className="border rounded px-2 py-0.5" value={targetCase} onChange={(e) => setTargetCase(e.target.value)}><option value="">請選擇案件</option>{cases.filter((c) => !c.archived).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>}
                    </div>
                    {needsForm && ready.length > 0 && (
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div className="col-span-3 text-amber-800">沒有送審書表 PDF，請填案件基本資料：</div>
                        <label className="block"><span className="text-slate-500">案號 *</span><input className="border rounded px-2 py-1 w-full" value={nf.case_no} onChange={(e) => setNf({ ...nf, case_no: e.target.value })} /></label>
                        <label className="block"><span className="text-slate-500">估價基準日 *</span><VDateSelect value={nf.valuation_date} onChange={(v) => setNf({ ...nf, valuation_date: v })} /></label>
                        <label className="block"><span className="text-slate-500">鄉鎮市區</span><select className="border rounded px-2 py-1 w-full" value={nf.district} onChange={(e) => setNf({ ...nf, district: e.target.value })}>{NTPC_DISTRICTS.map((d) => <option key={d} value={`新北市${d}`}>新北市{d}</option>)}</select></label>
                      </div>)}
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs text-slate-600">{umode === "one" ? "書表 PDF 依區段與實例編號聯集、只補空白；清冊與實例覆蓋有值欄位；基準表匯入並套用；地籍圖、區段圖補真實界線。同格不同值會標「不一致」交人工確認。" : umode === "each" ? "每份檔各建立一個案件；沒有書表 PDF 的檔要先填上方基本資料。" : "把這批檔併進所選案件，之後可在該案的「輸入檔」卡片看到。"}</span>
                      <div className="ml-auto flex gap-2">
                        <Btn kind="ghost" onClick={() => setUploads([])} disabled={busy}>全部清除</Btn>
                        <Btn onClick={createFromUploads} disabled={!canCreate} busy={busy}>{umode === "one" ? `建立一個案件並開始審查（來源 ${ready.length} 份）→` : umode === "each" ? `建立 ${ready.length} 件案件 →` : "加入到案件 →"}</Btn>
                      </div>
                    </div>
                    {batchMsg && <div className="text-xs text-red-700">{batchMsg}</div>}
                  </div>
                </div>
              )}
            </div>
          )}

          {method === "lot" && (
            <div>
              <div className="text-xs text-slate-600 mb-3">系統找地籍界線、推定宗地屬性與區段範圍、推算勘查表、量測設施距離、從實價登錄選比較標的，再產生書表與填寫結果清單。</div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-x-3 gap-y-2 text-sm">
                <label className="block"><span className="text-xs text-slate-500">案號 *</span><input className="border rounded px-2 py-1 w-full" value={nc.case_no} onChange={(e) => setNc({ ...nc, case_no: e.target.value })} /></label>
                <label className="block"><span className="text-xs text-slate-500" title="查估辦法 §17 第 2 項：3 月 1 日或 9 月 1 日">估價基準日 *</span><VDateSelect value={nc.valuation_date} onChange={(v) => setNc({ ...nc, valuation_date: v })} /></label>
                <label className="block"><span className="text-xs text-slate-500">鄉鎮市區 *</span><select className="border rounded px-2 py-1 w-full" value={nc.district} onChange={(e) => setNc({ ...nc, district: e.target.value })}>{NTPC_DISTRICTS.map((d) => <option key={d} value={`新北市${d}`}>新北市{d}</option>)}</select></label>
                <label className="block"><span className="text-xs text-slate-500" title="沒有地號時改填下方「區段範圍」，系統會圍出區段並依查估辦法 §18 自動選比準地">比準地地號 *</span>
                  {(() => {
                    const dist = nc.district.replace("新北市", "");
                    const inDist = lots.filter((l) => !l.district || l.district === dist);          // 沒標區的（舊格式）全部列出
                    const useSelect = inDist.length > 0 && !manualLot;
                    return (<>
                      {useSelect ? <select className="border rounded px-2 py-1 w-full" value={nc.subject_parcel_id} onChange={(e) => setNc({ ...nc, subject_parcel_id: e.target.value })}>
                        <option value="">請選擇（{dist}地籍圖內 {inDist.length} 筆）</option>{Array.from(new Set(inDist.map((l) => l.section))).map((sec) => <optgroup key={sec} label={sec}>{inDist.filter((l) => l.section === sec).map((l) => <option key={l.parcel_id} value={l.parcel_id}>{l.parcel_id}</option>)}</optgroup>)}</select>
                        : <input className="border rounded px-2 py-1 w-full" placeholder={inDist.length ? "輸入地號（例：金美段489地號）" : `${dist}尚無地籍圖，輸入地號後請到「輸入資料」匯入地籍圖或在圖上定位`} value={nc.subject_parcel_id} onChange={(e) => setNc({ ...nc, subject_parcel_id: e.target.value })} />}
                      {inDist.length > 0 && <button type="button" className="text-xs text-slate-600 underline mt-0.5" onClick={() => { setManualLot(!manualLot); setNc({ ...nc, subject_parcel_id: "" }); }}>{manualLot ? "改從地籍圖選" : "地籍圖沒有這筆？手動輸入"}</button>}
                    </>);
                  })()}</label>
                <label className="block"><span className="text-xs text-slate-500">區段編號</span><input className="border rounded px-2 py-1 w-full" placeholder="空白則暫編 P001-00" value={nc.section_id} onChange={(e) => setNc({ ...nc, section_id: e.target.value })} /></label>
                <label className="block"><span className="text-xs text-slate-500">用地別</span><select className="border rounded px-2 py-1 w-full" value={nc.land_use} onChange={(e) => setNc({ ...nc, land_use: e.target.value })}>{["商業用地", "住宅用地", "工業用地", "農業用地", "其他用地"].map((x) => <option key={x}>{x}</option>)}</select></label>
                <label className="block col-span-2 md:col-span-3"><span className="text-xs text-slate-500">區段範圍（無地號時必填）</span><input className="border rounded px-2 py-1 w-full" placeholder="例：北側至金包里街，南側至中山路，西側至中正路，東側至福德街" value={nc.range_desc} onChange={(e) => setNc({ ...nc, range_desc: e.target.value })} /></label>
                <div className="col-span-2 md:col-span-3 mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
                  <label className="text-xs text-slate-700 inline-flex items-center gap-1" title="依地號找地籍界線、推定宗地屬性與區段範圍、推算勘查表、量測設施距離、從實價登錄選比較標的；地籍圖未匯入時會提示到輸入頁匯入或點圖"><input type="checkbox" checked={autoFill} onChange={(e) => setAutoFill(e.target.checked)} />建立後立即依地號產生書表（含實價登錄比較標的）</label>
                  <div className="ml-auto"><Btn onClick={createBlank} disabled={busy} busy={busy}>{autoFill ? "建立並產生 →" : "建立 →"}</Btn></div>
                </div>
                {ncMsg && <div className="col-span-2 md:col-span-3 text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded px-2 py-1">{ncMsg}</div>}
              </div>
            </div>
          )}

          {method === "example" && (
            <ul className="grid gap-2">
              {EXAMPLES.map((d) => (
                <li key={d.v}>
                  <button type="button" disabled={loading} onClick={async () => { await loadDemo(d.v); closeNew(); router.push("/sheets"); }} className="w-full text-left rounded-lg border border-slate-200 hover:border-[#ea580c] hover:bg-orange-50 px-4 py-3 disabled:opacity-50">
                    <div className="font-semibold">{d.title}</div><div className="text-xs text-slate-600 mt-0.5">{d.desc}</div>
                  </button>
                </li>))}
              {loading && <li className="text-xs text-slate-500">載入中…</li>}
            </ul>
          )}
        </Modal>
      )}
    </div>
  );
}
