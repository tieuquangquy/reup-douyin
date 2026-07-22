import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(testDir, "..");
const capturePage = readFileSync(resolve(webRoot, "components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
const captureActions = readFileSync(resolve(webRoot, "components/capture-inbox/CaptureInboxTileActions.tsx"), "utf8");
const reviewPage = readFileSync(resolve(webRoot, "components/review-board/ReviewBoardPage.tsx"), "utf8");
const reviewActions = readFileSync(resolve(webRoot, "components/review-board/ReviewBoardTileActions.tsx"), "utf8");
const queuePage = readFileSync(resolve(webRoot, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

for (const [name, source] of [
  ["Capture Inbox", capturePage],
  ["Review Board", reviewPage],
  ["Reup Queue", queuePage],
] as const) {
  assert.match(source, /AsyncContentBoundary/, `${name} must consolidate list states through AsyncContentBoundary`);
  assert.match(source, /useAsyncAction/, `${name} must use keyed async action state`);
  assert.match(source, /useNotice/, `${name} must publish async completion and failure notices`);
}

assert.match(capturePage, /capture-item:\$\{item\.id\}:\$\{action\}/, "Capture Inbox item actions must use per-item pending keys");
assert.match(captureActions, /<AsyncButton/, "Capture Inbox tile actions must render immediate pending feedback");
assert.match(
  capturePage,
  /if \(action === "promote_now"\) \{[\s\S]*?const summary = buildPromoteSuccessSummary\(response\);[\s\S]*?notify\(\{ message: summary\.message, tone: "success" \}\)/,
  "Capture promotion must publish its completion through the global toast"
);
assert.doesNotMatch(capturePage, /capture-inbox-promote-success/, "Capture promotion must not duplicate its toast with an inline success panel");
assert.doesNotMatch(capturePage, /setPromoteSuccess/, "Toast-only promotion must not call the removed inline-panel state setter");
assert.match(reviewPage, /candidate:\$\{candidateId\}:\$\{action\}/, "Review Board mutations must use per-candidate pending keys");
assert.match(reviewActions, /<AsyncButton/, "Review Board tile actions must render immediate pending feedback");
assert.match(queuePage, /queue-item:\$\{item\.id\}:\$\{action\}/, "Reup Queue item actions must use per-row pending keys");
assert.match(queuePage, /bulk:\$\{action\}/, "Reup Queue bulk actions must use per-action pending keys");
assert.match(queuePage, /<AsyncButton/, "Reup Queue row and bulk controls must render immediate pending feedback");
assert.match(queuePage, /ACTIVE_DOWNLOAD_POLL_MS/, "Reup Queue must preserve long-job polling semantics");

console.log("async UX migration group 1 tests passed");
