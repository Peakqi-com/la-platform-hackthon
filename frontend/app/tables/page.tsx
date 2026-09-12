"use client";
import { Fragment, Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import Legend from "@/components/Legend";
import PageHeader from "@/components/PageHeader";
import { Badge, Btn, Card, Empty, FacilityChip, Help } from "@/components/ui";
import { api, Any, Finding, findingKey, fmtMoney, fmtPct } from "@/lib/api";
import { Tip } from "@/components/Basis";
import { StaleBanner, StaleDim } from "@/components/Stale";
import dynamic from "next/dynamic";
const LeafletMap = dynamic(() => import("@/components/LeafletMap"), { ssr: false });

function RulePanel({ rulesetId, ruleId, subject, comparable, onClose }: { rulesetId: string; ruleId: string; subject: string | null; comparable: string | null; onClose: () => void }) {
  const [rs, setRs] = useState<Any>(null);
  const { ruleName } = useCase();
  useEffect(() => { api.rule(rulesetId).then(setRs).catch(() => setRs(null)); }, [rulesetId]);
  const rule = rs?.rules?.find((r: Any) => r.id === ruleId);
  if (!rule) return <div className="text-sm text-slate-500">載入基準表…</div>;
  const c = rule.criteria || {};
  return (
    <div className="text-sm">
      <div className="flex items-start"><div><div className="text-xs text-slate-500">{ruleName(rulesetId)}</div><div className="font-semibold">{rule.name}</div>
        <div className="text-xs">等級：{rule.levels.join("／")}；最大影響範圍 {rule.max_pct}%；級距 {(rule.max_pct / Math.max(rule.levels.length - 1, 1)).toFixed(2)}%</div></div><button className="ml-auto text-slate-500" onClick={onClose}>✕</button></div>
      <div className="mt-2"><div className="text-xs text-slate-500 mb-1">判定條件</div>
        {c.type === "bands" || c.type === "distance" ? <ul className="text-xs">{c.bands?.map((b: Any, i: number) => <li key={i}>{b.level}：{b.min !== undefined ? `${b.min} 以上` : ""}{b.max !== undefined ? ` 未滿 ${b.max}` : ""}{c.unit ? ` ${c.unit}` : " 公尺"}</li>)}
          {c.none_level && <li>無該設施 → {c.none_level}</li>}{c.in_section_level && <li>區段內有該設施 → {c.in_section_level}</li>}{c.direction === "farther_is_better" && <li>愈遠愈優（嫌惡設施；多處時取最不利者，依範本推定）</li>}</ul>
          : c.type === "enum" ? <ul className="text-xs">{Object.entries(c.map || {}).map(([k, v]) => <li key={k}>{k} → {String(v)}</li>)}{c.default && <li>其他 → {c.default}</li>}</ul>
          : c.type === "boolean" ? <div className="text-xs">有 → {c.true_level}；無 → {c.false_level}</div> : <div className="text-xs">由估價人員自行判定填載</div>}
      </div>
      {rule.matrix_full && (
        <div className="mt-2"><Help className="mb-1">修正百分比矩陣：列＝比準地等級，欄＝比較標的等級；紅色＝本案格位。</Help>
          <table className="grid"><thead><tr><th></th>{rule.levels.map((l: string) => <th key={l}>{l}</th>)}</tr></thead>
            <tbody>{rule.levels.map((s: string) => <tr key={s}><th>{s}</th>{rule.levels.map((k: string) => <td key={k} className={`text-right font-mono ${s === subject && k === comparable ? "bg-[#ea580c] text-white font-bold" : ""}`}>{Number(rule.matrix_full[s][k]).toFixed(2)}</td>)}</tr>)}</tbody></table>
        </div>
      )}
      {rule.note && <div className="mt-2 text-xs text-amber-800">{rule.note}</div>}
    </div>
  );
}

const PARCEL_FIELD: Record<number, string> = { 7: "area_m2", 8: "width_m", 9: "depth_m", 10: "shape", 11: "frontage", 12: "terrain", 13: "road_type", 14: "front_road", 15: "school", 16: "market", 17: "park", 18: "station", 19: "commercial_district", 20: "nuisance", 21: "street_parking", 22: "zoning", 23: "bcr_pct", 24: "far_pct", 25: "building_restricted", 6: "other" };
const same = (a: Any, b: Any, tol = 0.005) => { if ((a === null || a === undefined || a === "" || a === "-") && (b === null || b === undefined || b === "-")) return true; const na = Number(a), nb = Number(b); if (!isNaN(na) && !isNaN(nb)) return Math.abs(na - nb) <= tol; return String(a) === String(b); };
/* 併列格：填載值與核算值不同 → 紅底並顯示填載值 */
function Cell({ computed, submitted, has, fmt = (v: Any) => String(v), finding, cls = "", tol = 0.005 }: { computed: Any; submitted?: Any; has: boolean; fmt?: (v: Any) => string; finding?: Finding | null; cls?: string; tol?: number }) {
  const mismatch = has && (finding ? finding.severity === "error" : !same(computed, submitted, tol));
  const warn = has && finding && finding.severity !== "error";
  return (
    <td className={`text-right font-mono ${mismatch ? "bg-red-100 text-red-900" : warn ? "bg-amber-50" : ""} ${cls}`} title={finding ? `${finding.message}${finding.basis ? "（" + finding.basis + "）" : ""}` : undefined}>
      {computed === null || computed === undefined ? "—" : fmt(computed)}
      {has && (mismatch || warn) && <div className="text-[11px] font-sans">{mismatch ? "填載 " : "填載 "}{submitted === null || submitted === undefined ? "—" : String(submitted)}</div>}
    </td>
  );
}

function TablesInner() {
  const { rec, status, ruleName, stale } = useCase();
  const params = useSearchParams();
  const tab = params.get("tab") === "4" ? "4" : "5";
  const run = status.run;
  const [sel, setSel] = useState<{ rulesetId: string; ruleId: string; subject: string | null; comparable: string | null } | null>(null);
  const [compNo, setCompNo] = useState<string>(params.get("comp") || "1");
  const [msg, setMsg] = useState<string | null>(null);
  const rsIds = rec?.data.case.rulesets || {};
  /* 區段設施小地圖：點某細項時高亮該細項對應的勘查表欄位（rule.survey_field）之設施與量測線 */
  const [layers, setLayers] = useState<Any>(null);
  const [regRules, setRegRules] = useState<Any>(null);
  useEffect(() => { if (rec && tab === "5") { api.mapLayers(rec.data).then(setLayers).catch(() => setLayers(null)); if (rsIds.regional) api.rule(rsIds.regional).then(setRegRules).catch(() => setRegRules(null)); } }, [rec, tab, rsIds.regional]);
  const hlRule = sel && tab === "5" ? regRules?.rules?.find((r: Any) => r.id === sel.ruleId) : null;
  const hlField = hlRule?.survey_field as string | undefined;
  const compNos: string[] = useMemo(() => (run ? Object.keys(run.table5) : []), [run]);
  const t5 = useMemo(() => run?.table5?.[compNo] || (run ? Object.values(run.table5)[0] : null), [run, compNo]) as Any;
  const groups = useMemo(() => { const g: Record<number, Any[]> = {}; (t5?.rows || []).forEach((r: Any) => (g[r.group] = g[r.group] || []).push(r)); return g; }, [t5]);
  const fmap = useMemo(() => { const m: Record<string, Finding> = {}; (status.findings || []).forEach((f) => { const k = findingKey(f); if (k && (!m[k] || f.severity === "error")) m[k] = f; }); return m; }, [status.findings]);
  const sub5of = (k: string) => rec?.submitted_table5?.[k] || null;
  const sub4of = (k: string) => rec?.submitted_table4?.comparables?.[k] || null;
  const has5 = compNos.some((k) => !!sub5of(k)), has4 = compNos.some((k) => !!sub4of(k));
  // 由審查頁「到該格」進來：預選並捲動
  useEffect(() => {
    if (!run || !rec) return;
    const rule = params.get("rule"), item = params.get("item");
    if (tab === "5" && rule && rule.startsWith("R")) { const row = t5?.rows?.find((x: Any) => x.rule_id === rule); if (row) setSel({ rulesetId: rsIds.regional, ruleId: rule, subject: row.subject_level, comparable: row.comparable_level }); }
    if (tab === "4" && item && Number(item) >= 6 && Number(item) <= 25) { const comp = run.table4.comparables.find((c: Any) => String(c.comp_no) === compNo) || run.table4.comparables[0]; const row = comp?.rows?.find((x: Any) => String(x.item_no) === item); if (row) setSel({ rulesetId: rsIds.individual, ruleId: `I${item}`, subject: row.subject_level, comparable: row.comparable_level }); }
    const id = tab === "5" ? (rule ? `row-${rule}` : null) : (item ? `row-I${item}` : null);
    if (id) setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "center", behavior: "smooth" }), 100);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, tab, params]);
  if (!rec) return <Empty />;
  if (status.error) return <div className="text-red-700">{status.error}</div>;
  if (!run) return <div className="text-sm">核算中…</div>;
  const t4 = run.table4;
  if (!compNos.length || !t4?.comparables?.length) return (
    <div>
      <PageHeader title={tab === "5" ? "② 產出書表：影響地價區域因素分析明細表（審查對照檢視）" : "② 產出書表：比較法調查估價表（審查對照檢視）"} />
      <StaleBanner what="書表" />
      <Card title="本案尚無比較標的">
        <p className="text-sm text-slate-700">區域因素分析明細表與比較法調查估價表都是逐一比較標的計算，要先選取一至三件買賣實例（查估辦法 §19）才有內容可對照。</p>
        <div className="mt-3 flex flex-wrap gap-2 items-center">
          <Link href={`/input?tab=parcels&case=${encodeURIComponent(rec.id)}`}><Btn>到輸入資料選取比較標的 →</Btn></Link>
          <Link className="text-sm underline" href={`/review?case=${encodeURIComponent(rec.id)}`}>回審查結果</Link>
        </div>
      </Card>
    </div>
  );
  const subj = rec.data.subject_parcel;
  const parcelVal = (p: Any, row: Any) => {
    const f = PARCEL_FIELD[row.item_no]; const v = p?.[f];
    if (v === null || v === undefined) return "—";
    if (typeof v === "boolean") return v ? "有" : "無";
    if (Array.isArray(v)) return v.length ? v.map((x: Any, i: number) => <FacilityChip key={i} f={x} />) : "無";
    if (typeof v === "object") return f === "front_road" ? `${v.name || ""} ${v.width_m ?? ""} M` : <FacilityChip f={v} />;
    return String(v) + (f === "bcr_pct" || f === "far_pct" ? "%" : "");
  };
  const q = `case=${rec.id}&comp=${compNo}`;
  const f5 = (rid: string, k: string = compNo) => fmap[`5:${k}:${rid}`] || null;
  const f4 = (item: number | string, k: string = compNo) => fmap[`4:${k}:${item}`] || null;
  const nErr = (status.findings || []).filter((f) => f.severity === "error" && f.table === (tab === "5" ? "表5" : "表4")).length;
  const lvl = (computed: string | null, submitted: Any, num: Any, has: boolean, finding: Finding | null) => {
    const mismatch = has && finding?.severity === "error" && submitted && computed && submitted !== computed;
    return <><td className="text-center">{num ?? ""}</td><td className={mismatch ? "bg-red-100 text-red-900" : ""} title={finding?.message}>{computed ?? <Badge kind="warn">需人工確認</Badge>}{mismatch && <div className="text-[11px]">填載 {submitted}</div>}</td></>;
  };
  return (
    <div className="print-landscape">
      {tab === "5" ? (
        <PageHeader print title="② 產出書表：影響地價區域因素分析明細表（審查對照檢視）" desc="以比準地所在地價區段與各比較標的所在區段之勘查事實，依區域因素評價基準明細表判定等級並查得修正百分比；各主要項目小計之和為區域因素總修正數，帶入比較法調查估價表。"
          input="地價區段勘查表事實、區域因素評價基準明細表" output="各細項等級與修正百分比、百分比小計、區域因素總修正數；有送審書表時併列填載值" next={{ href: "/tables?tab=4", label: "比較法調查估價表" }} />
      ) : (
        <PageHeader print title="② 產出書表：比較法調查估價表（審查對照檢視）" desc="比較標的土地正常單價經期日調整、區域因素調整、個別因素調整後得試算價格；依價格形成因素相近程度賦予權重，加權平均並四捨五入至個位數為比準地比較價格。"
          input="買賣實例正常單價與交易日期、區域因素總修正數、宗地條件、個別因素評價基準明細表" output="各項差異率、個別因素合計、試算價格、權重、比準地比較價格、比準地地價；有送審書表時併列填載值" next={{ href: "/review", label: "審查結果" }} />
      )}
      <StaleBanner what="書表" />
      <Legend />
      <div className="flex items-center gap-2 mb-3 text-sm">
        <Link href={`/tables?tab=5&${q}`} className={`px-3 py-1.5 rounded ${tab === "5" ? "bg-[#ea580c] text-white" : "bg-white border"}`}>影響地價區域因素分析明細表</Link>
        <Link href={`/tables?tab=4&${q}`} className={`px-3 py-1.5 rounded ${tab === "4" ? "bg-[#ea580c] text-white" : "bg-white border"}`}>比較法調查估價表</Link>
        {(tab === "5" ? has5 : has4) ? <span className="text-xs">{nErr ? <Badge kind="error">{nErr} 格與送審書表不符</Badge> : <Badge kind="ok">與送審書表相符</Badge>}</span> : <span className="text-xs text-slate-500">本案無送審書表填載值</span>}
        <span className="ml-auto text-xs text-slate-500">點任一列查看判定條件與矩陣格位</span>
      </div>
      {msg && <div className="text-xs bg-slate-50 border rounded p-2 mb-2">{msg}</div>}
      <div className="grid lg:grid-cols-3 gap-4">
        <StaleDim className="lg:col-span-2"><div>
          {tab === "5" ? (
            <Card title="影響地價區域因素分析明細表" lead={`適用：${ruleName(rsIds.regional)}`} hint="點比較標的的等級格，右側會切換到該項判定依據的本案格位。">
              <div className="overflow-x-auto"><table className="grid"><thead>
                <tr><th rowSpan={2}>主要項目</th><th rowSpan={2}>修正細項</th><th colSpan={2}>比準地區段 {t5.subject_section}</th>{compNos.map((k) => <th key={k} colSpan={3}>比較標的{k} 區段 {run.table5[k].comparable_section}</th>)}</tr>
                <tr><th colSpan={2}><Tip k="t5.level">優劣等級</Tip></th>{compNos.map((k) => <Fragment key={k}><th colSpan={2}><Tip k="t5.level">優劣等級</Tip></th><th key={`${k}b`}><Tip k="t5.row">修正百分比</Tip></th></Fragment>)}</tr></thead>
                <tbody>{Object.entries(groups).map(([g, rows]) => (<Fragment key={g}>
                  {rows.map((r: Any, i: number) => { const fS = compNos.map((k) => f5(r.rule_id, k)).find((f) => f && String(f.location).includes("比準地")) || null; return (
                    <tr key={r.rule_id} id={`row-${r.rule_id}`} className={`clickable ${sel?.ruleId === r.rule_id ? "selected" : ""}`} onClick={() => setSel({ rulesetId: rsIds.regional, ruleId: r.rule_id, subject: r.subject_level, comparable: r.comparable_level })}>
                      {i === 0 && <td rowSpan={rows.length + 1} className="bg-[#ffedd5] font-medium">{t5.group_names?.[g] || ""}({g})</td>}
                      <td>{r.name}{r.issues?.length ? <span title={r.issues.join("\n")} className="ml-1 text-amber-700">⚠</span> : null}</td>
                      {lvl(r.subject_level, sub5of(compNo)?.levels?.[r.rule_id]?.subject, r.subject_num, has5, fS)}
                      {compNos.map((k) => { const rk = run.table5[k].rows.find((x: Any) => x.rule_id === r.rule_id); const f = f5(r.rule_id, k); const sk = sub5of(k)?.levels?.[r.rule_id]; return (<Fragment key={k}>
                        <td key={`${k}n`} className="text-center" onClick={(e) => { e.stopPropagation(); setCompNo(k); setSel({ rulesetId: rsIds.regional, ruleId: r.rule_id, subject: rk?.subject_level, comparable: rk?.comparable_level }); }}>{rk?.comparable_num ?? ""}</td>
                        <td key={`${k}l`} className={f && f.severity === "error" && f.message.includes("比較標的") ? "bg-red-100 text-red-900" : ""} onClick={(e) => { e.stopPropagation(); setCompNo(k); setSel({ rulesetId: rsIds.regional, ruleId: r.rule_id, subject: rk?.subject_level, comparable: rk?.comparable_level }); }}>{rk?.comparable_level ?? <Badge kind="warn">需人工確認</Badge>}{f && f.severity === "error" && f.message.includes("比較標的") && sk?.comparable ? <div className="text-[11px]">填載 {sk.comparable}</div> : null}</td>
                        <Cell key={`${k}p`} computed={rk?.pct} submitted={sk?.pct} has={!!sub5of(k) && !!sk} fmt={(v) => Number(v).toFixed(2)} finding={f && f.message.includes("修正百分比") ? f : null} /></Fragment>); })}
                    </tr>); })}
                  <tr key={`sub${g}`}><td colSpan={3} className="text-right text-slate-600"><Tip k="t5.subtotal">百分比小計 ({g})</Tip></td>{compNos.map((k) => <><td key={`${k}x`} colSpan={2}></td><Cell key={`${k}s`} computed={run.table5[k].group_subtotals[g]} submitted={sub5of(k)?.group_subtotals?.[g]} has={!!sub5of(k)} fmt={(v) => `${Number(v).toFixed(2)} %`} finding={f5(`G${g}`, k)} /></>)}</tr>
                </Fragment>))}
                  <tr><td colSpan={4} className="text-right font-semibold"><Tip k="t5.total">影響地價區域因素總修正數</Tip></td>{compNos.map((k) => <><td key={`${k}x`} colSpan={2}></td><Cell key={`${k}t`} computed={run.table5[k].total_pct} submitted={sub5of(k)?.total_pct} has={!!sub5of(k)} fmt={(v) => `${Number(v).toFixed(2)} %`} finding={f5("TOTAL", k)} cls="font-semibold" /></>)}</tr></tbody></table></div>
            </Card>
          ) : (
            <Card title="比較法調查估價表" lead={`適用：${ruleName(rsIds.individual)}`}>
              <div className="overflow-x-auto"><table className="grid"><thead><tr><th>調整項目</th><th>比準地 {subj.parcel_id}</th>{t4.comparables.map((c: Any) => <Fragment key={c.comp_no}><th>比較標的{c.comp_no} {c.parcel_id}</th><th key={`${c.comp_no}b`}>差異率</th></Fragment>)}</tr></thead>
                <tbody>
                  {(() => { const C = t4.comparables; const cd = (c: Any) => rec.data.comparables.find((x: Any) => String(x.comp_no) === String(c.comp_no)); const S = (c: Any) => sub4of(String(c.comp_no)); const H = (c: Any) => !!S(c); const K = String; return (<>
                  <tr><td><Tip k="t4.normal_unit_price">土地正常單價（元/m²）</Tip></td><td></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td className="text-right font-mono">{fmtMoney(c.normal_unit_price)}</td><td key={`${c.comp_no}b`}></td></Fragment>)}</tr>
                  <tr><td><Tip k="t4.date_adjustment">交易日期／估價基準日調整</Tip></td><td></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td className="text-right font-mono">{cd(c)?.transaction_date}</td><Cell key={`${c.comp_no}b`} computed={c.date_adjustment_pct} submitted={S(c)?.date_adjustment_pct} has={H(c)} fmt={fmtPct} /></Fragment>)}</tr>
                  <tr><td><Tip k="t4.price_at_valuation_date">調整至估價基準日單價（元/m²）</Tip></td><td></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td></td><Cell key={`${c.comp_no}b`} computed={Math.round(c.price_at_valuation_date)} submitted={S(c)?.price_at_valuation_date} has={H(c)} fmt={fmtMoney} tol={1} finding={f4(0, K(c.comp_no)) && f4(0, K(c.comp_no))!.location.includes("調整至") ? f4(0, K(c.comp_no)) : null} /></Fragment>)}</tr>
                  <tr id="row-I0"><td><Tip k="t4.regional_adjustment">地價區段／區域因素調整百分率</Tip></td><td>{subj.section_id}</td>{C.map((c: Any) => <Fragment key={c.comp_no}><td>{c.section_id}</td><Cell key={`${c.comp_no}b`} computed={c.regional_adjustment_pct} submitted={S(c)?.regional_adjustment_pct} has={H(c)} fmt={fmtPct} finding={f4(0, K(c.comp_no)) && f4(0, K(c.comp_no))!.location.includes("區域因素") ? f4(0, K(c.comp_no)) : null} /></Fragment>)}</tr>
                  {C[0].rows.map((r0: Any) => (
                    <tr key={r0.item_no} id={`row-I${r0.item_no}`} className={`clickable ${sel?.ruleId === `I${r0.item_no}` ? "selected" : ""}`} onClick={() => setSel({ rulesetId: rsIds.individual, ruleId: `I${r0.item_no}`, subject: r0.subject_level, comparable: r0.comparable_level })}>
                      <td><Tip k={[`t4.item.${r0.item_no}`, "t4.item"]}>{r0.item_no} {r0.name}</Tip>{C.some((c: Any) => c.rows.find((x: Any) => x.item_no === r0.item_no)?.issues?.length) ? <span className="ml-1 text-amber-700">⚠</span> : null}</td>
                      <td>{parcelVal(subj, r0)} <span className="text-xs text-slate-500">{r0.subject_level ? `（${r0.subject_level}）` : ""}</span></td>
                      {C.map((c: Any) => { const r = c.rows.find((x: Any) => x.item_no === r0.item_no); return (<Fragment key={c.comp_no}>
                        <td key={`${c.comp_no}a`} onClick={(e) => { e.stopPropagation(); setCompNo(K(c.comp_no)); setSel({ rulesetId: rsIds.individual, ruleId: `I${r0.item_no}`, subject: r?.subject_level, comparable: r?.comparable_level }); }}>{parcelVal(cd(c), r0)} <span className="text-xs text-slate-500">{r?.comparable_level ? `（${r.comparable_level}）` : ""}</span></td>
                        <Cell key={`${c.comp_no}b`} computed={r?.pct} submitted={S(c)?.individual?.[String(r0.item_no)]} has={H(c)} fmt={fmtPct} finding={f4(r0.item_no, K(c.comp_no))} /></Fragment>); })}
                    </tr>))}
                  <tr id="row-I99"><td colSpan={2} className="text-right font-semibold"><Tip k="t4.individual_total">個別因素合計</Tip></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td></td><Cell key={`${c.comp_no}b`} computed={c.individual_total_pct} submitted={S(c)?.individual_total_pct} has={H(c)} fmt={fmtPct} finding={f4(99, K(c.comp_no)) && f4(99, K(c.comp_no))!.location.includes("合計") ? f4(99, K(c.comp_no)) : null} cls="font-semibold" /></Fragment>)}</tr>
                  <tr><td><Tip k="t4.abs_sum">調整百分率絕對值加總</Tip>／<Tip k="t4.similarity">相近程度／權重</Tip></td><td></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td>{c.similarity}{H(c) && S(c)?.similarity && S(c).similarity !== c.similarity ? <span className="text-red-800 ml-1">（填載 {S(c).similarity}）</span> : ""}，權重 {c.weight_pct}%</td><Cell key={`${c.comp_no}b`} computed={c.abs_sum_pct} submitted={S(c)?.abs_sum_pct} has={H(c)} fmt={fmtPct} finding={f4(99, K(c.comp_no)) && f4(99, K(c.comp_no))!.location.includes("絕對值") ? f4(99, K(c.comp_no)) : null} /></Fragment>)}</tr>
                  <tr><td><Tip k="t4.trial_price">試算價格（調整後單價 ×（1＋區域）×（1＋個別））</Tip></td><td></td>{C.map((c: Any) => <Fragment key={c.comp_no}><td></td><Cell key={`${c.comp_no}b`} computed={Math.round(c.trial_price)} submitted={S(c)?.trial_price} has={H(c)} fmt={fmtMoney} tol={1} finding={f4(99, K(c.comp_no)) && f4(99, K(c.comp_no))!.location.includes("試算") ? f4(99, K(c.comp_no)) : null} /></Fragment>)}</tr>
                  <tr id="row-I100" className="font-semibold"><td><Tip k="t4.comparison_price">比準地比較價格（Σ 試算價格 × 權重，四捨五入至個位數）</Tip></td><td></td><Cell computed={t4.subject_comparison_price} submitted={rec.submitted_table4?.subject_comparison_price} has={has4} fmt={fmtMoney} tol={1} finding={fmap["4::100"] || null} cls="text-left" />{C.length > 1 && <td colSpan={C.length * 2 - 1}></td>}</tr>
                  <tr><td><Tip k="t4.land_price">比準地地價（查估辦法第 21 條尾數處理，僅比較法）</Tip></td><td></td><td className="text-right font-mono">{fmtMoney(t4.subject_land_price)}</td>{C.length > 1 && <td colSpan={C.length * 2 - 1}></td>}</tr>
                  </>); })()}
                </tbody></table></div>
              <Help className="mt-2" label="符號說明">差異率「—」＝免修正項目（手冊 p.52），與 0.00% 不同。⚠＝事實不足以判定等級，需人工確認。紅底＝送審書表填載值與系統核算不符（格內顯示填載值，滑過去看說明）。</Help>
            </Card>
          )}
        </div></StaleDim>
        <div>
          <Card title="判定依據">{sel ? <RulePanel {...sel} onClose={() => setSel(null)} /> : <div className="text-sm text-slate-500">點左表任一列，這裡會顯示該細項在評價基準明細表的判定條件與修正百分比矩陣，並標出本案格位。</div>}</Card>
          {tab === "5" && layers && layers.bbox && (
            <Card title="區段設施位置" hint={hlField ? `高亮「${hlRule?.name}」的設施與量測線` : "點左表的設施類細項（車站、市場、公園…）會高亮該設施與量測線"} right={<a className="text-xs underline" href={`/map?case=${encodeURIComponent(rec.id)}`}>到圖說 →</a>}>
              <LeafletMap layers={layers} mode="section" highlight={hlField ? { field: hlField } : null} className="h-[38vh]" />
            </Card>
          )}
          {(status.findings || []).some((f) => f.severity === "error" && f.table === (tab === "5" ? "表5" : "表4")) && (
            <Card title="本表不符項目">
              <ul className="text-xs space-y-1">{(status.findings || []).filter((f) => f.severity === "error" && f.table === (tab === "5" ? "表5" : "表4")).map((f, i) => <li key={i}><span className="text-red-800">{f.location}</span>：填載 {f.submitted}，核算 {f.computed}。{f.basis && <span className="text-slate-500">{f.basis}</span>}</li>)}</ul>
              <Link className="text-xs underline" href={`/review?case=${rec.id}`}>到審查結果 →</Link>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
export default function Tables() { return <Suspense fallback={<div className="text-sm">載入中…</div>}><TablesInner /></Suspense>; }
