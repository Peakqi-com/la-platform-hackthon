"use client";
import { useState } from "react";
/* 估價基準日依查估辦法 §17 第2項應為 3/1 或 9/1；其他日期無法決定蒐集期間，多半是誤植 */
export function vdateHint(v: unknown) {
  const s = String(v || "").replace(/\D/g, "");
  if (s.length !== 7) return null;
  const md = s.slice(3);
  if (md === "0301" || md === "0901") return null;
  return <div className="text-[11px] text-amber-800 mt-0.5">估價基準日 {s.slice(0, 3)}.{s.slice(3, 5)}.{s.slice(5)} 不是 3 月 1 日或 9 月 1 日（查估辦法 §17 第 2 項），可能誤植，請確認。</div>;
}

/* 最近一個已到的基準日（民國 7 碼）：今天在 9/1 之後 → 今年 0901；3/1～8/31 → 今年 0301；否則去年 0901 */
export function latestVdate(now = new Date()): string {
  const y = now.getFullYear() - 1911, m = now.getMonth() + 1;
  if (m >= 9) return `${y}0901`;
  if (m >= 3) return `${y}0301`;
  return `${y - 1}0901`;
}

/* 估價基準日下拉：民國年 × {3月1日, 9月1日}；「其他日期」才開放 7 碼手動輸入。value／onChange 一律 7 碼字串，後端不用改。 */
export function VDateSelect({ value, onChange, className = "", years = 4 }: { value: string; onChange: (v: string) => void; className?: string; years?: number }) {
  const s = String(value || "").replace(/\D/g, "");
  const std = s.length === 7 && (s.slice(3) === "0301" || s.slice(3) === "0901");
  const [manual, setManual] = useState(!!s && !std);
  const thisY = new Date().getFullYear() - 1911;
  const yearsList = Array.from({ length: years + 2 }, (_, i) => thisY + 1 - i);          // 明年到 years 年前
  const y = std ? Number(s.slice(0, 3)) : thisY;
  const md = std ? s.slice(3) : "";
  if (!yearsList.includes(y)) yearsList.push(y);
  const set = (yy: number, mm: string) => onChange(mm ? `${yy}${mm}` : "");
  if (manual) {
    return (<div className={className}>
      <div className="flex items-center gap-2"><input className="border rounded px-2 py-1 w-full" placeholder="民國 7 碼，例 1140901" value={value || ""} onChange={(e) => onChange(e.target.value)} />
        <button type="button" className="text-xs underline text-slate-600 whitespace-nowrap" onClick={() => { setManual(false); if (!std) onChange(""); }}>改用下拉</button></div>
      {vdateHint(value)}
    </div>);
  }
  return (<div className={`flex items-center gap-1 ${className}`}>
    <select className="border rounded px-2 py-1" value={std ? y : ""} onChange={(e) => set(Number(e.target.value), md || "0901")} title="民國年">
      {!std && <option value="">年</option>}{yearsList.sort((a, b) => b - a).map((yy) => <option key={yy} value={yy}>{yy} 年</option>)}</select>
    <select className="border rounded px-2 py-1" value={md} onChange={(e) => set(std ? y : thisY, e.target.value)} title="查估辦法 §17 第 2 項：估價基準日為 3 月 1 日或 9 月 1 日">
      {!std && <option value="">月日</option>}<option value="0301">3 月 1 日</option><option value="0901">9 月 1 日</option></select>
    <button type="button" className="text-xs underline text-slate-600 whitespace-nowrap" onClick={() => setManual(true)} title="徵收案偶有其他基準日，手動輸入 7 碼">其他日期</button>
  </div>);
}
