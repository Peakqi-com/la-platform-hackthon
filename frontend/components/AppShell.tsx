"use client";
import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";
import CaseBar from "./CaseBar";
import StepBar from "./StepBar";

/* 應用程式外框：側邊欄＋步驟列＋案件列＋頁尾。根路徑 / 是首頁介紹頁，不套外框，全頁交給 app/page.tsx。 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  if (path === "/") return <>{children}</>;
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 min-w-0 px-6 py-5 max-w-[1400px]"><StepBar /><CaseBar />{children}
        <footer className="no-print mt-10 pt-3 border-t border-slate-200 text-[11px] text-slate-500">
          底圖與段籍圖 © 國土測繪中心；路網與設施 © OpenStreetMap contributors（ODbL）；使用分區、實價登錄、淹水潛勢、列管污染源、商圈、停車格、交流道、都市地價指數：政府資料開放授權條款第 1 版；
          法規與作業手冊：土地徵收補償市價查估辦法、土地徵收補償市價查估作業手冊。數字全部由規則引擎依法規確定性計算。
        </footer></main>
    </div>
  );
}
