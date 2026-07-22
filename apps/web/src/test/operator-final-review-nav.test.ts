import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const routeSource = readFileSync(
  resolve(testDir, "../components/operator-routes/OperatorFinalReviewPage.tsx"),
  "utf8"
);
const pageSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewPage.tsx"),
  "utf8"
);

assert.match(routeSource, /TopbarRefreshButton/, "Final Review topbar must expose Refresh like other Operator pages");
assert.doesNotMatch(
  routeSource,
  /nav\.transcriptEditor|nav\.publishDraft|nav\.publishDrafts/,
  "Final Review must not keep Transcript / Publish / Drafts links in the shell topbar"
);
assert.match(routeSource, /FinalReviewPageHandle|useRef/, "Shell must call into the Final Review refresh handle");
assert.match(pageSource, /useImperativeHandle|forwardRef/, "Final Review must expose an imperative refresh handle");
assert.match(pageSource, /mode:\s*"initial"\s*\|\s*"refresh"|mode === "refresh"/, "Refresh must reload quietly without full-page loading flash");

console.log("operator-final-review-nav tests passed");
