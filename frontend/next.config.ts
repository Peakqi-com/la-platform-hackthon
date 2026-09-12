import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // /api 代理逾時：Next 預設 30 秒，「依地號產生」（線上地籍、門牌定位、實價登錄）可能超過 30 秒會被切斷回 500，改為 300 秒；正式環境 Caddy 直接把 /api 轉後端，不經此處
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    // 前端不直接碰後端網址：/api/* 由 Next 代理到 BACKEND_URL（本機 dev 與 compose 皆同；Caddy 上線時也是同樣路徑）
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
