import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  isFinalReviewDialogueTranslationApprovalPending,
  resolveFinalReviewPrepStepProgress
} from "../lib/finalReviewState";

const testDir = dirname(fileURLToPath(import.meta.url));
const statesSource = readFileSync(resolve(testDir, "../components/final-review/FinalReviewStates.tsx"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = JSON.parse(readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8")) as {
  finalReviewStates: Record<string, string>;
};

assert.equal(
  isFinalReviewDialogueTranslationApprovalPending({
    workflow_stage: "WAITING_DIALOGUE_TRANSLATION_APPROVAL"
  }),
  true
);

{
  const progress = resolveFinalReviewPrepStepProgress({
    ocrSummary: {
      workflow_version: "QUALITY_LOCALIZATION_V24_1",
      workflow_stage: "WAITING_DIALOGUE_TRANSLATION_APPROVAL",
      dialogue_translation_blocked_count: 86,
      requires_dialogue_translation_approval: true
    }
  });
  assert.ok(
    progress.clean >= 50 && progress.clean < 100,
    `Clean progress must reflect dialogue-approval gate (got ${progress.clean}%)`
  );
  assert.equal(progress.render, 0);
}

assert.match(
  statesSource,
  /hideCta|hideJourneyCta|dialogueTranslationPending[\s\S]{0,80}null/,
  "Journey must hide the duplicate Approve translation CTA while the visual gate owns it"
);
assert.match(
  statesSource,
  /is-attention|waitingApproval|journeyWaiting/,
  "Journey Clean step must mark attention while translation approval is pending"
);
assert.doesNotMatch(
  statesSource,
  /dialogueTranslationPending\s*\?\s*t\("finalReviewVisual\.approveDialogueTranslation"\)/,
  "Journey must not label its CTA as Approve translation when the gate callout already owns that action"
);
assert.match(
  cssSource,
  /\.final-review-prep-steps__item\.is-attention|\.final-review-prep-steps__card\.is-attention/,
  "Journey attention state must have stylesheet rules"
);
assert.ok(
  en.finalReviewStates.journeyWaitingTranslationApproval || en.finalReviewStates.emptyStepWaitingApproval,
  "EN must expose a waiting-approval status label for the journey Clean step"
);
assert.match(
  en.finalReviewStates.journeyWaitingTranslationApproval,
  /^Waiting approval$/i,
  "Journey waiting pill copy must stay short"
);
assert.match(
  statesSource,
  /final-review-prep-steps__waiting-icon/,
  "Journey waiting pill must include a status icon"
);

console.log("final-review journey gate demotion tests passed");
