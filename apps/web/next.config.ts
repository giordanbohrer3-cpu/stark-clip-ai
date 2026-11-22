import type { NextConfig } from "next";

const CLOUD = process.env.VERCEL === "1" || process.env.CLIPZOU_MODE === "cloud";

const nextConfig: NextConfig = {
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  distDir: process.env.NEXT_DIST_DIR || ".next", // teste local do modo nuvem em pasta separada
  env: { NEXT_PUBLIC_CLIPZOU_CLOUD: CLOUD ? "1" : "" }, // app online (Vercel) x app no PC
  poweredByHeader: false,
  // o proxy.ts faz o Next guardar o corpo da requisição (padrão 10 MB): sem isso, cada parte de 48 MB do
  // upload em partes chegava cortada ao motor ("parte incompleta") e vídeo grande não entrava
  experimental: { proxyClientMaxBodySize: "64mb" },
  async headers() {
    return [{
      source: "/sw.js",
      headers: [
        { key: "Content-Type", value: "application/javascript; charset=utf-8" },
        { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        { key: "Content-Security-Policy", value: "default-src 'self'; script-src 'self'" },
      ],
    }];
  },
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
