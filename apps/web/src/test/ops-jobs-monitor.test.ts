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
assert.match(page, /ops-jobs-kpi__label/, "KPI cards must show top-left label");
assert.match(page, /ops-jobs-kpi__value/, "KPI cards must show large primary value");
assert.match(page, /ops-jobs-kpi__glyph/, "KPI cards must show top-right icon box");
assert.match(page, /ops-jobs-kpi__trend/, "KPI cards must show trend pill");
assert.match(page, /ops-jobs-kpi__hint/, "KPI cards must show comparison hint text");
assert.match(page, /kind=\"backlog\"|kind=\"retries\"/, "KPI band must include backlog and retries cards");
assert.doesNotMatch(page, /ops-jobs-controls__pill/, "Backlog/retries must leave control-bar pill");
assert.match(page, /ops-jobs-kpi is-hotel|is-hotel/, "KPI cards must use hotel mockup aesthetic");
assert.match(page, /ops-jobs-controls/, "Jobs page must render control bar");
assert.match(page, /ops-jobs-controls__status/, "Control bar must include status select");
assert.match(page, /ops-jobs-controls__type/, "Control bar must include job type select");
assert.match(page, /ops-jobs-controls__view-all/, "Control bar must include View All clear action");
assert.match(page, /jobTypeFilter/, "Jobs page must keep job type filter state");
assert.match(page, /statusFilter/, "Jobs page must keep status filter state");
assert.match(page, /searchParams\.get\(["']status["']\)|get\(["']status["']\)/, "Jobs page must read status deep-link from URL");
assert.match(page, /searchQuery/, "Jobs page must keep search state");
assert.match(page, /ops-jobs-sheet/, "Jobs table must sit in a Users-style sheet card");
assert.match(page, /ops-jobs-sheet__bar|ops-jobs-sheet__meta/, "Sheet must show count meta like Users");
assert.match(page, /ops-jobs-table is-sheet/, "Jobs table must use Users sheet aesthetic");
assert.match(page, /ops-jobs-table/, "Jobs must render in a dense data table");
assert.match(page, /opsJobs\.videoSource/, "Table must include Video Source column");
assert.match(page, /opsJobs\.progress/, "Table must include Progress column");
assert.match(page, /opsJobs\.startedAt|opsJobs\.start/, "Table must include Start datetime column");
assert.match(page, /opsJobs\.finishedAt|opsJobs\.end/, "Table must include End datetime column");
assert.match(page, /opsJobs\.duration|opsJobs\.processingTime/, "Table must include processing duration column");
assert.doesNotMatch(page, /opsJobs\.updated/, "Table must replace Updated column with End");
assert.match(page, /ops-jobs-table__id/, "Job ID must be its own bold column");
assert.match(page, /ops-jobs-table__type/, "Job type must render as category pill");
assert.match(page, /ops-jobs-table__progress/, "Progress must render with bar/percent");
assert.match(page, /progress_percent/, "Progress must read job.progress_percent");
assert.doesNotMatch(
  page,
  /ops-jobs-table__done|doneShort/,
  "Completed jobs must show a 100% progress bar, not a Done pill"
);
assert.match(
  page,
  /status === "COMPLETED"[\s\S]*?\b100\b/,
  "Completed status must force displayed progress to 100%"
);
assert.match(
  page,
  /status === "CANCELLED"[\s\S]*?\b0\b/,
  "Cancelled status must force displayed progress to 0%"
);
assert.match(page, /job\.started_at/, "Start column must read job.started_at");
assert.match(page, /job\.finished_at/, "End column must read job.finished_at");
assert.match(page, /formatJobDuration|jobDuration/, "Duration must be derived from finished_at − started_at");
assert.match(page, /ops-jobs-table__copy/, "Job id must offer a copy control");
assert.doesNotMatch(page, /ops-jobs-table__view/, "Row actions must remove View");
assert.match(page, /ops-jobs-table__retry/, "Row actions must include Retry");
assert.match(page, /ops-jobs-table__icon|ActionIcon|aria-hidden=\"true\"/, "Retry/Delete must render icon glyphs");
assert.match(page, /retryJob/, "Jobs page must call retryJob");
assert.match(page, /formatStatusLabel/, "Status pills must use soft title-case labels");
assert.match(
  page,
  /ops-jobs-table__status/,
  "Status column must use redesigned status chips"
);
assert.match(
  page,
  /ops-jobs-table__status-dot/,
  "Status chips must include a status color dot"
);
assert.doesNotMatch(
  page,
  /ops-jobs-table__badge tone-\$\{tone\}/,
  "Status column must not keep the old generic tone badge markup"
);
assert.match(
  page,
  /function formatTableDateTime[\s\S]*?padStart\(2,\s*"0"\)[\s\S]*?\$\{dd\}\/\$\{mm\}\/\$\{yy\} \$\{hh\}:\$\{min\}/,
  "Start/End datetime must use compact dd/MM/yy HH:mm"
);
assert.doesNotMatch(
  page,
  /function formatTableDateTime[\s\S]*?toLocaleString/,
  "Start/End must not use verbose locale month strings like 'thg'"
);
assert.match(page, /jobTypePillTone|typeTone/, "Job type pills must map to colored variants");
assert.doesNotMatch(page, /ops-jobs-table is-booking/, "Jobs table must leave hotel-booking chrome");
assert.match(page, /failureCategories\.length > 0/, "Failure categories must only render when present");
assert.doesNotMatch(page, /ops-jobs-desk|ops-jobs-chip\b/, "Jobs page must leave desk/chip chrome");
assert.doesNotMatch(page, /ops-jobs-stream|ops-jobs-row\b/, "Jobs page must leave card-stream chrome");
assert.doesNotMatch(page, /OpsMetricCard/, "Jobs page must not use OpsMetricCard tiles");
assert.doesNotMatch(page, /health-overview-grid/, "Jobs page must leave health overview grid");
assert.match(page, /deleteJob/, "Jobs page must keep delete behavior");
assert.match(page, /OffsetLoadMoreFooter/, "Jobs page must keep load-more pagination");
assert.match(page, /variant=\"inline\"/, "Jobs footer must use inline aesthetic pager");
assert.match(page, /ops-jobs-monitor__footer/, "Jobs page must style the monitor footer");
assert.match(page, /ops-job-row-\$\{/, "Jobs page must keep job_id focus row ids");

assert.match(api, /export async function retryJob/, "api.ts must export retryJob");
assert.match(api, /\/jobs\/\$\{jobId\}\/retry/, "retryJob must POST /jobs/{id}/retry");

const footer = readFileSync(resolve(webSrc, "components/shared/OffsetLoadMoreFooter.tsx"), "utf8");
assert.match(footer, /variant\?:/, "OffsetLoadMoreFooter must accept a variant prop");
assert.match(footer, /offset-load-more is-inline|is-inline/, "Inline variant must render offset-load-more is-inline");
assert.match(footer, /offset-load-more__bar|loadedPercent/, "Inline variant must expose loaded percent progress");

assert.match(css, /\.ops-jobs-monitor\.is-compact/, "CSS must define compact Monitor density");
assert.match(
  css,
  /\.ops-jobs-monitor\s*\{[^}]*padding:\s*[^;]*var\(--app-content-inset-x\)/,
  "Jobs monitor must use horizontal page inset token",
);
assert.match(
  css,
  /\.ops-jobs-monitor\.is-compact\s*\{[^}]*padding:\s*[^;]*var\(--app-content-inset-x\)/,
  "Compact Jobs monitor must keep horizontal inset token like Health",
);
assert.match(css, /\.ops-jobs-kpi__icon/, "CSS must define KPI icons");
assert.match(css, /\.ops-jobs-kpi\.is-hotel|\.ops-jobs-kpi__label/, "CSS must define hotel KPI layout");
assert.match(css, /\.ops-jobs-kpi__value/, "CSS must define large KPI value");
assert.match(css, /\.ops-jobs-kpi__trend/, "CSS must define KPI trend pill");
assert.match(css, /\.ops-jobs-kpi\.is-active/, "CSS must define active mint KPI card");
assert.match(css, /\.ops-jobs-controls__status/, "CSS must define status select");
assert.match(css, /\.ops-jobs-sheet/, "CSS must define Jobs sheet card");
assert.match(css, /\.ops-jobs-table\.is-sheet/, "CSS must define sheet-table aesthetic");
assert.match(css, /\.ops-jobs-table__status/, "CSS must define redesigned status chips");
assert.match(css, /\.ops-jobs-table__status-dot/, "CSS must define status chip dots");
assert.match(css, /ops-jobs-status-pulse|@keyframes\s+ops-jobs-status-pulse/, "Running status must have a live pulse");
assert.match(
  css,
  /\.ops-jobs-table\.is-sheet\s+\.ops-jobs-table__status\s*\{[^}]*font-size:\s*0\.66rem[^}]*text-transform:\s*lowercase/,
  "Status chip text must be lowercase and one size smaller"
);
assert.match(css, /\.ops-jobs-table__type/, "CSS must define type category pills");
assert.match(css, /\.ops-jobs-table__id/, "CSS must define bold job id column");
assert.match(css, /\.ops-jobs-table__progress/, "CSS must define progress cell");
assert.match(css, /\.ops-jobs-table\.is-sheet th[\s\S]*?text-transform:\s*uppercase/, "Sheet headers must use uppercase like Users");
assert.doesNotMatch(css, /\.ops-jobs-table\.is-booking/, "CSS must leave booking-table aesthetic");
assert.match(css, /\.offset-load-more\.is-inline/, "CSS must define inline pager footer");
assert.match(css, /\.ops-jobs-monitor__footer/, "CSS must define Jobs monitor footer");
assert.doesNotMatch(css, /\.ops-jobs-desk\b/, "CSS must leave Jobs desk shell");
assert.doesNotMatch(css, /\.ops-jobs-stream\b/, "CSS must leave card-stream layout");

console.log("ops-jobs-monitor tests passed");
