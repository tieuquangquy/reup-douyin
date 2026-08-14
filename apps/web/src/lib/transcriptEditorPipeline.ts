import type { EditableSegment, TranscriptEditorState } from "../types/transcript-editor";

export type TranscriptPipelineStepKey = "review" | "translate" | "tts" | "final";

export type TranscriptPipelineStepState = "done" | "active" | "pending";

export type TranscriptPipelineStep = {
  key: TranscriptPipelineStepKey;
  state: TranscriptPipelineStepState;
};

export type TranscriptPipelinePrimaryAction = "translate" | "tts" | "final";

export type TranscriptPipelineGuide = {
  steps: TranscriptPipelineStep[];
  /** Current operator focus — drives the single primary CTA. */
  primaryAction: TranscriptPipelinePrimaryAction;
  currentStep: TranscriptPipelineStepKey;
  viFilledCount: number;
  segmentCount: number;
  hasVietnamese: boolean;
  hasJoinedTts: boolean;
  /** True when joined TTS exists but VI draft no longer matches the fingerprint used for that TTS. */
  ttsOutdated: boolean;
  /** UI chip: hide unless joined TTS + VI + known fingerprint. */
  ttsFreshness: TtsFreshness;
  /** True only when every current Chinese beat is approved for translation. */
  sourceTranscriptApproved: boolean;
  /** A new/uncertain ASR run keeps the pipeline on Review and fails closed. */
  sourceReviewRequired: boolean;
};

export type TtsFreshness = "hidden" | "current" | "outdated";

const STEP_ORDER: TranscriptPipelineStepKey[] = ["review", "translate", "tts", "final"];

function countVietnameseFilled(segments: EditableSegment[]): number {
  return segments.filter((segment) => segment.translatedText.trim().length > 0).length;
}

/** Backend-equivalent source gate used before trusting any Translation/TTS projection. */
export function isSourceTranscriptReadyForTranslation(
  state: TranscriptEditorState,
  dialoguePhase: string | null | undefined
): boolean {
  if (state.segments.length === 0 || dialoguePhase === "dialogue_uncertain") return false;
  return state.segments.every((segment) => segment.status === "APPROVED");
}

/** Stable VI draft fingerprint for TTS freshness checks. */
export function fingerprintVietnameseDraft(segments: EditableSegment[]): string {
  return segments
    .map((segment) => {
      const id = segment.translationId ?? segment.localId;
      const text = segment.translatedText.replace(/\s+/g, " ").trim();
      return `${id}\t${text}`;
    })
    .join("\n");
}

export function isTtsDraftOutdated(
  segments: EditableSegment[],
  options: { hasJoinedTts: boolean; ttsSourceFingerprint: string | null | undefined }
): boolean {
  if (!options.hasJoinedTts || !options.ttsSourceFingerprint) return false;
  return fingerprintVietnameseDraft(segments) !== options.ttsSourceFingerprint;
}

/**
 * Freshness chip gate: never claim "current" without VI + stored fingerprint.
 * Leftover joined TTS while Translate is active must stay hidden.
 */
export function resolveTtsFreshness(options: {
  hasJoinedTts: boolean;
  hasVietnamese: boolean;
  ttsOutdated: boolean;
  ttsSourceFingerprint: string | null | undefined;
}): TtsFreshness {
  if (!options.hasJoinedTts || !options.hasVietnamese || !options.ttsSourceFingerprint) return "hidden";
  return options.ttsOutdated ? "outdated" : "current";
}

/**
 * First incomplete step in Review → Translate → TTS → Final.
 * Later steps stay pending until earlier ones are done (strict sequence).
 */
export function resolveTranscriptPipelineCurrentStep(
  state: TranscriptEditorState,
  options: { hasJoinedTts?: boolean; sourceTranscriptApproved?: boolean } = {}
): TranscriptPipelineStepKey {
  if (state.segments.length === 0) return "review";
  const sourceTranscriptApproved =
    options.sourceTranscriptApproved ?? state.segments.every((segment) => segment.status === "APPROVED");
  if (!sourceTranscriptApproved) return "review";
  const hasVietnamese = countVietnameseFilled(state.segments) > 0;
  if (!hasVietnamese) return "translate";
  if (!options.hasJoinedTts) return "tts";
  return "final";
}

