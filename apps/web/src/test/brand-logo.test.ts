/**
 * Loop-R product mark — favicon, sidebar, auth brand.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const webRoot = resolve(webSrc, "..");

const svgPath = resolve(webRoot, "public/brand/logo-loop-r.svg");
const pngPath = resolve(webRoot, "public/brand/logo-loop-r.png");
const sidebar = readFileSync(resolve(webSrc, "components/app-shell/Sidebar.tsx"), "utf8");
const login = readFileSync(resolve(webSrc, "app/auth/login/page.tsx"), "utf8");
const opsLogin = readFileSync(resolve(webSrc, "app/auth/ops/login/page.tsx"), "utf8");
const metadata = readFileSync(resolve(webSrc, "lib/pageMetadata.ts"), "utf8");
const pkg = readFileSync(resolve(webRoot, "package.json"), "utf8");

assert.ok(existsSync(svgPath), "public/brand/logo-loop-r.svg must exist");
assert.ok(existsSync(pngPath), "public/brand/logo-loop-r.png must exist");
assert.match(readFileSync(svgPath, "utf8"), /#007a5a|#005f46/, "SVG mark must use brand green");
assert.match(sidebar, /\/brand\/logo-loop-r/, "Sidebar must render Loop-R mark");
assert.match(login, /\/brand\/logo-loop-r/, "Operator login must show Loop-R mark");
assert.match(opsLogin, /\/brand\/logo-loop-r/, "Ops login must show Loop-R mark");
assert.match(metadata, /logo-loop-r|icons:/, "Root metadata must expose logo icons");
assert.match(pkg, /brand-logo\.test\.ts/, "package.json must run brand-logo test");

console.log("brand-logo tests passed");
