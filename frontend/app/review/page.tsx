"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import PageHeader from "@/components/PageHeader";
import { Badge, Btn, Card, Empty } from "@/components/ui";
import { Any, api, Decision, findingHref, findingKey, STATUS_LABEL } from "@/lib/api";
import { decisionKeyLabel } from "@/lib/labels";
import Legend from "@/components/Legend";
import AuditLog from "@/components/AuditLog";
import { StaleBanner } from "@/components/Stale";
import { pathLabel } from "@/lib/labels";
import { getActor } from "@/lib/api";

export default function Review() {
  const { rec, save, status, label, patch, mode } = useCase();
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [decDirty, setDecDirty] = useState(false);
  const decKey = rec ? `${rec.id}:${JSON.stringify(rec.decisions || {})}` : "";
  const [decNotice, setDecNotice] = useState<string | null>(null);
  useEffect(() => {                                                   // 只在案件或後端裁決真的變了才同步；有未儲存裁決時保留並提示
    if (decDirty && rec && JSON.stringify(rec.decisions || {}) !== JSON.stringify(decisions)) { setDecNotice("案件資料已更新（狀態或書表重新產生），你尚未儲存的裁決仍保留在畫面上；請按「儲存裁決」或重新載入放棄。"); return; }   // 剛儲存的裁決回來時內容相同，不提示
    setDecisions(rec?.decisions || {}); setDecDirty(false); setDecNotice(null);
  }, [decKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { const h = (e: BeforeUnloadEvent) => { if (decDirty) { e.preventDefault(); e.returnValue = ""; } }; window.addEventListener("beforeunload", h); return () => window.removeEventListener("beforeunload", h); }, [decDirty]);
  const [filter, setFilter] = useState<string>("all");
  const [scope, setScope] = useState<string>("all");          // 分組顯示：all＝全部分組列出；case＝全案／比準地；1/2/3＝單一比較標的
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const res = status.findings;
  /* 每一項歸到「全案／比準地」或「比較標的 N」：有 comp_no 用 comp_no，否則從位置文字「比較標的N / …」判斷。 */
  const groupOf = (f: Any): string => { const n = f.comp_no ?? (String(f.location || "").match(/^比較標的(\d)/)?.[1]); return n ? String(n) : "case"; };
  const rows = useMemo(() => (res || []).filter((f) => (filter === "all" || f.severity === filter) && (scope === "all" || groupOf(f) === scope)), [res, filter, scope]);
  const groups = useMemo(() => {
    const order = ["case", "1", "2", "3", "4"];
    const g: Record<string, Any[]> = {};
    rows.forEach((f) => { (g[groupOf(f)] = g[groupOf(f)] || []).push(f); });
    return order.filter((k) => g[k]).map((k) => ({ key: k, rows: g[k] }));
  }, [rows]);
  const groupTitle = (k: string) => {
    if (k === "case") return "全案／比準地（勘查表、蒐集期間、比較價格與尾數、基準表上限）";
    const c = (rec?.data.comparables || []).find((x: Any) => String(x.comp_no) === k);
    return `比較標的${k}${c?.parcel_id ? `　${c.parcel_id}` : ""}${c?.transaction_date ? `　交易日期 ${c.transaction_date}` : ""}（區域因素分析明細表、比較法調查估價表、買賣實例）`;
  };
  const counts = useMemo(() => ({ error: res?.filter((f) => f.severity === "error").length ?? 0, warn: res?.filter((f) => f.severity === "warn").length ?? 0, info: res?.filter((f) => f.severity === "info").length ?? 0 }), [res]);

  const [busy, setBusy] = useState(false);
  const keyOf = (f: Any) => findingKey(f) || `loc:${f.table}:${f.location}`;
  const setDec = (f: Any, patchD: Partial<Decision>) => { const k = keyOf(f); const by = getActor().name || undefined; setDecisions((d) => ({ ...d, [k]: { ...({ decision: "pending" } as Decision), ...(d[k] || {}), ...patchD, by, at: new Date().toISOString() } as Decision })); setDecDirty(true); };
  async function saveDecisions() { setBusy(true); try { await patch({ decisions }); setDecDirty(false); } catch (e: Any) { alert(String(e.message || e)); } finally { setBusy(false); } }
  if (!rec) return <Empty />;
  const hasSubmitted = !!(rec.submitted_table4 || rec.submitted_table5);
  const accepted = (res || []).filter((f) => f.severity === "error" && decisions[keyOf(f)]?.decision === "accept").length;
  return (
    <div className="print-landscape">
      <PageHeader print title="③ 審查" desc="將送審書表上估價單位填載的等級、修正百分比、小計、差異率、跨表抄填與價格，與系統依評價基準明細表核算的結果逐項比對；每一項結果均標示作業手冊審查重點條號與依據格位。"
        input="送審書表填載值（影響地價區域因素分析明細表、比較法調查估價表）＋系統核算結果" output="不符／需確認／備註清單 → 審查意見書" next={{ href: "/report", label: "審查意見書" }} />
      <StaleBanner what="審查結果" />
      {(() => { const cs = (rec.inputs || []).flatMap((i) => (i.conflicts || []).map((c) => ({ ...c, file: i.filename }))); return cs.length ? (
        <Card title={`輸入檔不一致（${cs.length}）`} hint="同一格在兩份輸入檔裡的值不同：系統保留先併入的值、不自動裁決。請核對原檔後到「① 輸入資料」改成正確值，或移除有誤的檔案。">
          <div className="overflow-x-auto"><table className="grid"><thead><tr><th>欄位</th><th>保留的值</th><th>後來的檔案給的值</th><th>來自檔案</th></tr></thead>
            <tbody>{cs.slice(0, 60).map((c, i) => <tr key={i}><td>{pathLabel(c.path)}</td><td className="font-mono">{String(c.kept ?? "（空）")}</td><td className="font-mono">{String(c.incoming ?? "（空）")}</td><td className="text-slate-600">{c.file}</td></tr>)}</tbody></table></div>
          {cs.length > 60 && <div className="text-xs text-slate-500 mt-1">只列前 60 筆，完整明細在「① 輸入資料」的輸入檔卡片。</div>}
        </Card>) : null; })()}
      <Legend kinds={["review"]} />
      <Card hint="本頁每一項「系統核算」值都由規則引擎依查估辦法與作業手冊確定性計算並可對回基準明細表格位，AI 不參與數字；AI（語言模型）只用於掃描件辨識與意見書文字潤飾。 「承辦裁決」：接受填載＝經審酌採估價單位之填載（請填說明），維持不符＝請估價單位補正；裁決與說明會寫入審查意見書。審查重點條號依《土地徵收補償市價查估作業手冊》p.11–13：iii 勘查表等級、v 買賣實例、vi 區域因素分析明細表、vii 比較法調查估價表、x 宗地條件與清冊。「需確認」多為作業手冊未明定而依範本推定之事項，不判定為錯誤。" title={<>審查結果：{rec.name} <span className={`ml-2 align-middle rounded px-1.5 py-0.5 text-xs ${rec.status === "done" ? "bg-emerald-100 text-emerald-800" : rec.status === "reviewing" ? "bg-sky-100 text-sky-800" : "bg-slate-100 text-slate-700"}`}>{STATUS_LABEL[rec.status || "draft"]}</span></>}
        right={<>
          <Btn onClick={saveDecisions} busy={busy} disabled={busy || !decDirty} title={decDirty ? "把裁決與說明存到案件" : "沒有未儲存的裁決"}>{decDirty ? "儲存裁決" : "裁決已儲存"}</Btn><Link href={`/report?case=${rec.id}`}><Btn kind="ghost">審查意見書 →</Btn></Link></>}>
        {status.error && <div className="text-red-700 text-sm mb-2">{status.error}</div>}
        {decNotice && <div className="text-sm text-amber-900 bg-amber-50 border border-amber-300 rounded p-2 mb-2 flex items-center gap-2">{decNotice}<button className="underline text-xs" onClick={() => { setDecisions(rec?.decisions || {}); setDecDirty(false); setDecNotice(null); }}>放棄未儲存裁決</button></div>}
        {!hasSubmitted && <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 mb-2">本案為依地號產生的書表，沒有估價單位的送審書表可比對，因此沒有「不符」可裁決；下列「資料缺口」是產出前要補的資料（例如比較標的），「需確認」是系統推定值、基準表上限、蒐集期間等事項，請逐項確認後再輸出。</div>}
        {status.loading && <div className="text-sm">核算中…</div>}
        {res && (
          <div className="flex items-center gap-3 text-sm mb-3">
            {!hasSubmitted ? <>{counts.error ? <Badge kind="error">{counts.error} 項資料缺口</Badge> : <Badge kind="info">無送審書表可比對</Badge>}</> : counts.error === 0 ? <Badge kind="ok">全部相符</Badge> : <Badge kind="error">{counts.error} 項不符{accepted ? `（${accepted} 項已裁決接受）` : ""}</Badge>}
            <Badge kind="warn">{counts.warn} 項需確認</Badge><Badge kind="info">{counts.info} 項備註</Badge>
            {status.run?.table4.subject_comparison_price != null ? <span className="text-slate-500">系統核算比準地比較價格 {status.run.table4.subject_comparison_price.toLocaleString()} 元/m²；比準地地價 {status.run.table4.subject_land_price?.toLocaleString()} 元/m²</span> : <span className="text-slate-500">尚無比較標的，比較價格未計算</span>}
            <select className="no-print ml-auto border rounded px-2 py-1" value={scope} onChange={(e) => setScope(e.target.value)} title="一次只看一個對象，或全部分組列出">
              <option value="all">全部（分組列出）</option><option value="case">只看全案／比準地</option>{(rec.data.comparables || []).map((c: Any) => <option key={c.comp_no} value={String(c.comp_no)}>只看比較標的{c.comp_no}{c.parcel_id ? `（${c.parcel_id}）` : ""}</option>)}
            </select>
            <select className="no-print border rounded px-2 py-1" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="all">全部結果</option><option value="error">僅不符</option><option value="warn">僅需確認</option><option value="info">僅備註</option>
            </select>
          </div>
        )}
        {res && rows.length === 0 && <div className="text-slate-600 text-sm">{hasSubmitted ? "沒有符合篩選條件的項目。" : "本案沒有送審書表，沒有可比對的項目；上傳送審書表後這裡會逐項列出不符處。"}</div>}
        {rows.length > 0 && hasSubmitted && (
          <div className="no-print mb-2 rounded border border-orange-200 bg-orange-50 text-orange-900 text-sm px-3 py-2">
            <b>怎麼審：</b>每一項「不符」請在右側「承辦裁決」選擇 <b>接受填載</b>（經審酌採估價單位之值，請填說明）或 <b>維持不符</b>（請估價單位補正），按「儲存裁決」，再按右上「下一步：審查意見書」；裁決與說明會寫進意見書。按「看基準表格位」可看到該項在評價基準明細表的判定條件與矩陣格位。
          </div>
        )}
        {rows.length > 0 && (
          <div className="overflow-x-auto"><table className="grid">
            <thead><tr><th className="print-nowrap">#</th><th>結果</th><th>審查重點</th><th>書表</th><th>位置</th><th>{hasSubmitted ? "估價單位填載" : "目前值"}</th><th>系統核算</th><th>說明</th><th>依據</th><th className="whitespace-nowrap print-hide">追溯</th><th className="min-w-[6rem]">承辦裁決</th></tr></thead>
            <tbody>{(() => { let seq = 0; return groups.flatMap((grp) => { const start = seq; seq += grp.rows.length; const ne = grp.rows.filter((x) => x.severity === "error").length; const nw = grp.rows.filter((x) => x.severity === "warn").length; const head = (
              <tr key={`g-${grp.key}`} className="cursor-pointer" onClick={() => setCollapsed({ ...collapsed, [grp.key]: !collapsed[grp.key] })}>
                <td colSpan={11} className="bg-[#ffedd5] font-medium">{collapsed[grp.key] ? "▸" : "▾"} {groupTitle(grp.key)} <span className="text-xs font-normal text-slate-600">— {grp.rows.length} 項{ne ? `，不符 ${ne}` : ""}{nw ? `，需確認 ${nw}` : ""}{collapsed[grp.key] ? "，已收合" : ""}</span></td>
              </tr>); if (collapsed[grp.key]) return [head]; return [head, ...grp.rows.map((f, j) => { const i = start + j; return (
              <tr key={`${grp.key}-${j}`}>
                <td className="print-nowrap">{i + 1}</td><td><Badge kind={f.severity}>{f.kind === "gap" ? "資料缺口" : f.kind === "inferred" ? "需確認（推定）" : undefined}</Badge></td><td title={label("checklist", f.checklist)}>{f.checklist}</td><td className="min-w-[7rem]">{label("tables", f.table.replace("表", "")) || f.table}</td><td>{f.location}</td>
                <td className="text-right font-mono">{f.submitted ?? "—"}</td><td className="text-right font-mono">{f.computed ?? "—"}</td><td>{f.message}</td><td className="text-slate-600">{f.basis || "—"}</td>
                <td className="whitespace-nowrap print-hide">{findingHref(f, rec.id) ? <Link href={findingHref(f, rec.id)!} className="inline-block px-2 py-1 rounded border border-orange-400 bg-orange-50 text-orange-900 text-xs hover:bg-orange-100" title="到書表對照檢視，右側會標出該項在評價基準明細表的判定條件與修正矩陣格位">看基準表格位 →</Link> : null}</td>
                <td className={`whitespace-nowrap ${i === 0 && f.severity === "error" && !decisions[keyOf(f)]?.decision ? "bg-amber-50 ring-2 ring-amber-300" : ""}`}>{!hasSubmitted ? <span className="text-xs text-slate-500">{f.kind === "gap" ? "待補資料" : "待確認"}</span> : f.severity !== "info" && (() => { const d = decisions[keyOf(f)]; return (<><span className="print-only text-xs">{d?.decision === "accept" ? "接受填載" : d?.decision === "reject" ? "維持不符" : "待處理"}{d?.note ? `：${d.note}` : ""}</span><div className="flex flex-col gap-1 no-print">
                  <select className={`border rounded px-1 text-xs ${d?.decision === "accept" ? "bg-emerald-50" : d?.decision === "reject" ? "bg-red-50" : ""}`} value={d?.decision || "pending"} onChange={(e) => setDec(f, { decision: e.target.value as Decision["decision"] })}>
                    <option value="pending">待處理</option><option value="accept">接受填載</option><option value="reject">維持不符</option></select>
                  <input className="border rounded px-1 text-xs w-36" placeholder="說明（寫入意見書）" value={d?.note || ""} onChange={(e) => setDec(f, { note: e.target.value })} /></div></>); })()}</td>
              </tr>); })]; }); })()}</tbody>
          </table></div>
        )}
        {Object.entries(decisions).some(([, d]) => d.stale) && (
          <div className="mt-3 rounded border border-amber-300 bg-amber-50 text-amber-900 text-xs p-2">
            以下裁決對應的不符項在重新產生後已不存在，請確認是否移除：
            {Object.entries(decisions).filter(([, d]) => d.stale).map(([k, d]) => <span key={k} className="inline-flex items-center gap-1 ml-2 bg-white border rounded px-1.5 py-0.5"><span>{decisionKeyLabel(k)}</span>（{d.decision === "accept" ? "接受填載" : d.decision === "reject" ? "維持不符" : "待處理"}{d.note ? `：${d.note}` : ""}）<button className="underline" onClick={() => { setDecisions((cur) => { const n = { ...cur }; delete n[k]; return n; }); setDecDirty(true); }}>移除</button></span>)}
          </div>
        )}
      </Card>
      <div className="no-print"><AuditLog caseId={rec.id} refreshKey={rec.updated_at} /></div>
    </div>
  );
}
