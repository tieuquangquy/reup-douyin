/**
 * Work item action buttons must render leading icon + text (Capture / Review / Reup).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const iconSource = readFileSync(resolve(webSrc, "components/shared/WorkItemActionIcon.tsx"), "utf8");
const captureSource = readFileSync(resolve(webSrc, "components/capture-inbox/CaptureInboxTileActions.tsx"), "utf8");
const reviewSource = readFileSync(resolve(webSrc, "components/review-board/ReviewBoardTileActions.tsx"), "utf8");
const reupSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");
const cssSource = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(iconSource, /export function WorkItemActionIcon/, "Shared WorkItemActionIcon must exist");
assert.match(iconSource, /fill=\"currentColor\"/, "Icons must use solid filled glyphs");
assert.match(iconSource, /promote[\s\S]*lift up|11\.2 15\.2V8\.6/, "Promote must use lift-up metaphor");
assert.match(iconSource, /send[\s\S]*share|2\.2 2\.2 0 1 1 0 4\.4/, "Send must use share-nodes metaphor");
assert.match(iconSource, /details[\s\S]*stacked|5\.5 6\.2h13/, "Details must use list-lines metaphor");
assert.match(iconSource, /later[\s\S]*moon|14\.2 4\.6/, "Later must use moon/snooze metaphor");
assert.match(iconSource, /reject[\s\S]*thumbs|14\.8 4\.5H8\.6/, "Reject must use thumbs-down metaphor");
assert.match(iconSource, /transcript[\s\S]*speech|6\.5 4\.8h11/, "Transcript must use speech-bubble metaphor");

assert.match(captureSource, /WorkItemActionIcon/, "Capture tile actions must use WorkItemActionIcon");
assert.match(captureSource, /review-board-tile-btn__icon|WorkItemActionIcon/, "Capture buttons must expose icon slot");
assert.match(reviewSource, /WorkItemActionIcon/, "Review tile actions must use WorkItemActionIcon");
assert.match(reupSource, /WorkItemActionIcon/, "Reup Queue must use WorkItemActionIcon");

assert.match(
  cssSource,
  /\.review-board-tile-btn\s*\{[^}]*gap:\s*6px/,
  "Tile buttons must use icon+text gap"
);
assert.match(cssSource, /\.review-board-tile-btn__icon/, "CSS must size tile action icons");
assert.doesNotMatch(
  cssSource,
  /\.review-board-tile-btn\.is-primary::after\s*\{[^}]*content:\s*"→"/,
  "Primary tile buttons must not keep CSS arrow pseudo-content"
);

assert.match(reupSource, /is-with-icon|WorkItemActionIcon/, "Worklist actions must be icon+text");
assert.doesNotMatch(
  reupSource,
  /reup-queue-worklist-icon-action/,
  "Worklist must leave circular icon-only action controls"
);

console.log("work-item-action-icon-text tests passed");
