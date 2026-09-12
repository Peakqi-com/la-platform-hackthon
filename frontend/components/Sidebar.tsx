"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { findingKey } from "@/lib/api";
import { useCase } from "./CaseContext";
import { Help } from "./ui";
import ActorBox from "./Actor";

/* 側邊欄五項：案件總覽 → ① 輸入資料 → ② 產出書表 → ③ 審查 → ④ 輸出。勾號＝該段已完成。 */
export const NAV: { href: string; match: string[]; label: string; sub?: string }[] = [
  { href: "/", match: ["/"], label: "案件總覽", sub: "上傳送審書表、開啟案件" },
  { href: "/input", match: ["/input", "/case", "/parcels", "/rules"], label: "① 輸入資料", sub: "基準表・基本資料・宗地與實例" },
  { href: "/sheets", match: ["/sheets", "/table1", "/tables", "/map"], label: "② 產出書表", sub: "六頁書表預覽（照範本）・地圖" },
  { href: "/review", match: ["/review", "/report"], label: "③ 審查", sub: "逐項比對・承辦裁決・意見書" },
  { href: "/export", match: ["/export"], label: "④ 輸出", sub: "下載全部" },
];

/* 各段完成狀態（側邊欄勾號與頂端步驟列共用）。 */
export function useStepStatus(): Record<string, boolean> {
  const { rec, stale, status } = useCase();
  const d = rec?.data;
  return {
    "/": !!rec,
    "/input": !!(d?.subject_parcel?.parcel_id && (d?.comparables?.length || 0) > 0),
    "/sheets": !!rec && !stale && !!rec.outputs,
    "/review": (() => {
      if (rec?.status === "done") return true;
      if (!rec || !status.findings) return false;
      const errs = status.findings.filter((f) => f.severity === "error");
      const hasSubmitted = !!(rec.submitted_table4 || rec.submitted_table5);
      if (!hasSubmitted) return errs.length === 0;                                                      // 依地號產生：沒有資料缺口就算過
      return rec.status !== "draft" && errs.length > 0 && errs.every((f) => ["accept", "reject"].includes(rec.decisions?.[findingKey(f) || `loc:${f.table}:${f.location}`]?.decision || ""));   // 每項不符都裁決過（接受或維持）
    })(),
    "/export": false,
  };
}

function NavInner() {
  const path = usePathname();
  useSearchParams();
  const { rec, mode } = useCase();
  const q = rec ? `?case=${encodeURIComponent(rec.id)}` : "";
  const done = useStepStatus();
  const sub = (it: { href: string; sub?: string }) => (mode === "review" && it.href === "/input" ? "基準表・核對送審書表填載值" : mode === "review" && it.href === "/sheets" ? "重算的六頁書表・地圖" : it.sub);
  return (
    <nav className="flex-1 px-2 py-3 text-sm">
      {NAV.map((it) => {
        const active = it.match.includes(path);
        return (
          <Link key={it.href} href={it.href + (it.href === "/" ? "" : q)} className={`block px-3 py-2 rounded-lg mb-1 ${active ? "bg-[#ea580c] text-white" : "hover:bg-orange-100"}`}>
            <div className="flex items-center gap-2"><span className="font-medium">{it.label}</span>{done[it.href] && <span className={`ml-auto text-xs ${active ? "text-white" : "text-emerald-700"}`} title="此段已完成">✓</span>}</div>
            {sub(it) && <div className={`text-[11px] ${active ? "opacity-90" : "opacity-70"}`}>{sub(it)}</div>}
          </Link>
        );
      })}
    </nav>
  );
}

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 bg-[#fff1e3] text-[#3b2314] border-r border-orange-200 min-h-screen flex flex-col no-print">
      <div className="px-4 py-4 border-b border-orange-200">
        <div className="font-semibold leading-tight">土地徵收補償市價查估</div>
        <div className="text-xs opacity-70">估價案件審查輔助系統</div>
      </div>
      <Suspense fallback={<nav className="flex-1" />}><NavInner /></Suspense>
      <ActorBox />
      <div className="px-4 py-2 border-t border-orange-200"><Help label="核算依據">依《土地徵收補償市價查估辦法》與作業手冊核算；每個等級與修正率都能對回評價基準明細表格位。</Help></div>
    </aside>
  );
}
