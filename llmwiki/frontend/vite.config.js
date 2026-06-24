import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把各后端服务代理到本地端口,避免 CORS。
// 生产构建:由 VITE_API_BASE_URL 决定 fetch 前缀(见 src/api.js);base 用于子路径部署。
//   构建示例: VITE_BASE=/llm-wiki-engine/ VITE_API_BASE_URL=https://api.example.com npm run build
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE || "/",
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
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.js"],
    include: ["src/**/*.{test,spec}.{js,jsx}"],
  },
});
