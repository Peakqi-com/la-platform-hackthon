"use client";
import { useRef, useEffect, useState } from "react";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import Legend from "@/components/Legend";
import { StaleBanner } from "@/components/Stale";
import PageHeader from "@/components/PageHeader";
import { Field, SourceBadge, get, set } from "@/components/SurveyFields";
import { Badge, Btn, Card, Empty } from "@/components/ui";
import { api, Any, confidenceFor, LOW_CONF } from "@/lib/api";
import { FormToolbar, keyNav, useDirty, useFormTools } from "@/components/FormTools";
import { Tip } from "@/components/Basis";
import { IOBadge } from "@/components/IO";

/* 地價區段勘查表是「產出」：可能僅取得年期、區段編號、區段範圍。系統依分區圖、路網、設施資料庫推算可推的欄位，其餘標需人工填載，估價人員確認後存檔。 */
export default function Table1() {
  const { rec, save, ruleName, label, status, generate } = useCase();
  const [reg, setReg] = useState<Any>(null);
  const [draft, setDraft] = useState<Any>(null);
  const [prov, setProv] = useState<Any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rs = rec?.data.case.rulesets || {};
  useEffect(() => { if (rs.regional) api.rule(rs.regional).then(setReg); }, [rs.regional]);
  const sid = draft?.subject_parcel?.section_id;
  const section = draft?.sections?.[sid] || (draft ? Object.values(draft.sections)[0] as Any : null);
  const t5 = status.run?.table5 ? (Object.values(status.run.table5)[0] as Any) : null;   // 判定等級欄用全站共用的核算結果
  const dirty = useDirty(draft, rec?.data);
  const tools = useFormTools(dirty);
  const [keepNotice, setKeepNotice] = useState<string | null>(null);
  const lastRecId = useRef<string | null>(null);
  const recKey = rec ? `${rec.id}:${rec.updated_at}` : "";
  useEffect(() => {
    if (!rec) return;
    if (dirty && draft && rec.id === lastRecId.current) { setKeepNotice("案件資料已更新（狀態或書表重新產生），你尚未儲存的修改仍保留；請儲存或按「重新載入」放棄。"); return; }
    lastRecId.current = rec.id; setKeepNotice(null);
    const d = JSON.parse(JSON.stringify(rec.data)); setDraft(d); const sec = d.sections[d.subject_parcel?.section_id] || Object.values(d.sections)[0]; setProv(sec?.survey_provenance || null);
  }, [recKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const conf = (field: string) => confidenceFor(rec?.extraction, `sections.${section?.section_id}.survey.${field}`);

  async function inferAll(overwrite: boolean) {
    if (!draft) return; setBusy(true); setMsg(null);
    try {
      const r = await api.spatialSurveyDraft(draft, section.section_id, overwrite);
      setDraft(r.data); setProv({ filled: r.filled, suggestions: r.suggestions, manual: r.manual });
      setMsg(`已推算 ${r.filled.length} 個欄位；${Object.keys(r.suggestions).length} 個欄位有建議值待確認；${Object.keys(r.manual).length} 個欄位需人工填載。${r.warnings.join("；")}`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function recalc(saveIt: boolean) {
    if (!draft) return; setBusy(true); setMsg(null);
    try { if (saveIt) { await save({ data: draft }); await generate(); setMsg("已儲存並重新產生書表。"); } } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  function acceptSuggestion(field: string) {
    const s = prov?.suggestions?.[field]; if (!s) return;
    const d = JSON.parse(JSON.stringify(draft)); set(d.sections[section.section_id].survey, field, s.value); setDraft(d);
  }
  if (!rec || !draft || !section) return <Empty />;
  const provOf = (f: string) => (prov?.filled?.includes(f) ? "filled" : prov?.suggestions?.[f] ? "suggested" : prov?.manual?.[f] ? "manual" : undefined);
  const groups: Record<string, Any[]> = {};
  (reg?.rules || []).filter((r: Any) => r.survey_field && r.criteria?.type !== "manual").forEach((r: Any) => (groups[r.group] = groups[r.group] || []).push(r));
  const gname = (g: string) => reg?.groups?.find((x: Any) => String(x.no) === String(g))?.name || g;
  const filledN = prov?.filled?.length ?? 0, manualN = Object.keys(prov?.manual || {}).length, sugN = Object.keys(prov?.suggestions || {}).length;
  return (
    <div>
      <PageHeader print title="② 產出書表：地價區段勘查表（審查對照檢視）" desc="勘查表記錄地價區段的區域因素事實。來源三種：系統推算（設施距離依設施資料庫與路網量測，需通達者步行距離、嫌惡設施直線距離；都市計畫內外與主分區依新北市使用分區圖；主要道路依貼著區段邊界之最高等級道路）、有建議值（圖資只到「商業區」層級，基準表若以「第X種商業區」判定，系統不自行填，請確認後採用或改填）、需人工填載（建蔽率／容積率／禁限建、路寬、道路闢建程度、排水、地勢、顧客通行量、店舖毗連等屬實地勘查或都市計畫書事項）。法源：查估辦法第 9、10 條；作業手冊 p.24 量測標準、p.11 審查重點 iii。若僅有年期、區段編號與區段範圍，可按「依圖資推算」由系統填入能推算的欄位（設施距離、都市計畫內外、主要道路），其餘實地勘查事項標示需人工填載，確認後存檔。"
        input="區段範圍（「案件與地價區段」分頁）、都市計畫使用分區圖、路網、設施資料庫、評價基準明細表" output="地價區段勘查表各細項事實與判定等級 → 影響地價區域因素分析明細表" next={{ href: "/tables?tab=5", label: "影響地價區域因素分析明細表" }} />
      <StaleBanner what="書表" />
      <Legend kinds={["source"]} />
      <div>
        <div>
          <Card title={<>地價區段勘查表 — 年期 {draft.case.valuation_date}・區段編號 {section.section_id} <IOBadge kind="import" what="送審書表 PDF" /> <IOBadge kind="export" what="Excel／PDF" /></>} lead={`區段範圍：${section.range_desc || "（未填，請至「案件與地價區段」分頁）"}｜適用：${ruleName(rs.regional)}`}
            right={<><Btn kind="ghost" onClick={() => inferAll(false)} disabled={busy || !section.geometry} title={section.geometry ? "只填空白欄位" : "區段尚無範圍，請先到案件基本資料頁推估"}>依圖資推算（填空白欄）</Btn><Btn kind="ghost" onClick={() => inferAll(true)} disabled={busy || !section.geometry}>重新推算全部</Btn><Btn onClick={() => recalc(true)} disabled={busy} busy={busy}>儲存並重新產生書表</Btn></>}>
            {!section.geometry && <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 mb-2">此區段尚無範圍多邊形，無法推算距離與分區。請到 <Link className="underline" href={`/case?case=${rec.id}`}>案件與地價區段基本資料</Link> 頁在圖上推估區段範圍。</div>}
            {keepNotice && <div className="text-sm text-amber-900 bg-amber-50 border border-amber-300 rounded p-2 mb-2 flex items-center gap-2">{keepNotice}<button className="underline text-xs" onClick={() => { setDraft(JSON.parse(JSON.stringify(rec!.data))); setKeepNotice(null); }}>重新載入（放棄修改）</button></div>}
            {msg && <div className="text-xs bg-slate-50 border rounded p-2 mb-2">{msg}</div>}
            {prov && <div className="text-xs mb-2 flex gap-2"><span className="rounded px-1.5 bg-sky-100 text-sky-800">系統推算 {filledN}</span><span className="rounded px-1.5 bg-amber-100 text-amber-800">有建議值 {sugN}</span><span className="rounded px-1.5 bg-rose-100 text-rose-800">需人工填載 {manualN}</span></div>}
            <FormToolbar tools={tools} groups={Object.keys(groups)} dirty={dirty} />
            {reg ? <div className="overflow-x-auto"><table className="grid" onKeyDown={keyNav}><thead><tr><th className="whitespace-nowrap">主要項目</th><th>修正細項</th><th>勘查事實</th><th className="whitespace-nowrap">來源</th><th className="whitespace-nowrap">判定等級</th></tr></thead><tbody>
              {Object.entries(groups).map(([g, rulesAll]) => {
                const visible = rulesAll.filter((r: Any) => {
                  const row = t5?.rows?.find((x: Any) => x.rule_id === r.id); const p = provOf(r.survey_field); const c = conf(r.survey_field);
                  if (tools.filter === "manual") return p === "manual";
                  if (tools.filter === "attention") return p === "suggested" || !!row?.issues?.length || (row && row.subject_level === null);
                  if (tools.filter === "lowconf") return c !== null && c < LOW_CONF;
                  return true;
                });
                if (!visible.length) return null;
                const closed = tools.collapsed.has(g);
                const head = <tr key={`g${g}`} className="cursor-pointer" onClick={() => tools.toggle(g)}><td colSpan={5} className="bg-[#ffedd5] font-medium">{closed ? "▸" : "▾"} {gname(g)} <span className="text-xs text-slate-500 font-normal">（{visible.length} 項{closed ? "，已收合" : ""}）</span></td></tr>;
                if (closed) return head;
                return [head, ...visible.map((r: Any) => {
                const row = t5?.rows?.find((x: Any) => x.rule_id === r.id);
                const val = get(section.survey, r.survey_field);
                const p = provOf(r.survey_field);
                const c = conf(r.survey_field);
                return <tr key={r.id} className={p === "manual" ? "bg-rose-50/40" : c !== null && c < LOW_CONF ? "bg-yellow-50" : ""}>
                  <td className="text-xs text-slate-400"></td>
                  <td className="w-52"><Tip k={[r.criteria?.type === "distance" ? "t1.distance" : r.survey_field?.startsWith("land_control") ? "t1.zoning" : "t1.row"]}>{r.name}</Tip></td>
                  <td><Field rule={r} scope="regional" typeLabel={(t) => label("facility_types", t)} value={val} onChange={(v) => { const d = { ...draft }; set(d.sections[section.section_id].survey, r.survey_field, r.criteria.type === "bands" && r.survey_field.includes("width") ? { ...(val || {}), value: v } : v); setDraft(d); }} />
                    {p === "suggested" && <div className="text-xs mt-1 text-amber-800">建議：{typeof prov.suggestions[r.survey_field].value === "object" ? JSON.stringify(prov.suggestions[r.survey_field].value) : String(prov.suggestions[r.survey_field].value)}（{prov.suggestions[r.survey_field].source}）— {prov.suggestions[r.survey_field].note} <button className="underline" onClick={() => acceptSuggestion(r.survey_field)}>採用</button></div>}
                    {p === "manual" && <div className="text-xs mt-1 text-rose-700">{prov.manual[r.survey_field]}</div>}</td>
                  <td className="w-28"><SourceBadge v={val} prov={p} />{c !== null && c < LOW_CONF && <div className="text-[10px] text-yellow-800">抽取信心 {Math.round(c * 100)}%，請核對原件</div>}</td>
                  <td className="w-24">{row ? (row.subject_level ?? <Badge kind="warn">需人工確認</Badge>) : "—"}</td></tr>; })]; })}
            </tbody></table></div> : "載入基準表…"}
          </Card>
        </div>
      </div>
    </div>
  );
}
