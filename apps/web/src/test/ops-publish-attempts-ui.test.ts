/**
 * Ops Publish Attempts — latest connector attempts (scoped KPI/sheet, read-only).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsPublishAttemptsPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-attempts-page/, "Attempts page must use scoped ops-attempts-page shell");
assert.match(page, /ops-attempts-kpis/, "Attempts page must render KPI band");
assert.match(page, /ops-attempts-kpi/, "Attempts page must use scoped KPI cards");
assert.match(page, /ops-attempts-freshness|opsPublishAttempts\.loadedAt/, "Attempts page must surface load freshness");
assert.match(page, /fetchPublishAttemptList/, "Attempts must keep attempt-list authority");
assert.match(page, /ops-attempts-filters|statusFilter/, "Attempts must offer status filters");
assert.match(page, /ops-attempts-sheet|ops-attempts-row/, "Attempts must render attempts sheet");
assert.match(page, /ops-attempts-chip/, "Attempts must use soft status chips");
assert.match(page, /ops-attempts-attention/, "Attempts must surface failed/reconcile attention");
assert.match(page, /attentionAttempts\.length > 0/, "Attention side must only render when hot attempts exist");
assert.match(page, /ops-attempts-toolbar|ops-attempts-actions/, "Triage links must sit in toolbar");
assert.match(page, /\/ops\/reconciliation/, "Attempts must deep-link reconciliation");
assert.match(page, /\/ops\/publish-health/, "Attempts must deep-link publish health");
assert.match(page, /ops-attempts-pager|ATTEMPTS_PAGE_SIZE/, "Attempts sheet must paginate");
assert.match(page, /setPage\(1\)/, "Changing status filter must reset to first page");
assert.match(page, /ops-attempts-footnote|latest100Footnote/, "Attempts must footnote list limits");
assert.doesNotMatch(page, /refreshPublishAttemptStatus/, "Attempts must not steal reconciliation mutate");
assert.doesNotMatch(page, /health-overview-grid/, "Attempts must leave shared health-overview-grid");
assert.doesNotMatch(page, /health-table/, "Attempts must not use health-table");
assert.doesNotMatch(page, /<OpsMetricCard/, "Attempts must not use shared OpsMetricCard");
assert.doesNotMatch(page, /<OpsPanel/, "Attempts must not use shared OpsPanel");
assert.doesNotMatch(page, /<StatusBadge/, "Attempts must not use StatusBadge");

assert.match(css, /\.ops-attempts-page/, "CSS must define Attempts page shell");
assert.match(css, /\.ops-attempts-kpis/, "CSS must define Attempts KPI grid");
assert.match(css, /\.ops-attempts-chip\s*\{[^}]*font-weight:\s*400/, "Attempts chips must not use bold weight");
assert.match(css, /\.ops-attempts-main\.has-attention/, "CSS must support split only when attention is present");
assert.match(css, /\.ops-attempts-pager/, "CSS must define attempts pager");

assert.match(en, /"loadedAt"|"filterAll"|"latest100Footnote"|"status"/, "en.json must define Attempts redesign labels");
assert.match(vi, /"loadedAt"|"filterAll"|"latest100Footnote"|"status"/, "vi.json must define Attempts redesign labels");
assert.match(pkg, /ops-publish-attempts-ui\.test\.ts/, "package.json must run ops-publish-attempts-ui test");

console.log("ops-publish-attempts-ui tests passed");
