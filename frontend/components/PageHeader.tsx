"use client";
import Link from "next/link";
import { useState } from "react";
import { useCase } from "./CaseContext";

/* 頁首：標題＋一句說明；「?」展開完整說明與這一頁的輸入／產出。步驟導覽在頂端步驟列，這裡只留分頁內的下一步（例如輸入資料的三個分頁）。 */
export default function PageHeader({ title, desc, input, output, next, print = false }: { title: string; desc?: string; input?: string; output?: string; next?: { href: string; label: string; plain?: boolean }; print?: boolean }) {
  const { rec } = useCase();
  const [more, setMore] = useState(false);
  const q = rec ? `case=${encodeURIComponent(rec.id)}` : "";
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="flex-1 min-w-0">
        <h1 className="text-xl font-semibold">{title}</h1>
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
      {print && <button type="button" onClick={() => window.print()} className="shrink-0 text-xs underline text-slate-500 no-print" title="列印本頁（表格版面，隱藏側邊欄與按鈕）">列印</button>}
      {next && !next.plain && !["/", "/input", "/sheets", "/review", "/export"].includes(next.href) && <Link href={next.href + (q ? (next.href.includes("?") ? "&" : "?") + q : "")} className="shrink-0 px-3 py-2 rounded border border-slate-300 bg-white text-sm hover:bg-slate-50 no-print">下一步：{next.label} →</Link>}
    </div>
  );
}
