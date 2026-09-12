"use client";
import { useCase } from "./CaseContext";

const fmt = (s?: string | null) => (s ? String(s).replace("T", " ").slice(0, 16) : "—");

/* 產出已過期的提示：輸入在產出之後改過。放在產出／審查／輸出頁頂端。 */
export function StaleBanner({ what = "本頁書表" }: { what?: string }) {
  const { rec, stale, generating, generate } = useCase();
  if (!rec || !stale) return null;
  return (
    <div className="no-print mb-3 rounded border border-amber-300 bg-amber-50 text-amber-900 px-3 py-2 text-sm flex flex-wrap items-center gap-3">
      <span>⚠ {what}已過期：輸入於 <span className="font-mono">{fmt(rec.input_updated_at || rec.updated_at)}</span> 修改，產出於 <span className="font-mono">{fmt(rec.outputs?.generated_at)}</span> 產生。下載已停用，請先重新產生。</span>
      <button onClick={() => generate().catch(() => null)} disabled={generating} className="px-3 py-1 rounded bg-[#ea580c] text-white text-sm disabled:opacity-50">{generating ? "產生中…" : "重新產生書表"}</button>
    </div>
  );
}
/* 過期時把內容淡化（仍可讀，但不能下載） */
export function StaleDim({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  const { stale } = useCase();
  return <div className={`${className} ${stale ? "opacity-60" : ""}`}>{children}</div>;
}
