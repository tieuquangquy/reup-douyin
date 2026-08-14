/** Classification Queue results: v32 dense full-bleed — title fills Reel; Conf header fits. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const queue = readFileSync(resolve(webSrc, "components/operator-routes/ContentClassificationQueue.tsx"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");
const v32Start = cssFull.indexOf("/* Classification Queue Table Dense v32");
assert.ok(v32Start >= 0, "v32 dense table polish block must exist");
const v32 = cssFull.slice(v32Start, v32Start + 4500);

assert.match(
  queue,
  /classification-queue-table-wrap is-v26 is-v27 is-v28 is-v29 is-v30 is-v31 is-v32/,
  "Results must opt into v32 dense full-bleed table",
);
assert.match(
  v32,
  /table\.is-v32[\s\S]{0,240}?width:\s*100%/,
  "v32 table stays full panel width",
);
assert.match(
  v32,
  /\.classification-queue-reel\s+b[\s\S]{0,200}?max-width:\s*none/,
  "v32 must remove the 210px title cap so Reel text fills the cell",
);
assert.match(
  v32,
  /th:nth-child\(4\)[\s\S]{0,160}?min-width:\s*[5-7]\.\d+rem|td:nth-child\(4\)[\s\S]{0,160}?min-width:\s*[5-7]\.\d+rem/,
  "v32 Confidence column must be wide enough for the full header",
);
assert.match(
  v32,
  /th:nth-child\(1\)[\s\S]{0,80}?width:\s*(3[8-9]|4[0-5])%|td:nth-child\(1\)[\s\S]{0,80}?width:\s*(3[8-9]|4[0-5])%/,
  "v32 Reel gets the largest share so spare width becomes readable title",
);

console.log("classification-queue-table-polish: PASS");
