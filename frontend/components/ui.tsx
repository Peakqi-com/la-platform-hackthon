"use client";
import { useState } from "react";
import { Any } from "@/lib/api";
import { useCase } from "./CaseContext";
import { SOURCE_STYLES, sourceKind } from "./Legend";

export const SEV: Record<string, { label: string; cls: string }> = {
  error: { label: "不符", cls: "bg-red-100 text-red-800 border-red-300" },
  warn: { label: "需確認", cls: "bg-amber-100 text-amber-800 border-amber-300" },
  info: { label: "備註", cls: "bg-slate-100 text-slate-700 border-slate-300" },
  ok: { label: "相符", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
};
const HINT: Record<string, string> = {
  需人工確認: "系統判定不足：勘查事實缺漏或基準表沒有對應項目，無法自動判定等級，請人工判定；不算錯誤",
  需人工填載: "欄位空白：屬實地勘查或都市計畫書事項（建蔽率、路寬、排水、地勢等），系統不推測，請人工填入",
  需確認: "作業手冊未明定而依範本推定之事項，不判定為錯誤，請估價單位於備註敘明或承辦確認",
  不符: "估價單位填載值與系統依基準明細表核算之值不同",
  相符: "填載值與系統核算一致",
};
export function Badge({ kind, children }: { kind: string; children?: React.ReactNode }) {
  const s = SEV[kind] || SEV.info;
  const text = typeof children === "string" ? children : s.label;
  const hint = HINT[text];
  return <span className={`inline-block border rounded px-1.5 py-0.5 text-xs ${hint ? "cursor-help" : ""} ${s.cls}`} title={hint} aria-label={hint ? `${text}：${hint}` : undefined}>{children ?? s.label}</span>;
}
/* 卡片標題右側的「?」：按一下在標題下展開說明（與頁首的「?」同一種行為）；hint 沒給就不顯示。 */
export function Card({ title, children, right, hint, className, lead }: { title?: React.ReactNode; children: React.ReactNode; right?: React.ReactNode; hint?: string; className?: string; lead?: React.ReactNode }) {
  const [showHint, setShowHint] = useState(false);
  return (
    <section className={`bg-white rounded-lg border border-slate-200 p-4 ${className || "mb-4"}`}>
      {(title || right) && <div className="flex items-start gap-3 mb-3 flex-wrap"><div className="min-w-[14rem] flex-1"><h2 className="font-semibold text-base">{title}{hint && <button type="button" className={`ml-2 inline-block w-5 h-5 rounded-full border text-xs leading-4 text-center font-normal align-middle no-print hover:bg-slate-100 ${showHint ? "border-[#ea580c] text-[#ea580c]" : "border-slate-400 text-slate-500"}`} title={showHint ? "收起說明" : "說明"} aria-expanded={showHint} onClick={() => setShowHint(!showHint)}>?</button>}</h2>{lead && <p className="text-xs text-slate-600 mt-1">{lead}</p>}{hint && showHint && <p className="text-xs text-slate-600 mt-1 no-print">{hint}</p>}</div><div className="ml-auto flex flex-wrap justify-end gap-2 items-center">{right}</div></div>}
      {children}
    </section>
  );
}
export function Btn({ children, onClick, kind = "primary", disabled, title, busy }: { children: React.ReactNode; onClick?: () => void; kind?: "primary" | "ghost" | "danger"; disabled?: boolean; title?: string; busy?: boolean }) {
  const cls = kind === "primary" ? "bg-[#ea580c] text-white hover:bg-[#c2410c]" : kind === "danger" ? "bg-red-600 text-white" : "bg-white border border-slate-300 hover:bg-slate-50";
  return <button type="button" title={title} disabled={disabled} onClick={onClick} aria-busy={busy || undefined} className={`px-3 py-1.5 rounded text-sm whitespace-nowrap disabled:opacity-50 inline-flex items-center gap-1 ${cls}`}>{busy && <span className="inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent animate-spin" aria-hidden />}{children}</button>;
}
export function Empty({ text = "尚未載入案件。請到「案件總覽」載入範例或上傳送審書表。" }: { text?: string }) {
  return <div className="text-slate-600 text-sm bg-white border border-dashed border-slate-300 rounded-lg p-8 text-center">{text}</div>;
}
export function FacilityChip({ f }: { f: Any }) {
  const { label } = useCase();
  if (!f) return <span className="text-slate-400">—</span>;
  const src = String(f.source || "");
  const k = sourceKind(f);
  const st = SOURCE_STYLES[k];
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span>{f.name || "（未命名）"}</span>
      {f.in_section ? <span className="text-emerald-700">區段內</span> : f.distance_m !== undefined && f.distance_m !== null ? <span>{f.distance_m} m</span> : null}
      <span className={`border rounded px-1 text-[10px] ${st.cls}`} title={src}>{st.label}{f.measure ? `・${label("measure_labels", f.measure)}` : ""}{f.assumed ? "（量測方式推定）" : ""}</span>
    </span>
  );
}


/* 補充說明：預設收起，點「說明 ▸」展開；所有頁面的解釋性文字都用它，畫面只留操作要看的內容。 */
export function Help({ children, label = "說明", className = "" }: { children: React.ReactNode; label?: string; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`no-print ${className}`}>
      <button type="button" className="help-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>{label} {open ? "▾" : "▸"}</button>
      {open && <div className="help-body">{children}</div>}
    </div>
  );
}
