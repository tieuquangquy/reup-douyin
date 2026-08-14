import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
};

assert.match(visualSource, /final-visual-checkpoint__review-list is-compact|review-list is-ocr/, "OCR review list must use a compact shell class");
assert.match(visualSource, /final-visual-checkpoint__review-meta/, "OCR rows must use a dedicated meta column class");
assert.match(visualSource, /final-visual-checkpoint__review-input/, "OCR text field must use a styled input class");
assert.match(visualSource, /final-visual-checkpoint__review-select/, "OCR decision control must use a styled select class");
assert.match(visualSource, /final-visual-checkpoint__review-save/, "Save OCR decisions must use a compact save CTA class");
assert.match(visualSource, /leadingIcon=\{<WorkItemActionIcon[^>]*kind="approve"/, "Save OCR CTA must include an approve icon");
assert.match(
  visualSource,
  /UNCERTAIN|showProvenanceChip|provenanceChip/,
  "Default EDITOR provenance must not spam every row unless uncertain/non-default"
);
assert.match(
  visualSource,
  /WAITING_OCR_REVIEW[\s\S]{0,220}!ocrReviewPending|ocrReviewPending[\s\S]{0,220}stage-chip|!ocrReviewPending[\s\S]{0,80}stage-chip/,
  "Pipeline summary must not repeat Waiting OCR review while the exact-review list owns that gate"
);
assert.match(en.finalReviewVisual.reviewOcrBelow, /^Review OCR$/i, "Journey/header OCR CTA must stay short");
assert.match(en.finalReviewVisual.submitOcrReview, /^Save decisions$/i, "Save OCR CTA copy must stay compact");
assert.match(cssSource, /\.final-visual-checkpoint__review-list\.is-compact|\.final-visual-checkpoint__review-list\.is-ocr/, "Compact OCR review list must be styled");
assert.match(cssSource, /\.final-visual-checkpoint__review-input\b/, "Styled OCR input rules must exist");
assert.match(cssSource, /\.final-visual-checkpoint__review-save\b/, "Compact save CTA rules must exist");

console.log("final-review OCR review polish tests passed");
