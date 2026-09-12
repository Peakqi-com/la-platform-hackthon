/* 所有後端呼叫集中在這裡；路徑一律 /api/*，由 next.config 的 rewrites 代理到 BACKEND_URL。 */
export type Any = any;

export interface CaseData { case: Any; sections: Record<string, Any>; subject_parcel: Any; comparables: Any[] }
export type Decision = { decision: "accept" | "reject" | "pending"; note?: string; by?: string; at?: string; stale?: boolean };
export interface Outputs { generated_at: string; input_hash: string; summary?: Any; findings_keys?: string[] }
export interface Extraction { confidence?: Record<string, number>; missing_fields?: string[]; warnings?: string[]; pages?: Any[]; filename?: string }
export interface CaseRecord {
  id: string; name: string; origin: string; updated_at: string; created_at?: string; opened_at?: string; status?: "draft" | "reviewing" | "done"; data: CaseData;
  submitted_table5: Record<string, Any> | null; submitted_table4: Any | null; extraction?: Extraction | null; decisions?: Record<string, Decision>;
  original?: { data: CaseData; submitted_table5: Any; submitted_table4: Any; at: string } | null; input_hash?: string; input_updated_at?: string; outputs?: Outputs | null;
}
export const STATUS_LABEL: Record<string, string> = { draft: "草稿", reviewing: "審查中", done: "已完成" };
/* 操作身分（無登入的過渡做法）：存這台瀏覽器，隨每次請求以 header 送後端寫操作紀錄；不是案件資料。 */
export type Actor = { name: string; role: string };
export const ROLE_LABEL: Record<string, string> = { officer: "承辦", reviewer: "審查人", appraiser: "估價師" };
const ACTOR_KEY = "la_actor";
export function getActor(): Actor { try { const v = localStorage.getItem(ACTOR_KEY); if (v) { const a = JSON.parse(v); return { name: String(a.name || ""), role: String(a.role || "") }; } } catch { /* ignore */ } return { name: "", role: "" }; }
export function setActor(a: Actor) { try { localStorage.setItem(ACTOR_KEY, JSON.stringify(a)); } catch { /* ignore */ } }
export function actorHeaders(): Record<string, string> { if (typeof window === "undefined") return {}; const a = getActor(); const h: Record<string, string> = {}; if (a.name) h["X-Actor-Name"] = encodeURIComponent(a.name); if (a.role) h["X-Actor-Role"] = a.role; return h; }
export const mapPngUrl = (id: string, mode: "sketch" | "zoning" | "section", highlight?: string | null) => `/api/cases/${encodeURIComponent(id)}/map.png?mode=${mode}${highlight ? `&highlight=${encodeURIComponent(highlight)}` : ""}`;
export interface Finding { severity: "error" | "warn" | "info"; kind?: "mismatch" | "gap" | "inferred"; checklist: string; table: string; location: string; submitted: string | null; computed: string | null; message: string; basis: string | null; rule_id?: string | null; item_no?: number | null; comp_no?: number | null }

