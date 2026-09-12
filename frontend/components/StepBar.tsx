"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useCase } from "./CaseContext";
import { NAV, useStepStatus } from "./Sidebar";

/* 頂端步驟列：案件總覽 → ① 輸入資料 → ② 產出書表 → ③ 審查 → ④ 輸出。每個節點標示完成／進行中／未開始；上一步／下一步在頁首右側。 */
function Inner() {
  const path = usePathname();
  useSearchParams();
  const { rec } = useCase();
  const done = useStepStatus();
  if (path === "/dashboard" || !rec) return null;
  const q = `?case=${encodeURIComponent(rec.id)}`;
  const idx = NAV.findIndex((it) => it.match.includes(path));
  const href = (it: { href: string }) => it.href + (it.href === "/dashboard" ? "" : q);
  return (
    <ol className="no-print mb-3 flex items-center text-sm">
      {NAV.map((it, i) => { const active = i === idx; const ok = done[it.href]; return (
        <li key={it.href} className="flex-1 flex items-center min-w-0">
          <Link href={href(it)} className={`flex items-center gap-2 min-w-0 rounded-full pl-1 pr-3 py-1 border ${active ? "bg-[#ea580c] border-[#ea580c] text-white" : ok ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-white border-slate-300 text-slate-500"}`} title={it.sub}>
            <span className={`shrink-0 w-6 h-6 rounded-full text-xs leading-6 text-center ${active ? "bg-white text-[#ea580c]" : ok ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-600"}`}>{ok && !active ? "✓" : i === 0 ? "○" : String(i)}</span>
            <span className="truncate">{it.label.replace(/^[①②③④] /, "")}</span>
          </Link>
          {i < NAV.length - 1 && <span className={`flex-1 h-px mx-2 ${done[it.href] ? "bg-emerald-300" : "bg-slate-300"}`} />}
        </li>); })}
    </ol>
  );
}
export default function StepBar() { return <Suspense fallback={null}><Inner /></Suspense>; }
