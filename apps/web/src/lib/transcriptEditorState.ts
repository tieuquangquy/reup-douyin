import type {
  EditableSegment,
  TranscriptEditorState,
  TranscriptListResponse,
  TranscriptSavePayload,
  TranscriptValidationWarning,
  TranslationAuthority,
  TranslationDraftListResponse
} from "../types/transcript-editor";

function metaString(meta: Record<string, unknown> | null | undefined, key: string): string | null {
  const raw = meta?.[key];
  if (typeof raw !== "string") return null;
  const text = raw.trim();
  return text || null;
}

export function resolveTranslationAuthority(segments: EditableSegment[]): TranslationAuthority {
  const withVi = segments.filter((segment) => Boolean(segment.translatedText.trim()));
  const pool = withVi.length > 0 ? withVi : segments;
  return {
    promptSource: majorityString(pool.map((segment) => segment.promptSource)),
    llmProvider: majorityString(pool.map((segment) => segment.llmProvider))
  };
}

export function formatTranslationAuthorityChip(authority: TranslationAuthority): string | null {
  if (!authority.promptSource && !authority.llmProvider) return null;
  const prompt = authority.promptSource ?? "—";
  const llm = authority.llmProvider ?? "—";
  return `prompt: ${prompt} · llm: ${llm}`;
}

