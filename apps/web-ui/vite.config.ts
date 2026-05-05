import tailwindcss from "@tailwindcss/vite";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vitest/config";

const apiProxyTarget = process.env.NBA_INSIGHT_API_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [tailwindcss(), sveltekit()],
  server: {
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: true,
        secure: false
      }
    }
  },
  test: {
    include: ["src/**/*.test.ts"]
  }
});
