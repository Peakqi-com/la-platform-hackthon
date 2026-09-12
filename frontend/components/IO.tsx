"use client";
/* 匯入／匯出標示：全站統一。⬆ 可由檔案匯入、⬇ 可匯出成檔案。放在欄位名稱旁（小標）或卡片標題旁（徽章）。 */
export function IOMark({ kind, what, className = "" }: { kind: "import" | "export" | "both"; what: string; className?: string }) {
  const t = kind === "both" ? `可匯入／匯出：${what}` : kind === "import" ? `可由檔案匯入：${what}` : `可匯出成檔案：${what}`;
  return <span className={`io-mark io-${kind} ${className}`} title={t} aria-label={t}>{kind === "both" ? "⬆⬇" : kind === "import" ? "⬆" : "⬇"}</span>;
}
export function IOBadge({ kind, what }: { kind: "import" | "export"; what: string }) {
  return <span className={`io-badge io-${kind}`}>{kind === "import" ? "⬆ 可匯入" : "⬇ 可匯出"}<span className="opacity-80 ml-1">{what}</span></span>;
}
export function IOLegend() {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="opacity-70">檔案：</span>
      <span className="io-badge io-import">⬆ 可匯入</span><span className="io-badge io-export">⬇ 可匯出</span>
    </span>
  );
}
