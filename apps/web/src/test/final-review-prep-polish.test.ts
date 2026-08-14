import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const visualSource = readFileSync(
  resolve(testDir, "../components/final-review/FinalReviewVisualCheckpoint.tsx"),
  "utf8"
);
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewVisual: Record<string, string>;
  finalReviewStates: Record<string, string>;
};

// 1 — dedupe waiting status: pipeline summary must not echo journey waiting chip while closed
assert.match(
  visualSource,
  /!dialogueTranslationPending && !ocrReviewPending[\s\S]{0,160}stage-chip|dialogueTranslationPending[\s\S]{0,220}hideStageChip|hideStageChip[\s\S]{0,120}dialogueTranslationPending|!dialogueTranslationPending[\s\S]{0,80}stage-chip/,
  "Pipeline detail must not repeat Waiting translation approval while journey already shows it"
);

// 2 — no cleaned vs gate
assert.match(
  visualSource,
  /ocrGatePending|dialogueTranslationPending[\s\S]{0,200}noCleaned|waitingCleanShort|ocrDoneWaiting/,
  "Meta must not show bare No cleaned while dialogue translation gate is pending"
);
assert.ok(
  en.finalReviewVisual.ocrDoneWaitingShort || en.finalReviewVisual.waitingCleanShort,
  "EN must expose an OCR-done / waiting-clean meta label"
);

// 3 — transcript link once on prep side card when dialogue pending
assert.match(statesSource, /hideTranscriptLink/, "Empty/up-next card must support hiding Transcript editor");
assert.match(
  readFileSync(resolve(testDir, "../components/final-review/FinalReviewPage.tsx"), "utf8"),
  /hideTranscriptLink=\{isFinalReviewDialogueTranslationApprovalPending/,
  "Prep page must hide side Transcript link while dialogue gate is pending"
);

// 4 — attention border overrides active green
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]*?\.is-attention \.final-review-prep-steps__icon[\s\S]*?#9a3412/,
  "Waiting journey step icon must use the same attention amber as frame/text"
);
assert.match(
  cssSource,
  /\.final-review--prep[\s\S]*?\.is-attention \.final-review-prep-steps__prefix[\s\S]*?#92400e/,
  "Waiting journey step title prefix must use attention amber, not accent green"
);

// 5 — clarify object counts
assert.match(
  visualSource,
  /dialogue_translation_blocked_count|objectsNeedVi|needViApproval/,
  "Header meta must surface how many objects still need VI approval"
);
assert.ok(
  en.finalReviewVisual.objectsNeedViShort || en.finalReviewVisual.objectsNeedApprovalShort,
  "EN must expose a short need-VI-approval count label"
);

console.log("final-review prep polish tests passed");
