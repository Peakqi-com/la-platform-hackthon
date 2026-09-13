"use client";
import { useEffect, useState } from "react";
import { Btn, Card } from "@/components/ui";
import { api, Any, fmtMoney } from "@/lib/api";

/* 收益法（選用）：查估辦法 §14 以收益實例查估比準地收益價格（技術規則第三章第二節）；手冊 p.37～41 表2 收益法調查估價表、
   p.8 五(二)3、4 比準地地價由比較價格與收益價格綜合評估並敘明理由（表14）。
   設定存在案件 data.income，隨上方「儲存並重新產生書表」一起存；搜尋、採用收益實例走後端 /income/search、/income/apply；
   數字一律由後端規則引擎以草稿即時試算（/api/run），畫面不自己算。 */
type Props = { caseId: string; draft: Any; setIncome: (inc: Any) => void; onApplied: (rec: Any) => void; preview: (data: Any) => Promise<Any>; busy: boolean };

const PARAMS: [string, string, "all" | "building"][] = [
  ["idle_months", "閒置及其他收入損失（月／年）", "all"], ["deposit_months", "押租金（月租金倍數）", "all"], ["deposit_rate_pct", "一年期定存利率（%）", "all"],
  ["management_pct_of_gross", "管理費率（年總收入 %）", "all"], ["land_value_tax", "地價稅（元／年；填了就不依公告地價推算）", "all"],
  ["cap_rate_land_pct", "土地收益資本化率（%）", "all"], ["other_income", "其他收入（元／年）", "all"], ["other_expense", "其他費用（元／年）", "all"],
  ["house_tax", "房屋稅（元／年）", "building"], ["insurance_pct_of_building_cost", "保險費率（建物成本價格 %）", "building"],
  ["maintenance_pct_of_construction", "維修費率（營造施工費 %）", "building"], ["replacement_pct_of_construction", "重置提撥率（營造施工費 %）", "building"],
  ["cap_rate_building_pct", "建物收益資本化率（%）", "building"],
];
const num = (v: Any) => (v === "" || v === null || v === undefined ? null : Number(v));
const money = (v: Any) => (v === null || v === undefined ? "—" : fmtMoney(Math.round(Number(v))));

