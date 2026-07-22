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
assert.match(worklistSource, /work-studio-worklist-row/, "Each Worklist item must use shared Work studio row chrome");
assert.match(pageSource, /worklistStageLabel/, "Worklist must use short stage labels");
assert.match(pageSource, /worklistTranscriptHref/, "Worklist must deep-link Analyzed rows to Transcript");
assert.match(worklistSource, /worklistNoDialogueHint/, "Worklist must keep Skip dubbing context for No dialogue rows");
assert.match(
  worklistSource,
  /className=\{`reup-queue-worklist-status is-\$\{stageTone\}`\}[\s\S]*?title=\{\s*noDialogueHint/,
  "No-dialogue guidance must live on the status chip title, not a fake CTA"
);
assert.doesNotMatch(worklistSource, /reup-queue-worklist-no-dialogue/, "Worklist must not keep a dedicated no-dialogue action chip");
assert.doesNotMatch(
  worklistSource.slice(worklistSource.indexOf("reup-queue-worklist-actions")),
  /\{noDialogueHint\}/,
  "Worklist actions must not render the long Skip dubbing hint as a button label"
);
assert.doesNotMatch(pageSource, /\/ops\/jobs/, "Worklist must not deep-link Ops job monitor");
assert.match(pageSource, /primaryQueueActionLabel/, "Worklist must share Gallery primary CTA labels");
assert.doesNotMatch(
  worklistSource,
  /worklistPrimaryActionLabel/,
  "Worklist must not invent separate short CTA labels"
);
assert.match(pageSource, /worklistStageTone/, "Worklist must map stage colors for downloading/ready/paused");
assert.match(worklistSource, /reup-queue-worklist-status-col/, "Worklist must keep status in a dedicated column");
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
assert.doesNotMatch(worklistSource, /downloadJobErrorLine|downloadError/, "Worklist must keep job errors out of the dense rail");
assert.doesNotMatch(worklistSource, /queueTileScoreBadge|worklist-score/, "Worklist must not show score chips in the rail");
assert.doesNotMatch(worklistSource, /queueTilePostedLabel|queueTileViewsLabel|queueTileDurationLabel/, "Worklist rail must not show posted/views/duration meta");
assert.doesNotMatch(worklistSource, /capture-inbox-reup-score-badge|tierLabel/, "Worklist must not reuse gallery score badges");

assert.match(cssSource, /\.work-studio-worklist/, "Shared Worklist surface must have dedicated CSS");
assert.match(
  cssSource,
  /\.work-studio-worklist[\s\S]*gap:\s*0\.75rem/,
  "Soft worklist must space rows apart for item separation"
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
  /grid-template-columns:\s*auto\s+52px\s+minmax\(0,\s*1fr\)\s+10\.5rem\s+minmax\(12\.5rem,\s*auto\)/,
  "Soft worklist must reserve a fixed CTA column so Ready/Waiting rows share one right edge"
);
assert.match(cssSource, /\.reup-queue-worklist-action\.is-with-icon/, "Soft worklist must style icon+text actions");
assert.match(cssSource, /\.reup-queue-worklist-status\.is-active/, "Soft worklist must support active/downloading blue tone");
assert.match(cssSource, /\.reup-queue-worklist-progress-ring/, "Soft worklist must style the circular progress ring");
assert.doesNotMatch(
  cssSource,
  /\.reup-queue-worklist-progress-stack/,
  "Soft worklist must not keep the redundant progress stack layout"
);

console.log("reup-queue-view-mode tests passed");
