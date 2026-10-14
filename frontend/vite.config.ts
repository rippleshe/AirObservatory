import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

/* 默认连本机后端；把 frontend/.env.local 里的 VITE_API_PROXY_TARGET 指向共享后端
   （云端或组长的机器）即可让所有人读同一套数据，本地开发行为不变。 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8110";

  return {
    plugins: [vue()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": apiTarget,
      },
    },
    build: {
      chunkSizeWarningLimit: 650,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes("node_modules/echarts") || id.includes("node_modules/zrender")) {
              return "echarts";
            }
          },
        },
      },
    },
  };
});
