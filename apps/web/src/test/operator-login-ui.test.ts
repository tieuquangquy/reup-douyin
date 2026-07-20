/**
 * Operator Studio login — brand+form stage, no Ops Console CTA.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const webRoot = resolve(webSrc, "..");

const login = readFileSync(resolve(webSrc, "app/auth/login/page.tsx"), "utf8");
const opsLogin = readFileSync(resolve(webSrc, "app/auth/ops/login/page.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8")) as {
  auth: Record<string, string>;
};
const vi = JSON.parse(readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8")) as {
  auth: Record<string, string>;
};
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(login, /auth-stage/, "Operator login must use auth-stage shell");
assert.match(login, /auth-brand/, "Operator login must render brand panel");
assert.match(login, /auth-brand__visual|auth-brand__art/, "Operator login brand must include a product visual");
assert.match(login, /\/auth\/operator-studio.*\.(png|webp|svg)/, "Brand visual must load a static auth asset");
assert.ok(
  existsSync(resolve(webRoot, "public/auth/operator-studio-pipeline.png")),
  "public/auth/operator-studio-pipeline.png must exist"
);
assert.match(login, /auth-card/, "Operator login must keep form card");
assert.match(login, /auth\.loginBrand|auth\.secureAccess/, "Brand panel must use Operator Studio brand key");
assert.match(login, /auth\.loginTitle/, "Form must use short login title");
assert.match(login, /\/auth\/register/, "Operator login must keep register link");
assert.doesNotMatch(login, /\/auth\/ops\/login/, "Operator login must not deep-link Ops Console login");
assert.doesNotMatch(login, /needOpsConsole|opsSignInLink/, "Operator login must not reference Ops Console CTA keys");

assert.match(opsLogin, /auth-stage/, "Ops login must share auth-stage shell");
assert.match(opsLogin, /auth-brand/, "Ops login must render brand panel");
assert.match(opsLogin, /auth-brand__visual|auth-brand__art/, "Ops login brand must include a product visual");
assert.match(opsLogin, /\/auth\/ops-console.*\.(png|webp|svg)/, "Ops brand visual must load a static auth asset");
assert.ok(
  existsSync(resolve(webRoot, "public/auth/ops-console-monitor.png")),
  "public/auth/ops-console-monitor.png must exist"
);
assert.match(opsLogin, /\/auth\/login/, "Ops login must keep Operator Studio link");
assert.match(opsLogin, /AuthErrorBanner/, "Ops login must use polished auth error banner");
assert.match(login, /AuthErrorBanner/, "Operator login must use polished auth error banner");

assert.match(css, /\.auth-stage/, "CSS must define auth-stage");
assert.match(css, /\.auth-brand__visual|\.auth-brand__art/, "CSS must style the brand product visual");
assert.match(css, /\.auth-brand/, "CSS must define auth-brand");
assert.match(css, /@keyframes\s+auth-|animation:.*auth-/, "Auth stage must include light entrance motion");
assert.match(css, /\.auth-error__title/, "CSS must style auth error title");
assert.match(css, /\.auth-error__icon/, "CSS must style auth error icon");
assert.ok(en.auth.errorServerUnavailable, "en must humanize server login failures");
assert.ok(vi.auth.errorServerUnavailable, "vi must humanize server login failures");
assert.doesNotMatch(en.auth.errorServerUnavailable, /\b500\b/, "en server hint must not dump bare 500");

assert.ok(en.auth.loginCopy, "en loginCopy must exist");
assert.ok(vi.auth.loginCopy, "vi loginCopy must exist");
assert.doesNotMatch(en.auth.loginCopy, /Ops Console/i, "en loginCopy must not mention Ops Console");
assert.doesNotMatch(vi.auth.loginCopy, /Ops Console/i, "vi loginCopy must not mention Ops Console");
assert.match(en.auth.loginTitle, /^Sign in$/i, "en loginTitle must be short Sign in (brand lives in brand panel)");
assert.ok(en.auth.loginBrand || en.auth.secureAccess, "en must expose Operator Studio brand string");
assert.ok(en.auth.loginWorkflow || en.auth.loginCopy.includes("Collect"), "en must expose workflow copy");

assert.match(pkg, /operator-login-ui\.test\.ts/, "package.json must run operator-login-ui test");

console.log("operator-login-ui tests passed");
