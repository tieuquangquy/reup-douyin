/**
 * Residual Chinese triage + Pipeline detail — compact ledger chrome (OCR density).
 */
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
const vi = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
};

const triageBlockMatch = visualSource.match(
  /workflow_stage === "WAITING_RESIDUAL_TRIAGE"[\s\S]*?buildResidualProposal/
);
assert.ok(triageBlockMatch, "Residual triage block must remain gated on WAITING_RESIDUAL_TRIAGE");
const triageBlock = triageBlockMatch[0];

assert.match(
  triageBlock,
  /review-list is-compact is-triage/,
  "Residual triage must use a compact triage ledger shell"
);
assert.match(triageBlock, /final-visual-checkpoint__review-head/, "Residual triage must show a head with count");
assert.match(triageBlock, /final-visual-checkpoint__review-count/, "Residual triage must surface object count");
assert.match(
  triageBlock,
  /final-visual-checkpoint__review-instruction/,
  "Triage hint must use the shared instruction class, not a generic muted dump"
);
assert.match(
  triageBlock,
  /review-row is-triage/,
  "Triage rows must be flagged so they do not inherit the OCR decision grid"
);
assert.match(triageBlock, /final-visual-checkpoint__review-meta/, "Triage rows must use a meta column for source + frame");
assert.match(
  triageBlock,
  /final-visual-checkpoint__review-input/g,
  "Corrected ZH and VI fields must use the styled review input"
);
assert.match(triageBlock, /final-visual-checkpoint__review-save/, "Build proposal CTA must use compact save class");
assert.match(
  triageBlock,
  /leadingIcon=\{<WorkItemActionIcon[^>]*kind="approve"/,
  "Build proposal CTA must include an approve icon"
);
assert.match(
  triageBlock,
  /ocr_text_corrected:[\s\S]{0,80}vi_text_suggested:/,
  "Submit must keep ocr_text_corrected + vi_text_suggested authority"
);
assert.ok(en.finalReviewVisual.residualTriageHint && vi.finalReviewVisual.residualTriageHint, "Triage hint copy must stay i18n");
assert.ok(en.finalReviewVisual.residualCorrectedText && vi.finalReviewVisual.residualCorrectedText);
assert.ok(en.finalReviewVisual.residualVietnameseText && vi.finalReviewVisual.residualVietnameseText);

const triageRowCssMatch = cssSource.match(
  /\.final-visual-checkpoint__review-row\.is-triage\s*\{[^}]+\}/
);
assert.ok(triageRowCssMatch, "Triage rows must have is-triage layout rules");
const triageRowCss = triageRowCssMatch[0];
assert.match(triageRowCss, /align-items:\s*center/, "Triage rows must center on one baseline");
assert.match(
  triageRowCss,
  /grid-template-columns:\s*[^;]*minmax\([^)]+\)[^;]*minmax\([^)]+\)[^;]*minmax/,
  "Triage rows must be a 3-column one-line grid (source | ZH | VI)"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__review-list\.is-triage|\.final-visual-checkpoint__review-list\.is-compact/,
  "Triage ledger shell must be styled"
);

const pipelineBlockMatch = visualSource.match(
  /final-visual-checkpoint__pipeline-detail[\s\S]*?<\/details>/
);
assert.ok(pipelineBlockMatch, "Pipeline detail disclosure must remain");
const pipelineBlock = pipelineBlockMatch[0];
assert.match(
  pipelineBlock,
  /final-visual-checkpoint__pipeline-fingerprint/,
  "Model version must be a dedicated fingerprint line, not a wrap-competing muted span"
);
assert.match(
  pipelineBlock,
  /final-visual-checkpoint__pipeline-band/,
  "Pipeline metrics must group into bands instead of one wrap soup"
);
assert.match(
  pipelineBlock,
  /final-visual-checkpoint__pipeline-facts/,
  "Proxy and detector stats must share one facts line"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__pipeline-fingerprint/,
  "Fingerprint line must have stylesheet rules"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__pipeline-facts/,
  "Facts line must have stylesheet rules"
);

console.log("final-review residual triage polish tests passed");
