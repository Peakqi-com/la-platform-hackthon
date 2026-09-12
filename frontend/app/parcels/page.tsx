"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import { Btn, Card, Empty, FacilityChip } from "@/components/ui";
import Legend from "@/components/Legend";
import PageHeader from "@/components/PageHeader";
import { Field, set } from "@/components/SurveyFields";
import { FormToolbar, keyNav, useDirty, useFormTools } from "@/components/FormTools";
import { Tip } from "@/components/Basis";
import { IOBadge } from "@/components/IO";
import { actorHeaders, zhError } from "@/lib/api";
import { api, Any, confidenceFor, fmtMoney, fmtPct, LOW_CONF } from "@/lib/api";

/* 填寫模式：表單由基準表產生（enum → 下拉、bands → 數字、boolean → 有無、distance → 設施名稱＋距離＋量測方式、manual → 文字）。
   每個欄位就是 rules JSON 的 survey_field / parcel_field，所以換基準表表單跟著換。 */

/* 比較標的固定三欄（查估辦法 §19：一至三件，實務上通常三件）：畫面一律顯示三欄，沒填的空欄位儲存時自動略過。 */
const COMP_SLOTS = 3;
function emptyComparable(no: number, subj: Any) {
  return { comp_no: no, parcel_id: "", section_id: subj?.section_id, normal_unit_price: null, transaction_date: "", date_adjustment: { pct: null },
    school: subj?.school ?? null, market: subj?.market ?? null, park: subj?.park ?? null, station: subj?.station ?? null, commercial_district: subj?.commercial_district ?? null, nuisance: subj?.nuisance ?? [], _slot: true };
}
function isEmptyComparable(c: Any) {
  return !String(c?.parcel_id || "").trim() && (c?.normal_unit_price == null || c?.normal_unit_price === "") && !String(c?.transaction_date || "").trim()
    && ["area_m2", "width_m", "depth_m", "shape", "frontage", "road_type", "zoning"].every((k) => c?.[k] == null || c?.[k] === "");
}
function padComparables(d: Any) {
  d.comparables = d.comparables || [];
  d.comparables.forEach((c: Any, i: number) => { c.comp_no = i + 1; });
  while (d.comparables.length < COMP_SLOTS) d.comparables.push(emptyComparable(d.comparables.length + 1, d.subject_parcel));
}
function cleanComparables(d: Any) {
  const out = JSON.parse(JSON.stringify(d));
  out.comparables = (out.comparables || []).filter((c: Any) => !isEmptyComparable(c)).map((c: Any, i: number) => { delete c._slot; return { ...c, comp_no: i + 1 }; });
  return out;
}

