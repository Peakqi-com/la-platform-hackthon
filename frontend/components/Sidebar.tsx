"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Fragment, Suspense, useState } from "react";
import { useRouter } from "next/navigation";
import { Any, findingKey, STATUS_LABEL } from "@/lib/api";
import { useCase } from "./CaseContext";
import { Help } from "./ui";
import ActorBox from "./Actor";

/* 側邊欄五項：案件總覽 → ① 輸入資料 → ② 產出書表 → ③ 審查 → ④ 輸出。勾號＝該段已完成。 */
export const NAV: { href: string; match: string[]; label: string; sub?: string }[] = [
  { href: "/", match: ["/"], label: "案件總覽", sub: "上傳送審書表、開啟案件" },
  { href: "/input", match: ["/input", "/case", "/parcels", "/rules"], label: "① 輸入資料", sub: "基準表・基本資料・宗地與實例" },
  { href: "/sheets", match: ["/sheets", "/table1", "/tables", "/map"], label: "② 產出書表", sub: "書表預覽（照範本）・地圖" },
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
  const sub = (it: { href: string; sub?: string }) => (mode === "review" && it.href === "/input" ? "基準表・核對送審書表填載值" : mode === "review" && it.href === "/sheets" ? "重算的書表・地圖" : it.sub);
  const items = rec ? NAV : NAV.filter((it) => it.href === "/");   // 還沒選案件：①～④ 都是針對某個案件的步驟，只留案件總覽
  return (
    <nav className="flex-1 px-2 py-3 text-sm">
      {items.map((it) => {
        const active = it.match.includes(path);
        const caseHead = rec && it.href === "/input" ? (   // 案件總覽與 ①～④ 之間：目前案件標題，把「選案件」與「做這個案件」兩段隔開
          <div className="mt-3 mb-1 pt-3 border-t border-orange-200 px-3">
            <div className="text-[11px] opacity-60">目前案件</div>
            <div className="font-semibold leading-snug break-words" title={rec.name}>{rec.name}</div>
            <div className="text-[11px] opacity-70">{[rec.data?.case?.case_no, STATUS_LABEL[rec.status || "draft"]].filter(Boolean).join("・")}</div>
          </div>
        ) : null;
        return (<Fragment key={it.href}>{caseHead}
          <Link href={it.href + (it.href === "/" ? "" : q)} className={`block px-3 py-2 rounded-lg mb-1 ${active ? "bg-[#ea580c] text-white" : "hover:bg-orange-100"}`}>
            <div className="flex items-center gap-2"><span className="font-medium">{it.label}</span>{done[it.href] && <span className={`ml-auto text-xs ${active ? "text-white" : "text-emerald-700"}`} title="此段已完成">✓</span>}</div>
            {sub(it) && <div className={`text-[11px] ${active ? "opacity-90" : "opacity-70"}`}>{sub(it)}</div>}
          </Link>
        </Fragment>);
      })}
      {!rec && <div className="px-3 py-2 text-[11px] opacity-60">開啟或建立案件後，這裡會出現 ①～④ 的步驟。</div>}
    </nav>
  );
}

/* 左下角：重置所有案件。兩段式確認（按一次展開，再按「確定清除」才送出），清後端全部案件、操作紀錄與匯入圖檔，不可復原。 */
function ResetAllBox() {
  const { cases, resetAll } = useCase();
  const router = useRouter();
  const [arm, setArm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const run = async () => {
    setBusy(true); setMsg(null);
    try { const n = await resetAll(); setArm(false); setMsg(`已清除 ${n} 件案件`); router.push("/"); }
    catch (e: Any) { setMsg(`清除失敗：${String(e?.message || e)}`); }
    finally { setBusy(false); }
  };
  return (
    <div className="px-3 py-2 border-t border-orange-200 text-xs">
      {!arm ? (
        <button type="button" className="text-red-700 underline hover:text-red-900" title="清除全部案件資料、操作紀錄與匯入的地籍圖檔，不可復原" onClick={() => { setArm(true); setMsg(null); }}>重置所有案件</button>
      ) : (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-red-900">
          <div className="mb-1">將清除全部 {cases.length} 件案件（含封存）、操作紀錄與匯入圖檔，<b>不可復原</b>。</div>
          <div className="flex gap-2">
            <button type="button" disabled={busy} className="px-2 py-0.5 rounded bg-red-600 text-white disabled:opacity-50" onClick={run}>{busy ? "清除中…" : "確定清除"}</button>
            <button type="button" disabled={busy} className="px-2 py-0.5 rounded border border-slate-300 bg-white text-slate-700" onClick={() => setArm(false)}>取消</button>
          </div>
        </div>
      )}
      {msg && <div className="mt-1 opacity-80">{msg}</div>}
    </div>
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
      <ResetAllBox />
    </aside>
  );
}
