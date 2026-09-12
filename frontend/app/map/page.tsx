"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useCase } from "@/components/CaseContext";
import { Btn, Card, Empty, FacilityChip, Help } from "@/components/ui";
import Legend from "@/components/Legend";
import { StaleBanner } from "@/components/Stale";
import PageHeader from "@/components/PageHeader";
import { api, Any, mapPngUrl } from "@/lib/api";
import type { MapMode } from "@/components/LeafletMap";
const LeafletMap = dynamic(() => import("@/components/LeafletMap"), { ssr: false });

const FIELDS: [string, string][] = [["school", "15 接近學校之程度"], ["market", "16 接近市場之程度"], ["park", "17 接近公園、廣場之程度"], ["station", "18 接近車站之程度"], ["commercial_district", "19 接近商圈之程度"], ["nuisance", "20 嫌惡設施"]];

/* 圖例色塊要和圖上一致：圖上分區以 45% 透明度疊在底圖上，圖例也用同樣透明度混白 */
function blendWhite(hex: string, a: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim()); if (!m) return hex;
  const n = parseInt(m[1], 16); const ch = (v: number) => Math.round(v * a + 255 * (1 - a)).toString(16).padStart(2, "0");
  return `#${ch(n >> 16)}${ch((n >> 8) & 255)}${ch(n & 255)}`;
}
export default function MapPage() {
  const { rec, label, stale } = useCase();
  const [layers, setLayers] = useState<Any>(null);
  const [showAll, setShowAll] = useState(false);       // 地圖取景：預設比準地周邊，可切成含遠處比較標的
  const [mode, setMode] = useState<MapMode>("sketch");
  const [hl, setHl] = useState<{ field?: string; owner?: string } | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => { if (rec) api.mapLayers(rec.data).then(setLayers).catch((e) => setMsg(String(e.message || e))); }, [rec]);

  const subj = rec?.data.subject_parcel;
  const facs = useMemo(() => FIELDS.map(([f, label]) => ({ f, label, v: subj?.[f] })), [subj]);
  if (!rec) return <Empty />;
  return (
    <div>
      <PageHeader title="② 地圖（互動檢視）" desc="互動檢視區段範圍、宗地位置、設施與量測路線，點右側設施可高亮量測路線。正式圖說在「② 產出書表」預覽第 4–6 頁；位置設定與人工標定設施在「① 輸入資料」的「案件與地價區段」分頁。"
        input="區段與宗地位置（地籍圖、人工點選或依面積合成）、設施資料庫" output="三張圖說、各設施距離與量測方式" />
      <StaleBanner what="圖說" />
      <Legend kinds={["source"]} />
    <div className="grid lg:grid-cols-4 gap-4">
      <div className="lg:col-span-3">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <div className="flex gap-1">{([["sketch", "區段略圖"], ["zoning", "使用分區圖"], ["section", "地價區段圖"]] as [MapMode, string][]).map(([m, l]) => <Btn key={m} kind={mode === m ? "primary" : "ghost"} onClick={() => setMode(m)}>{l}</Btn>)}</div>
          <div className="ml-auto flex items-center gap-2">
            {stale ? <span className="px-3 py-1.5 rounded text-sm bg-slate-100 text-slate-400 border border-slate-200 whitespace-nowrap" title="產出已過期，請先重新產生書表">⬇ 下載 PNG</span>
              : <a className="px-3 py-1.5 rounded text-sm bg-white border border-slate-300 hover:bg-slate-50 whitespace-nowrap" href={mapPngUrl(rec.id, mode, hl?.field)} download title="系統繪製的 PNG（1200×900，含底圖、圖例、比例尺），與 Excel 圖說、意見書附圖相同">⬇ 下載 PNG</a>}
          </div>
        </div>
        {layers?.n_far > 0 && <div className="no-print text-xs mb-1 flex items-center gap-2"><span className="text-slate-500">有 {layers.n_far} 筆幾何離比準地超過 2.5 km（其他鄉鎮的比較標的），預設不納入取景。</span><button className="underline" onClick={() => setShowAll(!showAll)}>{showAll ? "只看比準地周邊" : "顯示全部"}</button></div>}
        {layers ? <LeafletMap layers={showAll && layers.bbox_all ? { ...layers, bbox: layers.bbox_all } : layers} mode={mode} highlight={hl} /> : <div className="h-[70vh] bg-white border rounded-lg flex items-center justify-center text-slate-500">圖層計算中…</div>}
        {mode === "zoning" && layers?.zoning?.features?.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs">
            <span className="text-slate-500">使用分區：</span>
            {Array.from(new Map((layers.zoning.features as Any[]).map((f) => [f.properties.zone, f.properties.color])).entries()).map(([z, c]) => (
              <span key={String(z)} className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 border border-slate-500" style={{ background: blendWhite(String(c), 0.45) }} />{String(z)}</span>))}
            <span className="inline-flex items-center gap-1"><span className="inline-block w-3.5 h-3.5 border-2 border-dashed border-red-600" />地價區段範圍</span>
          </div>)}
        <div className="text-[11px] text-slate-500 mt-1">底圖 © 國土測繪中心；使用分區：新北市城鄉發展局開放資料；路網與設施：© OpenStreetMap contributors、政府開放資料、人工標定</div>
        {msg && <div className="text-sm mt-2 bg-white border rounded p-2">{msg}</div>}
      </div>
      <div>
        <Card title="比準地接近條件與嫌惡設施">
          <Help className="mb-2">點一列高亮量測路線：綠線步行距離、橘線直線距離、虛線直線估算。比準地位置來源：{subj.geometry ? label("geometry_sources", subj.geometry_source) : "尚無（到「① 輸入資料」基本資料分頁點圖設定）"}</Help>
          <table className="grid"><tbody>{facs.map(({ f, label, v }) => (
            <tr key={f} className={`clickable ${hl?.field === f ? "selected" : ""}`} onClick={() => setHl(hl?.field === f ? null : { field: f, owner: subj.parcel_id })}>
              <td className="whitespace-nowrap">{label}</td><td>{Array.isArray(v) ? (v.length ? v.map((x: Any, i: number) => <div key={i}><FacilityChip f={x} /></div>) : "無") : <FacilityChip f={v} />}</td></tr>))}</tbody></table>
        </Card>
        {layers?.sections?.features?.[0] && <Card title="地價區段範圍"><div className="text-xs">{layers.sections.features[0].properties.section_id}：{layers.sections.features[0].properties.range_desc}<br /><span className="text-slate-500">範圍來源：{label("geometry_sources", layers.sections.features[0].properties.geometry_source) || "勘查表"}</span></div></Card>}
      </div>
    </div>
    </div>
  );
}