function majorityString(values: Array<string | null>): string | null {
  const counts = new Map<string, number>();
  for (const value of values) {
    if (!value) continue;
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestCount = 0;
  for (const [value, count] of counts) {
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

export function buildTranscriptEditorState(
  transcript: TranscriptListResponse,
  translation: TranslationDraftListResponse
): TranscriptEditorState {
  const translationsByTranscript = new Map(
    translation.segments.map((segment) => [segment.transcript_segment_id, segment])
  );
  const segments = transcript.segments
    .map((segment) => {
      const translated = translationsByTranscript.get(segment.id);
      const meta = translated?.metadata_json ?? null;
      return {
        localId: segment.id,
        transcriptId: segment.id,
        translationId: translated?.id ?? null,
        segmentIndex: segment.segment_index,
        originalStartMs: segment.start_ms,
        originalEndMs: segment.end_ms,
        originalSourceText: segment.text,
        originalTranslatedText: translated?.text ?? "",
        startMs: segment.start_ms,
        endMs: segment.end_ms,
        sourceText: segment.text,
        translatedText: translated?.text ?? "",
        confidence: segment.confidence,
        speakerLabel: segment.speaker_label,
        difficultyFlags: segment.difficulty_flags_json?.flags ?? [],
        qualityFlags: translated?.quality_flags_json?.flags ?? [],
        promptSource: metaString(meta, "prompt_source"),
        llmProvider: metaString(meta, "llm_provider"),
        status: segment.status,
        analysisVersion: segment.analysis_version,
        translationPreset: translated?.translation_preset ?? translation.translation_preset,
        isDirty: false
      } satisfies EditableSegment;
    })
    .sort((a, b) => a.startMs - b.startMs || a.segmentIndex - b.segmentIndex);
  return {
    sourceVideoId: transcript.source_video_id,
    analysisVersion: transcript.analysis_version,
    translationPreset: translation.translation_preset,
    segments,
    selectedSegmentId: segments[0]?.localId ?? null
  };
}

export function updateSegment(
  state: TranscriptEditorState,
  segmentId: string,
  patch: Partial<Pick<EditableSegment, "sourceText" | "translatedText" | "startMs" | "endMs" | "status">>
): TranscriptEditorState {
  return {
    ...state,
    segments: state.segments.map((segment) => {
      if (segment.localId !== segmentId) return segment;
      const next = { ...segment, ...patch };
      return { ...next, isDirty: isSegmentDirty(next) };
    })
  };
}

export function selectSegment(state: TranscriptEditorState, segmentId: string): TranscriptEditorState {
  return { ...state, selectedSegmentId: segmentId };
}

export function resetSegment(state: TranscriptEditorState, segmentId: string): TranscriptEditorState {
  return {
    ...state,
    segments: state.segments.map((segment) =>
      segment.localId === segmentId
        ? {
            ...segment,
            startMs: segment.originalStartMs,
            endMs: segment.originalEndMs,
            sourceText: segment.originalSourceText,
            translatedText: segment.originalTranslatedText,
            isDirty: false
          }
        : segment
    )
  };
}

export function mergeAdjacentSegments(state: TranscriptEditorState, segmentId: string, direction: "previous" | "next"): TranscriptEditorState {
  const index = state.segments.findIndex((segment) => segment.localId === segmentId);
  const otherIndex = direction === "previous" ? index - 1 : index + 1;
  if (index < 0 || otherIndex < 0 || otherIndex >= state.segments.length) return state;
  const firstIndex = Math.min(index, otherIndex);
  const secondIndex = Math.max(index, otherIndex);
  const first = state.segments[firstIndex];
  const second = state.segments[secondIndex];
  const merged: EditableSegment = {
    ...first,
    endMs: Math.max(first.endMs, second.endMs),
    sourceText: joinText(first.sourceText, second.sourceText),
    translatedText: joinText(first.translatedText, second.translatedText),
    difficultyFlags: unique([...first.difficultyFlags, ...second.difficultyFlags, "merged_segment"]),
    qualityFlags: unique([...first.qualityFlags, ...second.qualityFlags, "merged_segment"]),
    promptSource: first.promptSource ?? second.promptSource,
    llmProvider: first.llmProvider ?? second.llmProvider,
    status: "NEEDS_REVIEW",
    isDirty: true
  };
  const segments = [...state.segments.slice(0, firstIndex), merged, ...state.segments.slice(secondIndex + 1)];
  return { ...state, segments, selectedSegmentId: merged.localId };
}

export function splitSegmentAtTextMidpoint(state: TranscriptEditorState, segmentId: string): TranscriptEditorState {
  const index = state.segments.findIndex((segment) => segment.localId === segmentId);
  if (index < 0) return state;
  const segment = state.segments[index];
  if (segment.endMs - segment.startMs < 2) return state;
  const splitMs = Math.floor((segment.startMs + segment.endMs) / 2);
  const [leftSource, rightSource] = splitText(segment.sourceText);
  const [leftTranslated, rightTranslated] = splitText(segment.translatedText);
  const left: EditableSegment = {
    ...segment,
    endMs: splitMs,
    sourceText: leftSource,
    translatedText: leftTranslated,
    difficultyFlags: unique([...segment.difficultyFlags, "split_segment"]),
    qualityFlags: unique([...segment.qualityFlags, "split_segment"]),
    status: "NEEDS_REVIEW",
    isDirty: true
  };
  const right: EditableSegment = {
    ...segment,
    localId: `${segment.localId}:split:${Date.now()}`,
    transcriptId: segment.transcriptId,
    translationId: segment.translationId,
    segmentIndex: segment.segmentIndex + 1,
    originalStartMs: splitMs,
    originalEndMs: segment.endMs,
    originalSourceText: "",
    originalTranslatedText: "",
    startMs: splitMs,
    endMs: segment.endMs,
    sourceText: rightSource,
    translatedText: rightTranslated,
    difficultyFlags: ["split_segment"],
    qualityFlags: ["split_segment"],
    status: "NEEDS_REVIEW",
    isDirty: true,
    isLocalOnly: true
  };
  return {
    ...state,
    segments: [...state.segments.slice(0, index), left, right, ...state.segments.slice(index + 1)],
    selectedSegmentId: right.localId
  };
}

export function buildSavePayload(state: TranscriptEditorState): TranscriptSavePayload {
  return {
    segments: state.segments
      .filter((segment) => segment.isDirty && !segment.isLocalOnly)
      .map((segment) => ({
        transcript_segment_id: segment.transcriptId,
        translation_segment_id: segment.translationId,
        start_ms: segment.startMs,
        end_ms: segment.endMs,
        source_text: segment.sourceText,
        translated_text: segment.translatedText,
        status: segment.status
      }))
  };
}

export function validateTranscriptSegments(segments: EditableSegment[]): TranscriptValidationWarning[] {
  const warnings: TranscriptValidationWarning[] = [];
  const sorted = [...segments].sort((a, b) => a.startMs - b.startMs);
  sorted.forEach((segment, index) => {
    const seenCodes = new Set<string>();
    const push = (code: string, label: string) => {
      if (seenCodes.has(code)) return;
      seenCodes.add(code);
      warnings.push(warning(segment.localId, code, label));
    };

    if (!segment.sourceText.trim()) push("empty_source_text", "Missing source text");
    if (!segment.translatedText.trim()) push("missing_translation", "Missing translation");
    if (segment.startMs < 0) push("negative_timing", "Start time is negative");
    if (segment.endMs <= segment.startMs) push("invalid_timing", "End must be after start");
    const duration = segment.endMs - segment.startMs;
    if (duration < 500) push("awkward_short_segment", "Segment is very short");
    // Do not warn on long duration — whole-clip untimed beats are intentional.
    const previous = sorted[index - 1];
    if (previous && segment.startMs < previous.endMs) {
      push("overlapping_timing", "Timing overlaps previous segment");
    }
    // Surface only ASR/source-quality signals — not pipeline / length / review spam.
    for (const flag of unique([...segment.difficultyFlags, ...segment.qualityFlags])) {
      if (flag.includes("low_confidence") || flag.includes("likely_mistranscribed")) {
        push(flag, humanizeFlag(flag));
      }
    }
  });
  return warnings;
}

export function hasUnsavedChanges(state: TranscriptEditorState): boolean {
  return state.segments.some((segment) => segment.isDirty);
}

export function formatMs(ms: number): string {
  const totalSeconds = Math.max(0, ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds - minutes * 60;
  return `${minutes}:${seconds.toFixed(2).padStart(5, "0")}`;
}

/** Stable seconds display for timing fields (always `.`, never locale commas). */
export function formatTimingSeconds(ms: number, digits = 2): string {
  return (Math.max(0, ms) / 1000).toFixed(digits);
}

/** Parse operator-typed seconds; accepts `.` or `,` as decimal. */
export function parseTimingSecondsToMs(raw: string): number | null {
  const normalized = raw.trim().replace(",", ".");
  if (!normalized) return null;
  const sec = Number(normalized);
  if (!Number.isFinite(sec) || sec < 0) return null;
  return Math.round(sec * 1000);
}

/**
 * Parse NLE-style timecode `M:SS.cc` (or `,` decimal) back to ms.
 * Also accepts bare seconds for mid-edit drafts.
 */
export function parseTimingTimecodeToMs(raw: string): number | null {
  const normalized = raw.trim().replace(",", ".");
  if (!normalized) return null;
  const match = normalized.match(/^(\d+):(\d{1,2}(?:\.\d{1,2})?)$/);
  if (match) {
    const minutes = Number(match[1]);
    const seconds = Number(match[2]);
    if (!Number.isFinite(minutes) || !Number.isFinite(seconds) || minutes < 0 || seconds < 0 || seconds >= 60) {
      return null;
    }
    return Math.round((minutes * 60 + seconds) * 1000);
  }
  return parseTimingSecondsToMs(normalized);
}

function isSegmentDirty(segment: EditableSegment): boolean {
  return (
    segment.startMs !== segment.originalStartMs ||
    segment.endMs !== segment.originalEndMs ||
    segment.sourceText !== segment.originalSourceText ||
    segment.translatedText !== segment.originalTranslatedText
  );
}

function splitText(text: string): [string, string] {
  const trimmed = text.trim();
  if (!trimmed) return ["", ""];
  const midpoint = Math.floor(trimmed.length / 2);
  const splitAt = trimmed.indexOf(" ", midpoint);
  const index = splitAt > 0 ? splitAt : midpoint;
  return [trimmed.slice(0, index).trim(), trimmed.slice(index).trim()];
}

function joinText(left: string, right: string): string {
  return [left.trim(), right.trim()].filter(Boolean).join(" ");
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function warning(segmentId: string, code: string, label: string): TranscriptValidationWarning {
  return { segmentId, code, label };
}

function humanizeFlag(flag: string): string {
  return flag.replace(/_/g, " ");
}
