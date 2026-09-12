import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // /api 代理逾時：Next 預設 30 秒，「依地號產生」（線上地籍、門牌定位、實價登錄）可能超過 30 秒會被切斷回 500，改為 300 秒；正式環境 Caddy 直接把 /api 轉後端，不經此處
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return {
      // beforeFiles 先於檔案系統路由：首頁 / 交給 public/city-wind 的靜態頁（「城市起風」Three.js 站）。
      // 那份 CSS 用大量裸標籤選擇器，和 globals.css 的 Tailwind preflight 會互相覆蓋，
      // 所以不併進 App Router，改走靜態直出，行為與原始碼一模一樣。
      // app/page.tsx 留著當退路：這條 rewrite 若失效，/ 仍會顯示舊的介紹頁而不是 404。
      beforeFiles: [{ source: "/", destination: "/city-wind/index.html" }],
      // 前端不直接碰後端網址：/api/* 由 Next 代理到 BACKEND_URL（本機 dev 與 compose 皆同；Caddy 上線時也是同樣路徑）
      afterFiles: [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }],
      fallback: [],
    };
  },
};

export default nextConfig;
