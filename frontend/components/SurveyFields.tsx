"use client";
import { Any } from "@/lib/api";
import { useCase } from "./CaseContext";
import { SOURCE_STYLES, sourceKind } from "./Legend";

/* 勘查表／宗地條件共用欄位編輯器：由基準表 criteria 型別決定輸入方式。 */
export const get = (o: Any, path: string) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
export const set = (o: Any, path: string, v: Any) => { const ks = path.split("."); let cur = o; ks.slice(0, -1).forEach((k) => (cur = cur[k] = cur[k] ?? {})); cur[ks[ks.length - 1]] = v; };

export function FacilityEditor({ value, onChange, list, types, typeLabel }: { value: Any; onChange: (v: Any) => void; list: boolean; types: string[]; typeLabel: (t: string) => string }) {
  const items: Any[] = list ? (value || []) : value ? [value] : [];
  const upd = (i: number, patch: Any) => { const n = items.map((x, j) => (j === i ? { ...x, ...patch, source: x.computed ? x.source : "manual" } : x)); onChange(list ? n : n[0] || null); };
  const add = () => onChange(list ? [...items, { name: "", distance_m: null, type: types[0], measure: "walking", origin: "section_boundary", source: "manual" }] : { name: "", distance_m: null, type: types[0], measure: "walking", origin: "parcel_centroid", source: "manual" });
  const del = (i: number) => onChange(list ? items.filter((_, j) => j !== i) : null);
  return (
    <div className="space-y-1">
      {items.map((f, i) => (
        <div key={i} className="flex flex-wrap gap-1 items-center text-xs">
          <input className="border rounded px-1 w-28" placeholder="設施名稱" value={f.name || ""} onChange={(e) => upd(i, { name: e.target.value })} />
          <input className="border rounded px-1 w-16" type="number" placeholder="公尺" value={f.distance_m ?? ""} onChange={(e) => upd(i, { distance_m: e.target.value === "" ? null : Number(e.target.value) })} />
          <label className="flex items-center gap-1"><input type="checkbox" checked={!!f.in_section} onChange={(e) => upd(i, { in_section: e.target.checked })} />區段內</label>
          <select className="border rounded px-1" value={f.measure || ""} onChange={(e) => upd(i, { measure: e.target.value, assumed: false })}><option value="walking">步行距離</option><option value="straight">直線距離</option><option value="straight_estimated">直線估算</option></select>
          <select className="border rounded px-1" value={f.type || types[0]} onChange={(e) => upd(i, { type: e.target.value })}>{types.map((t) => <option key={t} value={t}>{typeLabel(t)}</option>)}</select>
          <span className="text-slate-500" title={f.source}>{f.computed ? "系統推算" : "人工填載"}{f.assumed ? "・量測方式為推定" : ""}</span>
          <button className="text-red-600" onClick={() => del(i)}>✕</button>
        </div>))}
      <button className="text-xs underline" onClick={add}>＋{list ? "新增設施" : items.length ? "" : "填寫設施"}</button>
      {items.length === 0 && <span className="text-xs text-slate-400 ml-2">（未填＝無此設施）</span>}
    </div>
  );
}

export function Field({ rule, value, onChange, scope, typeLabel }: { rule: Any; value: Any; onChange: (v: Any) => void; scope: "regional" | "individual"; typeLabel: (t: string) => string }) {
  const c = rule.criteria || {};
  if (c.type === "enum") { const keys = [...Object.keys(c.map || {}), ...Object.keys(c.normalize || {})]; return <select className="border rounded px-1 text-xs w-full" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)}><option value="">（未填）</option>{keys.map((k) => <option key={k}>{k}</option>)}</select>; }
  if (c.type === "boolean") return <select className="border rounded px-1 text-xs" value={value === true ? "有" : value === false ? "無" : ""} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "有")}><option value="">（未填）</option><option>有</option><option>無</option></select>;
  if (c.type === "bands") { const v = value && typeof value === "object" ? value.value ?? value.width_m : value; return <input className="border rounded px-1 text-xs w-24" type="number" value={v ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />; }
  if (c.type === "distance") return <FacilityEditor value={value} onChange={onChange} list={scope === "regional" || c.direction === "farther_is_better"} types={rule.facility_types || ["unknown"]} typeLabel={typeLabel} />;
  return <input className="border rounded px-1 text-xs w-full" placeholder="估價師自填" value={value ?? ""} onChange={(e) => onChange(e.target.value || null)} />;
}


export function SourceBadge({ v, prov }: { v: Any; prov?: string }) {
  const { label } = useCase();
  const k = prov === "filled" ? "computed" : prov === "suggested" ? "suggested" : prov === "manual" ? "manual_required" : null;
  if (k) { const st = SOURCE_STYLES[k]; const hint = k === "manual_required" ? "欄位空白：屬實地勘查或都市計畫書事項，系統不推測，請人工填入" : k === "suggested" ? "圖資只到較粗的層級，系統給建議值，請確認後採用或改填" : "由設施資料庫、路網、使用分區圖等圖資推算"; return <span className={`border rounded px-1 text-[10px] cursor-help ${st.cls}`} title={hint}>{st.label}</span>; }
  const f = Array.isArray(v) ? v[0] : v;
  if (f && typeof f === "object" && (f.computed || f.source)) { const st = SOURCE_STYLES[sourceKind(f)]; return <span className={`border rounded px-1 text-[10px] ${st.cls}`} title={f.source}>{st.label}{f.measure ? `・${label("measure_labels", f.measure)}` : ""}</span>; }
  if (v !== null && v !== undefined && v !== "") { const st = SOURCE_STYLES.manual; return <span className={`border rounded px-1 text-[10px] ${st.cls}`}>{st.label}</span>; }
  return null;
}
