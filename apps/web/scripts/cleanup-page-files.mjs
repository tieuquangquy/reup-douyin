import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "../src/app");

function cleanup(source) {
  let next = source.replace(/\r\n/g, "\n");
  next = next.replace(/\n\}\n\}\s*$/g, "\n}\n");
  next = next.replace(/export default (async )?function ([^(]+)\(([^)]*)\) \{\nreturn /g, "export default $1function $2($3) {\n  return ");
  next = next.replace(/export default async function Page\(\{ params \}: \{ params: Promise<\{ packageId: string \}> \}\) \{\nconst /g,
    "export default async function Page({ params }: { params: Promise<{ packageId: string }> }) {\n  const ");
  return next.endsWith("\n") ? next : `${next}\n`;
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name === "page.tsx") {
      const original = fs.readFileSync(full, "utf8");
      const repaired = cleanup(original);
      if (repaired !== original) fs.writeFileSync(full, repaired);
    }
  }
}

walk(appRoot);
console.log("cleaned page files");
