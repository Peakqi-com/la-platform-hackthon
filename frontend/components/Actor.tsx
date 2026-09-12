"use client";
import { useEffect, useState } from "react";
import { Actor, getActor, ROLE_LABEL, setActor } from "@/lib/api";

/* 身分（沒有登入的過渡做法）：姓名＋角色存在這台瀏覽器，隨每次操作送到後端寫進操作紀錄，並作意見書落款。不是案件資料。 */
export default function ActorBox() {
  const [a, setA] = useState<Actor>({ name: "", role: "" });
  useEffect(() => { setA(getActor()); }, []);
  const upd = (p: Partial<Actor>) => { const n = { ...a, ...p }; setA(n); setActor(n); };
  return (
    <div className="px-3 py-2 border-t border-orange-200 text-xs no-print">
      <div className="opacity-70 mb-1">操作身分（寫入操作紀錄與意見書落款）</div>
      <div className="flex gap-1">
        <input className="flex-1 min-w-0 rounded px-2 py-1 text-slate-900 bg-white border border-orange-200" placeholder="姓名" value={a.name} onChange={(e) => upd({ name: e.target.value })} />
        <select className="rounded px-1 py-1 text-slate-900 bg-white border border-orange-200" value={a.role} onChange={(e) => upd({ role: e.target.value })}>
          <option value="">角色</option>{Object.entries(ROLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
    </div>
  );
}
