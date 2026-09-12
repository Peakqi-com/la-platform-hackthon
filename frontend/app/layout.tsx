import type { Metadata } from "next";
import "leaflet/dist/leaflet.css";
import "./globals.css";
import { CaseProvider } from "@/components/CaseContext";
import AppShell from "@/components/AppShell";

export const metadata: Metadata = {
  title: "土地徵收補償市價查估 估價案件審查輔助系統",
  description: "依土地徵收補償市價查估辦法與作業手冊，核算地價區段勘查表、影響地價區域因素分析明細表、比較法調查估價表，並比對送審書表",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className="h-full antialiased">
      <body className="min-h-full">
        <CaseProvider><AppShell>{children}</AppShell></CaseProvider>
      </body>
    </html>
  );
}
