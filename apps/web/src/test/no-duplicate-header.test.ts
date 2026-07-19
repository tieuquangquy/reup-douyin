/**
 * Topbar (AppShell) is the only page chrome. OpsPageHeader / nested PageShell headers duplicate it.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = join(testDir, "..");
const opsConsoleDir = join(webSrc, "components", "ops-console");
const opsAppDir = join(webSrc, "app", "ops");

const OPS_PAGES_WITH_REFRESH = [
  "OpsJobsPage.tsx",
  "OpsHealthPage.tsx",
  "OpsHomePage.tsx",
  "OpsAssetsPage.tsx",
  "OpsAccountsPage.tsx",
  "OpsPublishAttemptsPage.tsx",
  "OpsReconciliationPage.tsx",
  "OpsRiskPage.tsx",
  "OpsRoutingRulesPage.tsx",
  "OpsUsersPage.tsx"
];

const OPS_PAGES_NO_HEADER = [
  ...OPS_PAGES_WITH_REFRESH,
  "OpsToolsPage.tsx"
];

for (const fileName of OPS_PAGES_NO_HEADER) {
  const source = readFileSync(join(opsConsoleDir, fileName), "utf8");
  assert.doesNotMatch(source, /OpsPageHeader/, `${fileName} must not duplicate Topbar with OpsPageHeader`);
  assert.match(source, /OpsConsoleShell/, `${fileName} must own OpsConsoleShell so title/actions live in Topbar`);
}

for (const fileName of OPS_PAGES_WITH_REFRESH) {
  const source = readFileSync(join(opsConsoleDir, fileName), "utf8");
  assert.match(source, /TopbarRefreshButton/, `${fileName} must put Refresh in the Topbar`);
}

const routeShellOwners: Array<{ route: string; page: string }> = [
  { route: "jobs/page.tsx", page: "OpsJobsPage" },
  { route: "health/page.tsx", page: "OpsHealthPage" },
  { route: "page.tsx", page: "OpsHomePage" },
  { route: "assets/page.tsx", page: "OpsAssetsPage" },
  { route: "accounts/page.tsx", page: "OpsAccountsPage" },
  { route: "publish-attempts/page.tsx", page: "OpsPublishAttemptsPage" },
  { route: "reconciliation/page.tsx", page: "OpsReconciliationPage" },
  { route: "risk/page.tsx", page: "OpsRiskPage" },
  { route: "routing-rules/page.tsx", page: "OpsRoutingRulesPage" },
  { route: "tools/page.tsx", page: "OpsToolsPage" },
  { route: "users/page.tsx", page: "OpsUsersPage" }
];

for (const { route, page } of routeShellOwners) {
  const routeSource = readFileSync(join(opsAppDir, route), "utf8");
  assert.match(routeSource, new RegExp(page), `Route ${route} must render ${page}`);
  assert.doesNotMatch(routeSource, /OpsConsoleShell/, `Route ${route} must not double-wrap OpsConsoleShell (${page} owns it)`);
}

const operatorPagesWithStudioShell = [
  "components/operator-routes/PipelineDashboardPage.tsx",
  "components/capture-inbox/CaptureInboxPage.tsx",
  "components/operator-routes/PublishDraftsIndexPage.tsx",
  "components/operator-routes/PublishHandoffsIndexPage.tsx",
  "components/operator-routes/PublishHandoffByIdPage.tsx",
  "components/operator-routes/ExportPackagesIndexPage.tsx",
  "components/operator-routes/ExportPackageByIdPage.tsx",
  "components/intake/IntakePage.tsx",
  "components/douyin-extension-setup/DouyinExtensionSetupPage.tsx",
  "components/douyin-extension-manager/DouyinExtensionManagerPage.tsx",
  "components/operator-routes/OperatorPlaceholderPage.tsx"
];

for (const relative of operatorPagesWithStudioShell) {
  const source = readFileSync(join(webSrc, relative), "utf8");
  assert.doesNotMatch(
    source,
    /PageShell/,
    `${relative} must not nest PageShell under OperatorStudioShell (duplicate header)`
  );
}

// Sanity: ops-console still exports OpsPageHeader for legacy callers outside this set, but no Ops*Page uses it.
const sharedSource = readFileSync(join(opsConsoleDir, "OpsShared.tsx"), "utf8");
assert.match(sharedSource, /export function OpsPageHeader/, "OpsPageHeader may remain exported for gradual migration");

const pageFiles = readdirSync(opsConsoleDir).filter((name) => /^Ops.+Page\.tsx$/.test(name));
for (const fileName of pageFiles) {
  if (fileName === "OpsCaptionAiPage.tsx" || fileName === "OpsTranslationAiPage.tsx" || fileName === "OpsTtsAiPage.tsx") {
    // Settings pages are wrapped by route shell; still must not use OpsPageHeader.
    const source = readFileSync(join(opsConsoleDir, fileName), "utf8");
    assert.doesNotMatch(source, /OpsPageHeader/, `${fileName} must not use OpsPageHeader`);
    continue;
  }
}

console.log(`no-duplicate-header tests passed (${OPS_PAGES_NO_HEADER.length} ops pages, ${operatorPagesWithStudioShell.length} operator pages)`);