export default function Parcels({ embedded = false }: { embedded?: boolean } = {}) {
  const { rec, save, ruleName, label, generate, loadCase, status, meta, mode } = useCase();
  const fileRef = useRef<HTMLInputElement>(null);
  const [reg, setReg] = useState<Any>(null);
  const [ind, setInd] = useState<Any>(null);
  const [draft, setDraft] = useState<Any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState<Any>(null);            // 實價登錄候選（/comparables/search）
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [costs, setCosts] = useState<Record<string, string>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});   // 蒐集期間外參考案例的採用理由（手冊 p.77 問答四）
  const rs = rec?.data.case.rulesets || {};
  useEffect(() => { if (rs.regional) api.rule(rs.regional).then(setReg); if (rs.individual) api.rule(rs.individual).then(setInd); }, [rs.regional, rs.individual]);
  const [keepNotice, setKeepNotice] = useState<string | null>(null);
  const lastRecId = useRef<string | null>(null);
  const recKey = rec ? `${rec.id}:${rec.updated_at}` : "";
  useEffect(() => {
    if (!rec) return;
    const d0 = draft ? cleanComparables(draft) : null;
    const isDirty = !!d0 && JSON.stringify(d0) !== JSON.stringify(lastBase.current);
    if (isDirty && rec.id === lastRecId.current) { setKeepNotice("案件資料已更新（狀態或書表重新產生），你尚未儲存的修改仍保留；請儲存或按「重新載入」放棄。"); return; }
    lastRecId.current = rec.id; lastBase.current = rec.data; setKeepNotice(null);
    const d = JSON.parse(JSON.stringify(rec.data)); padComparables(d); setDraft(d);
  }, [recKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const lastBase = useRef<Any>(null);
  const sid = draft?.subject_parcel?.section_id;
  const section = draft?.sections?.[sid] || (draft ? Object.values(draft.sections)[0] : null);
  const parcelPath = (r: Any) => (r.parcel_field === "front_road_width_m" ? "front_road.width_m" : r.parcel_field);
  const distRules = useMemo(() => (ind?.rules || []).filter((r: Any) => r.criteria?.type === "distance"), [ind]);
  const dirty = useDirty(draft ? cleanComparables(draft) : draft, rec?.data);
  const tools = useFormTools(dirty);
  const indGroups = useMemo(() => { const g: Record<string, Any[]> = {}; (ind?.rules || []).filter((r: Any) => r.item_no && r.criteria?.type !== "manual").forEach((r: Any) => (g[String(r.group)] = g[String(r.group)] || []).push(r)); return g; }, [ind]);
  const gname = (g: string) => ind?.groups?.find((x: Any) => String(x.no) === g)?.name || g;
  const confP = (i: number, field: string) => confidenceFor(rec?.extraction, i === 0 ? `subject_parcel.${field}` : `comparables[${i - 1}].${field}`);

  /* 使用分區改變 → 依 rules/zoning_bcr_far.json（細部計畫土管要點／施行細則附表一）帶出法定建蔽率、容積率；只填空白欄位或先前推定的欄位，並標推定。 */
  function applyBcrFar(target: Any, zone: string) {
    const t = meta?.zoning_bcr_far; if (!t || !zone) return;
    const z = zone.split(":").pop() || zone; const district = String(rec?.data.case.district || "").replace("新北市", "").replace("台", "臺");
    let v: Any = null; let src = "";
    for (const [name, plan] of Object.entries<Any>(t.plans || {})) { if ((plan.districts || []).includes(district) && plan.zones?.[z]) { v = plan.zones[z]; src = t.sources?.[name] || name; break; } }
    if (!v) { const county = t.county_default?.["新北市"] || {}; const main = Object.keys(county).find((k) => z === k) || Object.keys(county).find((k) => z.includes(k)); if (main) { v = county[main]; src = t.sources?.["施行細則"] || "施行細則"; } }
    if (!v) return;
    target.derived = target.derived || {};
    for (const [field, key, lbl] of [["bcr_pct", "bcr", "建蔽率"], ["far_pct", "far", "容積率"]] as [string, string, string][]) {
      if (v[key] == null) continue;
      if (target[field] == null || target[field] === "" || target.derived[field]) { target[field] = v[key]; target.derived[field] = { source: src, note: `${z} 法定${lbl} ${v[key]}%；${v.note || ""}` }; }
    }
  }
  async function recalc(saveIt: boolean) {
    if (!draft) return; setBusy(true); setMsg(null);
    try { if (saveIt && rec) { await save({ data: cleanComparables(draft) }); await generate(); setMsg("已儲存並重新產生書表。"); } } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function importFile(file: File) {
    if (!rec) return; setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("kind", "auto");
      const r = await fetch(`/api/cases/${encodeURIComponent(rec.id)}/import`, { method: "POST", body: fd, headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const j = await r.json();
      await loadCase(rec.id);
      setMsg(`已匯入 ${file.name}（${j.kind === "parcels" ? "宗地個別因素清冊" : "買賣實例"}）：${j.matched.join("、") || "沒有對到任何宗地"}${j.unmatched.length ? `；對不到：${j.unmatched.join("、")}（地號須與本案相同）` : ""}。更新 ${j.changes} 欄，請按「儲存並重新產生書表」。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }
  async function searchLvr() {
    if (!rec) return; setBusy(true); setMsg(null);
    try {
      const r = await api.comparablesSearch(rec.id, {});
      setSearch(r); const pk: Record<string, boolean> = {}; r.chosen.forEach((c: Any) => { pk[c.id] = true; }); setPicked(pk); setReasons({});
      const st = r.stats;
      const warn = r.vdate_warning ? `${r.vdate_warning} ` : "";
      const gap = r.coverage && !r.coverage.covers_window ? `${r.coverage.note} 請先下載對應季別：${r.coverage.fetch_cmd}，重新啟動後端後再搜尋。` : "";
      setMsg(r.chosen.length ? `${warn}依查估辦法 §17、§19 自動選出 ${r.chosen.length} 件純土地實例，已勾選；確認後按「採用勾選的實例」。` :
        gap ? `${warn}${gap}` :
        `${warn}實價登錄沒有可自動採用的純土地實例：蒐集期間 ${r.window?.text}，放寬至 ${r.window?.relaxed_from}；同用地別 ${st.n_zone} 筆，特殊情況排除 ${st.n_excluded} 筆。含建物的實例填入建物成本價格後可勾選採用（查估辦法 §13 第3、4款）；下方「蒐集期間外參考案例」勾選並填理由亦可採用。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function applyLvr() {
    if (!rec || !search) return;
    const ids = Object.keys(picked).filter((k) => picked[k]);
    if (!ids.length) { setMsg("請先勾選實例。"); return; }
    if (ids.length > 3) { setMsg("比較標的最多三件（查估辦法 §19 第1項第1款）。"); return; }
    const bc: Record<string, number> = {};
    const rs: Record<string, string> = {};
    const all: Any[] = [...(search.candidates || []), ...(search.reference || [])];
    for (const id of ids) {
      const c = all.find((x: Any) => x.id === id);
      if (c?.needs_building_cost) { const v = Number(costs[id] ?? c.building_cost_estimate?.cost); if (!v) { setMsg(`${c.parcel_id} 含建物，請先填建物成本價格。`); return; } bc[id] = v; }
      if (c?.out_of_window) { const t = (reasons[id] || "").trim(); if (!t) { setMsg(`${c.parcel_id} 為蒐集期間外參考案例，請填採用理由（會寫進備註欄，手冊 p.77 問答四）。`); return; } rs[id] = t; }
    }
    setBusy(true); setMsg(null);
    try {
      const r = await api.comparablesApply(rec.id, ids, bc, rs);
      await loadCase(rec.id); await generate(); setSearch(null);
      setMsg(`已採用 ${r.comparables.length} 件為比較標的並重新產生書表。${r.notes?.length ? r.notes.join("；") : ""}`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  if (!rec || !draft) return <Empty />;
  const comps: Any[] = draft.comparables || [];
  function removeComparable(i: number) {
    const d = JSON.parse(JSON.stringify(draft)); d.comparables.splice(i, 1); padComparables(d); setDraft(d);
  }
  return (
    <div>
      {!embedded && <PageHeader title="① 輸入資料：宗地條件（宗地個別因素清冊）與買賣實例" desc="比準地與各比較標的的個別因素（面積、寬深、形狀、臨街、道路、接近條件、周邊環境、行政條件）與比較標的交易資料。可由需用土地人之宗地個別因素清冊 xlsx、買賣實例 xlsx 上傳，或在此填寫；接近條件可依比準地位置自動量測。"
        input="宗地個別因素清冊、買賣實例調查估價表（土地正常單價、交易日期、期日調整）、個別因素評價基準明細表" output="各宗地個別因素事實 → 比較法調查估價表" next={{ href: "/input?tab=rules", label: "評價基準明細表" }} />}
      {<Legend kinds={["source"]} />}
      <div className="space-y-4">
      <div>
        <Card title={<>宗地條件（宗地個別因素清冊）與比較標的交易資料 <IOBadge kind="import" what="送審書表 PDF；清冊／實例 xlsx（選填）" /> <IOBadge kind="export" what="xlsx" /></>} hint={`適用基準表：${ruleName(rs.individual)}。比較標的之接近條件與嫌惡設施，除鄰近另有同等級設施外，應填與比準地相同之設施（手冊 p.51）。`} right={<><Btn onClick={() => recalc(true)} disabled={busy} busy={busy}>儲存並重新產生書表</Btn></>}>
          {keepNotice && <div className="text-sm text-amber-900 bg-amber-50 border border-amber-300 rounded p-2 mb-2 flex items-center gap-2">{keepNotice}<button className="underline text-xs" onClick={() => { const d = JSON.parse(JSON.stringify(rec!.data)); padComparables(d); setDraft(d); lastBase.current = rec!.data; setKeepNotice(null); }}>重新載入（放棄修改）</button></div>}
            {msg && <div className="text-xs bg-slate-50 border rounded p-2 mb-2">{msg}</div>}
          <div className="no-print flex flex-wrap items-center gap-2 mb-2 text-xs"><span className="text-slate-500">檔案：</span>
            <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile(f); }} />
            <button className="px-3 py-1.5 rounded text-sm whitespace-nowrap btn-io-import disabled:opacity-50" disabled={busy} onClick={() => fileRef.current?.click()} title="上傳宗地個別因素清冊 xlsx 或買賣實例 xlsx，依地號併入本案（只覆蓋檔案裡有值的欄位）">⬆ 匯入清冊／實例 xlsx</button>
            <a className="px-3 py-1.5 rounded text-sm whitespace-nowrap bg-white border border-emerald-300 text-emerald-800 hover:bg-emerald-50" href={`/api/cases/${encodeURIComponent(rec.id)}/parcels.xlsx`} download title="匯出宗地個別因素清冊，可填好再匯入">⬇ 清冊 xlsx</a>
            <a className="px-3 py-1.5 rounded text-sm whitespace-nowrap bg-white border border-emerald-300 text-emerald-800 hover:bg-emerald-50" href={`/api/cases/${encodeURIComponent(rec.id)}/comparables.xlsx`} download title="匯出買賣實例，可填好再匯入">⬇ 實例 xlsx</a>
                      </div>
          <FormToolbar tools={tools} groups={Object.keys(indGroups)} dirty={dirty} />
          <div className="no-print text-xs mb-2 flex items-center gap-2"><span className="text-slate-500">比較標的 {comps.filter((c) => !isEmptyComparable(c)).length} 件已填（查估辦法 §19：一至三件；空欄不會存入）</span>{mode === "generate" && <Btn kind="ghost" onClick={searchLvr} disabled={busy} busy={busy} title="依查估辦法 §17 蒐集期間、§7 特殊情況、§13 正常單價、§19 同區段→其他地區，從內政部實價登錄找 1～3 件">⬇ 自動蒐集比較標的（實價登錄）</Btn>}</div>
          {search && <div className="no-print text-xs mb-3 border border-orange-200 bg-orange-50/50 rounded p-2">
            <div className="flex flex-wrap items-center gap-3 mb-1"><b>實價登錄候選</b><span>蒐集期間 {search.window?.text}（放寬至 {search.window?.relaxed_from}）</span><span>同用地別 {search.stats.n_zone} 筆，可採用 {search.stats.n_clean} 筆，特殊情況排除 {search.stats.n_excluded} 筆</span>
              <Btn onClick={applyLvr} disabled={busy} busy={busy}>採用勾選的實例</Btn><button className="underline text-slate-500" onClick={() => setSearch(null)}>關閉</button></div>
            <div className="text-slate-600 mb-1">{search.stages.filter((s: Any) => s.n).map((s: Any) => `${s.name}：${s.n} 件`).join("；") || "各階段皆無可自動採用之純土地實例"}</div>
            {search.candidates.length ? <div className="overflow-x-auto max-h-72 overflow-y-auto"><table className="grid text-[11px] min-w-[72rem]"><thead><tr><th></th><th className="min-w-[14rem]">地號／位置</th><th>交易日期</th><th>總價</th><th>土地面積</th><th>單價 元/m²</th><th>分區</th><th>階段</th><th>特殊情況／說明</th><th>建物成本價格（元）</th></tr></thead><tbody>
              {search.candidates.map((c: Any) => { const can = !c.excluded || c.needs_building_cost; return (
                <tr key={c.id} className={c.excluded && !c.needs_building_cost ? "opacity-60" : ""}>
                  <td><input type="checkbox" disabled={!can} checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} /></td>
                  <td className="whitespace-normal">{c.needs_building_cost ? `${c.position}（${c.parcel_id}）` : c.parcel_id}<div className="text-slate-500">{c.district}{c.in_section ? "・同區段" : c.distance_m != null ? `・距比準地 ${c.distance_m} m` : "・無界線"}</div></td>
                  <td>{c.date}{!c.in_window && <div className="text-amber-800">期間外（放寬）</div>}</td><td className="text-right font-mono">{fmtMoney(c.total_price)}</td><td className="text-right font-mono">{c.total_area}</td><td className="text-right font-mono">{fmtMoney(c.unit_price)}</td>
                  <td>{(c.lot_zones || []).map((z: string) => z.split(":").pop()).join("、") || c.zone}</td><td>{c.stage}</td>
                  <td className="max-w-[22rem] whitespace-normal">{c.flags.map((f: Any) => <div key={f.rule + f.label} className={f.exclude && !f.needs_building_cost ? "text-rose-700" : "text-amber-800"}>{f.label}（{f.rule}）</div>)}{c.building ? <div className="text-slate-500">建物 {c.building.type} {c.building.material} 完工 {c.building.completed} 建物面積 {c.building.area} m² 樓層 {c.building.level}/{c.building.floors}</div> : null}</td>
                  <td>{c.needs_building_cost ? <div><input className="border rounded px-1 w-28" type="number" placeholder="建物成本" value={costs[c.id] ?? c.building_cost_estimate?.cost ?? ""} onChange={(e) => setCosts({ ...costs, [c.id]: e.target.value })} />
                    {c.building_cost_estimate ? <div className="text-amber-800 whitespace-normal max-w-[16rem]" title={c.building_cost_estimate.note}>推定 {fmtMoney(c.building_cost_estimate.cost)} 元（第四號公報成本法：每坪 {fmtMoney(c.building_cost_estimate.unit_cost_per_ping)} × {c.building_cost_estimate.area_ping} 坪，折舊 {c.building_cost_estimate.depreciation_pct}%），可改</div> : <div className="text-rose-700">無法推定，請填</div>}</div> : "—"}</td>
                </tr>); })}
            </tbody></table></div> : <div className="text-rose-700">{search.coverage && !search.coverage.covers_window ? `${search.coverage.note} 請先下載對應季別（${search.coverage.fetch_cmd}）。` : "實價登錄在蒐集期間與放寬期間內沒有同用地別的實例。"}處理順序：§17 第3項放寬一年、§19 第2項其他地區、§13 第3、4款含建物實例扣建物成本（以上系統已做）→ 下方期間外參考案例（須敘明理由）→ §14 收益法 → 人工填寫買賣實例。</div>}
            {search.reference?.length ? <details className="mt-2">
              <summary className="cursor-pointer text-slate-700"><b>蒐集期間外參考案例</b>（{search.reference.length} 件，手冊 p.77 問答四）：預設不採用；勾選採用須填理由，理由會寫進備註欄，審查時列為不符項由承辦裁決</summary>
              <div className="overflow-x-auto max-h-72 overflow-y-auto mt-1"><table className="grid text-[11px] min-w-[72rem]"><thead><tr><th></th><th className="min-w-[14rem]">地號／位置</th><th>交易日期</th><th>總價</th><th>土地面積</th><th>單價 元/m²</th><th>分區</th><th>與期間差距</th><th>特殊情況／說明</th><th>建物成本價格（元）</th><th className="min-w-[16rem]">採用理由 *</th></tr></thead><tbody>
                {search.reference.map((c: Any) => (
                  <tr key={c.id} className={picked[c.id] ? "" : "opacity-70"}>
                    <td><input type="checkbox" checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} /></td>
                    <td className="whitespace-normal">{c.needs_building_cost ? `${c.position}（${c.parcel_id}）` : c.parcel_id}<div className="text-slate-500">{c.district}{c.in_section ? "・同區段" : c.distance_m != null ? `・距比準地 ${c.distance_m} m` : "・無界線"}</div></td>
                    <td>{c.date}</td><td className="text-right font-mono">{fmtMoney(c.total_price)}</td><td className="text-right font-mono">{c.total_area}</td><td className="text-right font-mono">{fmtMoney(c.unit_price)}</td>
                    <td>{(c.lot_zones || []).map((z: string) => z.split(":").pop()).join("、") || c.zone}</td><td className="text-amber-800">{c.days_from_window} 天</td>
                    <td className="max-w-[22rem] whitespace-normal">{c.flags.filter((f: Any) => !f.out_of_window).map((f: Any) => <div key={f.rule + f.label} className={f.exclude && !f.needs_building_cost ? "text-rose-700" : "text-amber-800"}>{f.label}（{f.rule}）</div>)}{c.building ? <div className="text-slate-500">建物 {c.building.type} {c.building.material} 完工 {c.building.completed} 建物面積 {c.building.area} m² 樓層 {c.building.level}/{c.building.floors}</div> : null}</td>
                    <td>{c.needs_building_cost ? <div><input className="border rounded px-1 w-28" type="number" placeholder="建物成本" value={costs[c.id] ?? c.building_cost_estimate?.cost ?? ""} onChange={(e) => setCosts({ ...costs, [c.id]: e.target.value })} />{c.building_cost_estimate ? <div className="text-amber-800 whitespace-normal max-w-[16rem]">推定 {fmtMoney(c.building_cost_estimate.cost)} 元，可改</div> : <div className="text-rose-700">無法推定，請填</div>}</div> : "—"}</td>
                    <td><input className="border rounded px-1 w-full" placeholder="例：蒐集期間內無同用地別實例，取最接近期間之案例並經期日調整" value={reasons[c.id] ?? ""} onChange={(e) => setReasons({ ...reasons, [c.id]: e.target.value })} /></td>
                  </tr>))}
              </tbody></table></div></details> : null}
          </div>}
          {ind ? <div className="overflow-x-auto"><table className="grid" onKeyDown={keyNav}><thead><tr><th>細項</th><th>比準地 {draft.subject_parcel.parcel_id}</th>{comps.map((c, i) => <th key={c.comp_no} className="align-middle"><div className="flex flex-col items-center gap-1"><span>比較標的{c.comp_no}</span><span className="whitespace-nowrap"><input className="border rounded px-1 w-28 font-normal" placeholder="地號" value={c.parcel_id || ""} onChange={(e) => { const d = JSON.parse(JSON.stringify(draft)); d.comparables[i].parcel_id = e.target.value; setDraft(d); }} /> <button className="text-xs text-slate-400 hover:text-red-700 underline font-normal" title="清空此比較標的的所有欄位" onClick={() => removeComparable(i)}>清空</button></span></div></th>)}</tr></thead><tbody>
            {Object.entries(indGroups).map(([g, rulesAll]) => {
              const t4c = status.run?.table4?.comparables?.[0];
              const visible = rulesAll.filter((r: Any) => {
                const row = t4c?.rows?.find((x: Any) => x.item_no === r.item_no);
                const empty = [draft.subject_parcel, ...comps].some((p: Any) => { const v = r.parcel_field === "front_road_width_m" ? p.front_road?.width_m : p[r.parcel_field]; return v === null || v === undefined || v === ""; });
                const low = [draft.subject_parcel, ...comps].some((_p: Any, i: number) => { const c = confP(i, r.parcel_field); return c !== null && c < LOW_CONF; });
                if (tools.filter === "manual") return empty;
                if (tools.filter === "attention") return !!row?.issues?.length || row?.pct === null;
                if (tools.filter === "lowconf") return low;
                return true;
              });
              if (!visible.length) return null;
              const closed = tools.collapsed.has(g);
              const head = <tr key={`g${g}`} className="cursor-pointer" onClick={() => tools.toggle(g)}><td colSpan={2 + comps.length} className="bg-[#ffedd5] font-medium">{closed ? "▸" : "▾"} {g} {gname(g)} <span className="text-xs text-slate-500 font-normal">（{visible.length} 項{closed ? "，已收合" : ""}）</span></td></tr>;
              if (closed) return head;
              return [head, ...visible.map((r: Any) => (
              <tr key={r.id}><td className="w-40"><Tip k={[`t4.item.${r.item_no}`, r.criteria?.type === "distance" ? "t1.reference" : "t4.item"]}>{r.item_no} {r.name}</Tip></td>
                {[draft.subject_parcel, ...comps].map((p: Any, i: number) => { const c = confP(i, r.parcel_field); return (
                  <td key={i} className={c !== null && c < LOW_CONF ? "bg-yellow-50" : ""}><Field rule={r} scope="individual" typeLabel={(t) => label("facility_types", t)} value={r.parcel_field === "front_road_width_m" ? p.front_road?.width_m : p[r.parcel_field]} onChange={(v) => { const d = JSON.parse(JSON.stringify(draft)); const target = i === 0 ? d.subject_parcel : d.comparables[i - 1]; if (r.parcel_field === "front_road_width_m") target.front_road = { ...(target.front_road || {}), width_m: v }; else set(target, parcelPath(r), v); if (r.parcel_field === "zoning") applyBcrFar(target, String(v || "")); setDraft(d); }} />
                    {c !== null && c < LOW_CONF && <div className="text-[10px] text-yellow-800">抽取信心 {Math.round(c * 100)}%，請核對原件</div>}
                    {i === 0 && (() => { const dv = draft.subject_parcel.derived?.[r.parcel_field === "front_road_width_m" ? "front_road" : r.parcel_field]; return dv ? <div className="text-[10px] text-amber-800" title={dv.note}>推定（{dv.source}），請確認</div> : null; })()}</td>); })}
              </tr>))]; })}
            <tr><td><Tip k="comp.window">交易資料</Tip></td><td></td>{comps.map((c, i) => <td key={i} className="text-xs">土地正常單價 <input className="border rounded px-1 w-24" type="number" value={c.normal_unit_price ?? ""} onChange={(e) => { const d = JSON.parse(JSON.stringify(draft)); d.comparables[i].normal_unit_price = Number(e.target.value); setDraft(d); }} /> 交易日期 <input className="border rounded px-1 w-24" value={c.transaction_date || ""} onChange={(e) => { const d = JSON.parse(JSON.stringify(draft)); d.comparables[i].transaction_date = e.target.value; setDraft(d); }} /> 期日調整率(%) <input className="border rounded px-1 w-16" type="number" step="0.01" value={c.date_adjustment?.pct ?? ""} onChange={(e) => { const d = JSON.parse(JSON.stringify(draft)); d.comparables[i].date_adjustment = { ...(c.date_adjustment || {}), pct: Number(e.target.value) }; setDraft(d); }} /></td>)}</tr>
          </tbody></table></div> : "載入基準表…"}
        </Card>
      </div>
      <div>
        <Card title="比準地設施距離與量測方式" hint="距離由「案件與地價區段」分頁的比準地位置自動量測，要重量請到該分頁按「重新量測設施距離」。作業手冊 p.24：需通達之設施採路線距離，嫌惡設施採直線距離，同一案件各細項量測標準一致；同一細項有多處設施時填影響最大者，全案共用同一參照設施。">
          <div className="text-xs space-y-1">{distRules.map((r: Any) => <div key={r.id}>{r.item_no} {r.name}：<FacilityChip f={Array.isArray(draft.subject_parcel[r.parcel_field]) ? draft.subject_parcel[r.parcel_field][0] : draft.subject_parcel[r.parcel_field]} /></div>)}</div>
        </Card>
      </div>
      </div>
    </div>
  );
}
