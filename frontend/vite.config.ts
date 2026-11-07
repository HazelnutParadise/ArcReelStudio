import { defineConfig, lazyPlugins } from "vite-plus";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";
import { lintConfig } from "./lint/config";

export default defineConfig({
    // vp lint、vp check 读取本文件时不需要构建插件，lazyPlugins 让插件只在 dev、build 时实例化。
    plugins: lazyPlugins(() => [react(), tailwindcss()]),
    lint: lintConfig,
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
