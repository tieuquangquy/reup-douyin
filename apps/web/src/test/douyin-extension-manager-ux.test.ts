import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(testDir, "..", "..", "..", "..");
const managerSource = readFileSync(
  join(repoRoot, "apps", "web", "src", "components", "douyin-extension-manager", "DouyinExtensionManagerPage.tsx"),
  "utf-8"
);
const navSource = readFileSync(join(repoRoot, "apps", "web", "src", "lib", "navigationConfig.ts"), "utf-8");
const enSource = readFileSync(join(repoRoot, "apps", "web", "src", "lib", "i18n", "en.json"), "utf-8");

assert.match(managerSource, /Manual backend test only/, "manager must badge the manual backend form as test-only");
assert.match(managerSource, /<details className=\"operator-panel advanced-panel\">/, "manual backend form must live in a collapsed advanced details section");
assert.match(managerSource, /Test detect from form/, "manual detect button must use form-test wording");
assert.match(managerSource, /Submit manual capture test/, "manual capture button must use form-test wording");
assert.doesNotMatch(managerSource, /<h2>Current page tools<\/h2>/, "manual backend form must not keep the primary-sounding Current page tools heading");
assert.doesNotMatch(
  managerSource,
  />\{working === \"detect\" \? \"Detecting\.\.\.\" : \"Detect current page\"\}<\/button>/,
  "web-manager manual detect button must not reuse popup active-tab label"
);
assert.doesNotMatch(
  managerSource,
  />\{working === \"capture\" \? \"Capturing\.\.\.\" : \"Capture current page\"\}<\/button>/,
  "web-manager manual capture button must not reuse popup active-tab label"
);

assert.match(managerSource, /Submitted/, "manager capture summary must show submitted backend item count");
assert.match(managerSource, /Staged items/, "manager capture summary must show staged backend item count");
assert.match(managerSource, /Failed/, "manager capture summary must show failed item count");
assert.match(managerSource, /Warnings/, "manager capture summary must show backend warning codes");
assert.match(managerSource, /Item-level diagnostics/, "manager must surface partial item diagnostics from backend");
assert.match(managerSource, /failure_summaries\.slice\(0, 5\)/, "manager must cap visible item-level diagnostics");
assert.match(managerSource, /captureResult\.stage/, "manager must show structured backend capture stage");
assert.match(managerSource, /captureResult\.diagnostics_id/, "manager must show backend diagnostics id");

assert.match(managerSource, /loginPathForSurface\("operator"\)/, "manager must route install to Operator Studio login portal");
assert.match(managerSource, /\/setup\/douyin-extension/, "manager must deep-link Setup after login");
assert.match(managerSource, /Open Extension Setup/, "manager must point operators to Studio Setup for install");
assert.doesNotMatch(managerSource, /Install & setup/, "manager must not keep a duplicate Install & setup panel");
assert.doesNotMatch(managerSource, /Download ZIP|EXTENSION_DIST_PATH|EXTENSION_BUILD_COMMAND/, "manager must not duplicate full install/download steps");
assert.doesNotMatch(managerSource, /function InstallSetupSection/, "manager must remove the full InstallSetupSection");
assert.doesNotMatch(managerSource, /Real capture via extension/, "manager must not keep the install-panel real-capture badge");

assert.match(navSource, /href: "\/setup\/douyin-extension"/, "Operator Studio must keep Extension Setup in nav");
assert.doesNotMatch(navSource, /label: "nav\.douyinExtensionManager"/, "Ops Console must not keep Extension Manager in sidebar");
assert.match(enSource, /"douyinExtensionSetupDesc": "Install and verify/, "Setup nav copy must remain install-first");

const managerRouteSource = readFileSync(
  join(repoRoot, "apps", "web", "src", "app", "ops", "extensions", "douyin", "page.tsx"),
  "utf-8"
);
assert.match(managerRouteSource, /redirect\(/, "legacy Manager URL must redirect");
assert.match(managerRouteSource, /loginPathForSurface\("operator"\)/, "legacy Manager URL must go through Operator login portal");
assert.match(managerRouteSource, /\/setup\/douyin-extension/, "legacy Manager URL must deep-link Extension Setup");

const apiSource = readFileSync(join(repoRoot, "apps", "web", "src", "lib", "api.ts"), "utf-8");
assert.match(apiSource, /payload\.detail\?\.message/, "web API helper must prefer backend structured error message");
assert.match(apiSource, /payload\.detail\.code/, "web API helper must include backend structured error code");
assert.match(apiSource, /payload\.detail\.stage/, "web API helper must include backend structured error stage");
assert.match(apiSource, /payload\.detail\.diagnostics_id/, "web API helper must include backend diagnostics id");

console.log("douyin-extension manager UX clarity tests passed");
