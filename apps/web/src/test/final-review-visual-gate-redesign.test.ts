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

assert.match(
  visualSource,
  /final-visual-checkpoint__gate/,
  "Dialogue translation gate must use a dedicated attention callout"
);
assert.match(
  visualSource,
  /final-visual-checkpoint__pipeline-detail/,
  "Quality workflow meta must collapse into a pipeline detail disclosure"
);
assert.match(
  visualSource,
  /workflowStageLabel/,
  "Workflow stage must be humanized for operators"
);
assert.match(
  visualSource,
  /hideAnalyzeCta[\s\S]{0,160}dialogueTranslationPending|dialogueTranslationPending[\s\S]{0,160}hideAnalyzeCta/,
  "Duplicate Approve translation CTA in steps must hide while the gate callout is shown"
);
assert.match(
  visualSource,
  /showVisualApprove/,
  "Visual Approve visibility must be gated by active visual-review stage"
);
assert.match(
  visualSource,
  /WAITING_VISUAL_REVIEW/,
  "Visual Approve gate must consult WAITING_VISUAL_REVIEW"
);
assert.doesNotMatch(
  visualSource,
  /className="inline-warning"/,
  "Dialogue gate must not reuse the generic inline-warning shell"
);
assert.match(cssSource, /\.final-visual-checkpoint__gate\b/, "Gate callout must have stylesheet rules");
assert.doesNotMatch(
  cssSource,
  /\.final-visual-checkpoint__gate\s*\{[^}]*(#d97706|#f59e0b|#92400e|#fffbeb)/i,
  "Gate callout must use normal prep colors, not the journey waiting amber"
);
assert.match(
  cssSource,
  /\.final-visual-checkpoint__gate\s*\{[^}]*(#14614b|#1e7e64|#3f6f5f|#f7faf9|#e8f4ef|var\(--accent\))/i,
  "Gate callout must use quiet sage/neutral prep palette"
);
assert.match(
  en.finalReviewVisual.approveAndResumeOcr,
  /Approve & resume|Approve and resume/i,
  "Gate primary CTA copy must stay compact"
);
assert.ok(en.finalReviewVisual.stageWaitingDialogueTranslationApproval, "EN must humanize waiting dialogue translation stage");
assert.ok(vi.finalReviewVisual.stageWaitingDialogueTranslationApproval, "VI must humanize waiting dialogue translation stage");
assert.ok(en.finalReviewVisual.pipelineDetail, "EN must label pipeline detail disclosure");
assert.ok(vi.finalReviewVisual.pipelineDetail, "VI must label pipeline detail disclosure");

console.log("final-review visual gate redesign tests passed");
