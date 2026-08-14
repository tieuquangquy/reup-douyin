/** Classification Queue results header: v33 masthead with KPI filter chips + icons. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const queue = readFileSync(resolve(webSrc, "components/operator-routes/ContentClassificationQueue.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const v33Start = cssFull.indexOf("/* Classification Queue Results Masthead v33");
assert.ok(v33Start >= 0, "v33 results masthead polish block must exist");
const v33 = cssFull.slice(v33Start, v33Start + 6500);

assert.match(
  queue,
  /classification-queue-results-head is-v33/,
  "Results header must use the v33 masthead shell",
);
assert.match(
  queue,
  /classification-queue-results-head__stats/,
  "Results header must expose a KPI stats cluster",
);
assert.match(
  queue,
  /classification-queue-results-head__chip/,
  "Results header must render clickable KPI chips",
);
assert.match(
  queue,
  /ClassificationResultsHeadGlyph|results-head__glyph/,
  "Masthead chips must include status glyphs",
);
assert.match(
  queue,
  /kind:\s*"unclassified"[\s\S]{0,80}?kind:\s*"review"|unclassified[\s\S]{0,200}?review[\s\S]{0,200}?approved[\s\S]{0,200}?low/,
  "Glyph kinds must cover unclassified / review / approved / low",
);
assert.match(
  queue,
  /unclassified_count[\s\S]{0,400}?needs_review_count[\s\S]{0,400}?approved_count[\s\S]{0,400}?low_confidence_count|resultsHeadStats/,
  "Masthead chips must bind to existing KPI authority",
);
assert.match(
  v33,
  /results-head\.is-v33[\s\S]{0,240}?display:\s*flex|results-head\.is-v33[\s\S]{0,240}?justify-content:\s*space-between/,
  "v33 masthead must span title left / stats right",
);
assert.match(
  v33,
  /results-head__glyph/,
  "v33 chip glyph styles must exist",
);

console.log("classification-queue-results-masthead-polish: PASS");
