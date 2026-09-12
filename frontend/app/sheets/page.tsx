"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import PageHeader from "@/components/PageHeader";
import { StaleBanner } from "@/components/Stale";
import { Btn, Card, Empty } from "@/components/ui";
import { actorHeaders, Any, zhError } from "@/lib/api";

/* 書表預覽：照《查估書表範本》頁序（勘查表每個區段一頁：比準地區段在前、比較標的區段在後；再來表5、表4、區段略圖、使用分區圖、地價區段圖）。
   格線來自後端 /api/cases/{id}/sheets（與 Excel 同一份版面），所見即 Excel／PDF／列印。 */
const A4 = { portrait: [794, 1123], landscape: [1123, 794] } as const;
const SHEET_FONT = '"標楷體", "DFKai-SB", "BiauKai", "Noto Serif TC", serif';

function Sheet({ g, scale }: { g: Any; scale: number }) {
  const [W, H] = A4[g.orientation as "portrait" | "landscape"] || A4.landscape;
  const totalW = g.cols.reduce((a: number, b: number) => a + b, 0), totalH = g.rows.reduce((a: number, b: number) => a + b, 0);
  const tbl = useRef<HTMLTableElement>(null);
  const [fit, setFit] = useState(Math.min((W - 40) / totalW, (H - 40) / totalH, 1));
  // 表格列高會隨內容長大（HTML 不能比內容矮），所以量實際大小再決定縮放，整張表一定落在一頁內
  useLayoutEffect(() => {
    if (!tbl.current) return;
    const aw = Math.max(tbl.current.scrollWidth, totalW), ah = Math.max(tbl.current.scrollHeight, totalH);
    setFit(Math.min((W - 40) / aw, (H - 40) / ah, 1));
  }, [g, W, H, totalW, totalH]);
  return (
    <div className="sheet bg-white shadow border border-slate-300 mx-auto overflow-hidden relative" style={{ width: W * scale, height: H * scale }} data-orient={g.orientation}>
      <div style={{ transform: `scale(${scale * fit})`, transformOrigin: "top left", position: "absolute", left: 20 * scale, top: 20 * scale, width: totalW }}>
        <table ref={tbl} style={{ borderCollapse: "collapse", tableLayout: "fixed", width: totalW, fontFamily: SHEET_FONT }}>
          <colgroup>{g.cols.map((w: number, i: number) => <col key={i} style={{ width: w }} />)}</colgroup>
          <tbody>
            {g.rows.map((h: number, r: number) => (
              <tr key={r} style={{ height: h }}>
                {g.cells.filter((c: Any) => c.r === r).map((c: Any) => (
                  <td key={c.c} rowSpan={c.rs} colSpan={c.cs} style={{
                    border: c.border ? "0.8px solid #000" : "0", background: c.fill || "transparent", padding: "1px 3px", fontSize: c.size * 1.33,
                    fontWeight: c.b ? 700 : 400, textAlign: c.h as Any, verticalAlign: c.va === "center" ? "middle" : c.va,
                    whiteSpace: c.border ? (c.wrap || c.cs === 1 ? "pre-wrap" : "pre") : "nowrap",
                    overflow: c.border ? "hidden" : "visible", lineHeight: 1.15, wordBreak: "break-all" }}>{c.v}</td>))}
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Sheets() {
  const { rec, stale, status } = useCase();
  const [data, setData] = useState<Any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [marks, setMarks] = useState(false);
  const nErr = (status.findings || []).filter((f) => f.severity === "error").length;
  const wrap = useRef<HTMLDivElement>(null);
  const key = rec ? `${rec.id}:${rec.outputs?.generated_at}:${rec.input_hash}` : "";
  useEffect(() => {
    const onBefore = () => {
      document.querySelectorAll<HTMLElement>(".sheet").forEach((el) => {
        const inner = el.querySelector<HTMLElement>(":scope > div"); const tbl = inner?.querySelector<HTMLElement>("table");
        const w = tbl?.scrollWidth || inner?.scrollWidth || 0, h = tbl?.scrollHeight || inner?.scrollHeight || 0;
        const land = el.dataset.orient === "landscape";
        const pw = (land ? 281 : 194) * 3.78, ph = (land ? 194 : 281) * 3.78;
        const z = w && h ? Math.min(1, pw / w, ph / h) : 1;
        el.style.setProperty("--print-zoom", String(Math.floor(z * 100) / 100));
      });
    };
    window.addEventListener("beforeprint", onBefore); return () => window.removeEventListener("beforeprint", onBefore);
  }, []);
  useEffect(() => { if (!rec) return; setData(null); setErr(null); fetch(`/api/cases/${encodeURIComponent(rec.id)}/sheets`).then(async (r) => { if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null))); return r.json(); }).then(setData).catch((e) => setErr(String(e.message || e))); }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const f = () => { if (wrap.current) setScale(Math.min(1, (wrap.current.clientWidth - 8) / 1123)); };
    f(); window.addEventListener("resize", f); return () => window.removeEventListener("resize", f);
  }, [data]);
  async function download(kind: "pdf" | "xlsx") {
    if (!rec) return; setBusy(kind);
    try {
      const r = await fetch(`/api/cases/${encodeURIComponent(rec.id)}/sheets.${kind}`, { headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${rec.data.case.case_no}_查估書表.${kind}`; a.click();
    } catch (e: Any) { setErr(String(e.message || e)); } finally { setBusy(null); }
  }
  if (!rec) return <Empty />;
  const name = (t: string) => (t.startsWith("表1") ? `地價區段勘查表${t.length > 2 ? `（${t.slice(3)}）` : ""}` : t.startsWith("表5") ? "影響地價區域因素分析明細表" : "比較法調查估價表");
  return (
    <div>
      <div className="sheets-page-head"><PageHeader title="② 產出書表" desc="書表依範本頁序重算：勘查表每個區段一頁（比準地與各比較標的區段）、區域因素分析明細表、比較法調查估價表、三張圖說；畫面所見即下載的 Excel 與 PDF，列印請由 PDF 進行（表 A4、圖 A3 橫式）。"
        input="案件資料、核算結果、圖說" output="完整書表 Excel／PDF" next={{ href: "/review", label: "審查結果" }} /></div>
      <StaleBanner what="書表" />
      <div className="no-print flex flex-wrap items-center gap-2 mb-3 bg-white border border-slate-200 rounded-lg px-3 py-2">
        <span className="text-xs text-slate-500">簽章欄：{rec.data.case.appraiser || "（未填，請到「① 輸入資料」基本資料填寫）"}</span>
        <label className="text-xs flex items-center gap-1 ml-2 cursor-pointer" title="開啟後顯示紅格與判定矩陣的審查對照檢視；正式書表預覽不帶標記">
          <input type="checkbox" checked={marks} onChange={(e) => setMarks(e.target.checked)} />顯示審查標記
        </label>
        {marks && <span className="text-xs">對照檢視：
          <Link className="underline ml-1" href={`/table1?case=${encodeURIComponent(rec.id)}`}>勘查表</Link>
          <Link className="underline ml-1" href={`/tables?tab=5&case=${encodeURIComponent(rec.id)}`}>區域因素分析明細表</Link>
          <Link className="underline ml-1" href={`/tables?tab=4&case=${encodeURIComponent(rec.id)}`}>比較法調查估價表</Link>
          <span className="text-slate-500 ml-1">（不符 {nErr} 項）</span></span>}
        <Link className="text-xs underline" href={`/map?case=${encodeURIComponent(rec.id)}`}>地圖（互動檢視）</Link>
        <div className="ml-auto flex gap-2">
          <Btn kind="ghost" onClick={() => download("xlsx")} disabled={stale || !!busy} busy={busy === "xlsx"} title={stale ? "產出已過期，請先重新產生書表" : "六張工作表：三表＋三圖"}>{busy === "xlsx" ? "產生中…" : "⬇ 下載完整書表 Excel"}</Btn>
          <Btn onClick={() => download("pdf")} disabled={stale || !!busy} busy={busy === "pdf"} title={stale ? "產出已過期，請先重新產生書表" : "完整 PDF，照範本頁序（勘查表每區段一頁＋兩表＋三圖）"}>{busy === "pdf" ? "產生中…" : "⬇ 下載完整書表 PDF"}</Btn>
          <Btn kind="ghost" onClick={() => window.open(`/api/cases/${encodeURIComponent(rec.id)}/sheets.pdf?inline=1`, "_blank")} disabled={stale} title={stale ? "產出已過期，請先重新產生書表" : "在新分頁開啟完整 PDF（各區段勘查表＋兩表＋三圖，照範本頁序與紙張），從 PDF 列印"}>🖨 列印（PDF）</Btn>
        </div>
      </div>
      {err && <div className="text-sm text-red-700 mb-3">{err}</div>}
      {!data && !err && <Card><div className="text-sm text-slate-500">書表產生中…</div></Card>}
      <div ref={wrap} className={`space-y-6 ${stale ? "opacity-60" : ""}`}>
        {data?.sheets?.map((g: Any, i: number) => (
          <div key={g.title}>
            <div className="no-print text-xs text-slate-500 mb-1">第 {i + 1} 頁　{name(g.title)}</div>
            <Sheet g={g} scale={scale} />
          </div>))}
        {data?.figures?.map((fg: Any, i: number) => (
          <div key={fg.mode}>
            <div className="no-print text-xs text-slate-500 mb-1">第 {(data.sheets?.length || 0) + i + 1} 頁　{fg.title}</div>
            <div className="sheet bg-white shadow border border-slate-300 mx-auto overflow-hidden flex items-center justify-center" style={{ width: 1123 * scale, height: 794 * scale }} data-orient="landscape">
              <img src={fg.url} alt={fg.title} style={{ maxWidth: 1083 * scale, maxHeight: 754 * scale, width: "auto", height: "auto" }} />
            </div>
          </div>))}
        {data && !data.figures?.length && <Card title="圖說"><div className="text-sm text-slate-600">本案尚無區段範圍或宗地位置，無法產生三張圖說。請到「案件與地價區段」分頁推估區段範圍或設定比準地位置。</div></Card>}
      </div>
    </div>
  );
}
