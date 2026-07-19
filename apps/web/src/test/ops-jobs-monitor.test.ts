/**
 * Ops Jobs Monitor — Process Monitor mockup: KPI icons, filter selects, dense table, retry.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsJobsPage.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const api = readFileSync(resolve(webSrc, "lib/api.ts"), "utf8");

assert.match(page, /ops-jobs-monitor is-compact/, "Jobs Monitor must opt into compact density");
assert.match(page, /ops-jobs-kpis/, "Jobs page must render KPI band");
assert.match(page, /ops-jobs-kpi__icon/, "KPI tiles must include mockup icons");
assert.match(page, /ops-jobs-controls/, "Jobs page must render control bar");
assert.match(page, /ops-jobs-controls__status/, "Control bar must include status select");
assert.match(page, /ops-jobs-controls__type/, "Control bar must include job type select");
assert.match(page, /ops-jobs-controls__view-all/, "Control bar must include View All clear action");
assert.match(page, /jobTypeFilter/, "Jobs page must keep job type filter state");
assert.match(page, /statusFilter/, "Jobs page must keep status filter state");
assert.match(page, /searchQuery/, "Jobs page must keep search state");
assert.match(page, /ops-jobs-table/, "Jobs must render in a dense data table");
assert.match(page, /opsJobs\.videoSource/, "Table must include Video Source column");
assert.match(page, /opsJobs\.progress/, "Table must include Progress column");
assert.match(page, /ops-jobs-table__job is-inline/, "Job cell must be single-line");
assert.match(page, /ops-jobs-table__progress/, "Progress must render with bar/percent");
assert.match(page, /progress_percent/, "Progress must read job.progress_percent");
assert.match(page, /ops-jobs-table__copy/, "Job id must offer a copy control");
assert.match(page, /ops-jobs-table__view/, "Row actions must include View");
assert.match(page, /ops-jobs-table__retry/, "Row actions must include Retry");
assert.match(page, /retryJob/, "Jobs page must call retryJob");
assert.match(page, /formatRelativeStamp|relative/, "Updated column must use relative time");
assert.match(page, /failureCategories\.length > 0/, "Failure categories must only render when present");
assert.doesNotMatch(page, /ops-jobs-desk|ops-jobs-sheet|ops-jobs-chip/, "Jobs page must leave desk/sheet/chip chrome");
assert.doesNotMatch(page, /ops-jobs-stream|ops-jobs-row/, "Jobs page must leave card-stream chrome");
assert.doesNotMatch(page, /OpsMetricCard/, "Jobs page must not use OpsMetricCard tiles");
assert.doesNotMatch(page, /health-overview-grid/, "Jobs page must leave health overview grid");
assert.match(page, /deleteJob/, "Jobs page must keep delete behavior");
assert.match(page, /OffsetLoadMoreFooter/, "Jobs page must keep load-more pagination");
assert.match(page, /ops-job-row-\$\{/, "Jobs page must keep job_id focus row ids");

assert.match(api, /export async function retryJob/, "api.ts must export retryJob");
assert.match(api, /\/jobs\/\$\{jobId\}\/retry/, "retryJob must POST /jobs/{id}/retry");

assert.match(css, /\.ops-jobs-monitor\.is-compact/, "CSS must define compact Monitor density");
assert.match(css, /\.ops-jobs-kpi__icon/, "CSS must define KPI icons");
assert.match(css, /\.ops-jobs-controls__status/, "CSS must define status select");
assert.match(css, /\.ops-jobs-table/, "CSS must define Jobs data table");
assert.match(css, /\.ops-jobs-table__job\.is-inline/, "CSS must define single-line job cell");
assert.match(css, /\.ops-jobs-table__progress/, "CSS must define progress cell");
assert.doesNotMatch(css, /\.ops-jobs-desk\b/, "CSS must leave Jobs desk shell");
assert.doesNotMatch(css, /\.ops-jobs-stream\b/, "CSS must leave card-stream layout");

console.log("ops-jobs-monitor tests passed");
