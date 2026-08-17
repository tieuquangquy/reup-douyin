/**
 * Residual remediation proposal — one-line ledger (OCR/translation density).
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

const residualBlockMatch = visualSource.match(
  /WAITING_RESIDUAL_REVIEW[\s\S]{0,350}?final-visual-checkpoint__review-list[\s\S]{0,3500}?approveResidualProposal/
);
assert.ok(residualBlockMatch, "Residual proposal block must remain gated on WAITING_RESIDUAL_REVIEW");
const residualBlock = residualBlockMatch[0];

assert.match(
  residualBlock,
  /review-list is-compact is-residual/,
  "Residual proposal must use a compact residual ledger shell"
);
assert.match(residualBlock, /final-visual-checkpoint__review-head/, "Residual proposal must show a head with count");
assert.match(residualBlock, /final-visual-checkpoint__review-count/, "Residual proposal must surface object count");
assert.match(
  residualBlock,
  /review-row is-residual/,
  "Residual rows must be flagged so they do not inherit the OCR 3-col decision grid"
);
assert.match(residualBlock, /final-visual-checkpoint__review-chip/, "proposed_action must render as a chip, not raw muted text");
assert.match(
  residualBlock,
  /final-visual-checkpoint__review-source/,
  "ZH (ocr_text_suggested) must be a dedicated source cell"
);
assert.match(
  residualBlock,
  /final-visual-checkpoint__review-target/,
  "VI (render_text_suggested) must be a dedicated target cell"
);
assert.doesNotMatch(
  residualBlock,
  /<strong>\{row\.ocr_text_suggested\}<\/strong>[\s\S]{0,80}proposed_action/,
  "ZH and proposed_action must not sit inline in one cell (causes overlap with VI)"
);
assert.match(
  residualBlock,
  /residual_proposal_sha256/,
  "Approve must keep residual_proposal_sha256 authority"
);
assert.match(residualBlock, /final-visual-checkpoint__review-save/, "Approve residual CTA must use compact save class");
assert.match(
  residualBlock,
  /leadingIcon=\{<WorkItemActionIcon[^>]*kind="approve"/,
  "Approve residual CTA must include an approve icon"
);
assert.ok(
  en.finalReviewVisual.residualActionExpandGeometry && vi.finalReviewVisual.residualActionExpandGeometry,
  "EXPAND_EXISTING_PHASE2_GEOMETRY must have operator-facing copy"
);
assert.ok(
  en.finalReviewVisual.residualActionAddOccurrence && vi.finalReviewVisual.residualActionAddOccurrence,
  "ADD_PHASE2_OCCURRENCE must have operator-facing copy"
);
assert.match(
  visualSource,
  /EXPAND_EXISTING_PHASE2_GEOMETRY[\s\S]{0,120}residualActionExpandGeometry|residualActionExpandGeometry[\s\S]{0,120}EXPAND_EXISTING/,
  "Known residual actions must map to i18n, not dump the enum"
);

const residualRowCssMatch = cssSource.match(
  /\.final-visual-checkpoint__review-row\.is-residual\s*\{[^}]+\}/
);
assert.ok(residualRowCssMatch, "Residual rows must have is-residual layout rules");
const residualRowCss = residualRowCssMatch[0];
assert.match(residualRowCss, /align-items:\s*center/, "Residual rows must center on one baseline");
assert.match(
  residualRowCss,
  /grid-template-columns:\s*[^;]*minmax\([^)]+\)[^;]*minmax\([^)]+\)[^;]*minmax/,
  "Residual rows must be a 3-column one-line grid (action | ZH | VI)"
);

console.log("final-review residual proposal polish tests passed");
