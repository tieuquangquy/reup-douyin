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
assert.match(pageSource, /22H-1R/, "Reup Queue UI version must identify Review Board parity");
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
  /\.reup-queue-media-tile[\s\S]*\.work-media-tile-overlay\.is-compact[\s\S]*max-width:\s*118px/,
  "Reup Queue compact status chips must fit Confirm ready / Transcript without fake truncation"
);
assert.match(studioSource, /isDownloadReadyForConfirm/, "Job chip must defer when download is ready for confirm");
assert.match(globalCssSource, /\.reup-queue-download-progress/, "Download progress bar must have dedicated CSS");
assert.match(pageSource, /kicker="Production queue"/, "Reup Queue deck must use a subdued workflow kicker instead of a second page title");
assert.match(
  pageSource,
  /shouldShowQueueTileDetailsButton/,
  "Queue gallery must gate quiet Open details for download-wait inspect tiles"
);
assert.doesNotMatch(pageSource, /is-promoted-details/, "Queue tiles must not render a secondary Details action");
assert.doesNotMatch(pageSource, />\s*Details\s*</, "Queue gallery and worklist tiles must not show a bare Details label");
assert.match(pageSource, /Open details/, "Download-wait inspect tiles must expose Open details");
assert.match(pageSource, /capture-inbox-media-thumbnail" onClick=\{onDetails\}/, "Queue gallery tiles must open details from the thumbnail");
assert.match(pageSource, /capture-inbox-tile-title[\s\S]*onClick=\{onDetails\}/, "Queue gallery tiles must open details from the title");
assert.match(pageSource, /reup-queue-worklist-thumb" onClick=\{onDetails\}/, "Queue worklist rows must open details from the thumbnail");
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
assert.match(pageSource, /reup-queue-hero-action-rail/, "Studio deck must place Start all ready in the Review-style action rail");
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
assert.match(pageSource, /WorkStudioDeck/, "Reup Queue must use shared Work studio deck chrome");
assert.match(pageSource, /capture-inbox-status-flow__lane is-pipeline/, "Reup Queue must group production stages in a pipeline lane");
assert.match(pageSource, /capture-inbox-status-flow__lane is-attention/, "Reup Queue must group attention and done stages separately");
assert.match(pageSource, /reup-queue-filter-deck/, "Reup Queue must use a Capture Inbox-style filter deck");
assert.match(pageSource, /WorkViewToggle/, "Reup Queue Gallery and Worklist toggle must live in shared Work chrome");
assert.match(
  pageSource,
  /<WorkGalleryHeader[\s\S]*Select visible[\s\S]*WorkViewToggle/,
  "Gallery header must place Select visible before the Gallery/Worklist toggle"
);
assert.doesNotMatch(
  pageSource.slice(pageSource.indexOf("function ReupQueueStudioFilters"), pageSource.indexOf("function ReupQueueGalleryPreloading")),
  /WorkViewToggle|reup-queue-filter-view/,
  "Filter deck must only own search and sort — not view mode"
);
assert.match(pageSource, /WorkBulkActionBar/, "Reup Queue lifecycle bulk actions must use shared Work bulk chrome");
assert.match(pageSource, /WorkGalleryHeader/, "Reup Queue content must use shared gallery heading hierarchy");
assert.match(pageSource, /WorkGalleryEmptyState/, "Reup Queue state branches must use shared Work gallery surfaces");
assert.match(pageSource, /reup-queue-gallery-empty/, "Reup Queue empty gallery must use a centered empty-state layout");
assert.match(pageSource, /reup-queue-empty-review-link[\s\S]*WorkItemActionIcon[\s\S]*kind="open"/, "Open Review Board empty CTA must include a leading action icon");
assert.match(pageSource, /glyph=\{\(/, "Reup Queue empty state must render a leading glyph");
assert.match(pageSource, /work-studio-worklist-row/, "Reup Queue Worklist rows must adopt the shared Work surface grammar");
assert.doesNotMatch(pageSource, /ReupQueueStatusStrip/, "Reup Queue must not duplicate status strip below hero chips");
assert.doesNotMatch(pageSource, /capture-inbox-gallery-summary/, "Reup Queue must not repeat hero counts in gallery summary");
assert.doesNotMatch(pageSource, /<OpsFilterBar/, "Reup Queue must not keep the generic filter panel");
assert.match(pageSource, /capture-inbox-media-tile/, "Reup Queue must render Capture Inbox-style media tiles");
assert.match(
  pageSource.slice(pageSource.indexOf("function ReupQueueMediaTile")),
  /selected \? "is-bulk-selected"/,
  "Bulk-selected Queue tiles must expose is-bulk-selected for the shared green selection ring"
);
assert.match(
  globalCssSource,
  /\.capture-inbox-media-tile\.is-bulk-selected(?:,[\s\S]*?\.review-board-media-tile\.is-bulk-selected)?\s*\{[^}]*border-color: var\(--accent\);[^}]*box-shadow: 0 0 0 2px color-mix\(in srgb, var\(--accent\) 38%, transparent\), var\(--shadow\);/,
  "Bulk-selected Queue gallery tiles must inherit the Capture/Review green outer ring"
);
assert.match(pageSource, /<WorkBulkActionBar/, "Reup Queue must use the shared sticky bulk action bar");
assert.match(globalCssSource, /\.reup-queue-bulk-stack\.is-sticky\s*\{[^}]*position: sticky;[^}]*top: 12px;[^}]*z-index: 8;/, "Queue bulk stack must stick at 12px while selected actions remain visible");
assert.match(pageSource, /reup-queue-bulk-stack is-sticky/, "Queue bulk stack must opt into sticky positioning when selection is active");
assert.match(pageSource, /WorkItemDetailsDrawer/, "Reup Queue must open details in WorkItemDetailsDrawer");
assert.doesNotMatch(pageSource, /capture-inbox-review-side/, "Reup Queue must not reserve sticky right inspector column");
assert.doesNotMatch(pageSource, /<OpsDetailPanel/, "Reup Queue drawer must use the Review Board detail hierarchy");
assert.match(pageSource, /WorkGalleryEmptyState/, "Reup Queue must use shared Work gallery state panels");

// Review Board visual-parity contract. Queue authority and lifecycle semantics stay queue-owned.
assert.match(pageSource, /reup-queue-command-deck/, "Reup Queue must use Review Board-style command deck chrome");
assert.match(pageSource, /capture-inbox-hero-action-rail reup-queue-hero-action-rail/, "Queue shortcuts must use the Review Board action rail hierarchy");
assert.match(pageSource, /ReupQueueStatusStatBars/, "Queue status cards must include compact mini bars");
assert.match(pageSource, /className="[^"]*reup-queue-filter-control is-search"/, "Queue search must be icon-led like Review Board");
assert.match(pageSource, /reup-queue-filter-search-icon/, "Queue search must render a leading search icon");
assert.match(pageSource, /reup-queue-filter-control__label">Sort by/, "Queue sort must use a micro-label");
assert.match(pageSource, /useTransition/, "Queue filter changes must preserve a stable transition surface");
assert.match(pageSource, /ReupQueueGalleryPreloading/, "Queue content must render a stable filter preloading state");
assert.match(pageSource, /operator-panel capture-inbox-media-gallery reup-queue-gallery-shell/, "Queue content must use the shared gallery surface hierarchy");
assert.match(pageSource, /Select visible/, "Queue gallery header must expose visible-scope selection");
assert.doesNotMatch(pageSource, />Selected scope</, "Queue bulk bar must not repeat the selected scope summary");
assert.doesNotMatch(pageSource, />Run on selected</, "Queue bulk bar must not repeat the selected action scope");
assert.match(pageSource, /if \(!selectedCount\) return null;/, "Queue bulk actions must only render after an item is selected");
assert.match(pageSource, /toolbar=\{\(/, "Queue bulk selection controls must live in the compact toolbar");
assert.match(pageSource, /bulkActionIconKind\(entry\.action\)/, "Queue bulk action buttons must use verb-specific icons");
assert.match(pageSource, /bulkActionButtonTone\(entry\.action\)/, "Queue bulk buttons must use semantic filled colors");
assert.match(pageSource, /reup-queue-bulk-actions/, "Queue bulk actions must render as one concise action group");
assert.match(globalCssSource, /\.reup-queue-bulk-btn\.is-queue-success\s*\{[^}]*background:/, "Queue success actions must have a filled background");
assert.match(globalCssSource, /\.reup-queue-bulk-btn\.is-queue-warning\s*\{[^}]*background:/, "Queue warning actions must have a filled background");
assert.match(globalCssSource, /\.reup-queue-bulk-btn\.is-queue-danger\s*\{[^}]*background:/, "Queue destructive actions must have a filled background");
assert.match(
  globalCssSource,
  /\.reup-queue-bulk-btn\.is-queue-success:hover:not\(:disabled\)\s*\{[^}]*background:[^}]*color:\s*#fff/,
  "Queue success hover must keep a filled green background and white label"
);
assert.match(
  globalCssSource,
  /\.reup-queue-bulk-btn\.is-queue-danger:hover:not\(:disabled\)\s*\{[^}]*background:[^}]*color:\s*#fff/,
  "Queue danger hover must keep a filled red background and white label"
);
assert.doesNotMatch(
  globalCssSource,
  /\.reup-queue-bulk-btn\[class\*="is-queue-"\]:hover:not\(:disabled\)\s*\{[^}]*filter:/,
  "Queue filled buttons must not rely on a filter-only hover that loses to the white deck-btn hover"
);
assert.match(pageSource, /reup-queue-inspector-summary-card/, "Queue inspector must start with a visual summary card");
assert.match(pageSource, /reup-queue-inspector-metadata-grid/, "Queue inspector must use two-column metadata cards");
assert.match(pageSource, /footer=\{item \? \(/, "Queue lifecycle actions must live in the drawer footer like Review Board");
assert.match(pageSource, /reup-queue-inspector-footer-actions[\s\S]*WorkItemActionIcon/, "Queue drawer footer actions must use the same icon-led hierarchy as Review Board");
assert.match(
  pageSource,
  /ReupQueueInspectorActions[\s\S]*review-board-tile-action-bar|review-board-tile-action-bar[\s\S]*is-inspector[\s\S]*reup-queue-tile-action-bar/,
  "Queue details footer must reuse the shared tile action bar so status CTAs match gallery tiles"
);
assert.match(
  pageSource,
  /queueTileTranscriptCta|primaryQueueAction|terminalQueueDismissAction/,
  "Queue details footer must gate primary CTAs with the same helpers as tiles"
);
assert.doesNotMatch(
  pageSource,
  /reup-queue-inspector-btn-grid/,
  "Queue details must not keep the legacy inspector button grid once tile-parity actions land"
);
{
  const applyQueueActionFn = pageSource.match(
    /async function applyQueueAction\([\s\S]*?(?=async function applyBatchAction)/
  )?.[0] ?? "";
  assert.ok(applyQueueActionFn.length > 0, "Must locate applyQueueAction");
  assert.doesNotMatch(
    applyQueueActionFn,
    /setQueueInspectorOpen\(true\)/,
    "Successful tile/inspector queue actions must not force-open Production details"
  );
  assert.match(
    applyQueueActionFn,
    /queueInspectorOpen[\s\S]*setActiveItemId/,
    "If the inspector is already open, refresh the active item after a successful action"
  );
  assert.match(
    applyQueueActionFn,
    /await loadQueue\(true\)/,
    "Single queue actions must refresh authoritative status_counts so Attention/pipeline boxes update without F5"
  );
}
assert.match(pageSource, /reup-queue-inspector-detail-grid/, "Queue inspector must group lifecycle details into compact cards");
assert.doesNotMatch(pageSource, /<OpsDetailPanel title="Queue detail panel">/, "Queue inspector must not wrap the redesigned content in the legacy Ops detail panel");
assert.match(pageSource, /CaptureInboxFilterChipIcon/, "Queue inspector metadata must use shared icon-led fields");
assert.doesNotMatch(pageSource, /Start processing → track media → export & handoff/, "Queue command deck must not keep the redundant workflow subtitle");
assert.match(pageSource, /review-board-filter-deck reup-queue-filter-deck/, "Queue filters must use the Review Board deck surface");
assert.match(pageSource, /review-board-command-deck-filters reup-queue-filter-controls/, "Queue filter controls must use the Review Board control grid");
assert.match(
  globalCssSource,
  /\.reup-queue-filter-controls\s*\{[^}]*grid-template-columns: minmax\(0,\s*1fr\) minmax\(250px,\s*300px\)/,
  "Queue filter deck must give the Sort control enough width for long option labels"
);
assert.match(
  globalCssSource,
  /\.reup-queue-filter-control\.is-sort \.review-board-deck-sort\s*\{[^}]*min-width: 0;[^}]*overflow: hidden;/,
  "Queue sort select must clip safely inside its control instead of overflowing the border"
);
assert.match(pageSource, /review-board-filter-control reup-queue-filter-control is-search/, "Queue search must reuse the Review Board field shell");
assert.match(pageSource, /review-board-deck-input review-board-deck-search/, "Queue search input must reuse Review Board input styling");
assert.match(pageSource, /review-board-command-deck-bulk review-board-bulk-command-bar reup-queue-bulk-command-bar/, "Queue bulk actions must use Review Board bulk chrome");
assert.match(pageSource, /className="review-board-deck-btn[^"]*reup-queue-bulk-btn/, "Queue bulk controls must use Review Board button hierarchy");

assert.match(studioSource, /label: "Download"/, "Reup Queue must expose Download pipeline filter");
assert.match(studioSource, /label: "Transcript"/, "Reup Queue must expose Transcript pipeline filter");
assert.match(studioSource, /label: "Render"/, "Reup Queue must expose Render pipeline filter");
assert.match(studioSource, /label: "Export"/, "Reup Queue must expose Export pipeline filter");
assert.doesNotMatch(studioSource, /label: "Needs start"/, "Needs start must not remain a pipeline chip label");
assert.doesNotMatch(studioSource, /label: "In production"/, "In production must not remain a pipeline chip label");
assert.match(pageSource, /\{ action: "START_PROCESSING", label: "Start"/, "Reup Queue must expose start processing action");
assert.match(pageSource, /CREATE_EXPORT_PACKAGE/, "Reup Queue must expose export batch action");
assert.match(pageSource, /CREATE_PUBLISH_HANDOFF/, "Reup Queue must expose handoff batch action");
assert.match(pageSource, /title="Production details"/, "Reup Queue must keep a clear production details title");
assert.match(
  pageSource,
  /filterInspectorCompanionActions/,
  "Queue details must stage-filter companion actions instead of dumping every available_action"
);
assert.match(
  studioSource,
  /export function filterInspectorCompanionActions/,
  "Studio state must own stage-aware details companion filtering"
);
assert.match(
  globalCssSource,
  /\.reup-queue-inspector-footer-actions[\s\S]*\.is-attention-compact/,
  "Attention compact row must pack Resume/Cancel/Dismiss horizontally"
);
assert.match(
  pageSource,
  /review-board-tile-action-bar[\s\S]*is-inspector[\s\S]*reup-queue-tile-action-bar/,
  "Inspector must use the shared tile action bar for status-gated CTAs"
);
assert.doesNotMatch(pageSource, /reup-queue-inspector-spotlight-btn/, "Inspector must not use oversized spotlight button class");
assert.match(pageSource, /Open workflows/, "Inspector must expose workflow navigation");
assert.doesNotMatch(pageSource, /card-actions[\s\S]*Open transcript editor/, "Inspector must not use legacy card-actions link row");
assert.match(studioSource, /buildInspectorWorkflowLinks/, "Studio state must build inspector workflow links");
assert.match(pageSource, /Queue lifecycle/, "Detail panel must show lifecycle section");
assert.match(pageSource, /Media prep/, "Detail panel must show media-prep section");
assert.match(pageSource, /Source engagement/, "Detail panel must show source engagement metrics");
assert.match(pageSource, /buildQueueInspectorEngagementStats/, "Queue Details must derive views/likes/comments/shares from shared studio helpers");
assert.doesNotMatch(
  pageSource.slice(pageSource.indexOf("function ReupQueueMediaTile"), pageSource.indexOf("function ReupQueueRightInspector")),
  /buildQueueInspectorEngagementStats|capture-inbox-tile-perf-rail/,
  "Queue gallery tiles must not render engagement rails — Details owns social metrics"
);
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
assert.match(pageSource, /reup-queue-status-flow/, "Reup Queue quick path must show Capture Inbox-style status lanes");
assert.doesNotMatch(pageSource, /reup-queue-hero-alert/, "Reup Queue must not show redundant quick-path guidance banner");
assert.doesNotMatch(pageSource, /quickPathGuidance/, "Reup Queue page must not wire quick-path guidance copy");
assert.match(studioSource, /buildQuickPathHeroStats/, "Reup Queue studio state must build hero stat chips");
assert.doesNotMatch(studioSource, /export function quickPathGuidance/, "Studio must not keep unused quick-path guidance helper");
assert.doesNotMatch(studioSource, /export function quickPathSuggestedFilter/, "Studio must not keep unused suggested-filter helper");
assert.match(studioSource, /bulkSelectionGuidance/, "Reup Queue studio state must provide bulk selection guidance");
assert.match(pageSource, /primaryQueueAction/, "Reup Queue tiles must use contextual primary actions");
assert.match(pageSource, /buildQueueTileSecondaryLinks/, "Reup Queue tiles must build contextual secondary links");
assert.match(pageSource, /\/publishing\/export-packages\//, "Reup Queue must link to Export Packages");
assert.match(pageSource, /\/publishing\/publish-handoffs\//, "Reup Queue must link to Publish Handoffs");
assert.match(pageSource, /formatBatchResultSummary/, "Reup Queue must render structured batch results");
assert.match(pageSource, /CREATE_EXPORT_PACKAGE/, "Reup Queue must offer Export Package batch creation");
assert.match(pageSource, /CREATE_PUBLISH_HANDOFF/, "Reup Queue must offer Publish Handoff batch creation");

assert.match(studioSource, /download/, "Studio state must model download pipeline filter");
assert.match(studioSource, /transcript/, "Studio state must model transcript pipeline filter");
assert.match(studioSource, /REUP_QUEUE_PIPELINE_FILTERS/, "Studio state must split pipeline vs attention lanes");
assert.match(studioSource, /REUP_QUEUE_ATTENTION_FILTERS/, "Studio state must keep attention lane filters");
assert.doesNotMatch(studioSource, /key: "needs_start"/, "Needs-start must not remain a pipeline chip key");
assert.doesNotMatch(studioSource, /in_production/, "In-production filter must be replaced by stage chips");
assert.match(pageSource, /REUP_QUEUE_PIPELINE_FILTERS/, "Quick path must place pipeline stage chips in the Pipeline lane");
assert.match(pageSource, /REUP_QUEUE_ATTENTION_FILTERS/, "Quick path must keep Handoff with Attention/Done");
assert.match(
  globalCssSource,
  /\.reup-queue-status-flow \.capture-inbox-status-flow__track\.is-compact\s*\{[^}]*grid-template-columns: repeat\(3, minmax\(0, 1fr\)\)/,
  "Attention lane (Handoff · Attention · Done) must stay on one row"
);
assert.match(globalCssSource, /\.reup-queue-hero-panel/, "Reup Queue hero panel must have dedicated CSS");
assert.match(globalCssSource, /\.reup-queue-studio-workspace/, "Reup Queue studio must have dedicated CSS hooks");
assert.match(globalCssSource, /\.capture-inbox-status-pill[\s\S]*border-radius: 999px/, "Status strip must inherit Capture Inbox pill styling");

assert.match(exportPackagesIndexSource, /ops-export-page|opsExportPackages/, "Export Package index page must exist");
assert.match(publishHandoffsIndexSource, /ops-handoffs-page|opsPublishHandoffs/, "Publish Handoff index page must exist");
assert.match(exportPackageDetailSource, /OpsDetailPanel/, "Export Package detail must use shared detail panel");
assert.match(publishHandoffDetailSource, /do(?:es)? not call platform APIs or auto-publish/, "Publish Handoff detail must preserve manual publishing boundary");
assert.doesNotMatch(pageSource, /is-promoted-pair/, "Queue tiles must not keep a Details+action promoted pair");
assert.match(globalCssSource, /\.reup-queue-tile-action-bar/, "Reup Queue tile actions must have dedicated spacing hook");
assert.match(pageSource, /reup-queue-tile-quick-links/, "Queue tiles must expose compact workflow shortcut links");
assert.doesNotMatch(pageSource, /P\{item\.priority\}/, "Queue tiles must not always show default P100 priority badge");
assert.match(pageSource, /useQueueTileScoreBadge/, "Queue tiles must derive score badge from metadata");
assert.match(pageSource, /useState<ReupQueueSortMode>\("active-first"\)/, "Reup Queue default sort must pin active jobs first");
assert.match(pageSource, /value="active-first"/, "Sort dropdown must expose active-first");
assert.doesNotMatch(
  pageSource,
  /capture-inbox-tile-metrics/,
  "Queue tiles must not spend half the card on Likes/Comments/Shares — keep those in Details"
);
assert.match(pageSource, /capture-inbox-tile-meta-line/, "Queue gallery tiles must use the Capture Inbox duration and posted meta line");
assert.doesNotMatch(pageSource, /capture-inbox-tile-quick-meta/, "Queue tiles must not keep legacy Posted/Duration/Views chips");
assert.doesNotMatch(pageSource, /queueTileViewsLabel\(item\)/, "Queue gallery tiles must leave estimated views to details instead of the production tile");
assert.match(pageSource, /reup-queue-pipeline-strip is-tile/, "Queue gallery tiles must mark pipeline progress for compact tile treatment");
assert.match(
  pageSource,
  /reup-queue-tile-bottom[\s\S]*reup-queue-pipeline-strip is-tile/,
  "Queue gallery pipeline must sit in the bottom stack so empty space grows above the stepper"
);
assert.match(
  pageSource,
  /capture-inbox-tile-main capture-inbox-compact-main[\s\S]*?<\/div>\s*<div className="reup-queue-tile-bottom"/,
  "Queue gallery main block must close before the bottom stack (title/meta only)"
);
assert.match(globalCssSource, /\.reup-queue-tile-bottom\s*\{[^}]*display: grid/, "Queue tile bottom stack must lay out pipeline and actions");
assert.match(pageSource, /reup-queue-pipeline-stepper/, "Queue tile pipeline must use a labeled horizontal stepper");
assert.match(pageSource, /reup-queue-pipeline-stepper__node/, "Queue tile stepper must render numbered or checked nodes");
assert.match(pageSource, /reup-queue-pipeline-stepper__label/, "Queue tile stepper must show stage labels under each node");
assert.doesNotMatch(pageSource, /reup-queue-pipeline-strip__focus|pipelineTileFocusLabel/, "Queue tile stepper must not keep the single Now-focus caption");
assert.match(globalCssSource, /\.reup-queue-pipeline-stepper\s*\{[^}]*width: 100%;[^}]*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/, "Queue tile stepper must span the full tile width with four stages");
assert.match(globalCssSource, /\.reup-queue-pipeline-stepper__step:first-child[\s\S]*justify-items: start/, "Queue tile stepper must pin the first stage to the left edge");
assert.match(globalCssSource, /\.reup-queue-pipeline-stepper__step:last-child[\s\S]*justify-items: end/, "Queue tile stepper must pin the last stage to the right edge");
assert.match(pageSource, /pipelineStageInteraction/, "Queue tile stepper must gate click actions per stage");
assert.match(
  pageSource,
  /reup-queue-pipeline-stepper__hit[\s\S]*target="_blank"[\s\S]*rel="noopener noreferrer"|reup-queue-pipeline-stepper__hit[\s\S]*rel="noopener noreferrer"[\s\S]*target="_blank"/,
  "Queue tile stepper deep-links must open in a new browser tab"
);
assert.match(pageSource, /revealSourceVideoLocalAsset/, "Queue tile Download step must call the local reveal API");
assert.match(globalCssSource, /\.reup-queue-pipeline-stepper__step\.is-interactive:hover/, "Queue tile stepper must expose hover feedback on interactive steps");
assert.match(globalCssSource, /\.reup-queue-pipeline-stepper__step\.is-active[\s\S]*animation:/, "Active stepper nodes must use a subtle motion cue");
assert.doesNotMatch(studioSource, /label: "Open transcript"/, "Secondary tile links must not duplicate Open transcript under the stepper");
assert.doesNotMatch(
  studioSource.slice(
    studioSource.indexOf("export function buildQueueTileSecondaryLinks"),
    studioSource.indexOf("export function operatorStatusLabel")
  ),
  /worklistTranscriptHref|Open transcript/,
  "buildQueueTileSecondaryLinks must not wire transcript — primary CTA + stepper own that deep-link"
);
assert.match(studioSource, /export function queueTileTranscriptCta/, "Gallery tiles must expose an Open Transcript CTA helper");
assert.match(studioSource, /export function queueTileFailureAlert/, "Gallery tiles must expose a compact failure alert for analyze/download errors");
assert.match(studioSource, /export function queueTileNextStepHint/, "Gallery tiles must expose a visible next-step hint when Transcript is blocked");
assert.match(pageSource, /queueTileTranscriptCta/, "Gallery tile must render Open Transcript from shared CTA helper");
assert.match(pageSource, /queueTileFailureAlert/, "Gallery tile must render compact failure alert instead of stacked error+hint");
assert.match(pageSource, /reup-queue-tile-failure-alert/, "Gallery failure alert must use a dedicated compact class");
assert.match(pageSource, /reup-queue-tile-failure-alert__icon/, "Gallery failure alert must show a leading status icon");
assert.match(pageSource, /reup-queue-tile-failure-alert__text/, "Gallery failure alert message must use regular-weight text span");
assert.match(pageSource, /queueTileNextStepHint/, "Gallery tile must show next-step hint when analyze is not ready");
assert.match(pageSource, /Open Transcript/, "Gallery tile must label the Transcript CTA for operators");
assert.match(pageSource, /reup-queue-tile-stage-hint/, "Gallery tile must surface a visible stage hint under the stepper");
assert.equal(queueTileMetric({ like_count: 1611, like_count_text: "1.6K" }, "like_count_text", "like_count"), "1,611", "queueTileMetric helper must still prefer exact counts for inspector/details");
assert.match(pageSource, /Clear visible/, "Done and Attention tabs must expose soft-clear bulk action");
assert.match(pageSource, /Delete permanently/, "Done and Attention tabs must expose purge bulk action for test cleanup");

console.log("reup-queue UI tests passed");
