import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const source = path.join(frontendRoot, "node_modules", "luckysheet", "dist");
const target = path.join(repoRoot, "static", "vendor", "luckysheet");

if (!fs.existsSync(source)) {
  console.error("Luckysheet dist not found. Run npm install in frontend/ first.");
  process.exit(1);
}

fs.rmSync(target, { recursive: true, force: true });
fs.cpSync(source, target, { recursive: true });
console.log(`Copied Luckysheet assets to ${target}`);
