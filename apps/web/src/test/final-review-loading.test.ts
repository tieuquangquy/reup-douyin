import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");

assert.match(statesSource, /export function FinalReviewLoadingState/, "Must expose a final-review loading shell");
assert.match(statesSource, /final-review-loading/, "Loading shell must use a stable CSS root class");
assert.match(statesSource, /final-review-loading__journey/, "Loading shell must ghost the prep journey steps");
assert.match(statesSource, /final-review-loading__split/, "Loading shell must ghost the prep split grid");
assert.match(statesSource, /final-review-loading__preview/, "Loading shell must ghost the visual preview panel");
assert.match(statesSource, /final-review-loading__side/, "Loading shell must ghost the up-next side card");
assert.match(statesSource, /role="status"/, "Loading shell must announce as a status region");
assert.match(statesSource, /aria-busy/, "Loading shell must mark itself busy");
assert.match(statesSource, /finalReviewStates\.loading/, "Loading shell must use i18n loading copy");

assert.match(pageSource, /FinalReviewLoadingState/, "Final Review page must mount the layout-matched loading shell");
assert.match(
  pageSource,
  /skeleton=\{<\s*FinalReviewLoadingState\s*\/>\}|skeleton=\{<FinalReviewLoadingState\s*\/>\}/,
  "Final Review page must pass FinalReviewLoadingState via AsyncContentBoundary skeleton prop"
);
assert.doesNotMatch(
  pageSource,
  /skeletonVariant="detail"/,
  "Final Review initial load must not use the generic detail skeleton"
);

assert.match(cssSource, /\.final-review-loading\b/, "Loading shell must have stylesheet rules");
assert.match(cssSource, /\.final-review-loading__journey\b/, "Journey ghost must be styled");
assert.match(enSource, /"loading":\s*"Loading final review/, "Loading copy must be short and operator-facing");

console.log("final-review loading tests passed");
