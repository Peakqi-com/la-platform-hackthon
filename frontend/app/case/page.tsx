"use client";
import { useDirty } from "@/components/FormTools";
import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useCase } from "@/components/CaseContext";
import PageHeader from "@/components/PageHeader";
import { vdateHint } from "@/components/vdate";
import { Btn, Card, Empty, Help } from "@/components/ui";
import { actorHeaders, api, Any, zhError } from "@/lib/api";
import FillReport from "@/components/FillReport";
import { InputsCard } from "@/components/Inputs";
const LeafletMap = dynamic(() => import("@/components/LeafletMap"), { ssr: false });

/* 案件與地價區段基本資料：通常僅有年期、區段編號、區段範圍文字。區段範圍多邊形與比準地位置在圖上設定，之後勘查表、設施距離、圖說都靠它。 */
export default function CasePage({ embedded = false }: { embedded?: boolean } = {}) {
  const { rec, save, label, ruleName, generate, meta, loadCase, mode: caseMode } = useCase();
  const cadRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<Any>(null);
  const [layers, setLayers] = useState<Any>(null);
  const [showAll, setShowAll] = useState(false);       // 地圖取景：預設比準地周邊，可切成含遠處比較標的
  const [preloaded, setPreloaded] = useState<{ n?: number; districts?: string[] } | null>(null);     // 預載地籍圖（沒有匯入本案地籍圖時用它）
  useEffect(() => { api.cadastreLots().then((r) => setPreloaded(r.n ? { n: r.n, districts: r.districts } : null)).catch(() => setPreloaded(null)); }, []);
  const [mode, setMode] = useState<"" | "section" | "subject" | "poi" | "comp">("");
  const [poi, setPoi] = useState({ type: "substation", name: "" });
  const [hints, setHints] = useState<[number, number][]>([]);
  const [preview, setPreview] = useState<Any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<{ step: string; ok: boolean; note: string }[] | null>(null);
  const [overwriteLot, setOverwriteLot] = useState(false);
  const [showReport, setShowReport] = useState(false);
  useEffect(() => { try { if (new URL(window.location.href).searchParams.get("report") === "1") setShowReport(true); } catch { /* ignore */ } }, []);   // 一鍵建案後帶 report=1 直接展開清單
  const [reportKey, setReportKey] = useState(0);
  const dirty = useDirty(draft, rec?.data);
  const [keepNotice, setKeepNotice] = useState<string | null>(null);
  const [compTarget, setCompTarget] = useState<number>(1);      // 在圖上設定位置的比較標的
  const pdfRef = useRef<HTMLInputElement>(null);
  async function attachPdf(file: File) {
    if (!rec) return; setBusy(true); setMsg(null);
    try {
      const r = await api.addInputs(rec.id, [file]);
      const e = r.results[0];
      if (e?.error) throw new Error(e.error);
      await loadCase(rec.id);
      setMsg(e?.skipped ? String(e.summary) : `已補上送審書表 ${file.name}${e?.missing?.length ? `（抽取缺漏 ${e.missing.length} 欄）` : ""}${e?.conflicts?.length ? `；與既有資料不一致 ${e.conflicts.length} 處（保留既有值，見「輸入檔」卡片）` : ""}；到「③ 審查」逐格比對。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  const recKey = rec ? `${rec.id}:${rec.updated_at}` : "";
  useEffect(() => {                                                    // 案件真的變了才重載；有未儲存修改就保留並提示
    if (!rec) return;
    if (dirty && draft && rec.id === lastRecId.current) { setKeepNotice("案件資料已更新（狀態或書表重新產生），你尚未儲存的修改仍保留；請儲存或按「重新載入」放棄。"); return; }
    lastRecId.current = rec.id; setKeepNotice(null);
    setDraft(JSON.parse(JSON.stringify(rec.data))); api.mapLayers(rec.data).then(setLayers).catch(() => null);
  }, [recKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const lastRecId = useRef<string | null>(null);
  const sid = draft?.subject_parcel?.section_id;
  const section = draft?.sections?.[sid] || (draft ? Object.values(draft.sections)[0] as Any : null);

  const upd = (path: string, v: Any) => { const d = JSON.parse(JSON.stringify(draft)); const ks = path.split("."); let cur = d; ks.slice(0, -1).forEach((k) => (cur = cur[k])); cur[ks[ks.length - 1]] = v; setDraft(d); };
  async function onMapClick(lon: number, lat: number) {
    if (!mode || !draft) return;
    if (mode === "section") {
      const hs: [number, number][] = [...hints, [lon, lat]]; setHints(hs); setBusy(true);
      try { const r = await api.bootstrapBlock(hs, { section_id: section.section_id, zoning: section.survey?.land_control?.zoning || undefined }); setPreview(r);
        setLayers({ ...layers, sections: { type: "FeatureCollection", features: [{ type: "Feature", geometry: r.geometry, properties: { section_id: section.section_id, range_desc: r.range_desc, status: "draft", label: section.section_id + "（草稿）" } }] } });
        setMode("");
        setMsg(`依路網推估街廊 ${Math.round(r.area_m2).toLocaleString()} m²，邊界道路：${r.bounding_roads.join("、")}。四至草稿：${r.range_desc}${r.zoning_note ? "；分區：" + (r.zoning || "—") + "（" + r.zoning_note + "）" : ""}。範圍已畫在圖上（紅虛線）：滿意請按「採用此範圍」，不夠大請按「再點一處擴大」。`.replace("街廊", "街廓")); }
      catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
    } else if (mode === "comp") {
      setBusy(true);
      try {
        const r = await api.comparablesLocate(rec!.id, compTarget, lon, lat);
        await loadCase(rec!.id);
        setMsg(`已設定比較標的${compTarget}的位置（依實例土地面積合成示意範圍，非地籍圖），已重推宗地屬性、區段草稿、勘查表與設施距離。${(r.notes || []).slice(0, 2).join("；")}`);
      } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); setMode(""); }
    } else if (mode === "poi") {
      if (!poi.name) { setMsg("先填設施名稱再點圖。"); return; }
      setBusy(true);
      try { await api.addPoi({ ...poi, lon, lat, note: "地圖人工標定" }); setMsg(`已標定 ${poi.name}（${label("facility_types", poi.type)}），來源「人工標定」。要納入距離請按「重新量測設施距離」。`); }
      catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); setMode(""); }
    } else {
      setMode("");
      await runFromLot([lon, lat]);
    }
  }
  /* 依地號產生：先存目前草稿，再由後端依比準地地號跑「地籍界線 → 宗地屬性 → 區段範圍 → 勘查表 → 設施距離」，最後重新產生書表。manualPoint 為找不到界線時人工指定的位置。 */
  async function runFromLot(manualPoint?: [number, number]) {
    if (!rec || !draft) return;
    const pid = (draft.subject_parcel.parcel_id || "").trim();
    const rangeText = String(section?.range_desc || "").trim();
    if (!pid && !rangeText) { setMsg("請先填比準地地號（例如「金美段489地號」），或在「地價區段」填區段範圍文字（例如「北側至金包里街，南側至中山路…」），系統會圍出區段並依查估辦法 §18 自動選比準地。"); return; }
    setBusy(true); setMsg(null);
    try {
      const changed = pid !== ((rec.data?.subject_parcel?.parcel_id || "") as string).trim();   // 與已存案件比，先存草稿後後端就比不出來
      await save({ data: draft });
      const r = await api.fromLot(rec.id, { parcel_id: pid, manual_point: manualPoint, overwrite: overwriteLot, parcel_changed: changed });
      await loadCase(rec.id); await generate();
      const failed = r.steps.find((s) => !s.ok && s.step === "地籍界線");
      const failedPre = r.steps.find((s) => !s.ok && (s.step === "區段範圍（文字）" || s.step === "比準地選取"));
      setSteps(r.steps); setShowReport(true); setReportKey((k) => k + 1);
      const picked = r.rec?.data?.subject_parcel?.parcel_id || pid;
      setMsg(failedPre ? `${failedPre.step}未完成：${failedPre.note}` : failed ? `找不到「${picked}」的地籍界線：請按「⬆ 匯入地籍圖」（含此地號的檔案），或在下方「在圖上設定比準地位置」點一下，系統會以該位置繼續產生。` : `已依「${picked}」產生${!pid ? "（比準地由系統依區段範圍文字選取，請確認）" : r.parcel_changed ? "（換了地號，推定值全部重算）" : ""}，書表已重新產生。推定值在「宗地條件」分頁會標「推定」，請逐項確認。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  async function importCadastre(file: File) {
    if (!rec) return; setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch(`/api/cases/${encodeURIComponent(rec.id)}/cadastre`, { method: "POST", body: fd, headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const j = await r.json();
      await loadCase(rec.id); await generate();
      setMsg(`已匯入地籍圖 ${file.name}：${j.n} 筆（段名欄「${j.section_field || "—"}」、地號欄「${j.lot_field}」）。對到真實界線：${j.matched.filter(Boolean).join("、") || "無"}${j.unmatched.filter(Boolean).length ? `；對不到：${j.unmatched.filter(Boolean).join("、")}（請確認段名與地號寫法）` : ""}。三張圖已改用地籍界線與地號。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); if (cadRef.current) cadRef.current.value = ""; }
  }
  const secRef = useRef<HTMLInputElement>(null);
  async function importSectionMap(file: File) {
    if (!rec) return; setBusy(true); setMsg(null);
    try {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch(`/api/cases/${encodeURIComponent(rec.id)}/sections_map`, { method: "POST", body: fd, headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const j = await r.json();
      await loadCase(rec.id); await generate();
      setMsg(`已匯入地價區段圖 ${file.name}：${j.n} 個區段（編號欄「${j.id_field || "—"}」）。本案區段 ${j.matched.join("、") || "沒有對到"}${j.unmatched.length ? `；對不到：${j.unmatched.join("、")}（檔案裡的編號：${j.ids.slice(0, 8).join("、")}${j.ids.length > 8 ? "…" : ""}）` : ""}。範圍已更新為正式區段圖。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); if (secRef.current) secRef.current.value = ""; }
  }
  async function refill() {
    if (!draft) return; setBusy(true);
    try { const filled = await api.spatialFill(draft, true); setDraft(filled.data); api.mapLayers(filled.data).then(setLayers).catch(() => null); setMsg(`已重新量測比準地、比較標的與區段的設施距離；${filled.warnings.join("；") || "無提醒事項"}。請儲存。`); }
    catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  function acceptPreview() {
    if (!preview) return;
    const d = JSON.parse(JSON.stringify(draft)); const s = d.sections[section.section_id];
    s.geometry = preview.geometry; s.geometry_source = "estimate_osm_block"; s.status = "draft";
    s.geometry_note = `依路網推估之街廓（邊界道路：${preview.bounding_roads.join("、")}），需估價人員確認`;
    if (!s.range_desc) s.range_desc = preview.range_desc;
    setDraft(d); setPreview(null); setHints([]); setMode(""); setMsg("已採用推估的區段範圍（草稿）。請儲存。");
  }
  async function doSave() { if (!draft) return; setBusy(true); try { await save({ data: draft }); await generate(); setMsg("已儲存並重新產生書表。"); } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); } }
  if (!rec || !draft || !section) return <Empty />;
  const rs = draft.case.rulesets || {};
  return (
    <div>
      {!embedded && <PageHeader title="① 輸入資料：案件與地價區段" desc="填寫案件基本資料與比準地地號，按「依地號產生」由地籍界線推定宗地屬性、區段範圍、勘查表與設施距離。若無區段圖，可在圖上點區段內位置，系統依路網推估街廓範圍與四至草稿；比準地若無地籍圖，點圖設定位置後依清冊面積合成示意範圍。"
        input="案號、估價基準日、用地別、鄉鎮市區、比準地地號、區段編號、區段範圍（文字）、區段與比準地位置（地籍圖／區段圖／點圖）" output="案件基本資料、區段範圍多邊形、比準地位置 → 勘查表推算、設施距離、圖說" next={{ href: "/input?tab=parcels", label: "宗地條件與買賣實例" }} />}
      {showReport && rec && <div className="mb-4"><FillReport caseId={rec.id} refreshKey={reportKey} /></div>}
      <div className="grid lg:grid-cols-3 gap-4">
        <div>
          <Card title="案件" right={<Btn kind={caseMode === "review" ? "primary" : "ghost"} onClick={doSave} disabled={busy} busy={busy}>儲存並重新產生書表</Btn>}>
            <div className="text-sm space-y-2">
              {[["case.case_no", "案號"], ["case.valuation_date", "估價基準日（年期，民國 7 碼）"], ["case.district", "鄉鎮市區"], ["case.appraiser", "不動產估價師（書表與圖說簽章欄）"], ["case.fill_date", "填寫日期（如 114 年 09 月 18 日）"]].map(([k, l]) => (
                <label key={k} className="block"><span className="text-xs text-slate-500">{l}</span><input className="border rounded px-2 py-1 w-full" value={k.split(".").reduce((a: Any, x) => a?.[x], draft) ?? ""} onChange={(e) => upd(k, e.target.value)} />
                  {k === "case.valuation_date" && vdateHint(draft.case.valuation_date)}</label>))}
              {caseMode === "generate" && <div className="border border-orange-200 bg-orange-50/60 rounded p-2 space-y-1">
                <label className="block"><span className="text-xs text-slate-700 font-medium">比準地地號</span><input className="border rounded px-2 py-1 w-full" placeholder="例：金美段489地號" value={draft.subject_parcel.parcel_id ?? ""} onChange={(e) => upd("subject_parcel.parcel_id", e.target.value)} /></label>
                <div className="flex flex-wrap items-center gap-2">
                  <Btn onClick={() => runFromLot()} disabled={busy} busy={busy} title="依地號找地籍界線，推定宗地屬性、區段範圍草稿、勘查表與設施距離，並重新產生書表">依地號產生</Btn>
                  <label className="text-xs text-slate-600 inline-flex items-center gap-1"><input type="checkbox" checked={overwriteLot} onChange={(e) => setOverwriteLot(e.target.checked)} />覆寫已填值</label>
                </div>
                <details className="text-[11px] text-slate-600"><summary className="cursor-pointer text-slate-500 hover:text-slate-800">依地號產生會做什麼</summary>
                  <Help className="mt-1" label="系統會做什麼">地號 → 地籍界線 → 面積、寬深、形狀、臨街、地勢、道路、分區、建蔽率、容積率 → 區段範圍草稿 → 勘查表 → 設施距離 → 實價登錄比較標的。推定值只填空白欄位，換地號時全部重算。沒有地號時，填「區段範圍」文字，系統圍區段並依查估辦法 §18 自動選比準地。</Help></details>
                {steps && <ul className="text-[11px] space-y-0.5">{steps.map((st) => <li key={st.step} className={st.ok ? "text-emerald-800" : "text-rose-700"}>{st.ok ? "✓" : "✗"} {st.step}：{st.note}</li>)}</ul>}
                <button className="text-xs underline text-slate-700" onClick={() => { setShowReport(!showReport); setReportKey((k) => k + 1); }}>{showReport ? "收起填寫結果清單" : "看填寫結果清單（每欄的值、狀態、來源）"}</button>
              </div>}
              {caseMode === "review" && <label className="block"><span className="text-xs text-slate-500">比準地地號（送審書表）</span><input className="border rounded px-2 py-1 w-full" value={draft.subject_parcel.parcel_id ?? ""} onChange={(e) => upd("subject_parcel.parcel_id", e.target.value)} /></label>}
              <label className="block"><span className="text-xs text-slate-500">用地別</span><select className="border rounded px-2 py-1 w-full" value={draft.case.land_use || ""} onChange={(e) => upd("case.land_use", e.target.value)}>{["商業用地", "住宅用地", "工業用地", "農業用地", "其他用地"].map((x) => <option key={x}>{x}</option>)}</select></label>
              <details className="text-xs text-slate-500"><summary className="cursor-pointer hover:text-slate-800">適用基準表</summary>
                <div className="mt-1">{ruleName(rs.regional)}／{ruleName(rs.individual)}（到「評價基準明細表」頁更換）</div></details>
            </div>
          </Card>
          <InputsCard />
          <Card title={`地價區段 ${section.section_id}`}>
            <div className="text-sm space-y-2">
              <label className="block"><span className="text-xs text-slate-500">區段編號</span><input className="border rounded px-2 py-1 w-full" value={section.section_id || ""} onChange={(e) => { const d = JSON.parse(JSON.stringify(draft)); const s = d.sections[section.section_id]; delete d.sections[section.section_id]; s.section_id = e.target.value; d.sections[e.target.value] = s; d.subject_parcel.section_id = e.target.value; d.comparables.forEach((c: Any) => { if (c.section_id === section.section_id) c.section_id = e.target.value; }); setDraft(d); }} /></label>
              <label className="block"><span className="text-xs text-slate-500">區段範圍（文字描述）</span><textarea className="border rounded px-2 py-1 w-full h-20" value={section.range_desc || ""} onChange={(e) => upd(`sections.${section.section_id}.range_desc`, e.target.value)} /></label>
              <label className="block"><span className="text-xs text-slate-500">勘查日期</span><input className="border rounded px-2 py-1 w-full" value={section.survey_date || ""} onChange={(e) => upd(`sections.${section.section_id}.survey_date`, e.target.value)} /></label>
              <div className="text-xs">範圍多邊形：{section.geometry ? <span className="text-emerald-700">已有（{label("geometry_sources", section.geometry_source) || "勘查表／區段圖"}）</span> : <span className="text-rose-700">尚無 — 請在右側圖上推估或提供區段圖</span>}</div>
              <div className="text-xs">比準地位置：{draft.subject_parcel.geometry ? <span className="text-emerald-700">已有（{label("geometry_sources", draft.subject_parcel.geometry_source) || "地籍圖"}）</span> : <span className="text-rose-700">尚無 — 請在右側圖上點選</span>}</div>
            </div>
          </Card>
        </div>
        <div className="lg:col-span-2">
          <Card title="位置與設施距離" hint="區段範圍與宗地界線以地價區段圖、地籍圖為準；設施距離由比準地位置自動量測。">
            <div className="flex flex-wrap gap-2 mb-2 items-center">
              <input ref={secRef} type="file" accept=".geojson,.json,.kml,.gml,.xml,.zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importSectionMap(f); }} />
              <input ref={cadRef} type="file" accept=".geojson,.json,.kml,.gml,.xml,.zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importCadastre(f); }} />
              <button className="px-3 py-1.5 rounded text-sm btn-io-import disabled:opacity-50" disabled={busy} onClick={() => secRef.current?.click()} title="GeoJSON／KML／GML／Shapefile zip（TWD97）；依區段編號對到本案區段">⬆ 匯入地價區段圖</button>
              <button className="px-3 py-1.5 rounded text-sm btn-io-import disabled:opacity-50" disabled={busy} onClick={() => cadRef.current?.click()} title="GeoJSON／KML／GML／Shapefile zip（TWD97）；依段名地號對到本案宗地">⬆ 匯入地籍圖</button>
              {!(rec.submitted_table4 || rec.submitted_table5) && <><button className="px-3 py-1.5 rounded text-sm btn-io-import disabled:opacity-50" disabled={busy} onClick={() => pdfRef.current?.click()} title="既有案件補上估價單位送來的六頁書表 PDF：只掛送審表與抽取資訊，不動本案輸入資料；掛上後即可到「審查」逐格比對">⬆ 補上送審書表 PDF</button><input ref={pdfRef} type="file" accept=".pdf" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) attachPdf(f); e.target.value = ""; }} /></>}
              <Btn kind="ghost" onClick={refill} disabled={busy || !draft.subject_parcel.geometry} title={draft.subject_parcel.geometry ? "依設施資料庫重新量測比準地、比較標的與區段之設施距離（覆寫現有距離）" : "先有比準地位置"}>重新量測設施距離</Btn>
              <span className="text-xs text-slate-500">
                區段圖：{draft.case.section_map ? <span className="text-emerald-700">已匯入 {draft.case.section_map.n} 區段（{draft.case.section_map.filename}）</span> : "未匯入"}；
                地籍圖：{draft.case.cadastre ? <span className="text-emerald-700">已匯入 {draft.case.cadastre.n} 筆（{draft.case.cadastre.filename}）</span> : preloaded ? <span className="text-slate-700">未匯入，使用預載地籍圖（{preloaded.n} 筆{preloaded.districts?.length ? `，${preloaded.districts.join("、")}` : ""}）</span> : "未匯入"}
              </span>
            </div>
            <details className="mb-2 text-sm" open={!section.geometry || !draft.subject_parcel.geometry}>
              <summary className="text-xs text-slate-600 cursor-pointer">無地籍圖／區段圖時的替代方式（結果標示為草稿）</summary>
              <div className="flex flex-wrap gap-2 mt-2 items-center">
                {!preview && <Btn kind={mode === "section" ? "danger" : "ghost"} onClick={() => { setMode(mode === "section" ? "" : "section"); setHints([]); setPreview(null); }} disabled={busy}>{mode === "section" ? "請在圖上點區段內的位置…（按此取消）" : "在圖上推估區段範圍"}</Btn>}
                {preview && <><Btn onClick={acceptPreview}>採用此範圍</Btn><Btn kind={mode === "section" ? "danger" : "ghost"} onClick={() => setMode(mode === "section" ? "" : "section")} disabled={busy}>{mode === "section" ? "請再點一處…（按此取消）" : "再點一處擴大"}</Btn><Btn kind="ghost" onClick={() => { setPreview(null); setHints([]); setMode(""); if (rec) api.mapLayers(rec.data).then(setLayers).catch(() => null); setMsg("已放棄推估的範圍。"); }}>放棄</Btn></>}
                <Btn kind={mode === "subject" ? "danger" : "ghost"} onClick={() => setMode(mode === "subject" ? "" : "subject")} disabled={busy}>{mode === "subject" ? "請在圖上點比準地的位置…（按此取消）" : "在圖上設定比準地位置"}</Btn>
                {(draft.comparables || []).filter((c: Any) => c.parcel_id).length > 0 && <span className="flex items-center gap-1">
                  <select className="border rounded px-2 py-1 text-sm" value={compTarget} onChange={(e) => setCompTarget(Number(e.target.value))}>{(draft.comparables || []).filter((c: Any) => c.parcel_id).map((c: Any) => <option key={c.comp_no} value={c.comp_no}>比較標的{c.comp_no} {c.parcel_id}{c.geometry ? "" : "（無位置）"}</option>)}</select>
                  <Btn kind={mode === "comp" ? "danger" : "ghost"} onClick={() => setMode(mode === "comp" ? "" : "comp")} disabled={busy}>{mode === "comp" ? `請在圖上點比較標的${compTarget}的位置…（按此取消）` : "在圖上設定比較標的位置"}</Btn></span>}
                <Help className="w-full">區段：依路網圍出街廓；比準地：點選位置若落在已匯入地籍圖的某筆宗地內採其界線，否則依清冊面積合成示意範圍，並接著依地號產生其餘內容；比較標的：不在地籍圖的實例會先依實價登錄門牌定位，不準時在圖上點一下重設。</Help>
              </div>
              <div className="flex flex-wrap gap-2 items-center mt-2">
                <span className="text-xs text-slate-600">人工標定設施：</span>
                <select className="border rounded px-2 py-1 text-sm" value={poi.type} onChange={(e) => setPoi({ ...poi, type: e.target.value })}>{Object.entries(meta?.facility_types || {}).map(([t, l]) => <option key={t} value={t}>{String(l)}</option>)}</select>
                <input className="border rounded px-2 py-1 text-sm" placeholder="設施名稱" value={poi.name} onChange={(e) => setPoi({ ...poi, name: e.target.value })} />
                <Btn kind={mode === "poi" ? "danger" : "ghost"} onClick={() => setMode(mode === "poi" ? "" : "poi")} disabled={busy || !poi.name}>{mode === "poi" ? "請在圖上點選…（取消）" : "於圖上標定"}</Btn>
                <span className="text-xs text-slate-500">標定後請重新量測。</span>
              </div>
            </details>
            {layers?.n_far > 0 && <div className="no-print text-xs mb-1 flex items-center gap-2"><span className="text-slate-500">有 {layers.n_far} 筆幾何離比準地超過 2.5 km（其他鄉鎮的比較標的），預設不納入取景。</span><button className="underline" onClick={() => setShowAll(!showAll)}>{showAll ? "只看比準地周邊" : "顯示全部"}</button></div>}
        {layers ? <LeafletMap layers={showAll && layers.bbox_all ? { ...layers, bbox: layers.bbox_all } : layers} mode="sketch" onMapClick={onMapClick} clickMode={!!mode} /> : <div className="h-[60vh] bg-white border rounded flex items-center justify-center text-slate-500">圖層載入中…</div>}
            {keepNotice && <div className="text-sm text-amber-900 bg-amber-50 border border-amber-300 rounded p-2 mb-2 flex items-center gap-2">{keepNotice}<button className="underline text-xs" onClick={() => { setDraft(JSON.parse(JSON.stringify(rec!.data))); setKeepNotice(null); }}>重新載入（放棄修改）</button></div>}
            {msg && <div className="text-sm mt-2 bg-slate-50 border rounded p-2">{msg}</div>}
          </Card>
        </div>
      </div>
    </div>
  );
}
