import Link from "next/link";

/* 首頁介紹頁（/）：全頁版面、不套側邊欄。案件總覽在 /dashboard。這裡是介紹頁骨架，內容待發展。 */
export default function Landing() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="px-8 py-4 flex items-center gap-4 border-b border-orange-200 bg-[#fff1e3] text-[#3b2314]">
        <div>
          <div className="font-semibold leading-tight">土地徵收補償市價查估</div>
          <div className="text-xs opacity-70">估價案件審查輔助系統</div>
        </div>
        <Link href="/dashboard" className="ml-auto h-9 px-4 inline-flex items-center rounded bg-[#ea580c] text-white text-sm hover:bg-[#c2410c]">進入系統 →</Link>
      </header>
      <main className="flex-1 flex items-center justify-center px-8 py-16">
        <div className="max-w-3xl text-center">
          <h1 className="text-3xl font-semibold leading-snug">AI 輔助不動產估價案件審查</h1>
          <p className="mt-4 text-slate-700">把土地徵收補償市價查估的「勘查表事實 → 優劣等級 → 修正率 → 加總 → 跨表抄填」自動化，並反向審查估價單位送來的書表：逐格比對、指出不符、引用依據。</p>
          <div className="mt-8 flex justify-center gap-3">
            <Link href="/dashboard" className="h-11 px-6 inline-flex items-center rounded-lg bg-[#ea580c] text-white font-semibold hover:bg-[#c2410c]">進入案件總覽 →</Link>
          </div>
        </div>
      </main>
      <footer className="px-8 py-3 border-t border-slate-200 text-[11px] text-slate-500">
        底圖與段籍圖 © 國土測繪中心；路網與設施 © OpenStreetMap contributors（ODbL）；法規與作業手冊：土地徵收補償市價查估辦法、土地徵收補償市價查估作業手冊。
      </footer>
    </div>
  );
}
