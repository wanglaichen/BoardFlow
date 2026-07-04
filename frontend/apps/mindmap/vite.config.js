import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createEditorViteConfig } from "../../vite.shared.js";

export default defineConfig({
  plugins: [react()],
  ...createEditorViteConfig("mindmap"),
});