function stepStateFor(
  key: TranscriptPipelineStepKey,
  currentStep: TranscriptPipelineStepKey
): TranscriptPipelineStepState {
  const keyIndex = STEP_ORDER.indexOf(key);
  const currentIndex = STEP_ORDER.indexOf(currentStep);
  if (keyIndex < currentIndex) return "done";
  if (keyIndex === currentIndex) return "active";
  return "pending";
}

/**
 * Guided Dialogue Bench pipeline: Review ZH → Translate → TTS → Final.
 * Re-ASR is advanced (not a default step) because Phase A already ran from the queue.
 * Rework is allowed after unlock; ttsOutdated flags stale narration without stealing Final primary.
 */
export function resolveTranscriptPipelineGuide(
  state: TranscriptEditorState,
  options: {
    hasJoinedTts?: boolean;
    ttsSourceFingerprint?: string | null;
    sourceTranscriptApproved?: boolean;
  } = {}
): TranscriptPipelineGuide {
  const segmentCount = state.segments.length;
  const viFilledCount = countVietnameseFilled(state.segments);
  const hasVietnamese = viFilledCount > 0;
  const hasJoinedTts = Boolean(options.hasJoinedTts);
  const sourceTranscriptApproved =
    options.sourceTranscriptApproved ??
    (segmentCount > 0 && state.segments.every((segment) => segment.status === "APPROVED"));
  const sourceReviewRequired = !sourceTranscriptApproved;
  const ttsOutdated = isTtsDraftOutdated(state.segments, {
    hasJoinedTts,
    ttsSourceFingerprint: options.ttsSourceFingerprint
  });
  const ttsFreshness = resolveTtsFreshness({
    hasJoinedTts,
    hasVietnamese,
    ttsOutdated,
    ttsSourceFingerprint: options.ttsSourceFingerprint
  });
  const currentStep = resolveTranscriptPipelineCurrentStep(state, {
    hasJoinedTts,
    sourceTranscriptApproved,
  });

  const primaryAction: TranscriptPipelinePrimaryAction =
    currentStep === "review" || currentStep === "translate"
      ? "translate"
      : currentStep === "tts"
        ? "tts"
        : "final";

  const steps: TranscriptPipelineStep[] = STEP_ORDER.map((key) => ({
    key,
    state: stepStateFor(key, currentStep)
  }));

  return {
    steps,
    primaryAction,
    currentStep,
    viFilledCount,
    segmentCount,
    hasVietnamese,
    hasJoinedTts,
    ttsOutdated,
    ttsFreshness,
    sourceTranscriptApproved,
    sourceReviewRequired
  };
}

export function transcriptPipelineStepLabelKey(key: TranscriptPipelineStepKey): string {
  if (key === "review") return "transcriptEditorHeader.pipelineReview";
  if (key === "translate") return "transcriptEditorHeader.pipelineTranslate";
  if (key === "tts") return "transcriptEditorHeader.pipelineTts";
  return "transcriptEditorHeader.pipelineFinal";
}

const ACTION_ORDER: TranscriptPipelinePrimaryAction[] = ["translate", "tts", "final"];

/**
 * Progressive unlock: an action is available only once the pipeline has reached that stage.
 * Earlier actions stay available for rework; later ones stay hidden until unlocked.
 */
export function isTranscriptPipelineActionUnlocked(
  action: TranscriptPipelinePrimaryAction,
  currentStep: TranscriptPipelineStepKey
): boolean {
  if (currentStep === "review") return false;
  const currentAction: TranscriptPipelinePrimaryAction =
    currentStep === "translate"
      ? "translate"
      : currentStep === "tts"
        ? "tts"
        : "final";
  return ACTION_ORDER.indexOf(action) <= ACTION_ORDER.indexOf(currentAction);
}

/** Main-path vs rework labels for Translate / TTS / Final. */
export function transcriptPipelineActionLabelKey(
  action: TranscriptPipelinePrimaryAction,
  options: { isPrimary: boolean; ttsOutdated?: boolean } = { isPrimary: true }
): string {
  if (action === "translate") {
    return options.isPrimary ? "transcriptEditorHeader.translateMenu" : "transcriptEditorHeader.translateAgain";
  }
  if (action === "tts") {
    if (!options.isPrimary || options.ttsOutdated) return "transcriptEditorHeader.regenerateTts";
    return "transcriptEditorHeader.generateTts";
  }
  return "transcriptEditorHeader.finalReviewShort";
}

export function ttsViFingerprintStorageKey(sourceVideoId: string): string {
  return `reup.douyin.ttsViFp.${sourceVideoId}`;
}
