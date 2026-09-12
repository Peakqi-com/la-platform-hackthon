"use client";
import { Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import CasePage from "../case/page";
import Parcels from "../parcels/page";
import Rules from "../rules/page";
import PageHeader from "@/components/PageHeader";
import { useCase } from "@/components/CaseContext";
import { Empty } from "@/components/ui";

/* ① 輸入資料：依案件路徑決定分頁順序。審查送審書表：基準表（主要輸入）→ 案件 → 宗地與實例（核對填載值）；依地號產生：案件（依地號產生）→ 宗地與實例 → 基準表。 */
const TABS_GENERATE = [["case", "案件與地價區段"], ["parcels", "宗地條件與買賣實例"], ["rules", "評價基準明細表"]] as const;
const TABS_REVIEW = [["rules", "評價基準明細表（主要輸入）"], ["case", "案件與地價區段"], ["parcels", "宗地條件與買賣實例（核對填載值）"]] as const;
function Inner() {
  const { rec, mode } = useCase();
  const params = useSearchParams();
  const TABS = mode === "review" ? TABS_REVIEW : TABS_GENERATE;
  const tab = (params.get("tab") || TABS[0][0]) as "case" | "parcels" | "rules";
  const q = rec ? `&case=${encodeURIComponent(rec.id)}` : "";
  return (
    <div>
      {mode === "review"
        ? <PageHeader title="① 輸入資料" desc="送審書表已抽出填載值；請確認評價基準明細表是該地區的版本，再核對案件與宗地資料。" input="評價基準明細表、送審書表抽出的案件、宗地與買賣實例資料" output="重算書表與比對所需的全部輸入" />
        : <PageHeader title="① 輸入資料" desc="填年期與比準地地號按「依地號產生」，系統推定其餘欄位；推定值請逐項確認。" input="案件基本資料、比準地地號、評價基準明細表；其餘由地籍圖、路網、設施資料庫與實價登錄推定" output="產出書表所需的全部輸入" />}
      <div className="no-print flex gap-1 mb-4 border-b border-slate-200">
        {TABS.map(([k, l]) => <Link key={k} href={`/input?tab=${k}${q}`} className={`px-3 py-2 text-sm rounded-t ${tab === k ? "bg-white border border-b-white border-slate-200 -mb-px font-semibold" : "text-slate-600 hover:bg-white/60"}`}>{l}</Link>)}
      </div>
      {!rec ? <Empty /> : tab === "parcels" ? <Parcels embedded /> : tab === "rules" ? <Rules embedded /> : <CasePage embedded />}
    </div>
  );
}
export default function InputPage() { return <Suspense fallback={<div className="text-sm">載入中…</div>}><Inner /></Suspense>; }
