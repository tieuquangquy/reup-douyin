/**
 * Ops Reconciliation — uncertain publish attempts (filter/sheet/refresh mutate, scoped UI).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsReconciliationPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-recon-page/, "Reconciliation page must use scoped ops-recon-page shell");
assert.match(page, /ops-recon-kpis/, "Reconciliation page must render KPI band");
assert.match(page, /ops-recon-kpi/, "Reconciliation page must use scoped KPI cards");
assert.match(page, /ops-recon-freshness|opsReconciliation\.loadedAt/, "Reconciliation page must surface load freshness");
assert.match(page, /fetchPublishAttemptList/, "Reconciliation must keep attempt-list authority");
assert.match(page, /NEEDS_RECONCILIATION/, "Reconciliation must load NEEDS_RECONCILIATION");
assert.match(page, /RECONCILING/, "Reconciliation must load RECONCILING");
assert.match(page, /refreshPublishAttemptStatus/, "Reconciliation must keep per-row refresh mutate");
assert.match(page, /savingId/, "Reconciliation must track busy refresh id");
assert.match(page, /ops-recon-filters|statusFilter/, "Reconciliation must offer status filters");
assert.match(page, /useState<StatusFilter>\("NEEDS"\)|useState\("NEEDS"\)/, "Filter must default to Needs");
assert.match(page, /ops-recon-sheet|ops-recon-row/, "Reconciliation must render attempts sheet");
assert.match(page, /ops-recon-chip/, "Reconciliation must use soft status chips");
assert.match(page, /ops-recon-row__action|refreshStatus/, "Reconciliation must expose compact refresh action");
assert.match(page, /ops-recon-attention/, "Reconciliation must surface unknown-external attention");
assert.match(page, /attentionAttempts\.length > 0/, "Attention side must only render when unknown externals exist");
assert.match(page, /ops-recon-pager|RECON_PAGE_SIZE/, "Reconciliation sheet must paginate");
assert.match(page, /\.slice\(/, "Paginated rows must slice the filtered list");
assert.match(page, /setPage\(1\)/, "Changing status filter must reset to first page");
assert.match(page, /ops-recon-footnote|notTrustedUntilRefresh/, "Reconciliation must footnote trust limits");
assert.doesNotMatch(page, /health-overview-grid/, "Reconciliation must leave shared health-overview-grid");
assert.doesNotMatch(page, /health-table/, "Reconciliation must not use health-table");
assert.doesNotMatch(page, /<OpsMetricCard/, "Reconciliation must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Reconciliation must not use shared OpsPanel");
assert.doesNotMatch(page, /<StatusBadge/, "Reconciliation must not use StatusBadge");

assert.match(css, /\.ops-recon-page/, "CSS must define Reconciliation page shell");
assert.match(css, /\.ops-recon-kpis/, "CSS must define Reconciliation KPI grid");
assert.match(css, /\.ops-recon-row|\.ops-recon-sheet/, "CSS must define attempts sheet");
assert.match(css, /\.ops-recon-chip\s*\{[^}]*font-weight:\s*400/, "Recon chips must not use bold weight");
assert.match(css, /\.ops-recon-attention/, "CSS must define attention list");
assert.match(css, /\.ops-recon-footnote/, "CSS must define compact footnote");
assert.match(css, /\.ops-recon-main\.has-attention/, "CSS must support split only when attention is present");
assert.match(css, /\.ops-recon-pager/, "CSS must define recon pager");

assert.match(en, /"loadedAt"|"filterAll"|"notTrustedUntilRefresh"|"internal"/, "en.json must define Reconciliation redesign labels");
assert.match(en, /"pagePrev"|"pageNext"|"pageRange"/, "en.json must define recon pager labels");
assert.match(vi, /"loadedAt"|"filterAll"|"notTrustedUntilRefresh"|"internal"/, "vi.json must define Reconciliation redesign labels");
assert.match(vi, /"pagePrev"|"pageNext"|"pageRange"/, "vi.json must define recon pager labels");

assert.match(pkg, /ops-reconciliation-ui\.test\.ts/, "package.json must run ops-reconciliation-ui test");

console.log("ops-reconciliation-ui tests passed");
