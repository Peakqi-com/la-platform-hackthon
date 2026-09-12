"use client";
import { marked } from "marked";
import { useEffect, useState } from "react";
import { useCase } from "@/components/CaseContext";
import { StaleBanner } from "@/components/Stale";
import PageHeader from "@/components/PageHeader";
import { Btn, Card, Empty } from "@/components/ui";
import { actorHeaders, api, Any, getActor, mapPngUrl, ROLE_LABEL, zhError } from "@/lib/api";

const CONCLUSION_ZH: Record<string, string> = { pass: "相符", confirm: "需確認", reject: "不符，請補正", revise: "不符，請補正後再送審", incomplete: "資料不全", warn: "需確認" };

export default function Report() {
  const { rec, meta, stale } = useCase();
  const [report, setReport] = useState<Any>(null);
  const [polish, setPolish] = useState(false);
  const [actor, setActor] = useState<{ name: string; role: string }>({ name: "", role: "" });
  useEffect(() => { setActor(getActor()); }, []);   // 落款＝側邊欄的操作身分
  const autoKey = rec ? `${rec.id}:${rec.outputs?.generated_at}:${JSON.stringify(rec.decisions || {})}:${actor.name}:${actor.role}` : "";
  useEffect(() => { if (rec && !stale && !busy) { make(); } }, [autoKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  async function make() {
    if (!rec) return; setBusy(true); setErr(null);
    try { setReport(await api.report(rec.data, rec.submitted_table5, rec.submitted_table4, { polish, reviewer: actor.name, reviewer_role: actor.role, case_id: rec.id, decisions: rec.decisions || {} })); } catch (e: Any) { setErr(String(e.message || e)); } finally { setBusy(false); }
  }
  const [dlBusy, setDlBusy] = useState<string | null>(null);
  async function download(kind: "docx" | "pdf") {
    if (!rec) return; setDlBusy(kind);
    try {
      const r = await fetch(`/api/cases/${encodeURIComponent(rec.id)}/report.${kind}?reviewer=${encodeURIComponent(actor.name)}&reviewer_role=${encodeURIComponent(actor.role)}`, { headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${rec.data.case.case_no}_審查意見書.${kind}`; a.click();
    } catch (e: Any) { setErr(String(e.message || e)); } finally { setDlBusy(null); }
  }
  if (!rec) return <Empty />;
  return (
    <div>
      <PageHeader print title="③ 審查意見書" desc="依審查結果逐條產生意見，每條標示編號與依據（作業手冊審查重點條號、評價基準明細表格位或查估辦法條號），數字全部來自核算結果。可選擇以語言模型潤飾文句；潤飾後系統會檢查每條編號與數字未被更動，不通過即保留原句。"
        input="審查結果清單、核算摘要" output="審查意見書（Word／PDF）" next={{ href: "/export", label: "輸出" }} />
      <StaleBanner what="審查結果" />
      <Card title="產生審查意見書" right={<>
        <span className="text-xs text-slate-600">落款：{actor.name ? `${actor.name}${actor.role ? `（${ROLE_LABEL[actor.role]}）` : ""}` : "（未填，請在側邊欄填操作身分）"}</span>
        <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={polish} onChange={(e) => setPolish(e.target.checked)} />語言模型潤飾（含守門檢查）</label>
        <Btn onClick={make} busy={busy} disabled={busy || stale} title={stale ? "產出已過期，請先重新產生書表" : undefined}>{busy ? "產生中…" : "重新產生"}</Btn>
        {report && <><Btn kind="ghost" onClick={() => download("docx")} busy={dlBusy === "docx"} disabled={!!dlBusy}>⬇ Word</Btn><Btn kind="ghost" onClick={() => download("pdf")} busy={dlBusy === "pdf"} disabled={!!dlBusy}>⬇ PDF</Btn></>}
      </>}>
        {err && <div className="text-red-700 text-sm">{err}</div>}
        {!report && !err && <div className="text-sm text-slate-500">意見書產生中…結論分三種：審查通過／請估價單位確認並敘明／請估價單位補正後再送審。審查結果頁的承辦裁決與說明會一併寫入。</div>}
        {report && (
          <>
            <div className="text-xs text-slate-500 mb-2">結論：{CONCLUSION_ZH[report.report.conclusion_code] || report.report.conclusion_code}；語言模型潤飾：{report.report.polish?.status || "未啟用"}{report.report.polish?.note ? `（${report.report.polish.note}）` : ""}{report.report.polish?.rejected?.length ? `；守門退回 ${report.report.polish.rejected.length} 條，已保留原句` : ""}</div>
            <div className="report-md text-sm leading-6 bg-slate-50 border rounded p-4" dangerouslySetInnerHTML={{ __html: marked.parse(report.markdown, { async: false }) as string }} />
            {report.report.figures?.length ? (
              <div className="mt-4">
                <div className="font-semibold mb-2">四、圖說（Word 與 PDF 會附上這三張圖）</div>
                <div className="grid md:grid-cols-3 gap-3">{report.report.figures.map((fg: Any) => (
                  <figure key={fg.mode} className="border rounded bg-white p-2"><img src={mapPngUrl(rec.id, fg.mode)} alt={fg.title} className="w-full" /><figcaption className="text-xs text-slate-600 mt-1">{fg.title}</figcaption></figure>))}</div>
              </div>) : null}
          </>
        )}
      </Card>
    </div>
  );
}
