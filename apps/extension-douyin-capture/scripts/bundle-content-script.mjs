import { build } from "esbuild";
import { rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const rootDir = join(scriptDir, "..");
const distDir = join(rootDir, "dist");

const banner = `(()=>{`;
const footer = `})();`;

rmSync(join(distDir, "contentScript.js"), { force: true });

await build({
  entryPoints: [join(rootDir, "src", "contentScript.ts")],
  outfile: join(distDir, "contentScript.js"),
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["chrome114"],
  banner: { js: banner },
  footer: { js: footer },
  sourcemap: false,
  logLevel: "info"
});
