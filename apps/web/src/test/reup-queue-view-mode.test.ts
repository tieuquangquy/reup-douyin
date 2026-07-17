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

assert.match(pageSource, /reup-queue-view-toggle/, "Reup Queue must expose Gallery/Worklist toggle");
assert.match(pageSource, /ReupQueueWorklistRow/, "Reup Queue must render dense worklist rows");
assert.match(pageSource, /readReupQueueViewMode/, "Reup Queue must restore view mode preference");
assert.match(pageSource, /writeReupQueueViewMode/, "Reup Queue must persist view mode preference");
assert.match(pageSource, /viewMode === "worklist"/, "Reup Queue must switch gallery vs worklist rendering");

const worklistSource = pageSource.slice(
  pageSource.indexOf("function ReupQueueWorklistRow"),
  pageSource.indexOf("function ReupQueueMediaTile")
);

assert.match(pageSource, /reup-queue-worklist is-rail is-dense is-soft/, "Worklist must use spaced soft-row chrome");
assert.match(pageSource, /worklistStageLabel/, "Worklist must use short stage labels");
assert.match(pageSource, /worklistTranscriptHref/, "Worklist must deep-link Analyzed rows to Transcript");
assert.match(pageSource, /worklistNoDialogueHint/, "Worklist must surface Skip dubbing when analyze finds no speech");
assert.match(pageSource, /shouldShowWorklistOpenJobLink/, "Worklist must hide Open job after analyze completes");
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
assert.match(worklistSource, /reup-queue-worklist-icon-action/, "Worklist secondary actions must use icon-circle controls");
assert.match(worklistSource, /WorklistActionIcon/, "Worklist must render SVG icons for Pause/Resume/Details");
assert.doesNotMatch(worklistSource, /downloadJobErrorLine|downloadError/, "Worklist must keep job errors out of the dense rail");
assert.doesNotMatch(worklistSource, /queueTileScoreBadge|worklist-score/, "Worklist must not show score chips in the rail");
assert.doesNotMatch(worklistSource, /queueTilePostedLabel|queueTileViewsLabel|queueTileDurationLabel/, "Worklist rail must not show posted/views/duration meta");
assert.doesNotMatch(worklistSource, /capture-inbox-reup-score-badge|tierLabel/, "Worklist must not reuse gallery score badges");

assert.match(cssSource, /\.reup-queue-worklist\.is-rail\.is-dense\.is-soft/, "Soft dense rail must have dedicated CSS hook");
assert.match(
  cssSource,
  /\.reup-queue-worklist\.is-rail\.is-dense\.is-soft[\s\S]*gap:\s*0\.75rem/,
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
  /grid-template-columns:\s*auto\s+52px\s+minmax\(0,\s*1fr\)\s+10\.5rem\s+auto/,
  "Soft worklist must use mock-aligned ops grid"
);
assert.match(cssSource, /\.reup-queue-worklist-icon-action/, "Soft worklist must style circular icon actions");
assert.match(cssSource, /\.reup-queue-worklist-status\.is-active/, "Soft worklist must support active/downloading blue tone");
assert.match(cssSource, /\.reup-queue-worklist-progress-ring/, "Soft worklist must style the circular progress ring");
assert.doesNotMatch(
  cssSource,
  /\.reup-queue-worklist-progress-stack/,
  "Soft worklist must not keep the redundant progress stack layout"
);

console.log("reup-queue-view-mode tests passed");
