"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api, CaseRecord, CaseData, Any, Finding } from "@/lib/api";

/* 全站共用：目前案件、名稱對照（/api/meta）、核算與審查結果（各頁共用，不重算）。案件資料存後端。 */
export interface Status { run: Any | null; findings: Finding[] | null; error: string | null; loading: boolean }
interface Ctx {
  rec: CaseRecord | null; loading: boolean; error: string | null; cases: Any[]; meta: Any | null; status: Status;
  loadCase: (id: string) => Promise<void>;
  loadDemo: (variant: "template" | "tampered" | "residential" | "blank_survey" | "shulin") => Promise<void>;
  save: (patch: { data?: CaseData; name?: string; submitted_table5?: Any; submitted_table4?: Any }) => Promise<CaseRecord>;
  patch: (patch: { name?: string; status?: string; decisions?: Record<string, Any> }) => Promise<CaseRecord>;
  duplicate: (id: string, name?: string) => Promise<CaseRecord>;
  stale: boolean; generating: boolean;
  mode: "review" | "generate";   // review＝審查送審書表（有填載值可比對）；generate＝依地號產生書表
  generate: () => Promise<CaseRecord | null>;
  reset: () => Promise<CaseRecord | null>;
  clear: () => Promise<CaseRecord | null>;
  resetAll: () => Promise<number>;   // 重置所有案件：後端清空後，前端回到「沒有案件」狀態
  deselect: () => void;              // 放掉目前案件（回案件總覽時用）
  refreshList: () => Promise<Any[]>;
  ruleName: (id?: string) => string;
  label: (kind: "facility_types" | "measure_labels" | "origin_labels" | "geometry_sources" | "checklist" | "tables", key?: string | null) => string;
}
const C = createContext<Ctx | null>(null);
const EMPTY: Status = { run: null, findings: null, error: null, loading: false };

