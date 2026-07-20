/**
 * Auth boot screen + Ops page loading skeleton (pre-load UX).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const auth = readFileSync(resolve(webSrc, "lib/auth.tsx"), "utf8");
const shared = readFileSync(resolve(webSrc, "components/ops-console/OpsShared.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(auth, /auth-boot/, "AuthProvider must render branded auth-boot screen while booting");
assert.doesNotMatch(auth, /className=\"auth-loading\"/, "AuthProvider must leave bare auth-loading full-page text");
assert.match(auth, /role=\"status\"|aria-live/, "Auth boot must expose polite status for assistive tech");

assert.match(shared, /state-panel is-loading|is-loading/, "OpsState loading must use state-panel is-loading skeleton");
assert.match(shared, /state-panel__spinner|state-panel__skeleton/, "OpsState loading must show spinner/skeleton chrome");
assert.match(shared, /!retry|retry \?/, "OpsState must treat missing retry as loading (not error) path");

assert.match(css, /\.auth-boot/, "CSS must define auth-boot screen");
assert.match(css, /\.auth-boot__spinner|\.auth-boot__card/, "CSS must define auth-boot card/spinner");
assert.match(css, /\.state-panel\.is-loading/, "CSS must define Ops loading state panel");
assert.match(css, /\.state-panel__spinner|\.state-panel__skeleton/, "CSS must define Ops loading skeleton parts");

assert.match(pkg, /auth-boot-loading\.test\.ts/, "package.json must run auth-boot-loading test");

console.log("auth-boot-loading tests passed");
