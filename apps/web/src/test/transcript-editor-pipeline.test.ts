import assert from "node:assert/strict";
import {
  fingerprintVietnameseDraft,
  isTranscriptPipelineActionUnlocked,
  isSourceTranscriptReadyForTranslation,
  isTtsDraftOutdated,
  resolveTranscriptPipelineGuide,
  resolveTtsFreshness,
  transcriptPipelineActionLabelKey
} from "../lib/transcriptEditorPipeline";
import type { EditableSegment, TranscriptEditorState } from "../types/transcript-editor";

function makeSegment(partial: Partial<EditableSegment> & Pick<EditableSegment, "localId" | "translatedText">): EditableSegment {
  return {
    localId: partial.localId,
    transcriptId: partial.transcriptId ?? partial.localId,
    translationId: partial.translationId ?? null,
    segmentIndex: partial.segmentIndex ?? 0,
    originalStartMs: partial.originalStartMs ?? 0,
    originalEndMs: partial.originalEndMs ?? 1000,
    originalSourceText: partial.originalSourceText ?? "你好",
    originalTranslatedText: partial.originalTranslatedText ?? "",
    startMs: partial.startMs ?? 0,
    endMs: partial.endMs ?? 1000,
    sourceText: partial.sourceText ?? "你好",
    translatedText: partial.translatedText,
    confidence: partial.confidence ?? 0.9,
    speakerLabel: partial.speakerLabel ?? null,
    difficultyFlags: partial.difficultyFlags ?? [],
    qualityFlags: partial.qualityFlags ?? [],
    promptSource: partial.promptSource ?? null,
    llmProvider: partial.llmProvider ?? null,
    status: partial.status ?? "APPROVED",
    analysisVersion: partial.analysisVersion ?? null,
    translationPreset: partial.translationPreset ?? null,
    isDirty: partial.isDirty ?? false
  };
}

{
  const needsReview = makeState([
    makeSegment({ localId: "review", translatedText: "", status: "NEEDS_REVIEW" })
  ]);
  const guide = resolveTranscriptPipelineGuide(needsReview, { sourceTranscriptApproved: false });
  assert.equal(guide.currentStep, "review");
  assert.equal(guide.sourceReviewRequired, true);
  assert.equal(guide.steps.find((step) => step.key === "review")?.state, "active");
  assert.equal(guide.steps.find((step) => step.key === "translate")?.state, "pending");
  assert.equal(isTranscriptPipelineActionUnlocked("translate", guide.currentStep), false);
  assert.equal(isSourceTranscriptReadyForTranslation(needsReview, "dialogue_uncertain"), false);
}

{
  const approved = makeState([makeSegment({ localId: "approved", translatedText: "" })]);
  assert.equal(isSourceTranscriptReadyForTranslation(approved, "source_auto_approved"), true);
  assert.equal(
    isSourceTranscriptReadyForTranslation(approved, "dialogue_uncertain"),
    false,
    "dialogue_uncertain must fail closed even if a stale response paints rows approved"
  );
}

function makeState(segments: EditableSegment[]): TranscriptEditorState {
  return {
    sourceVideoId: "video-1",
    analysisVersion: "v1",
    selectedSegmentId: segments[0]?.localId ?? null,
    segments,
    translationPreset: null
  };
}

{
  const guide = resolveTranscriptPipelineGuide(makeState([makeSegment({ localId: "a", translatedText: "" })]));
  assert.equal(guide.primaryAction, "translate");
  assert.equal(guide.hasVietnamese, false);
  assert.equal(guide.steps.find((step) => step.key === "review")?.state, "done");
  assert.equal(guide.steps.find((step) => step.key === "translate")?.state, "active");
  assert.equal(guide.steps.find((step) => step.key === "tts")?.state, "pending");
  assert.equal(guide.steps.find((step) => step.key === "final")?.state, "pending");
  assert.equal(guide.steps.filter((step) => step.state === "active").length, 1, "exactly one active step");
  assert.equal(isTranscriptPipelineActionUnlocked("translate", guide.currentStep), true);
  assert.equal(isTranscriptPipelineActionUnlocked("tts", guide.currentStep), false);
  assert.equal(isTranscriptPipelineActionUnlocked("final", guide.currentStep), false);
}

