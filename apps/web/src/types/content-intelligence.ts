import type { Job } from "./jobs";

export type TopicCategory = {
  id: string;
  workspace_id: string;
  taxonomy_version: string;
  code: string;
  name: string;
  description: string | null;
  parent_id: string | null;
  keywords_json: string[] | null;
  sort_order: number;
  is_active: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type TopicCategoryListResponse = {
  topics: TopicCategory[];
  taxonomy_version: string;
};

export type ClassificationEvidence = {
  source: "PUBLICATION_TITLE" | "PUBLICATION_CAPTION" | "DRAFT_TITLE" | "DRAFT_CAPTION" | "SOURCE_CAPTION" | "TRANSCRIPT" | "OCR";
  source_id: string | null;
  text: string;
  language_code: string | null;
  confidence: number | null;
  matched_keywords: string[];
};

export type ContentClassification = {
  id: string;
  workspace_id: string;
  platform_publication_id: string;
  source_video_id: string | null;
  taxonomy_version: string;
  classifier_version: string;
  input_fingerprint_sha256: string;
  decision_status: "NEEDS_REVIEW" | "APPROVED" | "OVERRIDDEN";
  primary_topic_id: string | null;
  primary_topic_code: string | null;
  primary_topic_name: string | null;
  confidence: number;
  secondary_topics_json: Array<Record<string, unknown>> | null;
  evidence_json: ClassificationEvidence[] | null;
  rationale: string | null;
  created_by_job_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  override_reason: string | null;
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ContentClassificationRunResponse = {
  reused: boolean;
  classification: ContentClassification | null;
  job: Job | null;
};

export type ContentClassificationJobSummary = {
  id: string;
  status: string;
  progress_percent: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
};

export type ContentClassificationQueueItem = {
  platform_publication_id: string;
  platform_account_id: string;
  page_display_name: string;
  external_reel_id: string | null;
  external_permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  classification: ContentClassification | null;
  latest_job: ContentClassificationJobSummary | null;
};

export type ContentClassificationQueueResponse = {
  items: ContentClassificationQueueItem[];
  total: number;
  limit: number;
  offset: number;
  kpis: {
    total_publications: number;
    unclassified_count: number;
    needs_review_count: number;
    approved_count: number;
    overridden_count: number;
    low_confidence_count: number;
  };
};

export type ContentAiProvider = "auto" | "gemini" | "openai_compatible" | "ollama" | "placeholder";
export type ContentAiMode = "HYBRID" | "AI_ONLY" | "LOCAL_ONLY";
export type ContentAiFallbackMode = "none" | "local_keyword";

export type ContentAiPromptProfile = {
  id: string;
  name: string;
  version: string;
  prompt: string;
  is_active: boolean;
};

export type ContentAiConfig = {
  enabled: boolean;
  provider: ContentAiProvider;
  model: string;
  api_key_set: boolean;
  api_key_masked: string;
  base_url: string;
  timeout_seconds: number;
  fallback_mode: ContentAiFallbackMode;
  mode: ContentAiMode;
  local_confidence_threshold: number;
  temperature: number;
  max_output_tokens: number;
  source: string;
  active_prompt_id: string;
  active_prompt_name: string;
  active_prompt_version: string;
  prompts: ContentAiPromptProfile[];
};

export type ContentAiConfigUpdate = Pick<
  ContentAiConfig,
  | "enabled"
  | "provider"
  | "model"
  | "base_url"
  | "timeout_seconds"
  | "fallback_mode"
  | "mode"
  | "local_confidence_threshold"
  | "temperature"
  | "max_output_tokens"
> & {
  api_key?: string | null;
  clear_api_key?: boolean;
};

export type ContentAiTestResponse = {
  ok: boolean;
  provider: string;
  model: string;
  detail: string;
};

export type ContentAiModelsResponse = {
  ok: boolean;
  provider: string;
  models: string[];
  detail: string;
};
