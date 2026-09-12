"use client";
/* 估價基準日依查估辦法 §17 第2項應為 3/1 或 9/1；其他日期無法決定蒐集期間，多半是誤植 */
export function vdateHint(v: unknown) {
  const s = String(v || "").replace(/\D/g, "");
  if (s.length !== 7) return null;
  const md = s.slice(3);
  if (md === "0301" || md === "0901") return null;
  return <div className="text-[11px] text-amber-800 mt-0.5">估價基準日 {s.slice(0, 3)}.{s.slice(3, 5)}.{s.slice(5)} 不是 3 月 1 日或 9 月 1 日（查估辦法 §17 第 2 項），可能誤植，請確認。</div>;
}

