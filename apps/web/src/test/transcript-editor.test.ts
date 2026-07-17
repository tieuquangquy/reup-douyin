import assert from "node:assert/strict";
import {
  buildSavePayload,
  buildTranscriptEditorState,
  formatMs,
  formatTranslationAuthorityChip,
  hasUnsavedChanges,
  mergeAdjacentSegments,
  resetSegment,
  resolveTranslationAuthority,
  selectSegment,
  updateSegment,
  validateTranscriptSegments
} from "../lib/transcriptEditorState";
import type { TranscriptListResponse, TranslationDraftListResponse } from "../types/transcript-editor";

const transcript: TranscriptListResponse = {
  source_video_id: "video-1",
  analysis_version: "AUDIO_ANALYSIS_V1_RUN_1",
  segments: [
    makeTranscript("t1", 0, 0, 1200, "你好", 0.5, ["low_confidence"]),
    makeTranscript("t2", 1, 1200, 2400, "第二句", 0.9, [])
  ]
};

const translation: TranslationDraftListResponse = {
  source_video_id: "video-1",
  translation_preset: "natural_viral",
  segments: [
    makeTranslation("v1", "t1", 0, "Xin chao", ["low_confidence_source", "workspace_translation_prompt"], {
      prompt_source: "workspace_db",
      llm_provider: "openai_compatible"
    }),
    makeTranslation("v2", "t2", 1, "Cau thu hai", ["workspace_translation_prompt"], {
      prompt_source: "workspace_db",
      llm_provider: "openai_compatible"
    })
  ]
};

let state = buildTranscriptEditorState(transcript, translation);
assert.equal(state.segments.length, 2);
assert.equal(state.selectedSegmentId, "t1");
assert.equal(state.segments[0].translatedText, "Xin chao");
assert.equal(state.segments[0].promptSource, "workspace_db");
assert.equal(state.segments[0].llmProvider, "openai_compatible");
assert.equal(
  formatTranslationAuthorityChip(resolveTranslationAuthority(state.segments)),
  "prompt: workspace_db · llm: openai_compatible"
);

state = selectSegment(state, "t2");
assert.equal(state.selectedSegmentId, "t2");

state = updateSegment(state, "t1", { translatedText: "Xin chao ban" });
assert.equal(hasUnsavedChanges(state), true);
assert.equal(buildSavePayload(state).segments.length, 1);
assert.equal(buildSavePayload(state).segments[0].translated_text, "Xin chao ban");

const warnings = validateTranscriptSegments(state.segments);
assert.equal(warnings.some((warning) => warning.code === "low_confidence"), true);

{
  // Long whole-clip beats are expected after untimed FunASR keep-one-beat; do not warn on length.
  const longSegment = {
    ...state.segments[0],
    endMs: 189_750,
    difficultyFlags: ["too_long", "needs_operator_review", "funasr_untimed"],
    qualityFlags: ["too_long", "needs_operator_review"]
  };
  const longWarnings = validateTranscriptSegments([longSegment]).filter((warning) => warning.segmentId === "t1");
  const codes = longWarnings.map((warning) => warning.code);
  assert.equal(new Set(codes).size, codes.length, `duplicate warning codes crash list keys: ${codes.join(",")}`);
  assert.equal(codes.filter((code) => code === "too_long").length, 0);
  assert.equal(codes.some((code) => code.includes("review")), false);
}

const overlapped = updateSegment(state, "t2", { startMs: 900 });
const overlapWarnings = validateTranscriptSegments(overlapped.segments);
assert.equal(overlapWarnings.some((warning) => warning.code === "overlapping_timing"), true);

const reset = resetSegment(state, "t1");
assert.equal(reset.segments[0].isDirty, false);
assert.equal(reset.segments[0].translatedText, "Xin chao");

const merged = mergeAdjacentSegments(state, "t2", "previous");
assert.equal(merged.segments.length, 1);
assert.equal(merged.segments[0].sourceText, "你好 第二句");
assert.equal(merged.segments[0].isDirty, true);

assert.equal(formatMs(7210), "0:07.21");

console.log("transcript-editor state tests passed");

function makeTranscript(
  id: string,
  index: number,
  startMs: number,
  endMs: number,
  text: string,
  confidence: number,
  flags: string[]
): TranscriptListResponse["segments"][number] {
  return {
    id,
    source_video_id: "video-1",
    segment_index: index,
    version: 1,
    start_ms: startMs,
    end_ms: endMs,
    text,
    normalized_text: text,
    language_code: "zh",
    status: "DRAFT",
    confidence,
    speaker_label: null,
    difficulty_flags_json: { flags },
    analysis_version: "AUDIO_ANALYSIS_V1_RUN_1",
    created_by_job_id: null,
    is_current: true,
    metadata_json: {},
    created_at: "2026-04-17T00:00:00Z",
    updated_at: "2026-04-17T00:00:00Z"
  };
}

function makeTranslation(
  id: string,
  transcriptId: string,
  index: number,
  text: string,
  flags: string[],
  metadata: Record<string, unknown> = {}
): TranslationDraftListResponse["segments"][number] {
  return {
    id,
    source_video_id: "video-1",
    transcript_segment_id: transcriptId,
    segment_index: index,
    language_code: "vi",
    version: 1,
    text,
    status: "DRAFT",
    translation_preset: "natural_viral",
    duration_budget_ms: 1200,
    estimated_tts_duration_ms: 900,
    quality_flags_json: { flags },
    created_by_job_id: null,
    is_current: true,
    metadata_json: metadata,
    created_at: "2026-04-17T00:00:00Z",
    updated_at: "2026-04-17T00:00:00Z"
  };
}
