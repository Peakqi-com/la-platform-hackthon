"use client";
import { useRef, useState } from "react";
import { useCase } from "./CaseContext";
import { Card } from "./ui";
import { pathLabel } from "@/lib/labels";
import { Any, api, InputEntry, InputResult, InputsSummary } from "@/lib/api";

/* 輸入資料徽章：案件清單與案件列共用。有＝實色、無＝淡灰；滑過顯示來源檔名。 */
export function InputBadges({ summary, compact = false }: { summary?: InputsSummary | null; compact?: boolean }) {
  if (!summary) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className={`inline-flex flex-wrap gap-1 ${compact ? "" : "max-w-[14rem]"}`}>
      {summary.items.map((it) => (
        <span key={it.key} title={it.present ? `${it.full || it.label}：${it.source || "已輸入"}` : `${it.full || it.label}：尚未輸入`}
          className={`rounded px-1 py-0.5 text-[11px] leading-none border ${it.present ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-slate-50 border-slate-200 text-slate-400"}`}>{it.label}</span>))}
      {summary.n_conflicts > 0 && <span className="rounded px-1 py-0.5 text-[11px] leading-none border bg-amber-50 border-amber-300 text-amber-900" title="輸入檔之間有不一致的欄位，到「③ 審查」看明細">不一致 {summary.n_conflicts}</span>}
    </span>
  );
}

