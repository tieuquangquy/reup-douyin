import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "../src/app");

function reorderPageSource(source) {
  const lines = source.split(/\r?\n/);
  const importLines = [];
  const metadataLines = [];
  const bodyLines = [];

  for (const line of lines) {
    if (line.startsWith("import ")) {
      importLines.push(line);
      continue;
    }
    if (line.startsWith("export const metadata") || line.startsWith("export async function generateMetadata")) {
      metadataLines.push(line);
      continue;
    }
    if (metadataLines.length > 0 && line.trim() !== "" && !line.startsWith("export ")) {
      metadataLines.push(line);
      continue;
    }
    bodyLines.push(line);
  }

  const blocks = [importLines.join("\n"), metadataLines.join("\n"), bodyLines.join("\n")].filter(Boolean);
  return `${blocks.join("\n\n").trim()}\n`;
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name === "page.tsx") {
      const next = reorderPageSource(fs.readFileSync(full, "utf8"));
      fs.writeFileSync(full, next);
    }
  }
}

walk(appRoot);
console.log("reordered page imports");
