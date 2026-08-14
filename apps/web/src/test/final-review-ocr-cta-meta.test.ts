import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const statesSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewStates.tsx"),
  "utf8"
);
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
};

// Visual steps must not duplicate journey "Review OCR" while the exact-review list owns the gate.
assert.match(
  visualSource,
  /const hideAnalyzeCta\s*=[\s\S]{0,240}?ocrReviewPending/,
  "hideAnalyzeCta must include ocrReviewPending so visual header does not repeat Review OCR"
);
assert.match(
  statesSource,
  /ocrReviewPending[\s\S]{0,200}reviewOcrBelow/,
  "Journey Step 1 must keep the single Review OCR CTA"
);

// Meta must not show bare No cleaned while OCR exact review is pending.
assert.match(
  visualSource,
  /dialogueTranslationPending\s*\|\|\s*ocrReviewPending[\s\S]{0,160}waitingOcrReview|ocrReviewPending\s*\?[\s\S]{0,200}waitingOcrReview/,
  "Cleaned meta must use a waiting-OCR-review label instead of No cleaned during OCR review"
);
assert.ok(
  en.finalReviewVisual.waitingOcrReviewShort,
  "EN must expose waitingOcrReviewShort meta label"
);
assert.notEqual(
  en.finalReviewVisual.waitingOcrReviewShort,
  en.finalReviewVisual.noCleanedShort,
  "Waiting OCR meta must not reuse the bare No cleaned short label"
);

console.log("final-review OCR CTA/meta dedupe tests passed");
