import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { hasMoreOffsetItems } from "../lib/offsetListPagination";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = join(testDir, "..");

const reupQueueSource = readFileSync(join(webSrc, "components", "reup-queue", "ReupQueuePage.tsx"), "utf-8");
const opsJobsSource = readFileSync(join(webSrc, "components", "ops-console", "OpsJobsPage.tsx"), "utf-8");
const reviewBoardSource = readFileSync(join(webSrc, "components", "review-board", "ReviewBoardPage.tsx"), "utf-8");
const captureInboxSource = readFileSync(join(webSrc, "components", "capture-inbox", "CaptureInboxPage.tsx"), "utf-8");
const apiSource = readFileSync(join(webSrc, "lib", "api.ts"), "utf-8");

assert.equal(hasMoreOffsetItems(50, 120), true, "Load more must stay available while loaded < total");
assert.equal(hasMoreOffsetItems(120, 120), false, "Load more must stop when all items are loaded");

assert.match(reupQueueSource, /REUP_QUEUE_LOAD_BATCH_SIZE\s*=\s*50/, "Reup Queue must use fixed auto-load batch size 50");
assert.doesNotMatch(reupQueueSource, /onPageSizeChange=\{handlePageSizeChange\}/, "Reup auto-load footer must not expose per-page control");
assert.doesNotMatch(reupQueueSource, /pageSizeOptions=\{OPERATOR_LIST_PAGE_SIZE_PRESETS\}/, "Reup auto-load footer must not expose page size presets");
assert.match(reupQueueSource, /loadMoreQueue/, "Reup Queue must expose load-more for offset pages");
assert.match(reupQueueSource, /resolveOffsetPageMerge/, "Reup Queue load-more must reconcile stalled offset tail pages");
assert.match(reupQueueSource, /loadMoreInFlightRef/, "Reup Queue must guard concurrent load-more requests");
assert.doesNotMatch(reupQueueSource, /queuePagerDisabled = .*refreshing/, "Reup pager must stay stable during background refresh");
assert.match(reupQueueSource, /OffsetLoadMoreFooter/, "Reup Queue must use shared load-more footer");
assert.match(reupQueueSource, /hasMoreOffsetItems\(items\.length, totalCount\)/, "Reup Queue must gate load-more on total_count");
assert.match(reupQueueSource, /statusesForReupQueueFilter/, "Reup Queue must map operator tabs to API statuses");
assert.match(reupQueueSource, /buildReupQueueSummaryFromStatusCounts/, "Reup Queue hero must use global status_counts");
assert.match(reupQueueSource, /handleOperatorFilterChange/, "Reup Queue must reload when operator tab changes");
assert.match(apiSource, /params\.append\("statuses"/, "fetchReupQueueItems must send statuses[] query params");
assert.match(apiSource, /params\.set\("sort"/, "fetchReupQueueItems must send sort for server-side paging order");
assert.match(apiSource, /status_counts: payload\.status_counts/, "fetchReupQueueItems must keep status_counts");

assert.match(opsJobsSource, /JOBS_PAGE_SIZE_DEFAULT\s*=\s*50/, "Jobs page must default page size 50");
assert.match(opsJobsSource, /async function loadMore/, "Jobs page must expose load-more");
assert.match(opsJobsSource, /OffsetLoadMoreFooter/, "Jobs page must use shared load-more footer");
assert.match(opsJobsSource, /hasMoreOffsetItems\(jobs\.length, totalCount\)/, "Jobs page must gate load-more on total_count");
assert.match(opsJobsSource, /OPS_JOBS_PAGE_SIZE_STORAGE_KEY/, "Jobs page must persist page size preference");
assert.match(opsJobsSource, /onPageSizeChange=\{handlePageSizeChange\}/, "Jobs page footer must expose page size control");

assert.match(apiSource, /Promise<JobListResponse>/, "fetchJobs must return JobListResponse with total_count");
assert.match(apiSource, /total_count: Number\(payload\.total_count/, "fetchJobs must normalize total_count");

assert.match(reviewBoardSource, /OffsetLoadMoreFooter/, "Review Board must use shared load-more footer");
assert.match(reviewBoardSource, /variant="studio"/, "Review Board must use Soft CTA studio pager");
assert.match(captureInboxSource, /SESSION_PAGE_SIZE\s*=\s*25/, "Capture Inbox session rail must page at 25");
assert.match(captureInboxSource, /loadMoreSessions/, "Capture Inbox must load more sessions");
assert.match(captureInboxSource, /sessionsTotalCount/, "Capture Inbox must honor sessions total_count");
assert.match(captureInboxSource, /variant="studio"/, "Capture Inbox must use Soft CTA studio pager");
assert.match(reupQueueSource, /variant="studio"/, "Reup Queue must use Soft CTA studio pager");

console.log("operator-list-pagination.test.ts: ok");
