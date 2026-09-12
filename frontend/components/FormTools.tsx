"use client";
import { useEffect, useMemo, useState } from "react";
import { Any } from "@/lib/api";

/* 長表單共用：主要項目摺疊、篩選（需人工填載／有差異或需確認／低信心）、方向鍵在欄位間移動、未儲存提醒。 */
export type Filter = "all" | "manual" | "attention" | "lowconf";
export const FILTER_LABEL: Record<Filter, string> = { all: "全部", manual: "只看需人工填載", attention: "只看需確認／有差異", lowconf: "只看低信心抽取" };

export function useFormTools(dirty: boolean) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<Filter>("all");
  const toggle = (g: string) => setCollapsed((s) => { const n = new Set(s); if (n.has(g)) n.delete(g); else n.add(g); return n; });
  const allOpen = () => setCollapsed(new Set());
  const allClosed = (groups: string[]) => setCollapsed(new Set(groups));
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", h); return () => window.removeEventListener("beforeunload", h);
  }, [dirty]);
  return { collapsed, toggle, allOpen, allClosed, filter, setFilter };
}

/* 在 <table> 上掛 onKeyDown：↑↓ 在同欄的 input/select 間移動，Enter 往下。 */
export function keyNav(e: React.KeyboardEvent<HTMLElement>) {
  if (!["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
  const t = e.target as HTMLElement;
  if (!(t instanceof HTMLInputElement || t instanceof HTMLSelectElement)) return;
  if (t instanceof HTMLSelectElement && (e.key === "ArrowDown" || e.key === "ArrowUp")) return;   // 下拉本身用方向鍵選值
  const inputs = [...e.currentTarget.querySelectorAll<HTMLElement>("input, select")].filter((x) => !(x as HTMLInputElement).disabled && x.getClientRects().length);
  const i = inputs.indexOf(t); if (i < 0) return;
  const col = (t.closest("td") as HTMLTableCellElement | null)?.cellIndex;
  const dir = e.key === "ArrowUp" ? -1 : 1;
  for (let k = i + dir; k >= 0 && k < inputs.length; k += dir) {
    const c = (inputs[k].closest("td") as HTMLTableCellElement | null)?.cellIndex;
    if (c === col) { e.preventDefault(); inputs[k].focus(); (inputs[k] as HTMLInputElement).select?.(); return; }
  }
}

export function FormToolbar({ tools, groups, dirty }: { tools: ReturnType<typeof useFormTools>; groups: string[]; dirty: boolean }) {
  return (
    <div className="no-print flex flex-wrap items-center gap-2 text-xs mb-2">
      <span className="text-slate-500">顯示：</span>
      {(Object.keys(FILTER_LABEL) as Filter[]).map((f) => <button key={f} onClick={() => tools.setFilter(f)} className={`px-2 py-0.5 rounded border ${tools.filter === f ? "bg-[#ea580c] text-white border-[#ea580c]" : "bg-white"}`}>{FILTER_LABEL[f]}</button>)}
      <span className="mx-1 text-slate-300">|</span>
      <button className="underline" onClick={tools.allOpen}>全部展開</button><button className="underline" onClick={() => tools.allClosed(groups)}>全部收合</button>
      <span className="text-slate-400">｜↑↓ 或 Enter 在欄位間移動</span>
      {dirty && <span className="ml-auto rounded px-2 py-0.5 bg-amber-100 text-amber-800">有未儲存的修改</span>}
    </div>
  );
}

export function useDirty(draft: Any, base: Any) {
  return useMemo(() => JSON.stringify(draft ?? null) !== JSON.stringify(base ?? null), [draft, base]);
}
