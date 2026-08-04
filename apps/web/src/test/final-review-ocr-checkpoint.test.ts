import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8");
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8"));
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8"));

assert.match(
  visualSource,
  /isFinalReviewOcrReviewPending[\s\S]*reviewOcrBelow/,
  "WAITING_OCR_REVIEW must expose Review OCR instead of the normal re-analyze CTA"
);
assert.match(
  visualSource,
  /final-review-ocr-review[\s\S]*submitOcrReview/,
  "Review OCR CTA must target the exact-review form that saves operator decisions"
);
assert.match(
  visualSource,
  /reanalyzeAdvanced[\s\S]*reanalyzeWarning[\s\S]*window\.confirm/,
  "Creating a superseding OCR run must be an explicit warned break-glass action"
);
assert.match(
  pageSource,
  /handleOcrJourneyAction[\s\S]*isFinalReviewOcrReviewPending[\s\S]*final-review-ocr-review/,
  "Journey OCR action must scroll to the pending review instead of creating another job"
);
assert.match(
  pageSource,
  /onAnalyze=\{\(\) => void asyncAction\.run\("analyze-ocr", \(\) => handleAnalyzeOcr\(false\)\)\}/,
  "Normal Analyze OCR must reuse the hash-bound Phase 1 authority"
);
assert.match(
  pageSource,
  /onReanalyze=\{\(\) => void asyncAction\.run\("reanalyze-ocr", \(\) => handleAnalyzeOcr\(true\)\)\}/,
  "Only the warned advanced action may force a superseding OCR run"
);
assert.match(
  apiSource,
  /export async function createOcrJob[\s\S]*force_refresh: options\.forceRefresh \?\? false/,
  "OCR API client must default to resume/reuse instead of an expensive full refresh"
);
assert.match(
  statesSource,
  /ocrStatus === "review"[\s\S]*prepOcrReview/,
  "Prep overview must distinguish a manual OCR checkpoint from an in-flight job"
);
assert.equal(en.finalReviewStates.prepOcrReview, "Needs review");
assert.equal(vi.finalReviewStates.prepOcrReview, "Cần duyệt OCR");

console.log("final-review OCR checkpoint tests passed");
