import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  REUP_QUEUE_VIEW_MODE_DEFAULT,
  REUP_QUEUE_VIEW_MODE_LABELS,
  REUP_QUEUE_VIEW_MODE_STORAGE_KEY,
  readReupQueueViewMode,
  resolveReupQueueViewMode,
  writeReupQueueViewMode
} from "../lib/reupQueueViewMode";

assert.equal(REUP_QUEUE_VIEW_MODE_DEFAULT, "gallery");
assert.equal(REUP_QUEUE_VIEW_MODE_LABELS.gallery, "Gallery");
assert.equal(REUP_QUEUE_VIEW_MODE_LABELS.worklist, "Worklist");
assert.equal(resolveReupQueueViewMode("worklist"), "worklist");
assert.equal(resolveReupQueueViewMode("gallery"), "gallery");
assert.equal(resolveReupQueueViewMode("table"), "gallery");
assert.equal(resolveReupQueueViewMode(null), "gallery");

const memory = new Map<string, string>();
const storage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => {
    memory.set(key, value);
  }
};

assert.equal(readReupQueueViewMode(storage), "gallery");
assert.equal(writeReupQueueViewMode("worklist", storage), true);
assert.equal(memory.get(REUP_QUEUE_VIEW_MODE_STORAGE_KEY), "worklist");
assert.equal(readReupQueueViewMode(storage), "worklist");

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/reup-queue/ReupQueuePage.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");

assert.match(pageSource, /WorkViewToggle/, "Reup Queue must expose Gallery/Worklist toggle in shared Work chrome");
assert.match(
  pageSource,
  /<WorkGalleryHeader[\s\S]*WorkViewToggle/,
  "View mode toggle must sit on the gallery/worklist content header"
);
assert.doesNotMatch(
  pageSource.slice(pageSource.indexOf("function ReupQueueStudioFilters"), pageSource.indexOf("function ReupQueueGalleryPreloading")),
  /WorkViewToggle/,
  "View mode must not remain in the search/sort filter deck"
);
assert.match(pageSource, /ReupQueueWorklistRow/, "Reup Queue must render dense worklist rows");
assert.match(pageSource, /readReupQueueViewMode/, "Reup Queue must restore view mode preference");
assert.match(pageSource, /writeReupQueueViewMode/, "Reup Queue must persist view mode preference");
assert.match(pageSource, /viewMode === "worklist"/, "Reup Queue must switch gallery vs worklist rendering");

const worklistSource = pageSource.slice(
  pageSource.indexOf("function ReupQueueWorklistRow"),
  pageSource.indexOf("function ReupQueueMediaTile")
);

