import path from "path";
import { fileURLToPath } from "url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(frontendRoot, "..");

export function createEditorViteConfig(appName) {
  const outDir = path.join(repoRoot, "static", "apps", appName);

  return {
    base: `/static/apps/${appName}/`,
    build: {
      outDir,
      emptyOutDir: true,
      rollupOptions: {
        output: {
          entryFileNames: "app.js",
          chunkFileNames: "chunks/[name]-[hash].js",
          assetFileNames: (assetInfo) => {
            if (assetInfo.name && assetInfo.name.endsWith(".css")) {
              return "app.css";
            }
            return "assets/[name]-[hash][extname]";
          },
        },
      },
    },
  };
}
