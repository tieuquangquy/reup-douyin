/**
 * Ops home — triage command center (pulse KPIs + publish week + attention).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsHomePage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const pkg = readFileSync(resolve(webSrc, "../package.json"), "utf8");

assert.match(page, /ops-home-page/, "Ops home must use scoped ops-home-page shell");
assert.match(page, /ops-home-kpis|ops-home-pulse/, "Ops home must render pulse KPI band");
assert.match(page, /by_day|publishHealth\.by_day/, "Ops home must chart publish by_day");
assert.match(page, /ops-home-week|ops-home-daybar/, "Ops home must render publish week chart");
assert.match(page, /ops-home-attention|ops\.actionQueue/, "Ops home must render attention / action queue");
assert.match(page, /ops-home-queue-mix|queue_backlog/, "Ops home must visualize queue mix");
assert.match(page, /\/ops\/jobs\?status=/, "Ops home must deep-link jobs by status");
assert.match(page, /\/ops\/risk/, "Ops home must deep-link risk");
assert.match(page, /\/ops\/reconciliation/, "Ops home must deep-link reconciliation");
assert.match(page, /\/ops\/publish-health/, "Ops home must deep-link publish health");
assert.match(page, /\/ops\/accounts/, "Ops home must deep-link accounts");
assert.match(page, /\/ops\/health/, "Ops home must deep-link system health for fetch detail");
assert.match(page, /blocked_ratio_percent|fetchHealthBlockedRatio/, "Ops home must keep a compact fetch signal");
assert.match(page, /generated_at/, "Ops home must surface metrics freshness");
assert.doesNotMatch(page, /studio-card-list/, "Ops home must leave long directory card list");
assert.doesNotMatch(page, /health-overview-grid/, "Ops home must leave shared health-overview-grid");
assert.doesNotMatch(page, /<OpsMetricCard/, "Ops home must not use shared OpsMetricCard");
assert.doesNotMatch(page, /fetchHealthTopBlockedReasons/, "Ops home must not dump full fetch reasons");
assert.match(page, /fetchOperationalMetrics/, "Ops home must keep metrics authority");
assert.match(page, /fetchPublishHealthDashboard/, "Ops home must keep publish health authority");
assert.match(page, /fetchPublishControlQueue/, "Ops home must keep publish control queue authority");
assert.match(page, /open_risk_counts_by_severity/, "Ops home must surface risk severity preview");
assert.match(page, /ops-home-risk|ops\.riskPreview/, "Ops home must render risk preview block");
assert.match(page, /health_status|is_on_hold/, "Ops home must surface accounts needing care from queue");
assert.match(page, /ops-home-accounts|ops\.accountsCare/, "Ops home must render accounts care preview");
assert.match(page, /common_failure_categories/, "Ops home must surface top failure categories");
assert.match(page, /ops-home-failures|ops\.topFailures/, "Ops home must render top failure codes");
assert.match(page, /job_counts_by_type_status/, "Ops home must surface jobs snapshot from type/status counts");
assert.match(page, /ops-home-jobs|ops\.jobsSnapshot/, "Ops home must render jobs snapshot");
assert.match(page, /ops-home-fallback|total_attempts|noPublishTrend/, "Ops home must fall back when publish window is empty");
assert.match(page, /render_counts_by_status|publish_draft_counts_by_status/, "Ops home fallback must surface pipeline chips");
assert.match(page, /average_processing_seconds_per_source_video|ops\.avgProcessing/, "Ops home must surface avg processing (P2)");
assert.match(page, /queue_backlog\.queued|ops\.queued/, "Ops home must surface queued count (P2)");

assert.match(css, /\.ops-home-page/, "CSS must define Ops home shell");
assert.match(css, /\.ops-home-kpis|\.ops-home-pulse/, "CSS must define Ops home KPI band");
assert.match(css, /\.ops-home-week|\.ops-home-daybar/, "CSS must define Ops home publish week chart");
assert.match(css, /\.ops-home-queue-mix/, "CSS must define Ops home queue mix");
assert.match(css, /\.ops-home-attention/, "CSS must define Ops home attention list");
assert.match(css, /\.ops-home-risk|\.ops-home-meter/, "CSS must define Ops home risk preview");
assert.match(css, /\.ops-home-accounts/, "CSS must define Ops home accounts care");
assert.match(css, /\.ops-home-failures/, "CSS must define Ops home failure list");
assert.match(css, /\.ops-home-jobs|\.ops-home-fallback/, "CSS must define Ops home jobs snapshot / publish fallback");

assert.match(en, /"attention"|"actionQueue"/, "en.json must define attention/action labels");
assert.match(en, /"publishWeek"|"publishTrend"/, "en.json must define publish week label for home");
assert.match(en, /"queueMix"/, "en.json must define queueMix for home");
assert.match(en, /"riskPreview"|"accountsCare"/, "en.json must define risk/accounts preview labels");
assert.match(en, /"topFailures"|"jobsSnapshot"/, "en.json must define failures/jobs snapshot labels");
assert.match(en, /"avgProcessing"/, "en.json must define avgProcessing");
assert.match(vi, /"attention"|"actionQueue"/, "vi.json must define attention/action labels");
assert.match(vi, /"publishWeek"|"publishTrend"/, "vi.json must define publish week label for home");
assert.match(vi, /"queueMix"/, "vi.json must define queueMix for home");
assert.match(vi, /"riskPreview"|"accountsCare"/, "vi.json must define risk/accounts preview labels");
assert.match(vi, /"topFailures"|"jobsSnapshot"/, "vi.json must define failures/jobs snapshot labels");
assert.match(vi, /"avgProcessing"/, "vi.json must define avgProcessing");

assert.match(pkg, /ops-home-ui\.test\.ts/, "package.json must run ops-home-ui test");

console.log("ops-home-ui tests passed");
