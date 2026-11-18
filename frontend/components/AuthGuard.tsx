"use client";
import { useEffect, useState } from "react";

/* 登入逾期時的處理：攔截 fetch，站內 /api/* 回 401 且標示 login（Caddy forward_auth → 後端 /api/auth/check）就導到登入頁，
   不留在畫面上顯示一堆「讀取失敗」。沒有設定登入（本機）時後端不會回這種 401，等於不作用。 */
let installed = false;

export default function AuthGuard() {
  useEffect(() => {
    if (installed || typeof window === "undefined") return;
    installed = true;
    const orig = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const res = await orig(input, init);
      if (res.status === 401 && window.location.pathname !== "/login") {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        const path = new URL(url, window.location.href);
        if (path.origin === window.location.origin && path.pathname.startsWith("/api/") && !path.pathname.startsWith("/api/auth/")) {
          const body = await res.clone().json().catch(() => null);
          if (body?.login) {
            window.location.assign("/login?next=" + encodeURIComponent(window.location.pathname + window.location.search));
          }
        }
      }
      return res;
    };
  }, []);
  return null;
}

/* 側邊欄：登入中的帳號與登出。後端沒有設定登入（/api/auth/me enabled=false）時不顯示。 */
export function LogoutBox() {
  const [me, setMe] = useState<{ enabled: boolean; user: string | null } | null>(null);
  useEffect(() => {
    fetch("/api/auth/me").then((r) => (r.ok ? r.json() : null)).then(setMe).catch(() => setMe(null));
  }, []);
  if (!me?.enabled || !me.user) return null;
  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
    window.location.assign("/login");
  };
  return (
    <div className="px-3 py-2 border-t border-orange-200 text-xs no-print flex items-center gap-2">
      <span className="opacity-70 truncate" title={`登入帳號：${me.user}`}>登入帳號：{me.user}</span>
      <button type="button" onClick={logout} className="ml-auto shrink-0 underline hover:text-[#c2410c]">登出</button>
    </div>
  );
}
