import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const pages = [
  "components/ops-console/OpsUsersPage.tsx",
  "components/publish-control/PublishControlPlanePage.tsx",
  "components/publish-health/PublishHealthDashboardPage.tsx",
  "components/ops-console/OpsReconciliationPage.tsx",
  "components/operator-routes/ExportPackageByIdPage.tsx",
];

for (const pagePath of pages) {
  const source = readFileSync(resolve(webSrc, pagePath), "utf8");
  assert.match(source, /useAsyncAction/, `${pagePath} must synchronously gate mutations`);
  assert.match(source, /useNotice/, `${pagePath} must publish global success/error notices`);
  assert.match(source, /AsyncContentBoundary/, `${pagePath} must standardize initial and refresh read states`);
  assert.match(source, /useLatestRequest/, `${pagePath} must prevent stale read commits`);
  assert.match(source, /inline-error/, `${pagePath} must retain important inline errors`);
}

const users = readFileSync(resolve(webSrc, pages[0]), "utf8");
assert.match(users, /<AsyncButton[^>]*pending=/, "Users mutations must expose accessible pending buttons");
assert.match(users, /isPending\(`member-\$\{member\.operatorId\}`\)/, "Member status changes must have a per-member gate");

const control = readFileSync(resolve(webSrc, pages[1]), "utf8");
assert.match(control, /<AsyncButton[^>]*pending=/, "Publish Control mutations must expose accessible pending buttons");
assert.match(control, /action\.run\(`assign-\$\{item\.publish_draft_id\}`/, "Draft assignment must be synchronously gated");

const health = readFileSync(resolve(webSrc, pages[2]), "utf8");
assert.match(health, /action\.run\("feedback"/, "Feedback submission must be synchronously gated");

const reconciliation = readFileSync(resolve(webSrc, pages[3]), "utf8");
assert.match(reconciliation, /action\.run\(`refresh-\$\{attempt\.id\}`/, "Reconciliation refresh must be synchronously gated per attempt");

const exportDetail = readFileSync(resolve(webSrc, pages[4]), "utf8");
assert.match(exportDetail, /action\.run\("create-handoff"/, "Handoff creation must be synchronously gated");
assert.match(exportDetail, /createdHandoff/, "Created handoff inline follow-up must remain visible");

console.log("async UX group 3 tests passed");
