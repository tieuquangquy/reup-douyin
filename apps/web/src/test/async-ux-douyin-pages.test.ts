import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const accounts = readFileSync(resolve(webSrc, "components/douyin-accounts/DouyinAccountsPage.tsx"), "utf8");
const manager = readFileSync(resolve(webSrc, "components/douyin-extension-manager/DouyinExtensionManagerPage.tsx"), "utf8");

for (const [name, source] of [
  ["Douyin Accounts", accounts],
  ["Douyin Extension Manager", manager],
] as const) {
  assert.match(source, /AsyncContentBoundary/, `${name} must standardize initial and refresh read states`);
  assert.match(source, /useLatestRequest/, `${name} must ignore stale initial and refresh reads`);
  assert.match(source, /useAsyncAction/, `${name} must synchronously gate duplicate actions`);
  assert.match(source, /AsyncButton/, `${name} must expose accessible per-action pending feedback`);
  assert.match(source, /useNotice/, `${name} must announce terminal action outcomes`);
}

assert.match(accounts, /action\.run\(`account-\$\{account\.id\}:\$\{operation\}`/, "Account row actions must use per-account, per-operation gates");
assert.match(accounts, /action\.run\("browser-start"/, "Browser connect start must be synchronously gated");
assert.match(accounts, /action\.run\("health-sweep"/, "Health sweep must be synchronously gated");
assert.match(accounts, /pollBrowserConnect/, "Browser connect polling must remain");
assert.match(accounts, /activeConnectSessionIdRef/, "Polling must retain stale-session protection");
assert.match(accounts, /currentPageByAccount/, "Current-page capture and detection diagnostics must remain inline");
assert.match(accounts, /connectPrimaryMessage/, "Critical browser-connect diagnostics must remain inline");

assert.match(manager, /action\.run\("check-connection"/, "Extension connection check must be synchronously gated");
assert.match(manager, /action\.run\("detect"/, "Manual detect must be synchronously gated");
assert.match(manager, /action\.run\("capture"/, "Manual capture must be synchronously gated");
assert.match(manager, /captureResult\.stage/, "Capture stage progress must remain inline");
assert.match(manager, /failure_summaries\.slice\(0, 5\)/, "Item-level capture diagnostics must remain inline");
assert.match(manager, /history\?\.items/, "Capture history must remain visible");

console.log("Douyin pages async UX contract tests passed");
