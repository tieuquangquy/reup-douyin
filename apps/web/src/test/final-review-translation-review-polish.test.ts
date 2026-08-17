/**
 * Visual translation review — one-line bilingual ledger (OCR density).
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

const translationBlockMatch = visualSource.match(
  /WAITING_TRANSLATION_REVIEW[\s\S]{0,400}?final-visual-checkpoint__review-list[\s\S]{0,4500}?submitTranslationReview|retryPreview/
);
assert.ok(translationBlockMatch, "Visual translation review block must remain gated on WAITING_TRANSLATION_REVIEW");
const translationBlock = translationBlockMatch[0];

assert.match(
  translationBlock,
  /review-list is-compact|is-translation/,
  "Translation review must use a compact ledger shell"
);
assert.match(translationBlock, /final-visual-checkpoint__review-head/, "Translation review must show a head with count");
assert.match(translationBlock, /final-visual-checkpoint__review-count/, "Translation review must surface object count");
assert.match(translationBlock, /final-visual-checkpoint__review-meta/, "Translation rows must use a meta column");
assert.match(translationBlock, /final-visual-checkpoint__review-chip/, "Role / quality flags must render as chips");
assert.match(
  translationBlock,
  /final-visual-checkpoint__review-source/,
  "ZH must render as a dedicated source cell"
);
assert.match(translationBlock, /final-visual-checkpoint__review-input/, "VI field must use the styled review input");
assert.match(translationBlock, /final-visual-checkpoint__review-save/, "Save translation CTA must use compact save class");
assert.match(
  translationBlock,
  /leadingIcon=\{<WorkItemActionIcon[^>]*kind="approve"/,
  "Save translation CTA must include an approve icon"
);

// One-line density: ZH source must be a row sibling (not stacked under meta with SOURCE/VIETNAMESE labels).
assert.doesNotMatch(
  translationBlock,
  /review-meta[\s\S]{0,800}?translationSource/,
  "ZH must not sit under a vertical SOURCE label inside meta (causes dead air)"
);
assert.doesNotMatch(
  translationBlock,
  /review-field[\s\S]{0,200}?translationTarget/,
  "VI must not use a labeled field stack (causes tall sparse rows)"
);
assert.match(
  translationBlock,
  /aria-label=\{`\$\{t\("finalReviewVisual\.translationTarget"\)\}/,
  "VI input must keep an accessible target label via aria-label"
);
assert.match(
  visualSource,
  /content_id:[\s\S]{0,80}vi_text:/,
  "Submit must keep content_id + vi_text authority"
);
assert.ok(en.finalReviewVisual.translationTarget, "en.json must define VI target label for aria");
assert.ok(vi.finalReviewVisual.translationTarget, "vi.json must define VI target label for aria");

const translationRowCssMatch = cssSource.match(
  /\.final-visual-checkpoint__review-row\.is-translation\s*\{[^}]+\}/
);
assert.ok(translationRowCssMatch, "Translation rows must have is-translation layout rules");
const translationRowCss = translationRowCssMatch[0];
assert.match(translationRowCss, /align-items:\s*center/, "Translation rows must center on one baseline");
assert.match(
  translationRowCss,
  /grid-template-columns:\s*[^;]*minmax\([^)]+\)[^;]*minmax\([^)]+\)[^;]*minmax/,
  "Translation rows must be a 3-column one-line grid (meta | ZH | VI)"
);

assert.match(
  cssSource,
  /\.final-visual-checkpoint__review-list\.is-translation|\.final-visual-checkpoint__review-list\.is-compact/,
  "Translation ledger shell must be styled"
);

console.log("final-review translation review polish tests passed");
