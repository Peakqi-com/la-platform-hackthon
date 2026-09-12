"use client";
import { pathLabel } from "@/lib/labels";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCase } from "./CaseContext";
import { Any, api, getActor, STATUS_LABEL } from "@/lib/api";

const fmt = (s?: string | null) => (s ? String(s).replace("T", " ").slice(0, 16) : "—");

/* 案件列：固定在每頁頂端。輸入最後修改／產出最後產生兩個時間對照，輸入比產出新＝產出已過期。 */
export default function CaseBar() {
  const { rec, stale, generating, generate, reset, clear, duplicate, patch } = useCase();
  const path = usePathname();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<Any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [noActor, setNoActor] = useState(false);
  const [todo, setTodo] = useState<Any>(null);      // 這一案還缺什麼（/todo），案件或產出變動時重抓
  useEffect(() => { if (rec) api.todo(rec.id).then(setTodo).catch(() => setTodo(null)); else setTodo(null); }, [rec?.id, rec?.updated_at, rec?.outputs?.generated_at]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const chk = () => setNoActor(!getActor().name); chk(); window.addEventListener("storage", chk); const t = setInterval(chk, 1500); return () => { window.removeEventListener("storage", chk); clearInterval(t); }; }, []);
  if (!rec || path === "/") return null;   // 首頁是總覽，不顯示單一案件
  async function askReset() {
    if (!rec) return; setBusy(true);
    try { setConfirm(await api.resetPreview(rec.id)); } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function doReset() {
    setBusy(true);
    try { await reset(); setConfirm(null); setMsg("已重置：輸入回到原始快照，裁決與產出已清除，狀態回草稿。"); } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function doClear() {
    setBusy(true);
    try { await clear(); setConfirm(null); setMsg("已清空：宗地、比較標的、勘查表、送審書表、裁決與產出全部清除，只留案件基本資料與區段編號。請到「① 輸入資料」填比準地地號後按「依地號產生」。"); } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function saveAs() {
    if (!rec) return;
    const name = window.prompt("另存為新案件，請輸入案件名稱：", `${rec.name}（副本）`);
    if (name === null) return;
    setBusy(true);
    try { await duplicate(rec.id, name || undefined); setMsg("已另存為新案件並切換過去；原案件未變更。"); } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  const st = rec.status || "draft";
  return (
    <div className="no-print mb-4 bg-white border border-slate-200 rounded-lg px-4 py-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
      <div className="font-semibold truncate max-w-[28rem]" title={rec.name}>{rec.name}</div>
      <select value={st} disabled={busy} onChange={async (e) => { setBusy(true); try { await patch({ status: e.target.value }); setMsg(`狀態已改為「${STATUS_LABEL[e.target.value]}」，已寫入操作紀錄。`); setTimeout(() => setMsg(null), 2500); } catch (err: Any) { setMsg(String(err.message || err)); } finally { setBusy(false); } }} title="案件狀態：草稿／審查中／已完成（會寫入操作紀錄）" className={`rounded px-1.5 py-0.5 text-xs border-0 ${st === "done" ? "bg-emerald-100 text-emerald-800" : st === "reviewing" ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-700"}`}>{Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
      <div className="text-xs text-slate-600">輸入最後修改 <span className="font-mono">{fmt(rec.input_updated_at || rec.updated_at)}</span></div>
      <Link href={`/input?tab=case&case=${encodeURIComponent(rec.id)}`} className="text-xs text-slate-600 hover:text-[#c2410c]" title={(rec.inputs || []).length ? `輸入檔：${(rec.inputs || []).map((i) => `${i.filename}（${i.kind_label}）`).join("、")}` : "這一案沒有輸入檔（範例或依地號產生）；到 ① 可加入"}>輸入檔 <span className="font-mono">{(rec.inputs || []).length}</span> 份{(rec.inputs || []).some((i) => (i.conflicts || []).length) ? <span className="ml-1 rounded px-1 bg-amber-100 text-amber-900 border border-amber-300">有不一致</span> : null}</Link>
      <div className="text-xs text-slate-600">產出最後產生 <span className="font-mono">{fmt(rec.outputs?.generated_at)}</span></div>
      {stale ? <span className="rounded px-1.5 py-0.5 text-xs bg-amber-100 text-amber-900 border border-amber-300">產出已過期</span> : rec.outputs ? <span className="rounded px-1.5 py-0.5 text-xs bg-emerald-50 text-emerald-800 border border-emerald-200">產出為最新</span> : null}
      <div className="ml-auto flex items-center gap-2">
        <button onClick={() => generate().catch((e: Any) => setMsg(`重新產生書表失敗：${String(e?.message || e)}`))} disabled={generating || busy} className={`px-3 py-1.5 rounded text-sm whitespace-nowrap disabled:opacity-50 inline-flex items-center gap-1 ${stale ? "bg-[#ea580c] text-white hover:bg-[#c2410c]" : "bg-white border border-slate-300 hover:bg-slate-50"}`} title="依目前輸入重新核算三張書表與審查結果，並記錄產生時間">{generating && <span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />}{generating ? "產生中…" : "重新產生書表"}</button>
        <details className="relative">
          <summary className="list-none cursor-pointer px-3 py-1.5 rounded text-sm whitespace-nowrap bg-white border border-slate-300 hover:bg-slate-50">更多 ▾</summary>
          <div className="absolute right-0 mt-1 z-[1500] bg-white border border-slate-200 rounded shadow-lg text-sm min-w-[10rem]">
            <button onClick={saveAs} disabled={busy} className="block w-full text-left px-3 py-2 hover:bg-slate-50 disabled:opacity-50" title="複製一份成新案件再改，原案件不動">另存為新案件</button>
            <button onClick={askReset} disabled={busy} className="block w-full text-left px-3 py-2 text-red-700 hover:bg-red-50 disabled:opacity-50" title="回到載入時的原始輸入或清空重填">重置案件…</button>
          </div>
        </details>
      </div>
      {todo && (todo.items.length ? (
        <div className="basis-full text-xs flex flex-wrap items-center gap-1.5">
          <span className="text-slate-600">這一案還缺：</span>
          {todo.items.map((it: Any) => <Link key={it.key} href={it.href} className={`rounded px-2 py-0.5 border hover:underline ${it.level === "error" ? "bg-rose-50 border-rose-200 text-rose-800" : it.level === "warn" ? "bg-amber-50 border-amber-200 text-amber-900" : "bg-slate-50 border-slate-200 text-slate-700"}`}>{it.label}{it.count != null ? ` ${it.count}` : ""}</Link>)}
        </div>
      ) : <div className="basis-full text-xs text-emerald-700">這一案沒有待辦：可到「④ 輸出」下載。</div>)}
      {noActor && <div className="basis-full text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2 py-1">尚未填操作身分：請在左下角填姓名並選角色，裁決、意見書落款與操作紀錄才會記到人。</div>}
      {msg && <div className="basis-full text-xs text-slate-700">{msg} <button className="underline ml-1" onClick={() => setMsg(null)}>關閉</button></div>}
      {confirm && (
        <div className="fixed inset-0 z-[2000] bg-black/40 flex items-center justify-center" onClick={() => setConfirm(null)}>
          <div className="bg-white rounded-lg shadow-xl p-5 w-[34rem] max-w-[92vw] text-sm" onClick={(e) => e.stopPropagation()}>
            <div className="font-semibold text-base mb-2">重置案件「{rec.name}」？</div>
            <div className="text-slate-700 mb-3">兩種方式，都會寫入操作紀錄且無法復原；若只是想試算，請改用「另存為新案件」。<br />「回到原始輸入」：回到 <span className="font-mono">{fmt(confirm.original_at)}</span> 載入時的內容。<br />「清空重填」：只留案件基本資料、區段編號與已匯入的地籍圖／區段圖，其餘全部清空，之後用「依地號產生」重新建立。</div>
            <ul className="list-disc pl-5 space-y-1 mb-3">
              <li>輸入變更 <b>{confirm.n_input_changes}</b> 處{confirm.input_changes?.length ? <details className="mt-1"><summary className="cursor-pointer text-slate-600 text-xs">明細</summary><ul className="font-mono text-[11px] mt-1">{confirm.input_changes.map((c: Any, i: number) => <li key={i}>{pathLabel(c.path)}：{String(c.old ?? "（空）")} → {String(c.new ?? "（空）")}</li>)}</ul></details> : null}</li>
              <li>承辦裁決 <b>{confirm.n_decisions}</b> 筆</li>
              <li>產出（書表核算與審查結果，{fmt(confirm.generated_at)} 產生）</li>
              <li>狀態 {STATUS_LABEL[confirm.status] || confirm.status} → 草稿</li>
            </ul>
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 rounded border border-slate-300" onClick={() => setConfirm(null)}>取消</button>
              <button className="px-3 py-1.5 rounded bg-white border border-red-300 text-red-700 hover:bg-red-50 disabled:opacity-50" disabled={busy} onClick={doClear} title="清空宗地、比較標的、勘查表、送審書表、裁決與產出；保留案件基本資料與區段編號">清空重填</button>
              <button className="px-3 py-1.5 rounded bg-red-600 text-white disabled:opacity-50" disabled={busy} onClick={doReset}>回到原始輸入</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
