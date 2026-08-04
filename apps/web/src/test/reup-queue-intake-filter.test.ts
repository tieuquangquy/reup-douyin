import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrcDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const apiSource = readFileSync(resolve(webSrcDir, "lib/api.ts"), "utf8");
const queuePageSource = readFileSync(resolve(webSrcDir, "components/reup-queue/ReupQueuePage.tsx"), "utf8");

// The queue pages 100 items at a time and reads its status tiles from the API response,
// so the intake filter has to travel with the request rather than trimming the page.
const fetchBlock = apiSource.slice(
  apiSource.indexOf("export async function fetchReupQueueItems"),
  apiSource.indexOf("export async function fetchReupQueueItem(")
);
assert.match(
  fetchBlock,
  /params\.set\("capture_session_id", filters\.captureSessionId\)/,
  "fetchReupQueueItems must send the intake batch filter"
);
assert.match(fetchBlock, /params\.set\("created_after"/, "fetchReupQueueItems must send the date lower bound");
assert.match(fetchBlock, /params\.set\("created_before"/, "fetchReupQueueItems must send the date upper bound");
assert.match(
  fetchBlock,
  /intakeDateRange\(/,
  "The queue must resolve date chips with the same helper as the Review Board"
);

// Both the first page and the infinite-scroll pages must carry the same filter, or
// scrolling would quietly pull in clips from other batches.
const loadMoreStart = queuePageSource.indexOf("const loadMoreQueue");
assert.notEqual(loadMoreStart, -1, "loadMoreQueue must exist");
const loadMoreBlock = queuePageSource.slice(loadMoreStart, loadMoreStart + 1400);
assert.match(
  loadMoreBlock,
  /intakeRef\.current/,
  "Loading more queue items must keep the active intake filter"
);

assert.match(queuePageSource, /<IntakeFilterRow/, "Reup Queue must render the shared intake filter row");
assert.match(
  queuePageSource,
  /function applyIntakeChange/,
  "Reup Queue must apply intake picks immediately, like its status tabs"
);
assert.match(
  queuePageSource,
  /fetchReupQueueIntakeSessions/,
  "Reup Queue must load batches that actually have clips in the queue — not every Capture Inbox promote"
);
assert.doesNotMatch(
  queuePageSource,
  /fetchCaptureInboxSessions/,
  "The Capture Inbox session list includes empty promotes and would make the picker look broken"
);
assert.match(
  apiSource,
  /export async function fetchReupQueueIntakeSessions[\s\S]{0,400}\/reup-queue\/intake-sessions/,
  "The client must call the queue-scoped intake sessions endpoint"
);
assert.match(
  queuePageSource,
  /busy=\{intakeBusy\}|busy=\{filterPreloading\}|busy=\{galleryBusy\}/,
  "Reup Queue must pass a busy flag into the intake row while the filtered list reloads"
);
assert.match(
  queuePageSource,
  /loading && items\.length > 0|intakeBusy|filterPreloading =[\s\S]{0,200}loading/,
  "Choosing an intake filter must show the gallery loading state, not leave stale tiles sitting still"
);

console.log("reup-queue-intake-filter tests passed");