export function CaseProvider({ children }: { children: React.ReactNode }) {
  const [rec, setRec] = useState<CaseRecord | null>(null);
  const [cases, setCases] = useState<Any[]>([]);
  const [meta, setMeta] = useState<Any | null>(null);
  const [status, setStatus] = useState<Status>(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  const setUrl = (id: string) => { const u = new URL(window.location.href); u.searchParams.set("case", id); window.history.replaceState({}, "", u.toString()); };
  const refreshList = useCallback(async () => { const r = await api.listCases(); setCases(r.cases); return r.cases; }, []);
  const loadCase = useCallback(async (id: string) => {
    setLoading(true); setError(null);
    try {
      let r = await api.getCase(id);
      if (!r.outputs) { try { r = await api.generate(id); } catch { /* 第一次載入自動產生；失敗就維持未產生 */ } }   // 從未產生過的案件（新建、上傳、舊資料）先產生一次
      setRec(r); setUrl(id);
    } catch (e: Any) { setError(String(e.message || e)); } finally { setLoading(false); }
  }, []);
  const loadDemo = useCallback(async (variant: "template" | "tampered" | "residential" | "blank_survey" | "shulin") => {
    setLoading(true); setError(null);
    try { const d = await api.demo(variant, true); await refreshList(); await loadCase(d.id); } catch (e: Any) { setError(String(e.message || e)); setLoading(false); }
  }, [loadCase, refreshList]);
  const save = useCallback(async (patch: { data?: CaseData; name?: string; submitted_table5?: Any; submitted_table4?: Any }) => {
    if (!rec) throw new Error("沒有目前案件");
    const next = { ...rec, ...patch, data: patch.data ?? rec.data } as CaseRecord;
    const saved = await api.saveCase(next); setRec(saved); await refreshList(); return saved;
  }, [rec, refreshList]);

  const patch = useCallback(async (p: { name?: string; status?: string; decisions?: Record<string, Any> }) => {
    if (!rec) throw new Error("沒有目前案件");
    const saved = await api.patchCase(rec.id, p); setRec(saved); await refreshList(); return saved;
  }, [rec, refreshList]);
  const duplicate = useCallback(async (id: string, name?: string) => { const d = await api.duplicateCase(id, name); await refreshList(); await loadCase(d.id); return d; }, [refreshList, loadCase]);
  const generate = useCallback(async () => {
    if (!rec) return null; setGenerating(true);
    try { const r = await api.generate(rec.id); setRec(r); setError(null); await refreshList(); return r; }
    catch (e: Any) { setError(`重新產生書表失敗：${String(e?.message || e)}`); throw e; }
    finally { setGenerating(false); }
  }, [rec, refreshList]);
  const reset = useCallback(async () => {
    if (!rec) return null;
    let r = await api.resetCase(rec.id);
    try { r = await api.generate(rec.id); } catch { /* 重置後先產生一次；失敗就維持未產生 */ }
    setRec(r); await refreshList(); return r;
  }, [rec, refreshList]);
  const clear = useCallback(async () => {
    if (!rec) return null;
    let r = await api.clearCase(rec.id);
    try { r = await api.generate(rec.id); } catch { /* 清空後先產生一次；失敗就維持未產生 */ }
    setRec(r); await refreshList(); return r;
  }, [rec, refreshList]);
  const clearUrl = () => { const u = new URL(window.location.href); u.searchParams.delete("case"); window.history.replaceState({}, "", u.toString()); };
  const deselect = useCallback(() => { setRec(null); setStatus(EMPTY); setError(null); clearUrl(); }, []);
  const path = usePathname();
  useEffect(() => { if (path === "/") deselect(); }, [path, deselect]);   // 案件總覽＝未選案件；①～④ 才是針對某個案件
  const resetAll = useCallback(async () => {
    const r = await api.resetAllCases();
    setRec(null); setCases([]); setStatus(EMPTY); setError(null);
    const u = new URL(window.location.href); u.searchParams.delete("case"); window.history.replaceState({}, "", u.toString());
    return r.cases;
  }, []);
  const stale = !!rec && (!rec.outputs || rec.outputs.input_hash !== rec.input_hash);
  const mode: "review" | "generate" = rec && (rec.submitted_table4 || rec.submitted_table5) ? "review" : "generate";

  useEffect(() => {
    api.meta().then(setMeta).catch(() => setMeta(null));
    const id = new URL(window.location.href).searchParams.get("case");
    (async () => { await refreshList().catch(() => []); if (id && window.location.pathname !== "/") await loadCase(id); })();   // 只在網址帶 ?case= 時載入，不自動選第一件
  }, [loadCase, refreshList]);

  const runKey = rec ? JSON.stringify([rec.id, rec.data, rec.submitted_table5, rec.submitted_table4]) : "";
  useEffect(() => {
    if (!rec) { setStatus(EMPTY); return; }
    let alive = true;
    setStatus({ run: null, findings: null, error: null, loading: true });
    (async () => {
      try {
        const run = await api.run(rec.data);
        let findings: Finding[] | null = null;
        if (rec.submitted_table4 || rec.submitted_table5) findings = (await api.verify(rec.data, rec.submitted_table5, rec.submitted_table4)).findings;
        else findings = (await api.verify(rec.data, null, null)).findings;   // 沒有送審書表也做實例蒐集期間等檢查
        if (alive) setStatus({ run, findings, error: null, loading: false });
      } catch (e: Any) { if (alive) setStatus({ run: null, findings: null, error: String(e.message || e), loading: false }); }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runKey]);

  const ruleName = (id?: string) => (id && meta?.rulesets?.[id]?.source) || id || "—";
  const label: Ctx["label"] = (kind, key) => (key ? (meta?.[kind]?.[key] ?? key) : "—");
  return <C.Provider value={{ rec, loading, error, cases, meta, status, loadCase, loadDemo, save, patch, duplicate, refreshList, ruleName, label, stale, generating, generate, reset, clear, resetAll, deselect, mode }}>{children}</C.Provider>;
}
export const useCase = () => { const c = useContext(C); if (!c) throw new Error("CaseProvider missing"); return c; };
