"use client";
import { useCase } from "./CaseContext";

/* 法源提示：滑過欄位名稱顯示辦法條號／手冊頁碼（內容在後端 app/report/basis.py，對照 docs/07）。k 可給多個，取第一個有內容的。 */
export function Tip({ k, children, className = "" }: { k: string | string[]; children?: React.ReactNode; className?: string }) {
  const { meta } = useCase();
  const keys = Array.isArray(k) ? k : [k];
  const text = keys.map((x) => meta?.legal_basis?.[x]).find(Boolean) as string | undefined;
  if (!text) return <>{children ?? null}</>;
  return <span className={`tip ${className}`} data-tip={text} tabIndex={0}>{children ?? <span className="tip-i">法源</span>}</span>;
}
