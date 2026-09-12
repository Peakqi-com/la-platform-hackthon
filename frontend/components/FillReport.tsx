"use client";
import { useEffect, useState } from "react";
import { Any, api } from "@/lib/api";
import { Help } from "./ui";

/* 填寫結果清單：一鍵產生後逐欄列出「值／狀態／來源／說明」。狀態：資料（匯入或人工）、量測（設施資料庫與路網）、推定（地籍界線、路網、分區圖，需確認）、空白（資料不足）。 */
const STATUS_CLS: Record<string, string> = { 資料: "bg-slate-100 text-slate-700", 量測: "bg-sky-100 text-sky-800", 推定: "bg-amber-100 text-amber-900", 空白: "bg-rose-100 text-rose-800" };
type Row = { label: string; field?: string; value: string; status: string; source: string; note: string };

function Table({ rows, filter }: { rows: Row[]; filter: string }) {
  const shown = rows.filter((r) => filter === "全部" || r.status === filter);
  if (!shown.length) return <div className="text-xs text-slate-500 px-1 py-1">（無）</div>;
  return (
    <table className="grid text-[11px] w-full"><thead><tr><th className="w-44">欄位</th><th>值</th><th className="w-12">狀態</th><th className="w-40">來源</th><th>說明</th></tr></thead>
      <tbody>{shown.map((r, i) => <tr key={i}><td>{r.label}</td><td className="font-mono whitespace-normal">{r.value || "—"}</td><td><span className={`rounded px-1 py-0.5 ${STATUS_CLS[r.status] || ""}`}>{r.status}</span></td><td className="whitespace-normal">{r.source}</td><td className="whitespace-normal text-slate-600">{r.note}</td></tr>)}</tbody></table>
  );
}

export default function FillReport({ caseId, refreshKey = 0 }: { caseId: string; refreshKey?: number }) {
  const [rep, setRep] = useState<Any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState("全部");
  const [open, setOpen] = useState<Record<string, boolean>>({ subject: true, section: true, comps: true });
  useEffect(() => { setErr(null); api.fillReport(caseId).then(setRep).catch((e) => setErr(String(e.message || e))); }, [caseId, refreshKey]);
  if (err) return <div className="text-xs text-rose-700">{err}</div>;
  if (!rep) return <div className="text-xs text-slate-500">整理填寫結果…</div>;
  const c = rep.counts || {};
  return (
    <div className="text-sm border border-orange-200 rounded bg-white p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <b>填寫結果清單</b>
        <span className="text-[11px] text-slate-500 flex items-center gap-1" title="資料：匯入或人工填載；量測：設施資料庫與路網；推定：地籍界線、路網、分區圖推算，需確認；空白：資料不足，需人工填載">
          {(["資料", "量測", "推定", "空白"] as const).map((k) => <span key={k} className={`rounded px-1 ${STATUS_CLS[k]}`}>{k}</span>)}</span>
        {["全部", "資料", "量測", "推定", "空白"].map((k) => <button key={k} className={`rounded px-2 py-0.5 text-xs border ${filter === k ? "bg-[#ea580c] text-white border-[#ea580c]" : "bg-white border-slate-300"}`} onClick={() => setFilter(k)}>{k}{k !== "全部" && ` ${c[k] ?? 0}`}</button>)}
        <Help>推定與空白請逐項確認；數字欄位皆由規則引擎依基準表核算，這裡只列事實欄位。</Help>
      </div>
      {rep.last_fill && <div className="text-xs text-slate-600">最近一次依地號產生：{String(rep.last_fill.at || "").replace("T", " ").slice(0, 16)}　{rep.last_fill.parcel_id}<ul className="mt-1 space-y-0.5">{(rep.last_fill.steps || []).map((s: Any) => <li key={s.step} className={s.ok ? "text-emerald-800" : "text-rose-700"}>{s.ok ? "✓" : "✗"} {s.step}：{s.note}</li>)}</ul></div>}
      {rep.gaps?.length > 0 && <div className="text-xs bg-rose-50 border border-rose-200 rounded p-2"><b className="text-rose-800">資料不足，需人工填載（{rep.gaps.length}）</b>：{rep.gaps.join("、")}</div>}
      <Table rows={rep.head} filter={filter} />
      <details open={open.subject} onToggle={(e) => setOpen({ ...open, subject: (e.target as HTMLDetailsElement).open })}><summary className="cursor-pointer text-xs font-medium">比準地個別因素（{rep.subject.length} 欄）</summary><Table rows={rep.subject} filter={filter} /></details>
      <details open={open.section} onToggle={(e) => setOpen({ ...open, section: (e.target as HTMLDetailsElement).open })}><summary className="cursor-pointer text-xs font-medium">地價區段勘查表 {rep.section_id}（{rep.section.length} 欄）</summary><Table rows={rep.section} filter={filter} /></details>
      <details open={open.comps} onToggle={(e) => setOpen({ ...open, comps: (e.target as HTMLDetailsElement).open })}><summary className="cursor-pointer text-xs font-medium">比較標的（{rep.comparables.length} 件）</summary>
        {rep.comparables.length ? rep.comparables.map((cp: Any) => (
          <div key={cp.comp_no} className="mt-1 border-t border-slate-200 pt-1">
            <div className="text-xs"><b>比較標的{cp.comp_no} {cp.parcel_id}</b>　交易日期 {cp.transaction_date || "—"}　正常單價 {cp.normal_unit_price ? Number(cp.normal_unit_price).toLocaleString("zh-TW") : "—"} 元/m²　期日調整 {cp.date_adjustment ?? "—"}%</div>
            <div className="text-[11px] text-slate-600">選取依據：{cp.basis}{cp.flags ? `；${cp.flags}` : ""}</div>
            {cp.date_note && <div className="text-[11px] text-slate-600">期日調整：{cp.date_note}</div>}
            <Table rows={cp.rows} filter={filter} />
          </div>)) : <div className="text-xs text-rose-700 px-1">尚無比較標的：到「宗地條件與買賣實例」按「自動蒐集比較標的（實價登錄）」或人工填寫。</div>}
      </details>
    </div>
  );
}