assert.match(pageSource, /reup-queue-worklist work-studio-worklist/, "Worklist must use shared Work studio list chrome");
assert.doesNotMatch(pageSource, /reup-queue-worklist-header/, "Stage Stack must not render a rigid table header");
assert.match(pageSource, /is-stage-stack/, "Worklist must use the grouped Stage Stack authority class");
assert.doesNotMatch(pageSource, /is-media-rail/, "Worklist must leave the flat Media rail concept");
assert.doesNotMatch(pageSource, /is-operations-table/, "Worklist must leave the rigid operations-table concept");
assert.doesNotMatch(pageSource, /reup-queue-worklist[^\n]*is-soft/, "Worklist must leave the floating soft-card stack");
assert.match(pageSource, /const worklistGroups = useMemo\(\(\) => groupReupQueueWorklistItems\(visibleItems\)/, "Stage Stack must group the visible queue before rendering rows");
assert.match(pageSource, /worklistStageGroupHint\(group\.label, group\.tone\)/, "Stage header must own the visible status context for its rows");
assert.match(pageSource, /reup-queue-stage-group/, "Stage Stack must render a dedicated surface for each stage");
assert.match(pageSource, /reup-queue-stage-count/, "Every stage header must expose its visible item count");
assert.match(pageSource, /collapsedWorklistStages/, "Stage Stack must keep independent open or closed state for each stage");
assert.match(pageSource, /toggleWorklistStage/, "Stage headers must toggle their own stage panel");
assert.match(pageSource, /document\.addEventListener\("pointerdown", handlePagePointerDown, true\)/, "Marquee selection must start from anywhere on the page");
assert.match(pageSource, /document\.addEventListener\("pointermove", handlePagePointerMove, true\)/, "Page-level pointer movement must update marquee selection");
assert.match(pageSource, /document\.addEventListener\("pointerup", handlePagePointerEnd, true\)/, "Page-level pointer release must finish marquee selection safely");
assert.match(pageSource, /document\.addEventListener\("click", handlePageClickCapture, true\)/, "A completed drag must suppress the following native click anywhere on the page");
assert.match(pageSource, /pageDragTargetBlocksMarquee/, "Editable form controls must remain protected from page-level drag selection");
assert.doesNotMatch(pageSource, /onPointerDown=\{handleWorklistPointerDown\}/, "Marquee start must no longer be scoped to the worklist element");
const pagePointerDownSource = pageSource.slice(
  pageSource.indexOf("function handlePagePointerDown"),
  pageSource.indexOf("function handlePagePointerMove")
);
const pagePointerMoveSource = pageSource.slice(
  pageSource.indexOf("function handlePagePointerMove"),
  pageSource.indexOf("function handlePagePointerEnd")
);
assert.doesNotMatch(pagePointerDownSource, /setPointerCapture/, "A normal button click must not lose its pointer target to page-level capture");
assert.match(
  pagePointerMoveSource,
  /if \(!session\.started\)[\s\S]*session\.started = true;[\s\S]*setPointerCapture/,
  "Pointer capture must begin only after movement crosses the marquee threshold"
);
assert.doesNotMatch(
  pageSource,
  /worklistTargetBlocksMarquee/,
  "Marquee must be able to start anywhere inside the Stage Stack canvas"
);
assert.match(pageSource, /scheduleWorklistMarqueeUpdate/, "Pointer and scroll updates must share a frame-throttled marquee scheduler");
assert.match(pageSource, /worklistSelectionFrameRef/, "Worklist must coalesce repeated pointer updates into one animation frame");
assert.match(pageSource, /selectionEntries:\s*readWorklistSelectionEntries\(worklistSurfaceRef\.current\)/, "Marquee must snapshot row geometry once at gesture start");
const marqueeUpdateSource = pageSource.slice(
  pageSource.indexOf("const updateWorklistMarqueeSelection"),
  pageSource.indexOf("const stopWorklistAutoScroll")
);
assert.doesNotMatch(marqueeUpdateSource, /querySelectorAll|getBoundingClientRect/, "Animation frames must not repeatedly measure every queue row");
assert.match(pageSource, /document\.addEventListener\("dragstart", handlePageDragStart, true\)/, "Native image or link dragging must not steal a page-level marquee gesture");
assert.match(pageSource, /reup-queue-selection-marquee/, "Worklist must render a visible desktop-style selection rectangle");
assert.match(pageSource, /data-queue-item-id=\{item\.id\}/, "Every worklist row must expose a stable id for marquee hit testing");
assert.match(pageSource, /handleWorklistRowSelection/, "Worklist must support Ctrl-click and Shift-click selection semantics");
assert.match(pageSource, /window\.addEventListener\("scroll"/, "Active marquee selection must follow wheel and page scrolling");
assert.match(pageSource, /if \(!selectedCount\) return null;/, "Bulk action dock must leave no empty layout slot without a selection");
assert.match(pageSource, /aria-expanded=\{!collapsed\}/, "Stage headers must expose expanded state to assistive technology");
assert.match(pageSource, /aria-controls=\{panelId\}/, "Stage headers must identify the controlled item panel");
assert.match(pageSource, /hidden=\{collapsed\}/, "Collapsed stages must hide their queue rows without changing queue data");
assert.match(pageSource, /reup-queue-stage-chevron/, "Stage headers must show a clear expand or collapse affordance");
assert.match(worklistSource, /work-studio-worklist-row/, "Each Worklist item must use shared Work studio row chrome");
assert.match(pageSource, /worklistStageLabel/, "Worklist must use short stage labels");
assert.match(pageSource, /worklistTranscriptHref/, "Worklist must deep-link Analyzed rows to Transcript");
assert.doesNotMatch(worklistSource, /worklistNoDialogueHint/, "Stage-owned rows must not repeat No dialogue context inside every row");
assert.doesNotMatch(worklistSource, /reup-queue-worklist-status is-/, "Stage-owned rows must not repeat the stage as a button-like status pill");
assert.match(pageSource, /label === "No dialogue"[\s\S]{0,100}Skip dubbing/, "No-dialogue guidance must remain visible once at the stage header");
assert.doesNotMatch(pageSource, /\/ops\/jobs/, "Worklist must not deep-link Ops job monitor");
assert.match(pageSource, /primaryQueueActionLabel/, "Worklist must share Gallery primary CTA labels");
assert.doesNotMatch(
  worklistSource,
  /worklistPrimaryActionLabel/,
  "Worklist must not invent separate short CTA labels"
);
assert.match(pageSource, /worklistStageTone/, "Worklist must map stage colors for downloading/ready/paused");
assert.match(worklistSource, /downloadProgress != null \? \([\s\S]*reup-queue-worklist-status-col/, "Worklist must reserve the former status column for active progress only");
assert.match(worklistSource, /reup-queue-worklist-progress-ring/, "Worklist must show a single circular progress ring when downloading");
assert.doesNotMatch(
  worklistSource,
  /reup-queue-worklist-progress-stack|reup-queue-worklist-progress-inline/,
  "Worklist must not duplicate progress as a linear bar plus percent text"
);
assert.match(worklistSource, /reup-queue-worklist-title-text/, "Worklist titles must clamp on an inner text node");
assert.match(worklistSource, /is-with-icon/, "Worklist actions must use icon+text controls");
assert.match(worklistSource, /WorkItemActionIcon/, "Worklist must render shared WorkItemActionIcon SVGs");
assert.doesNotMatch(worklistSource, /reup-queue-worklist-icon-action/, "Worklist must leave circular icon-only action controls");
assert.doesNotMatch(worklistSource, /downloadJobErrorLine|downloadError/, "Worklist must keep job errors out of dense stage rows");
assert.doesNotMatch(worklistSource, /queueTileScoreBadge|worklist-score/, "Worklist must not show score chips in stage rows");
assert.doesNotMatch(worklistSource, /queueTilePostedLabel|queueTileViewsLabel|queueTileDurationLabel/, "Stage rows must not show posted/views/duration meta");
assert.doesNotMatch(worklistSource, /capture-inbox-reup-score-badge|tierLabel/, "Worklist must not reuse gallery score badges");

assert.match(cssSource, /\.work-studio-worklist/, "Shared Worklist surface must have dedicated CSS");
assert.match(cssSource, /\.reup-queue-worklist\.is-rail\.is-dense\.is-stage-stack/, "Stage Stack must have one scoped CSS authority");
assert.match(cssSource, /\.reup-queue-stage-group\s*\{[\s\S]{0,320}border:/, "Each stage must render as a bounded work group");
assert.match(cssSource, /\.reup-queue-stage-heading\s*\{[\s\S]{0,360}grid-template-columns:/, "Stage headers must align marker, label, count, and context");
assert.match(cssSource, /\.reup-queue-stage-heading:hover/, "Clickable stage headers must provide hover feedback");
assert.match(cssSource, /\.reup-queue-stage-heading:focus-visible/, "Clickable stage headers must provide keyboard focus feedback");
assert.match(cssSource, /\.reup-queue-stage-group\.is-collapsed[\s\S]{0,260}reup-queue-stage-chevron/, "Collapsed stages must rotate the header chevron");
assert.match(cssSource, /\.reup-queue-selection-marquee\s*\{[\s\S]{0,360}pointer-events:\s*none;/, "Marquee rectangle must remain visual-only and never block pointer events");
assert.match(cssSource, /\.reup-queue-worklist\.is-marquee-selecting/, "Worklist must suppress text selection while marquee dragging");
assert.match(cssSource, /body\.is-reup-queue-marquee-selecting/, "Page-level marquee must expose crosshair and suppress text selection across the document");
assert.match(cssSource, /body\.is-reup-queue-marquee-selecting[\s\S]{0,520}reup-queue-worklist-row[\s\S]{0,120}transition:\s*none;/, "Rows must not animate selection paint while marquee dragging");
assert.doesNotMatch(cssSource, /\.reup-queue-bulk-command-bar\.is-idle\s*\{[\s\S]{0,180}visibility:\s*hidden;/, "Bulk action dock must not reserve hidden layout space");
assert.match(
  cssSource,
  /\.reup-queue-bulk-stack\.is-sticky\s*\{[\s\S]{0,360}bottom:[^;]+;[\s\S]{0,160}position:\s*fixed;/,
  "Selected bulk actions must float outside document layout at the bottom of the viewport"
);
assert.match(
  cssSource,
  /\.reup-queue-stage-items\[hidden\]\s*\{[\s\S]{0,80}display:\s*none;/,
  "Collapsed stage panels must override the Stage Stack grid display"
);
assert.match(
  cssSource,
  /\.reup-queue-worklist-title-text[\s\S]*-webkit-line-clamp:\s*2/,
  "Worklist titles must clamp to two lines on the inner text node"
);
assert.doesNotMatch(
  cssSource,
  /\.reup-queue-worklist-title\s*\{[\s\S]{0,220}-webkit-line-clamp/,
  "Worklist title button itself must not use webkit-line-clamp"
);
assert.match(
  cssSource,
  /\.is-stage-stack[\s\S]*grid-template-columns:\s*1\.25rem\s+48px\s+minmax\(0,\s*1fr\)\s+auto\s+8rem/,
  "Stage rows must prioritize thumbnail and caption while keeping a compact CTA rail"
);
assert.match(cssSource, /\.reup-queue-worklist-action\.is-with-icon/, "Soft worklist must style icon+text actions");
assert.match(cssSource, /\.reup-queue-worklist-progress-ring/, "Soft worklist must style the circular progress ring");
assert.doesNotMatch(
  cssSource,
  /\.reup-queue-worklist-progress-stack/,
  "Stage Stack must not keep the redundant progress stack layout"
);
assert.match(cssSource, /@media \(max-width:\s*920px\)[\s\S]*\.is-stage-stack[\s\S]*grid-template-columns:\s*1\.25rem\s+48px\s+minmax\(0,\s*1fr\)/, "Stage rows must stack status and action below the caption on narrow screens");
assert.match(cssSource, /\.reup-queue-worklist\.is-stage-stack \.reup-queue-worklist-actions\s*\{[\s\S]{0,240}grid-column:\s*5;/, "The single row CTA must occupy its own far-right command column");
assert.match(
  cssSource,
  /\.reup-queue-worklist\.is-stage-stack \.reup-queue-worklist-action\s*\{[\s\S]{0,260}min-height:\s*1\.95rem;[\s\S]{0,160}padding:\s*0\.3rem\s+0\.58rem;/,
  "Stage row buttons must use a compact 31px content-sized control"
);
assert.match(
  cssSource,
  /\.reup-queue-worklist\.is-stage-stack \.reup-queue-worklist-actions > :only-child\s*\{[\s\S]{0,80}width:\s*auto;/,
  "A single row action must stay content-width instead of filling the CTA rail"
);
assert.match(cssSource, /\.is-stage-stack \.reup-queue-worklist-action__icon[\s\S]{0,140}height:\s*0\.82rem/, "Compact buttons must use a balanced icon size");

console.log("reup-queue-view-mode tests passed");
