import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const compareSource = readFileSync(resolve(testDir, "../components/final-review/FinalCompareViewer.tsx"), "utf8");
const visualSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"), "utf8");
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");

assert.match(apiSource, /export async function fetchMediaAssetObjectUrl/, "API helper must fetch media with Bearer");
assert.match(compareSource, /fetchMediaAssetObjectUrl/, "Final compare must fetch protected media → blob URL");
assert.match(compareSource, /revokeObjectURL/, "Final compare must revoke blob URLs");
assert.doesNotMatch(
  compareSource,
  /src=\{src\}/,
  "Final compare must not put protected API content URL directly on <video src>"
);
assert.match(visualSource, /fetchMediaAssetObjectUrl/, "OCR cleaned preview must use blob URL");
assert.doesNotMatch(
  visualSource,
  /mediaAssetContentUrl\(summary\.cleaned_video_asset_id\)/,
  "OCR cleaned preview must not use bare mediaAssetContentUrl on <video>"
);
assert.match(pageSource, /finalAssetId|media_asset_id/, "Final Review must pass media asset id into compare viewer");
assert.doesNotMatch(
  pageSource,
  /finalUrl = render\?\.media_asset_id \? mediaAssetContentUrl/,
  "Final Review must not bind mediaAssetContentUrl directly as video src"
);
assert.match(pageSource, /fr-decision-bar|FinalReviewActions/, "Final Review must keep decision bar actions");
assert.match(compareSource, /fr-stage|fr-segmented/, "Compare viewer must use redesigned stage classes");

console.log("final-review preview auth tests passed");
