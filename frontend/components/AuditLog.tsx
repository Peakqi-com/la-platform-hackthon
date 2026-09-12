"use client";
import { pathLabel } from "@/lib/labels";
import { useEffect, useState } from "react";
import { api, Any } from "@/lib/api";
import { Card } from "./ui";

/* 操作紀錄：誰（姓名／角色）在何時做了什麼、改了哪些欄位。資料在後端 data/audit/<案件>.jsonl。 */
export default function AuditLog({ caseId, refreshKey }: { caseId: string; refreshKey?: string }) {
  const [rows, setRows] = useState<Any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { let alive = true; api.audit(caseId).then((r) => alive && setRows(r.entries)).catch((e) => alive && setErr(String(e.message || e))); return () => { alive = false; }; }, [caseId, refreshKey]);
  return (
    <Card title="操作紀錄" hint="每一次儲存、狀態變更、裁決、意見書與匯出都會記錄操作者（側邊欄的操作身分）與時間；儲存時另記欄位差異。">
      {err && <div className="text-sm text-red-700">{err}</div>}
      {rows && rows.length === 0 && <div className="text-sm text-slate-500">尚無紀錄。</div>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto"><table className="grid"><thead><tr><th className="whitespace-nowrap">時間</th><th className="whitespace-nowrap">操作者</th><th className="whitespace-nowrap">動作</th><th>內容</th></tr></thead>
          <tbody>{rows.map((e, i) => (
            <tr key={i} className={e.inherited_from ? "text-slate-500" : ""}>
              <td className="whitespace-nowrap text-xs">{String(e.at || "").replace("T", " ").slice(0, 19)}</td>
              <td className="whitespace-nowrap">{e.actor_label}</td>
              <td className="whitespace-nowrap">{e.action_label}{e.inherited_from ? <span className="text-[10px] ml-1">（來自原案件）</span> : null}</td>
              <td className="text-xs">{e.detail}{e.changes?.length ? (
                <details className="mt-1"><summary className="cursor-pointer text-slate-600">欄位差異 {e.changes.length} 處</summary>
                  <ul className="mt-1 space-y-0.5 text-[11px]">{e.changes.map((c: Any, j: number) => <li key={j}>{pathLabel(c.path)}：{fmt(c.old)} → {fmt(c.new)}</li>)}</ul></details>) : null}</td>
            </tr>))}</tbody></table></div>
      )}
    </Card>
  );
}
const fmt = (v: Any) => (v === null || v === undefined ? "（空）" : typeof v === "object" ? JSON.stringify(v) : String(v));
