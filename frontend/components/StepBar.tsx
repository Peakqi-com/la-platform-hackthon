"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useCase } from "./CaseContext";
import { NAV, useStepStatus } from "./Sidebar";

/* 頂端步驟列：案件總覽 → ① 輸入資料 → ② 產出書表 → ③ 審查 → ④ 輸出。每個節點標示完成／進行中／未開始，兩端是上一步、下一步。 */
function Inner() {
  const path = usePathname();
  useSearchParams();
  const { rec } = useCase();
  const done = useStepStatus();
  if (path === "/" || !rec) return null;
  const q = `?case=${encodeURIComponent(rec.id)}`;
  const idx = NAV.findIndex((it) => it.match.includes(path));
  const prev = idx > 0 ? NAV[idx - 1] : null;
  const next = idx >= 0 && idx < NAV.length - 1 ? NAV[idx + 1] : null;
  const href = (it: { href: string }) => it.href + (it.href === "/" ? "" : q);
  return (
    <div className="no-print mb-4 flex items-center gap-2 text-sm">
      {prev ? <Link href={href(prev)} className="shrink-0 px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-xs whitespace-nowrap">← {prev.label.replace(/^[①②③④] /, "")}</Link> : <span className="w-16" />}
      <ol className="flex-1 flex items-center">
        {NAV.map((it, i) => { const active = i === idx; const ok = done[it.href]; return (
          <li key={it.href} className="flex-1 flex items-center min-w-0">
            <Link href={href(it)} className={`flex items-center gap-2 min-w-0 rounded-full px-3 py-1.5 border ${active ? "bg-[#ea580c] border-[#ea580c] text-white" : ok ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-white border-slate-300 text-slate-500"}`} title={it.sub}>
              <span className={`shrink-0 w-5 h-5 rounded-full text-xs leading-5 text-center ${active ? "bg-white text-[#ea580c]" : ok ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-600"}`}>{ok && !active ? "✓" : i === 0 ? "○" : String(i)}</span>
              <span className="truncate">{it.label.replace(/^[①②③④] /, "")}</span>
            </Link>
            {i < NAV.length - 1 && <span className={`flex-1 h-px mx-1 ${done[it.href] ? "bg-emerald-300" : "bg-slate-300"}`} />}
          </li>); })}
      </ol>
      {next ? <Link href={href(next)} className="shrink-0 px-2 py-1 rounded border border-slate-300 bg-white hover:bg-slate-50 text-xs whitespace-nowrap">{next.label.replace(/^[①②③④] /, "")} →</Link> : <span className="w-16" />}
    </div>
  );
}
export default function StepBar() { return <Suspense fallback={null}><Inner /></Suspense>; }
