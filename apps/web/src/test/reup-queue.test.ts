import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { queueTileMetric } from "../lib/reupQueueStudioState";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");

const pageSource = readFileSync(resolve(webRoot, "components/reup-queue/ReupQueuePage.tsx"), "utf8");
const studioSource = readFileSync(resolve(webRoot, "lib/reupQueueStudioState.ts"), "utf8");
const globalCssSource = readFileSync(resolve(webRoot, "app/globals.css"), "utf8");
const routeSource = readFileSync(resolve(webRoot, "app/selection/reup-queue/page.tsx"), "utf8");
const apiSource = readFileSync(resolve(webRoot, "lib/api.ts"), "utf8");
const typeSource = readFileSync(resolve(webRoot, "types/reup-queue.ts"), "utf8");
const exportHandoffTypeSource = readFileSync(resolve(webRoot, "types/export-handoff.ts"), "utf8");
const exportPackagesIndexSource = readFileSync(resolve(webRoot, "components/operator-routes/ExportPackagesIndexPage.tsx"), "utf8");
const exportPackageDetailSource = readFileSync(resolve(webRoot, "components/operator-routes/ExportPackageByIdPage.tsx"), "utf8");
const publishHandoffsIndexSource = readFileSync(resolve(webRoot, "components/operator-routes/PublishHandoffsIndexPage.tsx"), "utf8");
const publishHandoffDetailSource = readFileSync(resolve(webRoot, "components/operator-routes/PublishHandoffByIdPage.tsx"), "utf8");

