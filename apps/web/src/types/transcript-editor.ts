export type TranscriptStatus = "DRAFT" | "NEEDS_REVIEW" | "APPROVED" | "REJECTED";

export type TranslationPreset = "literal_safe" | "natural_viral" | "affiliate_soft_sell";

export type TranscriptSegment = {
  id: string;
  source_video_id: string;
  segment_index: number;
  version: number;
  start_ms: number;
  end_ms: number;
  text: string;
  normalized_text: string | null;
  language_code: string | null;
  status: TranscriptStatus;
  confidence: number | null;
  speaker_label: string | null;
  difficulty_flags_json: { flags?: string[] } | null;
  analysis_version: string | null;
  created_by_job_id: string | null;
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type TranslationSegment = {
  id: string;
  source_video_id: string;
  transcript_segment_id: string;
  segment_index: number | null;
  language_code: string;
  version: number;
  text: string;
  status: TranscriptStatus;
  translation_preset: string | null;
  duration_budget_ms: number | null;
  estimated_tts_duration_ms: number | null;
  quality_flags_json: { flags?: string[] } | null;
  created_by_job_id: string | null;
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type TranscriptListResponse = {
  source_video_id: string;
  analysis_version: string | null;
  segments: TranscriptSegment[];
};

export type TranslationDraftListResponse = {
  source_video_id: string;
  translation_preset: string | null;
  segments: TranslationSegment[];
};

export type AudioAnalysisSummaryResponse = {
  source_video_id: string;
  analysis_version: string | null;
  transcript_count: number;
  translation_count: number;
  asset_count: number;
  manifest: AssetManifest;
  has_speech?: boolean | null;
  dialogue_phase?: string | null;
};

export type AssetManifest = {
  source_video?: {
    id: string;
    external_id: string;
    source_url: string | null;
    caption: string | null;
    duration_seconds: number | null;
  };
  storage?: {
    provider: string;
    root: string | null;
    video_prefix: string | null;
  };
  assets?: Array<{
    id: string;
    asset_type: string;
    status: string;
    logical_key: string | null;
    source_url: string | null;
    mime_type: string | null;
    is_current?: boolean;
  }>;
};

export type EditableSegment = {
  localId: string;
  transcriptId: string;
  translationId: string | null;
  segmentIndex: number;
  originalStartMs: number;
  originalEndMs: number;
  originalSourceText: string;
  originalTranslatedText: string;
  startMs: number;
  endMs: number;
  sourceText: string;
  translatedText: string;
  confidence: number | null;
  speakerLabel: string | null;
  difficultyFlags: string[];
  qualityFlags: string[];
  /** From translation metadata_json.prompt_source (e.g. workspace_db). */
  promptSource: string | null;
  /** From translation metadata_json.llm_provider (e.g. openai_compatible). */
  llmProvider: string | null;
  status: TranscriptStatus;
  analysisVersion: string | null;
  translationPreset: string | null;
  isDirty: boolean;
  isLocalOnly?: boolean;
};

export type TranslationAuthority = {
  promptSource: string | null;
  llmProvider: string | null;
};

export type TranscriptEditorState = {
  sourceVideoId: string;
  analysisVersion: string | null;
  translationPreset: string | null;
  segments: EditableSegment[];
  selectedSegmentId: string | null;
};

export type TranscriptSavePayload = {
  segments: Array<{
    transcript_segment_id: string;
    translation_segment_id: string | null;
    start_ms: number;
    end_ms: number;
    source_text: string;
    translated_text: string;
    status: TranscriptStatus;
  }>;
};

export type TranscriptValidationWarning = {
  segmentId: string;
  code: string;
  label: string;
};
