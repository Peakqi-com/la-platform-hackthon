"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";

/* 整站登入頁（後端 app/auth.py）。取代瀏覽器的 Basic 認證彈窗：機關電腦常以群組原則關掉 Basic 認證，彈窗出不來只剩 401 錯誤頁。
   不套側邊欄（AppShell 依路徑判斷）；Caddy 放行 /login 與 /_next/*，其餘頁面沒登入會被導到這裡。 */
function LoginForm() {
  const sp = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST", headers: { "content-type": "application/json" }, credentials: "same-origin",
        body: JSON.stringify({ username, password, next: sp.get("next") }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body?.detail || `登入失敗（${r.status}）`); return; }
      window.location.replace(body.next || "/dashboard");   // 整頁重新載入，讓各頁以登入後的 cookie 重新抓資料
    } catch {
      setErr("無法連線到伺服器，請稍後再試");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="w-full max-w-sm rounded-xl border border-orange-200 bg-white p-6 shadow-sm">
      <div className="mb-5">
        <div className="text-lg font-semibold text-[#3b2314]">土地徵收補償市價查估</div>
        <div className="text-sm text-slate-500">估價案件審查輔助系統</div>
      </div>
      <label className="block text-sm text-slate-700 mb-1" htmlFor="username">帳號</label>
      <input id="username" autoComplete="username" autoFocus required value={username} onChange={(e) => setUsername(e.target.value)}
        className="w-full mb-3 rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-orange-300" />
      <label className="block text-sm text-slate-700 mb-1" htmlFor="password">密碼</label>
      <input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)}
        className="w-full mb-4 rounded-lg border border-slate-300 px-3 py-2 text-slate-900 focus:outline-none focus:ring-2 focus:ring-orange-300" />
      {err && <div role="alert" className="mb-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{err}</div>}
      <button type="submit" disabled={busy || !username || !password}
        className="w-full rounded-lg bg-[#ea580c] px-3 py-2 font-medium text-white hover:bg-[#c2410c] disabled:opacity-50">
        {busy ? "登入中…" : "登入"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-[#fff7ef] px-4">
      <Suspense fallback={null}><LoginForm /></Suspense>
    </main>
  );
}
