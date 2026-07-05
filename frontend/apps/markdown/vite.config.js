import path from "path";
import { fileURLToPath } from "url";
import { defineConfig } from "vite";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(appRoot, "../../..");

export default defineConfig({
    build: {
        lib: {
            entry: path.join(appRoot, "src/main.js"),
            name: "CardMarkdownEditor",
            formats: ["iife"],
            fileName: () => "card-markdown-editor.js",
        },
        outDir: path.join(repoRoot, "static/js"),
        emptyOutDir: false,
        cssCodeSplit: false,
        rollupOptions: {
            output: {
                assetFileNames: "card-markdown-editor.css",
                extend: true,
            },
        },
    },
});
