import { mkdirSync, copyFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const root = process.cwd();
const publicDir = join(root, "public");
const distDir = join(root, "dist");
mkdirSync(distDir, { recursive: true });
for (const entry of readdirSync(publicDir)) {
  copyFileSync(join(publicDir, entry), join(distDir, entry));
}
