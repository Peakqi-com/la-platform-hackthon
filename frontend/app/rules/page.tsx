"use client";
import { useEffect, useRef, useState } from "react";
import { useCase } from "@/components/CaseContext";
import { Badge, Btn, Card, Empty, Help } from "@/components/ui";
import PageHeader from "@/components/PageHeader";
import { IOBadge } from "@/components/IO";
import { api, Any } from "@/lib/api";

export default function Rules({ embedded = false }: { embedded?: boolean } = {}) {
  const { rec, save, generate } = useCase();
  const [list, setList] = useState<Record<string, Any>>({});
  const [detail, setDetail] = useState<Any>(null);
  const [adapted, setAdapted] = useState<Any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const reload = () => api.rules().then(setList);
  useEffect(() => { reload(); }, []);

  async function apply(scope: "regional" | "individual", id: string) {
    if (!rec) return;
    const data = { ...rec.data, case: { ...rec.data.case, rulesets: { ...(rec.data.case.rulesets || {}), [scope]: id }, land_use: list[id]?.land_use || rec.data.case.land_use } };
    await save({ data }); await generate(); setMsg(`已將${scope === "regional" ? "區域" : "個別"}因素基準表換成「${list[id]?.source || id}」，兩張表會依新表重新核算。`);
  }
  async function onUpload(file: File) {
    setBusy(true); setMsg(null); setAdapted(null);
    try {
      if (file.name.endsWith(".json")) {
        const rs = JSON.parse(await file.text());
        const r = await api.importRules(rs); setMsg(`已匯入 ${r.id}`); await reload();
      } else {
        const ascii = file.name.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_]/g, "");
        const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
        const r = await api.adapt(file, "rules_table", { id_prefix: ascii ? `${ascii}_${stamp}` : `rules_${stamp}` });   // 中文檔名不能當 id，用時間戳
        setAdapted(r);
        const done: string[] = [];
        let data = rec ? { ...rec.data, case: { ...rec.data.case, rulesets: { ...(rec.data.case.rulesets || {}) } } } : null;
        for (const scope of Object.keys(r.data.rulesets || {})) {
          const imp = await api.importRules(r.data.rulesets[scope]);
          done.push(`${scope === "regional" ? "區域因素" : "個別因素"} ${imp.summary.n_rules} 條`);
          if (data) { data.case.rulesets[scope] = imp.id; if (r.data.rulesets[scope].land_use) data.case.land_use = r.data.rulesets[scope].land_use; }
        }
        await reload();
        if (data && done.length) { await save({ data }); await generate(); }
        setMsg(`已匯入 ${file.name}：${done.join("、") || "沒有讀到基準表"}${data && done.length ? "；已套用至本案並重新產生書表" : ""}。`);
      }
    } catch (e: Any) { setMsg(String(e.message || e)); } finally { setBusy(false); }
  }
  const cur = rec?.data.case.rulesets || {};
  return (
    <div>
      {!embedded && <PageHeader title="① 輸入資料：評價基準明細表" desc="各直轄市、縣（市）依內政部「影響地價區域因素評價基準表」與「影響地價個別因素評價基準表」之最大影響範圍，訂定各用地別的評價基準明細表。系統以基準明細表為資料，換一份即依新表核算。"
        input="評價基準明細表（PDF、CSV 或系統格式 JSON）" output="套用至本案的區域因素／個別因素基準表" next={{ href: "/sheets", label: "地價區段勘查表" }} />}
    <div className="grid lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2">
        <Card title={<>匯入評價基準明細表 <IOBadge kind="import" what="PDF／CSV／JSON" /></>}>
          <input ref={fileRef} type="file" accept=".pdf,.csv,.xlsx,.json" className="hidden" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) onUpload(f); e.target.value = ""; }} />
          <div className={`rounded-xl border-2 border-dashed p-6 text-center transition ${drag ? "border-[#ea580c] bg-orange-50" : "border-orange-300 bg-sky-50/40"}`}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) onUpload(f); }}>
            <div className="text-base font-semibold mb-2">將評價基準明細表 PDF 拖到這裡，或</div>
            <Btn onClick={() => fileRef.current?.click()} disabled={busy} busy={busy}>⬆ 選擇檔案匯入（PDF／CSV／JSON）</Btn>
            <Help className="mt-3">細項自動對回內政部基準表項目並解析級距；超過最大影響範圍者提醒。匯入後自動套用至本案。</Help>
          </div>
          {msg && <div className="text-sm bg-emerald-50 border border-emerald-200 rounded p-2 mt-3">{msg}</div>}
          {adapted && adapted.warnings?.length > 0 && (
            <details className="text-xs mt-2"><summary className="cursor-pointer text-slate-600">轉換提醒 {adapted.warnings.length} 則</summary>
              <ul className="list-disc pl-4 mt-1 text-slate-600 max-h-48 overflow-auto">{adapted.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul></details>
          )}
        </Card>
        <Card title="系統中的評價基準明細表" hint="標示「示範」者為系統示範用，非任何縣市正式基準表。">
          <table className="grid"><thead><tr><th>名稱</th><th>因素</th><th>用地別</th><th>細項數</th><th>備註</th><th>操作</th></tr></thead>
            <tbody>{Object.values(list).map((r: Any) => (
              <tr key={r.id} className={cur.regional === r.id || cur.individual === r.id ? "selected" : ""}>
                <td className="cursor-pointer underline" onClick={() => api.rule(r.id).then(setDetail)}>{r.source}</td><td>{r.scope === "regional" ? "區域因素" : "個別因素"}</td><td>{r.land_use}</td><td className="text-right">{r.n_rules}</td>
                <td className="text-xs">{r.is_demo && <Badge kind="warn">示範</Badge>}{r.note && !r.is_demo ? "" : ""}</td>
                <td className="whitespace-nowrap">{rec && <Btn kind="ghost" onClick={() => apply(r.scope, r.id)} disabled={cur[r.scope] === r.id}>{cur[r.scope] === r.id ? "本案適用中" : "套用至本案"}</Btn>}</td></tr>))}</tbody></table>
          {!rec && <div className="mt-2"><Empty text="載入案件後才能套用基準表。" /></div>}
        </Card>
      </div>
      <div>
        <Card title={detail ? detail.source : "基準表明細"}>
          {detail ? (<div className="text-xs">
            <div className="text-slate-600 mb-2">{detail.$schema_note}</div>
            <table className="grid"><thead><tr><th>編號</th><th>修正細項</th><th>等級數</th><th>最大影響範圍(%)</th><th>判定方式</th></tr></thead>
              <tbody>{detail.rules.map((r: Any) => <tr key={r.id}><td className="font-mono">{r.item_no ?? r.id}</td><td>{r.name}{r.note ? <span title={r.note} className="text-amber-700"> ⚠</span> : null}</td><td>{r.levels.length}</td><td className="text-right">{r.max_pct}</td><td>{({ enum: "分類", bands: "數值級距", distance: "距離級距", boolean: "有無", manual: "自行判定" } as Any)[r.criteria.type] || r.criteria.type}</td></tr>)}</tbody></table>
          </div>) : <div className="text-sm text-slate-500">點左表名稱查看細項。</div>}
        </Card>
      </div>
    </div>
    </div>
  );
}