assert.match(routeSource, /ReupQueuePage/, "Reup Queue route must render the queue page");
assert.match(apiSource, /fetchReupQueueItems/, "API client must expose Reup Queue list fetch");
assert.match(apiSource, /params\.set\("sort"/, "fetchReupQueueItems must send sort for server-side active-first paging");
assert.match(pageSource, /sort:\s*sortMode/, "Reup Queue loads must pass current sortMode to the API");
assert.match(apiSource, /runReupQueueAction/, "API client must expose lifecycle action execution");
assert.match(apiSource, /enqueueReupCandidates/, "API client must expose approved candidate enqueue");
assert.match(apiSource, /runReupQueueBatchAction/, "API client must expose Reup Queue batch action execution");
assert.match(typeSource, /ReupQueueAction/, "Reup Queue types must model operator lifecycle actions");
assert.match(typeSource, /EXPORT_PACKAGE_CREATED/, "Reup Queue types must include Export Package state");
assert.match(typeSource, /job_status/, "Reup Queue types must include job status");
assert.match(exportHandoffTypeSource, /BatchOperationResponse/, "Export handoff types must model structured batch results");

assert.match(pageSource, /OperatorStudioShell/, "Reup Queue page must use the Operator Studio shell");
assert.match(pageSource, /22G-2K/, "Reup Queue UI version must be 22G-2K");
assert.match(pageSource, /terminalQueueDismissAction/, "Cancelled tiles must use quiet Dismiss companion");
assert.match(pageSource, /queueTilePrimaryButtonClassName/, "Tile CTAs must use action-aware button styling");
assert.match(globalCssSource, /is-no-arrow/, "Recover/retry primary buttons must not show forward arrow");
assert.match(pageSource, /hasActiveDownloadJob/, "Reup Queue must auto-refresh while downloads are active");
assert.match(pageSource, /reup-queue-download-progress/, "Reup Queue tiles must show download progress bar");
assert.match(pageSource, /downloadJobErrorLine/, "Reup Queue tiles must surface download job errors");
assert.match(pageSource, /reup-queue-download-progress-label/, "Download progress bar must show percent label");
assert.match(studioSource, /Avoid duplicate orange chips/, "In-flight download must not duplicate a second job chip");
assert.doesNotMatch(studioSource, /Downloading \$\{/, "Percent must live on the progress bar, not a second chip");
assert.match(typeSource, /job_progress_percent/, "Reup Queue types must include job progress");
assert.match(typeSource, /job_error_message/, "Reup Queue types must include job error message");
assert.match(
  globalCssSource,
  /\.work-media-tile-overlay\.is-compact[\s\S]*min-height:\s*32px/,
  "Compact overlay must use a thinner scrim rail"
);
assert.match(
  globalCssSource,
  /\.reup-queue-media-tile[\s\S]*\.work-media-tile-overlay\.is-compact[\s\S]*text-overflow:\s*ellipsis/,
  "Reup Queue compact tiles must ellipsis long stage labels"
);
assert.match(studioSource, /isDownloadReadyForConfirm/, "Job chip must defer when download is ready for confirm");
assert.match(globalCssSource, /\.reup-queue-download-progress/, "Download progress bar must have dedicated CSS");
assert.match(pageSource, /reup-queue-hero-kicker/, "Reup Queue hero must use a subdued workflow kicker instead of a second page title");
assert.match(pageSource, /shouldShowQueueTileDetailsButton/, "Queue tiles must hide duplicate Details button");
assert.match(pageSource, /reup-queue-tile-action-bar/, "Queue tiles must use shared ops tile action bar");
assert.match(pageSource, /review-board-tile-action-bar/, "Queue tiles must share review-board action bar layout");
assert.match(pageSource, /queueTilePrimaryButtonClassName/, "Queue primary action must use action-aware tile button styling");
assert.match(studioSource, /is-primary is-recover is-no-arrow/, "Retry must keep primary style without forward arrow");
assert.match(pageSource, /reup-queue-bulk-stack/, "Reup Queue bulk bar must use compact stack layout");
assert.match(pageSource, /reup-queue-batch-banner/, "Reup Queue batch result must use compact banner");
assert.doesNotMatch(pageSource, /Last batch result/, "Reup Queue must not use heavy batch result panel heading");
assert.match(studioSource, /formatBulkBarScopeMeta/, "Studio state must format compact bulk scope meta");
assert.match(pageSource, /Cancel visible/, "Reup Queue bulk bar must expose cancel visible action");
assert.match(pageSource, /bulkCancelConfirmMessage/, "Reup Queue must confirm bulk cancel");
assert.match(studioSource, /cancellableReupQueueItems/, "Studio state must model cancellable visible items");
assert.match(pageSource, /reup-queue-hero-toolbar/, "Hero panel must place Start all ready in the toolbar row");
assert.doesNotMatch(pageSource, /reup-queue-hero-footer/, "Hero panel must not isolate Start all ready on a separate footer row");
assert.match(pageSource, /reup-queue-inspector-workflow-chip/, "Inspector must use compact workflow chips");
assert.doesNotMatch(pageSource, /reup-queue-inspector-action-group-label/, "Inspector must not use verbose action group labels");
assert.doesNotMatch(pageSource, /State transitions only/, "Inspector must not show redundant action footnote");
assert.match(pageSource, /reup-queue-pipeline-strip/, "Reup Queue tiles must show pipeline progress strip");
assert.match(pageSource, /resolveInitialReupQueueFilter/, "Reup Queue must apply smart default filter on load");
assert.match(pageSource, /formatJobChipLabel/, "Reup Queue must show job status chip on tiles");
assert.match(studioSource, /buildPipelineStages/, "Reup Queue studio must model pipeline stages");
assert.doesNotMatch(pageSource, /PageShell/, "Reup Queue studio must not nest PageShell inside OperatorStudioShell");
assert.doesNotMatch(pageSource, /OpsItemCard/, "Reup Queue studio must use media tiles instead of OpsItemCard");
assert.doesNotMatch(pageSource, /OpsContentGrid/, "Reup Queue studio must use capture-inbox-review-workspace instead of OpsContentGrid");
assert.doesNotMatch(pageSource, /OpsBatchActionBar/, "Reup Queue studio must use capture-inbox-command-bar bulk bar");
assert.doesNotMatch(pageSource, /OpsToolbarGroup label="Queue state filters"/, "Reup Queue must not duplicate status filters in the filter bar");

assert.match(pageSource, /capture-inbox-review-workspace/, "Reup Queue must use Capture Inbox studio workspace layout");
assert.match(pageSource, /reup-queue-studio-workspace/, "Reup Queue must expose studio workspace marker");
assert.match(pageSource, /ReupQueueQuickPathBar/, "Reup Queue must expose operator quick path bar");
assert.doesNotMatch(pageSource, /ReupQueueStatusStrip/, "Reup Queue must not duplicate status strip below hero chips");
assert.doesNotMatch(pageSource, /capture-inbox-gallery-summary/, "Reup Queue must not repeat hero counts in gallery summary");
assert.match(pageSource, /OpsFilterBar/, "Reup Queue must use shared search and sort controls");
assert.match(pageSource, /capture-inbox-media-tile/, "Reup Queue must render Capture Inbox-style media tiles");
assert.match(pageSource, /capture-inbox-command-bar/, "Reup Queue must use sticky capture-inbox bulk command bar");
assert.match(pageSource, /WorkItemDetailsDrawer/, "Reup Queue must open details in WorkItemDetailsDrawer");
assert.doesNotMatch(pageSource, /capture-inbox-review-side/, "Reup Queue must not reserve sticky right inspector column");
assert.match(pageSource, /OpsDetailPanel/, "Reup Queue must keep shared detail panel sections");
assert.match(pageSource, /OpsStatePanel/, "Reup Queue must use shared state panels");

assert.match(studioSource, /Needs start/, "Reup Queue must expose operator-facing needs-start stage");
assert.match(studioSource, /In production/, "Reup Queue must expose in-production stage filter");
assert.match(studioSource, /In production/, "Reup Queue must expose in-production stage filter");
assert.match(pageSource, /Start processing/, "Reup Queue must expose start processing action");
assert.match(pageSource, /CREATE_EXPORT_PACKAGE/, "Reup Queue must expose export batch action");
assert.match(pageSource, /CREATE_PUBLISH_HANDOFF/, "Reup Queue must expose handoff batch action");
assert.match(pageSource, /Queue detail panel/, "Reup Queue must keep queue detail panel");
assert.match(pageSource, /ReupQueueInspectorActions/, "Reup Queue inspector must use grouped actions panel");
assert.match(pageSource, /reup-queue-inspector-btn-grid/, "Inspector must use compact action button grid");
assert.doesNotMatch(pageSource, /reup-queue-inspector-spotlight-btn/, "Inspector must not use oversized spotlight button class");
assert.match(pageSource, /Open workflows/, "Inspector must expose workflow navigation");
assert.doesNotMatch(pageSource, /card-actions[\s\S]*Open transcript editor/, "Inspector must not use legacy card-actions link row");
assert.match(studioSource, /buildInspectorWorkflowLinks/, "Studio state must build inspector workflow links");
assert.match(pageSource, /Queue lifecycle/, "Detail panel must show lifecycle section");
assert.match(pageSource, /Media prep/, "Detail panel must show media-prep section");
assert.match(pageSource, /Not triggered here/, "Reup Queue must state publish automation is not triggered here");
assert.match(pageSource, /No worker job attached yet/, "Reup Queue must be honest about missing worker jobs");
assert.match(pageSource, /Job error/, "Inspector must show download job error field");
assert.match(pageSource, /Not prepared yet/, "Reup Queue must use honest media-prep missing labels");
assert.match(studioSource, /Pending/, "Reup Queue must use honest pending labels");

assert.match(pageSource, /activeItemId/, "Reup Queue must use explicit active item identity");
assert.match(pageSource, /queueInspectorOpen/, "Reup Queue must use explicit inspector open state");
assert.match(pageSource, /ReupQueueRightInspector/, "Reup Queue must render right-side inspector wrapper");
assert.match(pageSource, /Select actionable/, "Reup Queue bulk bar must select actionable items only");
assert.match(pageSource, /reup-queue-hero-panel/, "Reup Queue quick path must use hero panel layout");
assert.match(pageSource, /reup-queue-hero-stats/, "Reup Queue quick path must show stat chips");
assert.match(pageSource, /reup-queue-hero-alert/, "Reup Queue quick path must show contextual guidance banner");
assert.match(studioSource, /buildQuickPathHeroStats/, "Reup Queue studio state must build hero stat chips");
assert.match(studioSource, /quickPathSuggestedFilter/, "Reup Queue studio state must suggest quick path filter");
assert.match(studioSource, /quickPathGuidance/, "Reup Queue studio state must provide quick path guidance");
assert.match(studioSource, /bulkSelectionGuidance/, "Reup Queue studio state must provide bulk selection guidance");
assert.match(pageSource, /primaryQueueAction/, "Reup Queue tiles must use contextual primary actions");
assert.match(pageSource, /buildQueueTileSecondaryLinks/, "Reup Queue tiles must build contextual secondary links");
assert.match(pageSource, /\/publishing\/export-packages\//, "Reup Queue must link to Export Packages");
assert.match(pageSource, /\/publishing\/publish-handoffs\//, "Reup Queue must link to Publish Handoffs");
assert.match(pageSource, /formatBatchResultSummary/, "Reup Queue must render structured batch results");
assert.match(pageSource, /CREATE_EXPORT_PACKAGE/, "Reup Queue must offer Export Package batch creation");
assert.match(pageSource, /CREATE_PUBLISH_HANDOFF/, "Reup Queue must offer Publish Handoff batch creation");

assert.match(studioSource, /needs_start/, "Studio state must model needs-start filter");
assert.match(studioSource, /in_production/, "Studio state must model in-production filter");
assert.match(globalCssSource, /\.reup-queue-hero-panel/, "Reup Queue hero panel must have dedicated CSS");
assert.match(globalCssSource, /\.reup-queue-studio-workspace/, "Reup Queue studio must have dedicated CSS hooks");
assert.match(globalCssSource, /\.capture-inbox-status-pill[\s\S]*border-radius: 999px/, "Status strip must inherit Capture Inbox pill styling");

assert.match(exportPackagesIndexSource, /ops-export-page|opsExportPackages/, "Export Package index page must exist");
assert.match(publishHandoffsIndexSource, /ops-handoffs-page|opsPublishHandoffs/, "Publish Handoff index page must exist");
assert.match(exportPackageDetailSource, /OpsDetailPanel/, "Export Package detail must use shared detail panel");
assert.match(publishHandoffDetailSource, /do(?:es)? not call platform APIs or auto-publish/, "Publish Handoff detail must preserve manual publishing boundary");
assert.match(pageSource, /is-promoted-pair/, "Queue tiles must use promoted action pair layout when Details is shown");
assert.match(globalCssSource, /\.reup-queue-tile-action-bar/, "Reup Queue tile actions must have dedicated spacing hook");
assert.match(pageSource, /reup-queue-tile-quick-links/, "Queue tiles must expose compact workflow shortcut links");
assert.doesNotMatch(pageSource, /P\{item\.priority\}/, "Queue tiles must not always show default P100 priority badge");
assert.match(pageSource, /queueTileScoreBadge/, "Queue tiles must derive score badge from metadata");
assert.match(pageSource, /useState<ReupQueueSortMode>\("active-first"\)/, "Reup Queue default sort must pin active jobs first");
assert.match(pageSource, /value="active-first"/, "Sort dropdown must expose active-first");
assert.doesNotMatch(
  pageSource,
  /capture-inbox-tile-metrics/,
  "Queue tiles must not spend half the card on Likes/Comments/Shares — keep those in Details"
);
assert.match(pageSource, /capture-inbox-tile-quick-meta/, "Queue tiles must keep compact Posted/Duration/Views chips");
assert.equal(queueTileMetric({ like_count: 1611, like_count_text: "1.6K" }, "like_count_text", "like_count"), "1,611", "queueTileMetric helper must still prefer exact counts for inspector/details");
assert.match(pageSource, /Clear visible/, "Done and Attention tabs must expose soft-clear bulk action");
assert.match(pageSource, /Delete permanently/, "Done and Attention tabs must expose purge bulk action for test cleanup");

console.log("reup-queue UI tests passed");
