/**
 * Ops Jobs — truthful control-room flow, workload charts, six-column worklist and durable step trace.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const page = readFileSync(resolve(webSrc, "components/ops-console/OpsJobsPage.tsx"), "utf8");
const sharedPagination = readFileSync(resolve(webSrc, "components/shared/OperatorListPagination.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const api = readFileSync(resolve(webSrc, "lib/api.ts"), "utf8");

assert.match(page, /ops-jobs-monitor is-compact/, "Jobs must keep the compact Ops shell density");
assert.match(page, /function JobStateFlow/, "Jobs must use a state-flow control room");
assert.match(page, /ops-jobs-v2-command/, "State flow must have a dedicated command surface");
assert.match(page, /ops-jobs-v2-flow__main/, "State flow must show the main execution path");
assert.match(page, /ops-jobs-v2-flow__exceptions/, "State flow must separate exceptions from the main path");
assert.match(page, /ops-jobs-v2-flow__gauge/, "State flow must visualize the real completion share");
assert.match(page, /counts\.COMPLETED \/ total/, "Completion gauge must derive its percentage from real counts");
assert.match(page, /totalJobs[\s\S]*activeNow/, "State flow must give zero values useful volume context");
assert.match(page, /function JobFlowIcon/, "State flow must use semantic SVG icons");
assert.match(page, /<i><JobFlowIcon kind=\{item\.icon\} \/><\/i>/, "Main execution states must render icons");
assert.match(page, /<JobFlowIcon kind="workers" \/>[\s\S]*<JobFlowIcon kind="oldest" \/>/, "Metadata rail must render icons");
assert.doesNotMatch(page, /<p><JobFlowIcon|flow__gauge[\s\S]{0,300}<JobFlowIcon/, "Icons must stay out of summary and completion gauge");
assert.match(page, /clearSummary[\s\S]*activeSummary[\s\S]*exceptionSummary/, "State flow must narrate the current operational state");
assert.match(page, /generatedAt[\s\S]*formatMetricTime/, "State flow must expose metrics freshness");
assert.match(page, /WAITING_FOR_REVIEW/, "State flow must retain the manual review checkpoint");
assert.match(page, /active_worker_count/, "Control room must surface active worker authority");
assert.match(page, /running_with_lock/, "Control room must surface claimed running work");
assert.match(page, /running_without_lock/, "Control room must surface unclaimed running work");
assert.match(page, /oldest_queued_at/, "Control room must surface oldest queue wait");

assert.match(page, /stale_running_job_ids/, "Stale row filtering must use backend-provided job ids");
assert.match(page, /stale_running \?\? staleRunning\.length/, "Stale headline must use backend canonical count");
assert.doesNotMatch(page, /STALE_RUNNING_MINUTES|60 \* 60 \* 1000|running > 60/, "Frontend must not invent a stale threshold");
assert.doesNotMatch(page, /<KpiTile|ops-jobs-kpis/, "Jobs must not render the legacy KPI-card grid");
assert.doesNotMatch(page, /trend=|ops-jobs-kpi__trend/, "Jobs must not render decorative trends without history");

assert.match(page, /function JobWorkloadChart/, "Jobs must visualize workload by job type");
assert.match(page, /job_counts_by_type_status/, "Workload chart must use backend status counts");
assert.match(page, /statusOrder[\s\S]*?QUEUED[\s\S]*?RUNNING[\s\S]*?COMPLETED/, "Workload stack must keep truthful statuses");
assert.match(page, /function JobExceptionPareto/, "Jobs must visualize common errors as a Pareto chart");
assert.match(page, /common_failure_categories/, "Exception chart must use recorded backend error categories");
assert.doesNotMatch(page, /ops-jobs-failures/, "Text-heavy legacy failure banner must be removed from page markup");

assert.match(page, /ops-jobs-controls/, "Jobs must keep the filter control bar");
assert.match(page, /ops-jobs-controls__status/, "Control bar must keep status filtering");
assert.match(page, /ops-jobs-controls__type/, "Control bar must keep job type filtering");
assert.match(page, /ops-jobs-controls__view-all/, "Control bar must keep a clear action");
assert.match(page, /searchParams\.get\(["']status["']\)/, "Jobs must read status deep links");
assert.match(page, /queryForApi|query:/, "Search must be submitted to the jobs API");

assert.match(page, /ops-jobs-sheet/, "Worklist must remain in a sheet surface");
assert.match(page, /ops-jobs-table is-sheet/, "Worklist must remain a semantic table");
const tableHead = page.match(/<thead>[\s\S]*?<\/thead>/)?.[0] ?? "";
assert.equal((tableHead.match(/<th>/g) ?? []).length, 6, "Worklist must use six grouped columns");
for (const key of ["jobAndSource", "work", "execution", "health", "timing", "actions"]) {
  assert.match(tableHead, new RegExp(`opsJobs\\.${key}`), `Worklist must include ${key}`);
}
assert.match(page, /ops-jobs-table__source-line/, "Job identity must keep source context");
assert.match(page, /ops-jobs-table__type/, "Work column must keep type pills");
assert.match(page, /current_step_key/, "Work column must surface the current durable step");
assert.match(page, /ops-jobs-table__progress/, "Execution column must visualize progress");
assert.match(page, /attempts[\s\S]*max_attempts/, "Execution column must show attempt budget");
assert.match(page, /completed_steps[\s\S]*total_steps/, "Execution column must show durable step completion");
assert.match(page, /error_code/, "Health column must surface the last error code");
assert.match(page, /locked_at|heartbeat/, "Health column must surface worker heartbeat evidence");
assert.match(page, /ops-jobs-table__timing/, "Timing column must group start, end and elapsed duration");
assert.match(page, /formatJobDuration|formatJobElapsed/, "Timing must derive truthful duration from timestamps");

assert.match(page, /expandedJobId/, "Rows must keep explicit expansion state");
assert.match(page, /function JobStepTrace/, "Expanded rows must render durable step traces");
assert.match(page, /ops-jobs-v2-trace-row/, "Step trace must render inline with its job");
assert.match(page, /colSpan=\{6\}/, "Step trace must span the six-column worklist");
assert.match(page, /job\.steps/, "Step trace must use persisted job steps");
assert.match(
  page,
  /resolveOcrCheckpointOutcome[\s\S]*persist_outputs[\s\S]*WAITING_OCR_REVIEW/,
  "Completed Analyze OCR jobs must derive their operator checkpoint from persisted step output"
);
assert.match(
  page,
  /ocrAnalysisReviewPending[\s\S]*reviewRequired/,
  "Jobs worklist must replace No current step with the pending OCR decision count"
);
assert.match(
  page,
  /ops-jobs-table__checkpoint-badge[\s\S]*ocrReviewBadge/,
  "Completed OCR jobs must show review attention as a separate badge"
);
assert.match(css, /\.ops-jobs-table__step\.is-attention/, "Pending OCR checkpoint copy must have an attention treatment");
assert.match(css, /\.ops-jobs-table__checkpoint-badge/, "OCR review badge must have a compact amber treatment");

assert.match(page, /status === "COMPLETED"[\s\S]*?100/, "Completed jobs must force displayed progress to 100%");
assert.match(page, /status === "CANCELLED"[\s\S]*?0/, "Cancelled jobs must force displayed progress to 0%");
assert.match(page, /ops-jobs-table__copy/, "Job id must keep a copy control");
assert.match(page, /retryJob/, "Jobs must keep retry behavior");
assert.match(page, /resumeJob/, "Jobs must keep resume behavior");
assert.match(page, /cancelJob/, "Jobs must keep cancel behavior");
assert.match(page, /deleteJob/, "Jobs must keep delete behavior");
assert.match(page, /JobActionIcon/, "Row actions must retain icon controls");
assert.match(page, /formatStatusLabel/, "Status pills must retain readable labels");
assert.match(page, /ops-jobs-table__status-dot/, "Status pills must retain semantic color dots");
assert.match(page, /OperatorListPagination/, "Jobs must use a dedicated numbered Pagination Dock");
assert.match(sharedPagination, /function paginationItems|paginationItems\(/, "Pagination Dock must build a bounded page-number window");
assert.match(page, /offset:\s*\(currentPage - 1\) \* pageSize/, "Jobs API offset must follow the selected page");
assert.match(page, /params\.set\("page"[\s\S]*params\.set\("per_page"/, "Page and page size must sync to the URL");
assert.match(sharedPagination, /ops-jobs-pagination__size/, "Page size must use segmented controls");
assert.match(sharedPagination, /ops-jobs-pagination__numbers/, "Desktop pagination must expose direct page buttons");
assert.match(sharedPagination, /ops-jobs-pagination__compact/, "Mobile pagination must expose compact page context");
assert.doesNotMatch(page, /OffsetLoadMoreFooter|variant="inline"|loadMore/, "Jobs must remove accumulated Load more pagination");
assert.match(page, /ops-job-row-\$\{/, "Jobs must keep focusable row ids");

assert.match(css, /\.ops-jobs-v2-command/, "CSS must define the control-room surface");
assert.match(css, /\.ops-jobs-v2-flow__gauge/, "CSS must define the completion gauge");
assert.match(css, /\.ops-jobs-v2-icon/, "CSS must define semantic flow icons");
assert.match(css, /\.ops-jobs-v2-command__status/, "CSS must define freshness and state treatment");
assert.match(css, /\.ops-jobs-v2-workload/, "CSS must define the workload chart");
assert.match(css, /\.ops-jobs-v2-pareto/, "CSS must define the exception Pareto");
assert.match(css, /\.ops-jobs-v2-trace/, "CSS must define inline step traces");
assert.match(css, /--ops-jobs-axis:\s*0\.6875rem/, "Desktop chart labels must be at least 11px");
assert.match(css, /--ops-jobs-axis:\s*0\.75rem/, "Mobile chart labels must increase to 12px");
assert.match(css, /ops-jobs-status-pulse|@keyframes\s+ops-jobs-status-pulse/, "Running status must retain a live pulse");
assert.match(css, /\.ops-jobs-table\.is-sheet th:nth-child\(6\)/, "Six-column worklist must have explicit sizing");
assert.match(css, /\.ops-jobs-pagination\s*\{/, "CSS must define the Pagination Dock");
assert.match(css, /\.ops-jobs-pagination__numbers/, "CSS must define numbered navigation");
assert.match(css, /\.ops-jobs-pagination__size/, "CSS must define segmented page-size controls");
assert.match(css, /\.ops-jobs-pagination__compact/, "CSS must define mobile compact pagination");

assert.match(api, /export async function retryJob/, "api.ts must export retryJob");
assert.match(api, /\/jobs\/\$\{jobId\}\/retry/, "retryJob must POST /jobs/{id}/retry");

console.log("ops-jobs-monitor tests passed");