export const fmtSize = (n?: number) => (n == null ? "" : n > 1_048_576 ? `${(n / 1_048_576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const fmtT = (t?: string | null) => (t ? String(t).replace("T", " ").slice(0, 16) : "—");
const PAGE_ZH: Record<string, string> = { t1: "勘查表", t5: "區域因素分析表", t4: "比較法估價表", map: "圖說", other: "其他" };
const METHOD_ZH: Record<string, string> = { text: "文字讀取", vision: "影像辨識", "text+vision": "文字＋影像", none: "未讀取" };

export function pagesText(pages?: InputEntry["pages"]) {
  return (pages || []).filter((p) => p.kind !== "other" || p.method !== "none").map((p) => `第${p.page}頁 ${PAGE_ZH[p.kind] || p.kind}（${METHOD_ZH[p.method] || p.method}）`).join("；") || "—";
}

/* 一份輸入檔的結果摘要（首頁辨識結果與案件頁輸入檔清單共用） */
export function InputDetail({ e }: { e: InputResult | InputEntry }) {
  return (
    <div className="text-xs text-slate-700 space-y-0.5">
      {e.kind === "pdf_forms" && <div><span className="text-slate-500">頁面：</span>{pagesText(e.pages)}</div>}
      {e.summary && <div><span className="text-slate-500">併入：</span>{e.summary}</div>}
      {(e.notes?.length ?? 0) > 0 && <div className="text-slate-600">{e.notes!.slice(0, 3).join("；")}</div>}
      {(e.missing?.length ?? 0) > 0 && <div className="text-slate-600" title="這份檔本身沒讀到的欄位；由其他輸入檔補上的不算缺漏，案件整體的缺漏看案件列「這一案還缺」">此檔未含 {e.missing!.length} 欄：{e.missing!.slice(0, 8).map(pathLabel).join("、")}{e.missing!.length > 8 ? "…" : ""}</div>}
      {(e.conflicts?.length ?? 0) > 0 && <details><summary className="cursor-pointer text-amber-900">與先前檔案不一致 {e.conflicts!.length} 處（保留先前的值，需人工確認）</summary>
        <ul className="font-mono text-[11px] mt-1 list-disc pl-4">{e.conflicts!.slice(0, 20).map((c, i) => <li key={i}>{pathLabel(c.path)}：保留 {String(c.kept ?? "（空）")}，此檔 {String(c.incoming ?? "（空）")}</li>)}</ul></details>}
      {(e.overrides?.length ?? 0) > 0 && <details><summary className="cursor-pointer text-slate-700">覆蓋既有值 {e.overrides!.length} 欄</summary>
        <ul className="font-mono text-[11px] mt-1 list-disc pl-4">{e.overrides!.slice(0, 20).map((c, i) => <li key={i}>{pathLabel(c.path)}：{String(c.old ?? "（空）")} → {String(c.new ?? "（空）")}</li>)}</ul></details>}
      {(e.unmatched?.length ?? 0) > 0 && <div className="text-rose-700">對不到：{e.unmatched!.slice(0, 6).join("、")}{e.unmatched!.length > 6 ? "…" : ""}</div>}
      {(e.warnings?.length ?? 0) > 0 && <details><summary className="cursor-pointer text-slate-500">提醒 {e.warnings!.length}</summary><ul className="list-disc pl-4 mt-1">{e.warnings!.slice(0, 8).map((w, i) => <li key={i}>{w}</li>)}</ul></details>}
    </div>
  );
}

/* 案件頁「輸入檔」卡片：這一案由哪些檔組成；可再加入、移除（移除＝其餘檔重新併入）、下載原檔。 */
export function InputsCard({ onChanged }: { onChanged?: () => Promise<void> | void }) {
  const { rec, loadCase, generate, refreshList } = useCase();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [pendingRemove, setPendingRemove] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  if (!rec) return null;
  const inputs = rec.inputs || [];
  async function add(files: FileList | File[] | null | undefined) {
    const list = Array.from(files || []); if (!rec || !list.length) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api.addInputs(rec.id, list);
      const ok = r.results.filter((x) => !x.error && !x.skipped).length; const skipped = r.results.filter((x) => x.skipped); const failed = r.results.filter((x) => x.error);
      await loadCase(rec.id); await refreshList();
      try { await generate(); } catch { /* 產出失敗留在案件列提示 */ }
      await onChanged?.();
      setMsg(`已加入 ${ok} 份${skipped.length ? `；略過 ${skipped.length} 份（${skipped.map((x) => x.filename).join("、")}，已加入過）` : ""}${failed.length ? `；失敗 ${failed.length} 份：${failed.map((x) => `${x.filename}（${x.error}）`).join("、")}` : ""}。書表已重新產生。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }
  async function remove(iid: string) {
    if (!rec) return; setBusy(true); setMsg(null); setPendingRemove(null);
    try {
      const r = await api.removeInput(rec.id, iid);
      await loadCase(rec.id); await refreshList();
      try { await generate(); } catch { /* ignore */ }
      await onChanged?.();
      setMsg(`已移除 ${r.removed.filename}，其餘 ${r.replayed.length} 份已重新併入${r.failed.length ? `；失敗：${r.failed.join("；")}` : ""}。之後手動修改過的欄位會回到檔案裡的值，請再確認。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  return (
    <Card title={`輸入檔（${inputs.length}）`} hint="這一案由哪些檔案組成。書表 PDF 依區段與實例編號聯集、只補空白，同格不同值記「不一致」；清冊與實例覆蓋有值欄位；基準表匯入後直接套用；地籍圖、區段圖補真實界線。移除一份會回到第一份併入前的狀態，再把其餘檔重新併入。"
      right={<><input ref={fileRef} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.json,.geojson,.kml,.gml,.xml,.zip" hidden onChange={(e) => add(e.target.files)} />
        <button className="px-3 py-1.5 rounded text-sm btn-io-import disabled:opacity-50" disabled={busy} onClick={() => fileRef.current?.click()} title="送審書表 PDF、宗地清冊、買賣實例、評價基準明細表、地籍圖、地價區段圖；可一次選多份">⬆ 加入輸入檔</button></>}>
      <div className={`rounded border border-dashed px-3 py-2 text-xs mb-2 ${drag ? "border-[#ea580c] bg-orange-50" : "border-slate-300 text-slate-500"}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}>
        {busy ? <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />處理中…</span> : "也可把檔案拖到這裡（可多份）。"}
      </div>
      {inputs.length === 0 ? <div className="text-sm text-slate-500">尚無輸入檔。{rec.origin?.startsWith("demo") ? "此案為範例，資料由系統載入。" : rec.origin === "from_lot" ? "此案依地號產生。" : ""}</div> : (
        <ol className="space-y-2">
          {inputs.map((e, i) => (
            <li key={e.id} className="rounded border border-slate-200 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-slate-400 text-xs">{i + 1}.</span>
                <span className="font-medium">{e.filename}</span>
                <span className="rounded px-1.5 py-0.5 text-xs bg-slate-100 text-slate-700">{e.kind_label}</span>
                <span className="text-xs text-slate-500">{fmtT(e.at)}{e.actor ? `・${e.actor}` : ""}{e.size ? `・${fmtSize(e.size)}` : ""}</span>
                <span className="ml-auto flex items-center gap-2 text-xs">
                  {e.path && <a className="underline text-slate-600" href={api.inputFileUrl(rec.id, e.id)} title="下載原檔">⬇ 原檔</a>}
                  {pendingRemove === e.id
                    ? <span className="inline-flex items-center gap-1 bg-red-50 border border-red-200 rounded px-2 py-0.5"><span className="text-red-800">移除並重新併入其餘 {inputs.length - 1} 份？</span><button className="px-2 py-0.5 rounded bg-red-600 text-white" disabled={busy} onClick={() => remove(e.id)}>確定</button><button className="underline" onClick={() => setPendingRemove(null)}>取消</button></span>
                    : <button className="underline text-red-700 disabled:opacity-50" disabled={busy || !!e.legacy} title={e.legacy ? "舊版建案留下的紀錄，沒有原檔可重併" : "移除這份檔，其餘檔重新併入"} onClick={() => setPendingRemove(e.id)}>移除</button>}
                </span>
              </div>
              <div className="mt-1"><InputDetail e={e} /></div>
            </li>))}
        </ol>)}
      {msg && <div className="text-xs mt-2 bg-slate-50 border rounded p-2 flex items-start gap-2">{msg}<button className="underline ml-auto shrink-0" onClick={() => setMsg(null)}>關閉</button></div>}
    </Card>
  );
}
