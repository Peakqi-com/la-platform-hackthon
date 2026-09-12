import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    // 前端不直接碰後端網址：/api/* 由 Next 代理到 BACKEND_URL（本機 dev 與 compose 皆同；Caddy 上線時也是同樣路徑）
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
