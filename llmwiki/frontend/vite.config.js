import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把各后端服务代理到本地端口,避免 CORS。生产由网关/Ingress 统一路由。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/query": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api\/query/, "") },
      "/api/admin": { target: "http://localhost:8002", rewrite: (p) => p.replace(/^\/api\/admin/, "") },
      "/api/ingest": { target: "http://localhost:8003", rewrite: (p) => p.replace(/^\/api\/ingest/, "") },
      "/api/gen": { target: "http://localhost:8004", rewrite: (p) => p.replace(/^\/api\/gen/, "") },
      "/api/evidence": { target: "http://localhost:8001", rewrite: (p) => p.replace(/^\/api\/evidence/, "") },
    },
  },
});
