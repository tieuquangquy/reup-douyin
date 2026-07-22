import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const pages = [
  "components/operator-home/OperatorHomePage.tsx",
  "components/operator-routes/PipelineDashboardPage.tsx",
  "components/optimization/OptimizationPage.tsx",
  "components/douyin-extension-setup/DouyinExtensionSetupPage.tsx",
  "components/ops-console/OpsHealthPage.tsx",
  "components/ops-console/OpsAssetsPage.tsx",
  "components/ops-console/OpsAccountsPage.tsx",
  "components/ops-console/OpsRiskPage.tsx",
  "components/ops-console/OpsPublishAttemptsPage.tsx",
  "components/operator-routes/ExportPackagesIndexPage.tsx",
  "components/operator-routes/PublishHandoffsIndexPage.tsx",
  "components/operator-routes/PublishDraftsIndexPage.tsx",
] as const;

for (const relativePath of pages) {
  const source = readFileSync(resolve(webSrc, relativePath), "utf8");
  assert.match(source, /useLatestRequest/, `${relativePath} must guard read freshness`);
  assert.match(source, /AsyncContentBoundary/, `${relativePath} must use the shared async content boundary`);
  assert.match(source, /skeletonVariant="(gallery|list|detail|form)"/, `${relativePath} must choose a skeleton shape`);
  assert.match(source, /refreshing=\{[^}]+\}/, `${relativePath} must preserve content during background refresh`);
  assert.match(source, /useNotice/, `${relativePath} must report refresh failures without replacing content`);
}

const optimization = readFileSync(resolve(webSrc, "components/optimization/OptimizationPage.tsx"), "utf8");
assert.match(optimization, /AsyncButton/, "Optimization schedule hint reads must expose button pending state");

console.log("async UX group 2 tests passed");
