"use client";
import { Fragment, useEffect, useMemo, useState } from "react";
import { Block, Doc, parseDoc, Section, splitName, STATUS_KINDS, StatusKind, statusKind, statusTokens } from "@/lib/mdsources";

/* 資料來源總表：讀 docs/05_data_sources.md（GET /api/docs/data_sources）解析後套版。左＝目錄與狀態篩選，右＝各章表格。 */

const BADGE: Record<StatusKind, string> = {
  offline: "bg-emerald-50 text-emerald-800 border-emerald-200",
  online: "bg-sky-50 text-sky-800 border-sky-200",
  apply: "bg-red-50 text-red-800 border-red-200",
  inferred: "bg-amber-50 text-amber-900 border-amber-200",
  fallback: "bg-slate-100 text-slate-700 border-slate-300",
  other: "bg-slate-50 text-slate-500 border-slate-200",
};
const NUM2 = (n: number) => String(n).padStart(2, "0");

/* 行內：`code`、**粗體**、http(s) 連結 */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(`[^`]*`)/g);
  return (<>{parts.map((p, i) => {
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="src-code">{p.slice(1, -1)}</code>;
    const sub = p.split(/(\*\*[^*]+\*\*|https?:\/\/[^\s）)、；;，,]+)/g);
    return <Fragment key={i}>{sub.map((q, j) => {
      if (/^\*\*[^*]+\*\*$/.test(q)) return <b key={j}>{q.slice(2, -2)}</b>;
      if (/^https?:\/\//.test(q)) return <a key={j} href={q} target="_blank" rel="noreferrer" className="underline decoration-dotted break-all hover:text-[#c2410c]">{q}</a>;
      return <Fragment key={j}>{q}</Fragment>;
    })}</Fragment>;
  })}</>);
}

function StatusCell({ cell }: { cell: string }) {
  return (<span className="inline-flex flex-wrap gap-1">{statusTokens(cell).map((t, i) => <span key={i} className={`inline-block border rounded px-1.5 py-0.5 text-[11px] leading-tight whitespace-nowrap ${BADGE[statusKind(t)]}`}>{t}</span>)}</span>);
}

function Table({ headers, rows, active }: { headers: string[]; rows: string[][]; active: Set<StatusKind> }) {
  const si = headers.findIndex((h) => h.includes("狀態"));
  const ni = Math.max(0, headers.findIndex((h) => /名稱|資料集|來源|供應商/.test(h)));   // 名稱欄（地籍幾何表第一欄是「順位」）
  const shown = active.size === 0 || si < 0 ? rows : rows.filter((r) => statusTokens(r[si] || "").some((t) => active.has(statusKind(t))));
  if (!shown.length) return <div className="text-sm text-slate-500 py-3 border-t-2 border-[#2a1d14]">這一章沒有符合篩選的項目。</div>;
  const w = (i: number) => {
    const h = headers[i];
    if (/順位/.test(h)) return "w-10";
    if (i === ni) return "w-[21%]";
    if (i === si) return "w-[8%]";
    if (/機關|提供者/.test(h)) return "w-[11%]";
    if (/用途|說明|設定/.test(h)) return "w-[24%]";
    return "";   // 位置／取得方式：剩餘寬度
  };
  return (
    <div className="overflow-x-auto">
      <table className="src-table w-full text-sm">
        <thead><tr>{headers.map((h, i) => <th key={i} className={`${w(i)} text-left font-normal text-slate-500 text-xs pb-2 pr-3 align-bottom`}>{h}</th>)}</tr></thead>
        <tbody>
          {shown.map((r, ri) => (
            <tr key={ri}>
              {headers.map((_, ci) => {
                const cell = r[ci] ?? "";
                if (/順位/.test(headers[ci])) return <td key={ci} className="align-top py-3 pr-3 font-mono text-slate-500">{cell}</td>;
                if (ci === ni) { const { title, note } = splitName(cell); return <td key={ci} className="align-top py-3 pr-3"><div className="font-semibold leading-snug"><Inline text={title} /></div>{note && <div className="text-xs text-slate-500 mt-0.5 leading-snug"><Inline text={note} /></div>}</td>; }
                if (ci === si) return <td key={ci} className="align-top py-3 pr-3"><StatusCell cell={cell} /></td>;
                return <td key={ci} className="align-top py-3 pr-3 leading-relaxed"><Inline text={cell} /></td>;
              })}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function BlockView({ b, active }: { b: Block; active: Set<StatusKind> }) {
  if (b.kind === "p") return <p className="text-sm text-slate-700 leading-relaxed mb-3 max-w-3xl"><Inline text={b.text} /></p>;
  if (b.kind === "list") return <ul className="text-sm text-slate-700 leading-relaxed list-disc pl-5 mb-3 max-w-3xl space-y-1">{b.items.map((it, i) => <li key={i}><Inline text={it} /></li>)}</ul>;
  return <div className="mb-4"><Table headers={b.headers} rows={b.rows} active={active} /></div>;
}

export default function Sources() {
  const [doc, setDoc] = useState<Doc | null>(null);
  const [meta, setMeta] = useState<{ file: string; modified: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [active, setActive] = useState<Set<StatusKind>>(new Set());
  useEffect(() => {
    fetch("/api/docs/data_sources").then(async (r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((j) => { setDoc(parseDoc(j.markdown)); setMeta({ file: j.file, modified: j.modified }); })
      .catch((e) => setErr(String(e?.message || e)));
  }, []);
  const numbered = useMemo(() => (doc?.sections || []).filter((s) => s.numeral), [doc]);
  const appendix = useMemo(() => (doc?.sections || []).filter((s) => !s.numeral), [doc]);
  const toggle = (k: StatusKind) => setActive((prev) => { const n = new Set(prev); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const numberOf = (s: Section) => NUM2(numbered.indexOf(s) + 1);

  return (
    <div className="sources">
      <header className="mb-8">
        <div className="text-xs font-semibold tracking-wider text-[#c2410c] mb-2">土地徵收補償市價查估 · 估價案件審查輔助系統</div>
        <h1 className="src-serif text-4xl font-bold leading-tight mb-4">查估審查系統資料來源總表</h1>
        {doc?.intro.map((t, i) => <p key={i} className="text-base leading-relaxed text-slate-700 max-w-3xl mb-1"><Inline text={t} /></p>)}
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
          <span>版本 <b className="text-[#2a1d14]">{meta?.modified || "—"}</b></span>
          <span>依據 <b className="text-[#2a1d14]">{meta?.file || "docs/05_data_sources.md"}</b>、docs/07、docs/08、rules/*.json、backend/app 原始碼</span>
          <span>共 <b className="text-[#2a1d14]">{numbered.length}</b> 類</span>
        </div>
        <hr className="mt-4 border-0 border-t-2 border-[#2a1d14]" />
      </header>

      {err && <div className="bg-red-50 border border-red-200 text-red-800 rounded p-3 text-sm mb-3">讀取文件失敗：{err}</div>}
      {!doc && !err && <div className="text-sm text-slate-500">載入中…</div>}

      {doc && (
        <div className="flex gap-10 items-start">
          <aside className="no-print w-52 shrink-0 sticky top-4">
            <div className="text-xs text-slate-500 mb-2">目錄</div>
            <ol className="border-l border-slate-300">
              {numbered.map((s) => (
                <li key={s.id}><a href={`#${s.id}`} className="flex items-baseline gap-3 pl-4 py-1.5 text-sm hover:text-[#c2410c]"><span className="text-slate-400 w-4 text-center">{s.numeral}</span><span>{s.title}</span><span className="text-xs text-slate-400">{s.rowCount || ""}</span></a></li>))}
            </ol>
            <div className="mt-6 pt-4 border-t border-slate-200">
              <div className="text-xs text-slate-500 mb-2">只看</div>
              <div className="flex flex-wrap gap-1.5">
                {STATUS_KINDS.map((k) => <button key={k.kind} type="button" aria-pressed={active.has(k.kind)} onClick={() => toggle(k.kind)} className={`border rounded-full px-2.5 py-0.5 text-xs ${BADGE[k.kind]} ${active.has(k.kind) ? "ring-2 ring-offset-1 ring-[#ea580c]" : "opacity-80"}`}>{k.label}</button>)}
              </div>
              <div className="text-[11px] text-slate-500 mt-2 leading-relaxed">再按一次取消。未按任何一個時顯示全部。</div>
            </div>
          </aside>

          <div className="flex-1 min-w-0">
            {numbered.map((s) => (
              <section key={s.id} id={s.id} className="mb-12 scroll-mt-4">
                <h2 className="src-serif text-2xl font-bold mb-2 flex items-baseline gap-3"><span className="font-mono text-sm font-normal text-[#c2410c]">{numberOf(s)}</span>{s.title}</h2>
                {s.blocks.map((b, i) => <BlockView key={i} b={b} active={active} />)}
              </section>))}
            {appendix.length > 0 && (
              <div className="mt-4 pt-6 border-t-2 border-[#2a1d14]">
                {appendix.map((s) => (
                  <section key={s.id} id={s.id} className="mb-8 scroll-mt-4">
                    <h2 className="src-serif text-xl font-bold mb-2">{s.title}</h2>
                    {s.blocks.map((b, i) => <BlockView key={i} b={b} active={active} />)}
                  </section>))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
