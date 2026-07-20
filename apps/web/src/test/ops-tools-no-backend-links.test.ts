/**
 * Ops Tools — no browser entry points to backend Swagger/docs.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const page = readFileSync(resolve(webSrc, "components/ops-console/OpsToolsPage.tsx"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.doesNotMatch(page, /\/docs|apiDocsUrl|opsTools\.swagger/, "Ops Tools must not link to Swagger/docs");
assert.doesNotMatch(page, /127\.0\.0\.1:8000|auth\/ui/, "Ops Tools must not deep-link backend HTML UI");
assert.match(page, /opsTools\.localCommands|npm run doctor/, "Ops Tools must keep local command runbook");
assert.match(pkg, /ops-tools-no-backend-links\.test\.ts/, "package.json must run ops-tools-no-backend-links test");

console.log("ops-tools-no-backend-links tests passed");