const STATUS_ZH: Record<number, string> = { 400: "請求內容不正確", 404: "找不到資料", 413: "檔案太大", 422: "資料格式有誤", 500: "系統發生錯誤，請稍後再試", 502: "後端服務未啟動", 503: "後端服務暫時無法使用", 504: "後端逾時" };
export function zhError(status: number, body: Any): string {
  const d = body?.detail ?? body;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return "資料格式有誤：" + d.map((e: Any) => `${(e.loc || []).filter((x: Any) => x !== "body").join("／") || "資料"} ${e.msg || ""}`).join("；");
  return STATUS_ZH[status] || `系統回應異常（${status}）`;
}
async function j<T = Any>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try { r = await fetch(url, { ...init, headers: { "content-type": "application/json", ...actorHeaders(), ...(init?.headers || {}) } }); }
  catch { throw new Error("無法連線到後端服務，請確認系統已啟動"); }
  if (!r.ok) {
    let body: Any = null; try { body = await r.json(); } catch { /* ignore */ }
    throw new Error(zhError(r.status, body));
  }
  return r.json();
}
const post = <T = Any>(url: string, body: Any) => j<T>(url, { method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => j("/api/health"),
  meta: () => j("/api/meta"),
  demo: (variant: "template" | "tampered" | "residential" | "blank_survey" | "shulin", save = true) => j(`/api/cases/demo?variant=${variant}&save=${save}`),
  listCases: () => j<{ cases: Any[] }>("/api/cases"),
  getCase: (id: string) => j<CaseRecord>(`/api/cases/${encodeURIComponent(id)}`),
  saveCase: (rec: Partial<CaseRecord> & { data: CaseData }) =>
    post<CaseRecord>("/api/cases", { ...rec.data, id: rec.id, name: rec.name, submitted_table5: rec.submitted_table5 ?? null, submitted_table4: rec.submitted_table4 ?? null,
      extraction: rec.extraction ?? null, status: rec.status ?? null, decisions: rec.decisions ?? null }),
  patchCase: (id: string, patch: { name?: string; status?: string; decisions?: Record<string, Decision> }) => j<CaseRecord>(`/api/cases/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) }),
  duplicateCase: (id: string, name?: string) => post<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/duplicate${name ? `?name=${encodeURIComponent(name)}` : ""}`, {}),
  generate: (id: string) => post<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/generate`, {}),
  newCase: (p: { case_no: string; valuation_date: string; district: string; land_use: string; section_id: string; range_desc?: string; subject_parcel_id?: string }) => post<CaseRecord>("/api/cases/new", p),
  resetPreview: (id: string) => j(`/api/cases/${encodeURIComponent(id)}/reset_preview`),
  resetCase: (id: string) => post<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/reset`, {}),
  comparablesSearch: (id: string, opts: { max_n?: number; relax?: boolean; neighbors?: boolean } = {}) => post<Any>(`/api/cases/${encodeURIComponent(id)}/comparables/search`, opts),
  comparablesApply: (id: string, ids: string[], building_costs: Record<string, number> = {}, reasons: Record<string, string> = {}) => post<Any>(`/api/cases/${encodeURIComponent(id)}/comparables/apply`, { ids, building_costs, reasons }),
  comparablesLocate: (id: string, comp_no: number, lon: number, lat: number) => post<Any>(`/api/cases/${encodeURIComponent(id)}/comparables/locate`, { comp_no, lon, lat }),
  notes: (id: string) => j<Any>(`/api/cases/${encodeURIComponent(id)}/notes`),
  polishText: (id: string, targets: string[] = ["range_desc", "notes"]) => post<Any>(`/api/cases/${encodeURIComponent(id)}/polish_text`, { targets }),
  cadastreLots: () => j<{ source: string | null; n?: number; districts?: string[]; lots: { section: string; lot: string; parcel_id: string; district?: string | null }[] }>("/api/cadastre/lots"),
  todo: (id: string) => j<{ mode: string; items: { key: string; label: string; count: number | null; href: string; level: string }[]; ready: boolean }>(`/api/cases/${encodeURIComponent(id)}/todo`),
  fillReport: (id: string) => j<Any>(`/api/cases/${encodeURIComponent(id)}/fill_report`),
  clearCase: (id: string) => post<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/clear`, {}),
  fromLot: (id: string, p: { parcel_id: string; manual_point?: [number, number]; overwrite?: boolean; parcel_changed?: boolean }) =>
    post<{ rec: CaseRecord; steps: { step: string; ok: boolean; note: string; filled?: string[] }[]; parcel_changed: boolean }>(`/api/cases/${encodeURIComponent(id)}/from_lot`, p),
  deleteCase: (id: string) => j(`/api/cases/${encodeURIComponent(id)}`, { method: "DELETE" }),
  resetAllCases: () => j<{ ok: boolean; cases: number; files: number; aux_files: number }>("/api/cases", { method: "DELETE" }),
  archiveCase: (id: string, undo = false) => post<CaseRecord>(`/api/cases/${encodeURIComponent(id)}/archive${undo ? "?undo=true" : ""}`, {}),
  run: (data: CaseData) => post("/api/run", data),
  verify: (data: CaseData, t5: Any, t4: Any) => post<{ findings: Finding[]; computed: Any }>("/api/verify", { ...data, submitted_table5: t5, submitted_table4: t4 }),
  audit: (id: string) => j<{ entries: Any[]; roles: Record<string, string>; actions: Record<string, string> }>(`/api/cases/${encodeURIComponent(id)}/audit`),
  report: (data: CaseData, t5: Any, t4: Any, opts: { polish?: boolean; reviewer?: string; reviewer_role?: string; case_id?: string; decisions?: Record<string, Decision> }) =>
    post("/api/report", { ...data, submitted_table5: t5, submitted_table4: t4, ...opts }),
  rules: () => j<Record<string, Any>>("/api/rules"),
  rule: (id: string) => j(`/api/rules/${encodeURIComponent(id)}`),
  importRules: (ruleset: Any, id?: string) => post("/api/rules/import", { ruleset, id }),
  adapt: async (file: File, kind = "auto", extra: Record<string, string> = {}) => {
    const fd = new FormData(); fd.append("file", file); fd.append("kind", kind);
    Object.entries(extra).forEach(([k, v]) => fd.append(k, v));
    let r: Response;
    try { r = await fetch("/api/adapt", { method: "POST", body: fd, headers: actorHeaders() }); } catch { throw new Error("無法連線到後端服務，請確認系統已啟動"); }
    if (!r.ok) { let body: Any = null; try { body = await r.json(); } catch { /* ignore */ } throw new Error(zhError(r.status, body)); }
    return r.json();
  },
  exportXlsx: async (data: CaseData, meta: Any = {}, case_id?: string, figures = true) => {
    const r = await fetch("/api/export/xlsx", { method: "POST", headers: { "content-type": "application/json", ...actorHeaders() }, body: JSON.stringify({ ...data, meta, case_id: case_id ?? null, figures }) });
    if (!r.ok) { let body: Any = null; try { body = await r.json(); } catch { /* ignore */ } throw new Error(zhError(r.status, body)); }
    return r.blob();
  },
  spatialStatus: () => j("/api/spatial/status"),
  spatialFill: (data: CaseData, overwrite = false) => post("/api/spatial/fill", { ...data, overwrite }),
  cadastreResolve: (data: CaseData, manual_points: Record<string, [number, number]>, overwrite = true) =>
    post("/api/cadastre/resolve", { ...data, manual_points, overwrite }),
  mapLayers: (data: CaseData) => post("/api/maps/layers", data),
  spatialSurveyDraft: (data: CaseData, section_id: string, overwrite = false) => post("/api/spatial/survey_draft", { ...data, section_id, overwrite }),
  addPoi: (p: { type: string; name: string; lon: number; lat: number; note?: string }) => post("/api/spatial/poi", p),
  bootstrapBlock: (hints: [number, number][], extra: Any = {}) => post("/api/bootstrap/block", { hints, ...extra }),
};

export const fmtPct = (v: Any) => (v === null || v === undefined || v === "-" ? "-" : `${Number(v).toFixed(2)}%`);
export const fmtMoney = (v: Any) => (v === null || v === undefined ? "-" : Math.round(Number(v)).toLocaleString("zh-TW"));

/* finding → 書表格位連結（審查頁「到該格」與表格頁高亮共用） */
export function findingHref(f: Finding, caseId: string): string | null {
  const q = `case=${encodeURIComponent(caseId)}${f.comp_no ? `&comp=${f.comp_no}` : ""}`;
  if (f.table === "表5" && f.rule_id) return `/tables?tab=5&rule=${encodeURIComponent(f.rule_id)}&${q}`;
  if (f.table === "表4" && f.item_no !== null && f.item_no !== undefined) return `/tables?tab=4&item=${f.item_no}&${q}`;
  return null;   // 全案層級（蒐集期間、比較標的件數等）沒有對應格位，不給追溯連結
}
export function findingKey(f: Finding): string | null {
  if (f.table === "表5" && f.rule_id) return `5:${f.comp_no ?? ""}:${f.rule_id}`;
  if (f.table === "表4" && f.item_no !== null && f.item_no !== undefined) return `4:${f.comp_no ?? ""}:${f.item_no}`;
  return null;
}

/* 抽取信心值：先找完整路徑，再找最長前綴（例如 subject_parcel 涵蓋其所有欄位）。回 null 表示不是抽取來的。 */
export function confidenceFor(ex: Extraction | null | undefined, path: string): number | null {
  const c = ex?.confidence; if (!c) return null;
  if (path in c) return c[path];
  let best: string | null = null;
  for (const k of Object.keys(c)) if (path.startsWith(k + ".") || path.startsWith(k + "[")) if (!best || k.length > best.length) best = k;
  return best ? c[best] : null;
}
export const LOW_CONF = 0.85;
