import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "../src/app");

function repairPageSource(source) {
  if (!source.includes("export const metadata = pageMetadata.")) return source;

  const metadataMatch = source.match(/export const metadata = (pageMetadata\.[A-Za-z0-9_]+);/);
  if (!metadataMatch) return source;

  const defaultExportMatch = source.match(/export default (async )?function ([A-Za-z0-9_]+)\(([^)]*)\)\s*\{?/);
  if (!defaultExportMatch) return source;

  const asyncKeyword = defaultExportMatch[1] ?? "";
  const functionName = defaultExportMatch[2];
  const params = defaultExportMatch[3];

  const metadataIndex = source.indexOf(metadataMatch[0]);
  const defaultIndex = source.indexOf(`export default ${asyncKeyword}function ${functionName}`);
  if (defaultIndex <= metadataIndex) return source;

  const orphanedBody = source.slice(metadataIndex + metadataMatch[0].length, defaultIndex).trim();
  if (!orphanedBody) return source;

  const imports = source
    .split(/\r?\n/)
    .filter((line) => line.startsWith("import "))
    .join("\n");

  return `${imports}

export const metadata = ${metadataMatch[1]};

export default ${asyncKeyword}function ${functionName}(${params}) {
${orphanedBody}
}
`;
}

function repairGenerateMetadataSource(source) {
  if (!source.includes("export async function generateMetadata")) return source;

  const defaultExportMatch = source.match(/export default (async )?function ([A-Za-z0-9_]+)\(([^)]*)\)\s*\{?/);
  if (!defaultExportMatch) return source;

  const asyncKeyword = defaultExportMatch[1] ?? "";
  const functionName = defaultExportMatch[2];
  const params = defaultExportMatch[3];
  const defaultIndex = source.indexOf(`export default ${asyncKeyword}function ${functionName}`);
  const orphanedBody = source.slice(0, defaultIndex).split(/\}\n/).pop()?.trim();
  
  // If generateMetadata block is intact, only fix orphaned default body
  const generateEnd = source.indexOf("\n}", source.indexOf("export async function generateMetadata"));
  if (generateEnd < 0) return source;

  const beforeDefault = source.slice(0, defaultIndex);
  const afterDefaultHeader = source.slice(defaultIndex);
  const orphanedBetween = beforeDefault.slice(generateEnd + 2).trim();
  if (!orphanedBetween || orphanedBetween.startsWith("export default")) {
    return source;
  }

  const header = beforeDefault.slice(0, generateEnd + 2).trimEnd();
  return `${header}

export default ${asyncKeyword}function ${functionName}(${params}) {
${orphanedBetween}
}
`;
}

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name === "page.tsx") {
      const original = fs.readFileSync(full, "utf8");
      const repaired = repairGenerateMetadataSource(repairPageSource(original));
      if (repaired !== original) fs.writeFileSync(full, repaired);
    }
  }
}

walk(appRoot);
console.log("repaired page files");