export default function IncomePanel({ caseId, draft, setIncome, onApplied, preview, busy }: Props) {
  const inc = draft.income || {};
  const [view, setView] = useState<Any>(null);
  const [run, setRun] = useState<Any>(null);
  const [search, setSearch] = useState<Any>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  useEffect(() => { api.income(caseId).then(setView).catch(() => setView(null)); }, [caseId]);
  const previewKey = JSON.stringify(inc) + JSON.stringify(draft.subject_parcel?.area_m2 ?? null);
  useEffect(() => {
    if (!inc.enabled) { setRun(null); return; }
    const t = setTimeout(() => { preview(draft).then(setRun).catch((e: Any) => setMsg(String(e.message || e))); }, 400);
    return () => clearTimeout(t);
  }, [previewKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const res = run?.income;
  const dec = run?.land_price_decision;
  const mode: string = inc.mode || view?.mode || "land";
  const building = mode === "building";
  const defaults = view?.defaults || {};
  const subj = inc.subject || {};
  const bld = subj.building || {};
  const upd = (patch: Any) => setIncome({ ...inc, ...patch });
  const updEx = (i: number, patch: Any) => { const ex = [...(inc.examples || [])]; ex[i] = { ...ex[i], ...patch }; upd({ examples: ex }); };
  const updSubj = (patch: Any) => upd({ subject: { ...subj, ...patch } });
  const updBld = (patch: Any) => updSubj({ building: { ...bld, ...patch } });
  const updParam = (k: string, v: Any) => upd({ params: { ...(inc.params || {}), [k]: num(v) } });

  async function doSearch() {
    setWorking(true); setMsg(null);
    try {
      const s = await api.incomeSearch(caseId, { mode });
      setSearch(s); const pk: Record<string, boolean> = {}; s.chosen.forEach((c: Any) => { pk[c.id] = true; }); setPicked(pk);
      setMsg(s.note || `依查估辦法 §17，蒐集期間 ${s.window?.text}（得放寬至 ${s.window?.relaxed_from}）；${mode === "land" ? "素地（土地租賃）" : "同用途房屋租賃"}候選 ${s.candidates.length} 件，已勾選 ${s.chosen.length} 件。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setWorking(false); }
  }
  async function doApply() {
    const ids = Object.keys(picked).filter((k) => picked[k]);
    if (!ids.length || ids.length > 3) { setMsg("收益實例請勾選 1～3 件（手冊 p.37 (五)1(1) 以 3 件為原則）。"); return; }
    setWorking(true); setMsg(null);
    try {
      const r = await api.incomeApply(caseId, ids, mode);
      onApplied(r.rec); setView(r.view); setSearch(null);
      setMsg(`已採用 ${ids.length} 件收益實例並啟用收益法；價格日期調整已依主計總處房租指數帶入，情況、區域、個別因素調整請依實例與比準地差異填載。`);
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setWorking(false); }
  }
  const addManual = () => { const ex = [...(inc.examples || [])]; ex.push({ example_no: ex.length + 1, rent_type: "詢問租金", area_m2: null, total_rent: null, rent_date: "", situation_pct: 0, date_pct: 0, regional_pct: 0, individual_pct: 0, weight_pct: null, flags: [], note: "", source: "人工填載" }); upd({ enabled: true, examples: ex }); };
  const srcOf = (k: string) => res?.sources?.[k] || defaults[k];

  return (
    <Card title="收益法（選用）：表2 收益法調查估價表、表14 比準地地價估計表"
      hint="查估辦法 §14：得以收益實例查估比準地收益價格，依不動產估價技術規則第三章第二節辦理；比準地地價由比較價格與收益價格綜合評估，並於比準地地價估計表敘明理由（手冊 p.8 五(二)3、4）。收益實例取自內政部實價登錄租賃（僅涵蓋經紀業、包租業經手之案件）。">
      <div className="no-print toolbar mb-2 text-sm">
        <label className="flex items-center gap-1"><input type="checkbox" checked={!!inc.enabled} onChange={(e) => upd({ enabled: e.target.checked })} />啟用收益法</label>
        <span>比準地：<select className="ctl-sm" value={mode} onChange={(e) => upd({ mode: e.target.value })}>
          <option value="land">素地（採素地收益實例，建物欄位免填）</option><option value="building">有建物（房地收益，附表成本法）</option></select></span>
        <span className="text-xs text-slate-500">租賃資料 {view?.status?.rent?.n ?? "—"} 筆（{(view?.status?.rent?.seasons || []).join("、") || "未下載"}）；一年期定存至 {view?.status?.deposit?.latest || "—"}；房租指數至 {view?.status?.cpi_rent?.latest || "—"}</span>
        <span className="ml-auto" />
        <Btn kind="ghost" onClick={doSearch} disabled={working || busy} busy={working} title="依查估辦法 §17 蒐集期間、同鄉鎮→鄰近鄉鎮，從實價登錄租賃找 1～3 件">⬇ 搜尋收益實例（實價登錄租賃）</Btn>
        <Btn kind="ghost" onClick={addManual} disabled={working || busy} title="待租租金、詢問租金或委託人提供之租約（手冊 p.38 (9)）">＋ 人工收益實例</Btn>
      </div>
      {msg && <div className="text-xs bg-slate-50 border rounded p-2 mb-2">{msg}</div>}

      {search && <div className="no-print text-xs mb-3 border border-orange-200 bg-orange-50/50 rounded p-2">
        <div className="flex flex-wrap items-center gap-3 mb-1"><b>收益實例候選</b><span>蒐集期間 {search.window?.text}</span><span>符合者 {search.stats?.n_target} 筆，期間內 {search.stats?.n_window}、放寬 {search.stats?.n_relaxed}、特殊情況排除 {search.stats?.n_excluded}</span>
          <Btn onClick={doApply} disabled={working} busy={working}>採用勾選的收益實例</Btn><button className="underline text-slate-500" onClick={() => setSearch(null)}>關閉</button></div>
        {search.candidates?.length ? <div className="overflow-x-auto max-h-72 overflow-y-auto"><table className="grid text-[11px] min-w-[64rem]"><thead><tr><th></th><th className="min-w-[14rem]">位置</th><th>租金形成日</th><th>標的</th><th>面積 m²</th><th>月租金總額</th><th>月租金 元/m²</th><th>分區／用途</th><th>階段</th><th className="min-w-[16rem]">特殊情況／備註</th></tr></thead><tbody>
          {search.candidates.map((c: Any) => (
            <tr key={c.id} className={c.excluded ? "opacity-60" : ""}>
              <td><input type="checkbox" disabled={c.excluded} checked={!!picked[c.id]} onChange={(e) => setPicked({ ...picked, [c.id]: e.target.checked })} /></td>
              <td className="whitespace-normal">{c.position || (c.sections || []).join("、")}<div className="text-slate-500">{c.district}</div></td>
              <td>{c.date}{!c.in_window && <div className="text-amber-800">期間外（放寬）</div>}</td><td>{c.target}</td><td className="text-right font-mono">{c.area_m2}</td>
              <td className="text-right font-mono">{money(c.total_rent)}</td><td className="text-right font-mono">{c.unit_rent}</td>
              <td>{(c.lot_zones || []).map((z: string) => z.split(":").pop()).join("、") || c.zone}{c.use ? ` ${c.use}` : ""}</td><td title={c.basis}>{c.stage}</td>
              <td className="whitespace-normal">{(c.flags || []).map((f: Any) => <div key={f.label} className={f.exclude ? "text-rose-700" : "text-amber-800"}>{f.label}（{f.rule}）</div>)}{c.note ? <div className="text-slate-500">{c.note}</div> : null}</td>
            </tr>))}
        </tbody></table></div> : <div className="text-rose-700">{search.note || "沒有符合的收益實例。"}</div>}
      </div>}

      {inc.enabled ? <div className="space-y-3">
        <div className="overflow-x-auto"><table className="grid text-xs min-w-[70rem]"><thead><tr><th>編號</th><th className="min-w-[12rem]">收益實例</th><th>租金型態</th><th>租金形成日</th><th>面積 m²</th><th>月租金總額</th><th>情況 %</th><th>價格日期 %</th><th>區域 %</th><th>個別 %</th><th>權重 %</th><th>月租金</th><th>試算租金</th><th></th></tr></thead><tbody>
          {(inc.examples || []).map((ex: Any, i: number) => { const row = res?.examples?.[i]; return (
            <tr key={i}>
              <td><input className="ctl-sm w-12" value={ex.example_no ?? ""} onChange={(e) => updEx(i, { example_no: e.target.value })} /></td>
              <td className="whitespace-normal">{ex.position || ex.district || ex.source}{ex.flags?.length ? <div className="text-amber-800">{ex.flags.join("；")}</div> : null}{ex.date_note ? <div className="text-slate-500" title={ex.date_note}>價格日期調整：房租指數</div> : null}</td>
              <td><select className="ctl-sm" value={ex.rent_type || "登錄租金"} onChange={(e) => updEx(i, { rent_type: e.target.value })}><option>登錄租金</option><option>待租租金</option><option>詢問租金</option><option>契約租金</option></select></td>
              <td><input className="ctl-sm w-24" value={ex.rent_date || ""} placeholder="1110630" onChange={(e) => updEx(i, { rent_date: e.target.value })} /></td>
              <td><input className="ctl-sm w-20" type="number" value={ex.area_m2 ?? ""} onChange={(e) => updEx(i, { area_m2: num(e.target.value) })} /></td>
              <td><input className="ctl-sm w-24" type="number" value={ex.total_rent ?? ""} onChange={(e) => updEx(i, { total_rent: num(e.target.value) })} /></td>
              {(["situation_pct", "date_pct", "regional_pct", "individual_pct", "weight_pct"] as const).map((k) => (
                <td key={k}><input className="ctl-sm w-16" type="number" step="0.01" value={ex[k] ?? ""} placeholder={k === "weight_pct" ? String(row?.weight_pct ?? "") : ""} onChange={(e) => updEx(i, { [k]: num(e.target.value) })} /></td>))}
              <td className="text-right font-mono">{row?.unit_rent ?? "—"}</td><td className="text-right font-mono">{row?.trial_rent ?? "—"}</td>
              <td><button className="text-xs text-slate-400 hover:text-red-700 underline" onClick={() => upd({ examples: (inc.examples || []).filter((_: Any, j: number) => j !== i) })}>移除</button></td>
            </tr>); })}
          {!inc.examples?.length && <tr><td colSpan={14} className="text-slate-500">尚無收益實例：按「搜尋收益實例」或「＋ 人工收益實例」。</td></tr>}
        </tbody></table>
          <div className="text-[11px] text-slate-500 mt-1">試算租金＝月租金×(1＋情況)×(1＋價格日期)×(1＋區域)×(1＋個別)；權重空白時依調整率絕對值加總排名預設 50／30／20（手冊 p.38～39 (8)～(15)）。特殊情況依查估辦法 §7、§8 調整。</div></div>

        <div className="grid md:grid-cols-2 gap-3">
          <div className="border rounded p-2 text-xs space-y-1">
            <div className="font-medium">比準地收益資料</div>
            <label className="flex items-center gap-2">收益面積 m²<input className="ctl-sm w-24" type="number" value={subj.income_area_m2 ?? ""} placeholder={String(building ? (bld.reg_area_m2 ?? "") : (draft.subject_parcel?.area_m2 ?? ""))} onChange={(e) => updSubj({ income_area_m2: num(e.target.value) })} /></label>
            <label className="flex items-center gap-2">土地（持分）面積 m²<input className="ctl-sm w-24" type="number" value={subj.land_share_m2 ?? ""} placeholder={String(draft.subject_parcel?.area_m2 ?? "")} onChange={(e) => updSubj({ land_share_m2: num(e.target.value) })} /></label>
            <label className="flex items-center gap-2">公告地價 元/m²<input className="ctl-sm w-24" type="number" value={subj.announced_land_price ?? ""} onChange={(e) => updSubj({ announced_land_price: num(e.target.value) })} /><span className="text-slate-500">推算地價稅（申報地價＝公告地價 80%）</span></label>
            {building && <>
              <label className="flex items-center gap-2">總樓層／樓層別<input className="ctl-sm w-14" value={subj.total_floors ?? ""} onChange={(e) => updSubj({ total_floors: e.target.value })} />／<input className="ctl-sm w-14" value={subj.level ?? ""} onChange={(e) => updSubj({ level: e.target.value })} /></label>
              <label className="flex items-center gap-2">主要構造<select className="ctl-sm" value={bld.material || ""} onChange={(e) => updBld({ material: e.target.value })}><option value=""></option><option>鋼筋混凝土造</option><option>鋼骨鋼筋混凝土造</option><option>加強磚造</option><option>磚造</option></select>
                建物型態<select className="ctl-sm" value={bld.btype || ""} onChange={(e) => updBld({ btype: e.target.value })}><option value=""></option><option>住宅大樓</option><option>華廈</option><option>公寓</option><option>透天厝</option><option>店面</option><option>辦公商業大樓</option><option>工廠</option></select></label>
              <label className="flex items-center gap-2">建築完成年月日<input className="ctl-sm w-24" placeholder="0890403" value={bld.completed ?? ""} onChange={(e) => updBld({ completed: e.target.value })} />地上／地下層數<input className="ctl-sm w-12" type="number" value={bld.floors_above ?? ""} onChange={(e) => updBld({ floors_above: num(e.target.value) })} />／<input className="ctl-sm w-12" type="number" value={bld.floors_below ?? ""} onChange={(e) => updBld({ floors_below: num(e.target.value) })} /></label>
              <label className="flex items-center gap-2">建物登記面積 m²<input className="ctl-sm w-20" type="number" value={bld.reg_area_m2 ?? ""} onChange={(e) => updBld({ reg_area_m2: num(e.target.value) })} />計算面積（扣車位）<input className="ctl-sm w-20" type="number" value={bld.calc_area_m2 ?? ""} onChange={(e) => updBld({ calc_area_m2: num(e.target.value) })} /></label>
              <label className="flex items-center gap-2">營造施工費單價 元/m²（空白依第四號公報）<input className="ctl-sm w-24" type="number" value={bld.unit_cost_m2 ?? ""} placeholder={String(res?.cost?.unit_cost_m2 ?? "")} onChange={(e) => updBld({ unit_cost_m2: num(e.target.value) })} /></label>
              <label className="flex items-center gap-2">樓層別效用比 平均／該樓層<input className="ctl-sm w-16" type="number" step="0.01" value={subj.floor_util_avg ?? ""} onChange={(e) => updSubj({ floor_util_avg: num(e.target.value) })} />／<input className="ctl-sm w-16" type="number" step="0.01" value={subj.floor_util_level ?? ""} onChange={(e) => updSubj({ floor_util_level: num(e.target.value) })} /><span className="text-slate-500">技術規則 §100；全聯會未公告，估價師填</span></label>
            </>}
            <details><summary className="cursor-pointer text-slate-700">參數與出處（空白＝系統預設）</summary>
              <div className="space-y-1 mt-1">{PARAMS.filter(([, , m]) => m === "all" || building).map(([k, lbl]) => { const s = srcOf(k); return (
                <label key={k} className="flex items-center gap-2" title={s?.source || ""}>{lbl}<input className="ctl-sm w-20" type="number" step="0.001" value={inc.params?.[k] ?? ""} placeholder={s?.value != null ? String(s.value) : ""} onChange={(e) => updParam(k, e.target.value)} />
                  {s?.check ? <span className="text-amber-800">需確認</span> : null}{s?.range ? <span className="text-slate-500">區間 {s.range.join("～")}</span> : null}</label>); })}</div>
            </details>
          </div>

          <div className="border rounded p-2 text-xs">
            <div className="font-medium mb-1">核算結果（表2）</div>
            {!res ? <div className="text-slate-500">試算中…</div> : <table className="w-full"><tbody>
              {([["推估月租金（元/m²）", res.est_monthly_rent], ["年租金", res.annual_rent], ["押租金", res.deposit], ["押租金運用收益", res.deposit_income], ["總收入", res.gross_income], ["有效總收入", res.egi],
                 ["總費用", res.total_expense], [building ? "房地淨收益" : "土地淨收益", res.noi]] as [string, Any][]).map(([l, v]) => <tr key={l}><td className="text-slate-600">{l}</td><td className="text-right font-mono">{money(v)}</td></tr>)}
              {res.expenses && <tr><td colSpan={2} className="text-slate-500">{Object.entries<Any>(res.expenses).map(([k, v]) => `${({ land_value_tax: "地價稅", house_tax: "房屋稅", management: "管理費", insurance: "保險費", maintenance: "維修費", replacement: "重置提撥費", other: "其他" } as Any)[k] || k} ${money(v)}`).join("、")}</td></tr>}
              {building && <><tr><td className="text-slate-600">建物收益資本化率＋折舊提存率</td><td className="text-right font-mono">{res.building_cap_rate_pct ?? "—"}% ＋ {res.depreciation_rate != null ? (res.depreciation_rate * 100).toFixed(2) : "—"}%</td></tr>
                <tr><td className="text-slate-600">建物淨收益</td><td className="text-right font-mono">{money(res.building_noi)}</td></tr></>}
              <tr><td className="text-slate-600">土地淨收益</td><td className="text-right font-mono">{money(res.land_noi)}</td></tr>
              <tr><td className="text-slate-600">土地收益資本化率</td><td className="text-right font-mono">{res.land_cap_rate_pct ?? "—"}%</td></tr>
              <tr><td className="text-slate-600">土地收益總價格</td><td className="text-right font-mono">{money(res.land_income_total)}</td></tr>
              <tr><td className="text-slate-600">土地收益單價（元/m²）</td><td className="text-right font-mono">{money(res.land_income_unit)}</td></tr>
              <tr className="font-medium"><td>比準地收益價格（元/m²）{building ? "（樓層別調整後）" : ""}</td><td className="text-right font-mono">{money(res.income_price)}</td></tr>
            </tbody></table>}
            {res?.issues?.length ? <ul className="mt-1 text-amber-800 list-disc pl-4">{res.issues.map((s: string) => <li key={s}>{s}</li>)}</ul> : null}
          </div>
        </div>

        <div className="border rounded p-2 text-xs">
          <div className="font-medium mb-1">比準地地價估計表（表14）</div>
          <div className="flex flex-wrap items-center gap-3">
            <span>比較價格 <b className="font-mono">{money(run?.table4?.subject_comparison_price)}</b></span>
            <label>權重 <input className="ctl-sm w-14" type="number" step="0.1" value={inc.weights?.comparison ?? ""} placeholder="1" onChange={(e) => upd({ weights: { ...(inc.weights || {}), comparison: num(e.target.value) } })} /></label>
            <span>收益價格 <b className="font-mono">{money(res?.income_price)}</b></span>
            <label>權重 <input className="ctl-sm w-14" type="number" step="0.1" value={inc.weights?.income ?? ""} placeholder="0" onChange={(e) => upd({ weights: { ...(inc.weights || {}), income: num(e.target.value) } })} /></label>
            <span>→ 比準地地價 <b className="font-mono">{money(dec?.land_price)}</b> 元/m²（查估辦法 §21 尾數進位）</span>
          </div>
          <textarea className="border rounded w-full mt-1 p-1" rows={2} placeholder="決定理由：視不同價格所蒐集資料之可信度、價格形成因素之相近程度（手冊 p.8 五(二)3、4）" value={inc.reason || ""} onChange={(e) => upd({ reason: e.target.value })} />
          {dec?.issues?.length ? <ul className="text-amber-800 list-disc pl-4">{dec.issues.map((s: string) => <li key={s}>{s}</li>)}</ul> : null}
          <div className="no-print mt-1 flex gap-2"><a className="btn-io-export" href={`/api/cases/${encodeURIComponent(caseId)}/official/t2.xlsx`}>⬇ 表2 收益法調查估價表</a><a className="btn-io-export" href={`/api/cases/${encodeURIComponent(caseId)}/official/t14.xlsx`}>⬇ 表14 比準地地價估計表</a><span className="text-slate-500">下載前請先按上方「儲存並重新產生書表」</span></div>
        </div>
      </div> : <div className="text-xs text-slate-500">未啟用。比準地地價目前只採比較價格；勾選「啟用收益法」或搜尋收益實例後可試算收益價格，權重預設 0，不會改變比準地地價。</div>}
    </Card>
  );
}