{
  // Joined TTS without VI must not paint Final as reached ahead of Translate/TTS.
  const guide = resolveTranscriptPipelineGuide(
    makeState([makeSegment({ localId: "a", translatedText: "" })]),
    { hasJoinedTts: true }
  );
  assert.equal(guide.primaryAction, "translate");
  assert.equal(guide.steps.find((step) => step.key === "translate")?.state, "active");
  assert.equal(guide.steps.find((step) => step.key === "tts")?.state, "pending");
  assert.equal(guide.steps.find((step) => step.key === "final")?.state, "pending");
  assert.equal(guide.ttsFreshness, "hidden", "leftover TTS without VI must not show current/outdated chip");
  assert.equal(
    resolveTtsFreshness({ hasJoinedTts: true, hasVietnamese: false, ttsOutdated: false, ttsSourceFingerprint: "fp" }),
    "hidden"
  );
}

{
  const guide = resolveTranscriptPipelineGuide(
    makeState([makeSegment({ localId: "a", translatedText: "Xin chao" })]),
    { hasJoinedTts: false }
  );
  assert.equal(guide.primaryAction, "tts");
  assert.equal(guide.steps.find((step) => step.key === "translate")?.state, "done");
  assert.equal(guide.steps.find((step) => step.key === "tts")?.state, "active");
  assert.equal(guide.steps.find((step) => step.key === "final")?.state, "pending");
  assert.equal(guide.steps.filter((step) => step.state === "active").length, 1);
  assert.equal(isTranscriptPipelineActionUnlocked("translate", guide.currentStep), true);
  assert.equal(isTranscriptPipelineActionUnlocked("tts", guide.currentStep), true);
  assert.equal(isTranscriptPipelineActionUnlocked("final", guide.currentStep), false);
}

{
  const guide = resolveTranscriptPipelineGuide(
    makeState([makeSegment({ localId: "a", translatedText: "Xin chao" })]),
    { hasJoinedTts: true }
  );
  assert.equal(guide.primaryAction, "final");
  assert.equal(guide.steps.find((step) => step.key === "tts")?.state, "done");
  assert.equal(guide.steps.find((step) => step.key === "final")?.state, "active");
  assert.equal(guide.steps.filter((step) => step.state === "active").length, 1);
  assert.equal(isTranscriptPipelineActionUnlocked("final", guide.currentStep), true);
  assert.equal(guide.ttsOutdated, false);
  assert.equal(guide.ttsFreshness, "hidden", "joined TTS without fingerprint must not claim current");
  assert.equal(transcriptPipelineActionLabelKey("translate", { isPrimary: false }), "transcriptEditorHeader.translateAgain");
  assert.equal(transcriptPipelineActionLabelKey("tts", { isPrimary: false }), "transcriptEditorHeader.regenerateTts");
}

{
  const segments = [makeSegment({ localId: "a", translationId: "tr-1", translatedText: "Xin chao" })];
  const fp = fingerprintVietnameseDraft(segments);
  assert.equal(isTtsDraftOutdated(segments, { hasJoinedTts: true, ttsSourceFingerprint: fp }), false);
  const currentGuide = resolveTranscriptPipelineGuide(makeState(segments), {
    hasJoinedTts: true,
    ttsSourceFingerprint: fp
  });
  assert.equal(currentGuide.ttsFreshness, "current");
  const edited = [makeSegment({ localId: "a", translationId: "tr-1", translatedText: "Xin chao ban" })];
  assert.equal(isTtsDraftOutdated(edited, { hasJoinedTts: true, ttsSourceFingerprint: fp }), true);
  const guide = resolveTranscriptPipelineGuide(makeState(edited), {
    hasJoinedTts: true,
    ttsSourceFingerprint: fp
  });
  assert.equal(guide.primaryAction, "final", "outdated TTS must not steal Final primary");
  assert.equal(guide.ttsOutdated, true);
  assert.equal(guide.ttsFreshness, "outdated");
  assert.equal(transcriptPipelineActionLabelKey("tts", { isPrimary: false, ttsOutdated: true }), "transcriptEditorHeader.regenerateTts");
}

console.log("transcript-editor-pipeline tests passed");
