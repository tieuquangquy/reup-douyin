/**
 * Work pages share one compact media tile overlay (micro rail).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const overlaySource = readFileSync(resolve(webSrc, "components/shared/WorkMediaTileOverlay.tsx"), "utf8");
const cssSource = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const captureSource = readFileSync(resolve(webSrc, "components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
const reviewSource = readFileSync(resolve(webSrc, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const reupSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

assert.match(overlaySource, /export function WorkMediaTileOverlay/, "Shared overlay component must exist");
assert.match(overlaySource, /density = "compact"/, "Work tiles must default to compact micro rail");
assert.match(overlaySource, /is-compact/, "Compact overlay must expose is-compact class");
assert.match(overlaySource, /statusChips\.slice\(0, 1\)/, "Compact overlay must show only one status chip on tile");
assert.match(overlaySource, /work-media-tile-score-inline/, "Compact score badge must render inline score · tier");

assert.match(cssSource, /\.work-media-tile-overlay\.is-compact/, "CSS must style compact micro rail");
assert.match(cssSource, /\.work-media-tile-score-badge\.is-inline/, "CSS must style inline score badge");

assert.match(captureSource, /WorkMediaTileOverlay/, "Capture Inbox tiles must use shared overlay");
assert.match(reviewSource, /WorkMediaTileOverlay/, "Review Board tiles must use shared overlay");
assert.match(reupSource, /WorkMediaTileOverlay/, "Reup Queue tiles must use shared overlay");

assert.doesNotMatch(
  reviewSource.slice(reviewSource.indexOf("function CandidateMediaTile")),
  /In queue/,
  "Review compact tile must not render secondary In queue chip"
);
assert.doesNotMatch(
  reupSource.slice(reupSource.indexOf("function ReupQueueMediaTile")),
  /jobChip|work-media-tile-status-chip--job/,
  "Reup compact tile must not render secondary job chip"
);

console.log("work-media-tile-overlay tests passed");
