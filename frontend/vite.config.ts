import { defineConfig, lazyPlugins } from "vite-plus";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { lintConfig } from "./lint/config";

export default defineConfig({
  // vp lint、vp check 读取本文件时不需要构建插件，lazyPlugins 让插件只在 dev、build 时实例化。
  plugins: lazyPlugins(() => [react(), tailwindcss()]),
  lint: lintConfig,
  // vp fmt（Oxfmt）。行宽 120 与现有代码最接近；对象键的引号保持原样：后端测试按带引号的键名读取 i18n 文案
  // （如 tests/unit/test_frontend_task_type_i18n.py）。shadcn 原语保持上游格式，便于 shadcn add --diff 合并；
  // e2e 录制的接口替身由 e2e:record 用 JSON.stringify 生成，不另行格式化。
  fmt: {
    printWidth: 120,
    quoteProps: "preserve",
    sortPackageJson: false,
    ignorePatterns: ["src/components/ui/**", "e2e/fixtures/recorded/**"],
    // i18n 文案沿用各文件原有的引号：events.ts、assets.ts 用双引号，其余用单引号。
    // 后端测试按原样的键名读取这些文件（如 test_provider_models_api.py、test_project_state_projection.py）。
    overrides: [
      {
        files: ["src/i18n/**"],
        excludeFiles: ["src/i18n/*/events.ts", "src/i18n/*/assets.ts"],
        options: { singleQuote: true },
      },
    ],
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
    extensions: [".mjs", ".mts", ".ts", ".tsx", ".js", ".jsx", ".json"],
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:1241",
        changeOrigin: true,
        // 多人即时协作的 WebSocket（/api/v1/collab）
        ws: true,
      },
      "/mcp": {
        target: "http://127.0.0.1:1241",
        changeOrigin: true,
      },
      "/agent-installation-guide.md": {
        target: "http://127.0.0.1:1241",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
