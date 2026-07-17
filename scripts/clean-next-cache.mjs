import { rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const generatedPaths = [
  "apps/web/.next",
  ".next",
  "node_modules/.cache",
  ".turbo"
];

for (const relativePath of generatedPaths) {
  const absolutePath = path.join(root, relativePath);
  const exists = await stat(absolutePath).then(() => true, () => false);
  if (!exists) {
    console.log(`Skipped ${relativePath}`);
    continue;
  }
  await rm(absolutePath, { recursive: true, force: true });
  console.log(`Deleted ${relativePath}`);
}
