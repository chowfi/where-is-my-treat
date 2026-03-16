import { defineConfig } from "vite";
import { rcadePluginPyodide } from "@rcade/vite-plugins";

export default defineConfig({
    publicDir: "public",
    optimizeDeps: { exclude: ["pyodide"] },
    plugins: [rcadePluginPyodide()],
    build: {
        assetsInlineLimit: 0,
    },
});
