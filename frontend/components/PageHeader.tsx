"use client";
import Link from "next/link";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { useCase } from "./CaseContext";
import { NAV } from "./Sidebar";

/* 頁首：左＝標題＋「說明」摺疊；右＝列印（可選）＋下一步。下一步預設依步驟列自動算（① → ② → ③ → ④），分頁內可用 next 覆寫（例如 /report）。 */
export default function PageHeader({ title, desc, input, output, next, print = false }: { title: string; desc?: string; input?: string; output?: string; next?: { href: string; label: string; plain?: boolean }; print?: boolean }) {
  const { rec } = useCase();
  const path = usePathname();
  const [more, setMore] = useState(false);
  const q = rec ? `case=${encodeURIComponent(rec.id)}` : "";
  const idx = NAV.findIndex((it) => it.match.includes(path));
  const auto = idx >= 0 && idx < NAV.length - 1 ? { href: NAV[idx + 1].href, label: NAV[idx + 1].label } : null;
  const go = next && !next.plain ? next : !next ? auto : null;
  const href = go ? go.href + (q ? (go.href.includes("?") ? "&" : "?") + q : "") : "";
  return (
    <div className="mb-4 flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <h1 className="text-xl font-semibold leading-tight">{title}</h1>
        {(desc || input || output) && <button className="no-print help-toggle mt-1" aria-expanded={more} onClick={() => setMore(!more)}>說明 {more ? "▾" : "▸"}</button>}
        {more && (
          <div className="help-body">
            {desc && <p>{desc}</p>}
            {(input || output) && (
              <div className="mt-2 flex flex-wrap gap-4 text-xs">
                {input && <div><span className="inline-block rounded bg-orange-100 text-orange-800 px-1.5 py-0.5 mr-1">這一頁的輸入</span>{input}</div>}
                {output && <div><span className="inline-block rounded bg-emerald-100 text-emerald-800 px-1.5 py-0.5 mr-1">產出</span>{output}</div>}
              </div>
            )}
          </div>
        )}
      </div>
      {(print || go) && (
        <div className="no-print shrink-0 flex items-center gap-2">
          {print && <button type="button" onClick={() => window.print()} className="h-8 px-3 rounded border border-slate-300 bg-white text-sm hover:bg-slate-50" title="列印本頁（表格版面，隱藏側邊欄與按鈕）">列印</button>}
          {go && rec && <Link href={href} className="h-8 px-3 inline-flex items-center rounded border border-slate-300 bg-white text-sm hover:bg-slate-50 whitespace-nowrap">下一步：{go.label} →</Link>}
        </div>
      )}
    </div>
  );
}
