"use client";
import { useState } from "react";
import { IOLegend } from "./IO";
/* 全站統一的顏色語意。來源：系統推算（藍）、有建議值（黃）、需人工填載（紅）、人工填載（灰）、送審書表抽取（紫）；審查結果：相符（綠）、不符（紅）、需確認（黃）、備註（灰）。 */
export const SOURCE_STYLES: Record<string, { label: string; cls: string }> = {
  computed: { label: "系統推算", cls: "bg-sky-100 text-sky-800 border-sky-300" },
  suggested: { label: "有建議值", cls: "bg-amber-100 text-amber-800 border-amber-300" },
  manual_required: { label: "需人工填載", cls: "bg-rose-100 text-rose-800 border-rose-300" },
  manual: { label: "人工填載", cls: "bg-slate-100 text-slate-700 border-slate-300" },
  extracted: { label: "送審書表抽取", cls: "bg-violet-100 text-violet-800 border-violet-300" },
};
export function sourceKind(f: { computed?: boolean; source?: string; assumed?: boolean } | null | undefined): keyof typeof SOURCE_STYLES {
  if (!f) return "manual";
  if (f.computed) return "computed";
  const s = String(f.source || "");
  if (/表1|表4|表7|估價師|需用土地人|vision|抽取/.test(s)) return "extracted";
  return "manual";
}
export default function Legend({ kinds = ["source", "review"] as ("source" | "review")[], inline = false }: { kinds?: ("source" | "review")[]; inline?: boolean }) {
  const [open, setOpen] = useState(false);
  const body = (
    <>
      <IOLegend />
      {kinds.includes("source") && <div className="flex items-center gap-1"><span className="opacity-70 mr-1">資料來源：</span>
        {Object.values(SOURCE_STYLES).map((s) => <span key={s.label} className={`border rounded px-1.5 ${s.cls}`}>{s.label}</span>)}</div>}
      {kinds.includes("review") && <div className="flex items-center gap-1"><span className="opacity-70 mr-1">審查結果：</span>
        <span className="border rounded px-1.5 bg-emerald-100 text-emerald-800 border-emerald-300">相符</span><span className="border rounded px-1.5 bg-red-100 text-red-800 border-red-300">不符</span>
        <span className="border rounded px-1.5 bg-amber-100 text-amber-800 border-amber-300">需確認</span><span className="border rounded px-1.5 bg-slate-100 text-slate-700 border-slate-300">備註</span></div>}
    </>
  );
  if (inline) {   // 放在 .toolbar 裡：一顆「圖例」鍵，展開時佔整列
    return (
      <>
        <button type="button" className="no-print h-8 px-2.5 rounded border border-slate-300 bg-white text-xs text-slate-600 hover:bg-slate-50" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "收起圖例" : "圖例"}</button>
        {open && <div className="no-print basis-full flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600">{body}</div>}
      </>
    );
  }
  if (!open) return <div className="no-print mb-3"><button className="text-[11px] text-slate-500 underline" onClick={() => setOpen(true)}>顯示圖例（顏色說明）</button></div>;
  return (
    <div className="no-print flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-600 mb-3">
      <button className="underline" onClick={() => setOpen(false)}>收起圖例</button>
      {body}
    </div>
  );
}
