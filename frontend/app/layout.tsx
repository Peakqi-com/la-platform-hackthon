import type { Metadata } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { CaseProvider } from "@/components/CaseContext";
import Sidebar from "@/components/Sidebar";
import CaseBar from "@/components/CaseBar";
import StepBar from "@/components/StepBar";

export const metadata: Metadata = {
  title: "土地徵收補償市價查估 估價案件審查輔助系統",
  description: "依土地徵收補償市價查估辦法與作業手冊，核算地價區段勘查表、影響地價區域因素分析明細表、比較法調查估價表，並比對送審書表",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className="h-full antialiased">
      <body className="min-h-full">
        <CaseProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 min-w-0 px-6 py-5 max-w-[1400px]"><StepBar /><CaseBar />{children}
              <footer className="no-print mt-10 pt-3 border-t border-slate-200 text-[11px] text-slate-500">
                底圖與段籍圖 © 國土測繪中心；路網與設施 © OpenStreetMap contributors（ODbL）；使用分區、實價登錄、淹水潛勢、列管污染源、商圈、停車格、交流道、都市地價指數：政府資料開放授權條款第 1 版；
                法規與作業手冊：土地徵收補償市價查估辦法、土地徵收補償市價查估作業手冊。數字全部由規則引擎依法規確定性計算。
              </footer></main>
          </div>
        </CaseProvider>
      </body>
    </html>
  );
}
