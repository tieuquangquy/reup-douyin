export type TtsVoiceConfig = {
  voice_id: string;
  language_code: string;
  speaking_rate: number;
};

export type TtsCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
  runtime_version: string;
};

export type TtsSummaryAsset = {
  id: string;
  asset_type: string;
  storage_key?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type TtsFitStatus = "fits_well" | "slightly_long" | "too_long" | "too_short";

export type TtsClipFit = {
  asset_id: string;
  translation_segment_id: string | null;
  translation_segment_ids?: string[];
  member_segment_indices?: number[];
  fit_status: TtsFitStatus | string | null;
  fit_ratio: number | null;
  duration_seconds?: number | null;
  warnings: string[];
};

export type TtsTimingFitSummary = {
  fits_well: number;
  slightly_long: number;
  too_long: number;
  too_short: number;
};

export type TtsSummaryResponse = {
  source_video_id: string;
  tts_asset_count: number;
  subtitle_count: number;
  warnings: string[];
  clips?: TtsClipFit[];
  timing_fit_summary?: TtsTimingFitSummary;
  temporal?: {
    pipeline_version?: string;
    status?: string;
    input_segment_count?: number;
    dialogue_group_count?: number;
    merged_segment_count?: number;
    candidate_probe_count?: number;
    selective_correction_count?: number;
    background_audio_preserved?: boolean;
    artifact_count?: number;
    final_timing_fit_passed?: boolean;
    tts_authority?: {
      schema_version?: string;
      profile_id?: string;
      profile_name?: string;
      provider?: string;
      model_id?: string;
      voice_id?: string;
      config_fingerprint?: string;
      configured_fallback_suppressed?: boolean;
    };
    performance?: {
      total_clip_count?: number;
      fitted_cache_hit_count?: number;
      acoustic_cache_hit_count?: number;
      provider_synthesis_clip_count?: number;
      provider_synthesis_call_count?: number;
      synthesis_strategy?: string;
      whole_video_version?: string | null;
      narration_block_count?: number;
      single_request_video?: boolean;
      whole_video_block_fit_count?: number;
      whole_video_block_refit_count?: number;
      whole_video_repair_batch_count?: number;
      whole_video_repaired_segment_count?: number;
      whole_video_gap_borrow_count?: number;
      whole_video_gap_borrowed_ms?: number;
      provider_avoidance_ratio?: number;
      provider_elapsed_ms?: number;
      total_elapsed_ms?: number;
      warmup?: {
        status?: string;
        device?: string;
        owner?: string;
      };
    };
  } | null;
  temporal_artifacts?: Array<{
    id: string;
    manifest_group?: string | null;
    storage_key?: string | null;
    sha256?: string | null;
  }>;
  assets: TtsSummaryAsset[];
};

export function findJoinedTtsAssetId(summary: TtsSummaryResponse | null | undefined): string | null {
  const assets = summary?.assets ?? [];
  const joined = assets.find((asset) => asset.asset_type === "TTS_AUDIO_JOINED");
  return joined?.id ?? null;
}

/** Map translation_segment_id → clip fit for Editor beat badges. */
export function indexTtsClipFitsByTranslationId(
  summary: TtsSummaryResponse | null | undefined
): Map<string, TtsClipFit> {
  const map = new Map<string, TtsClipFit>();
  for (const clip of summary?.clips ?? []) {
    const ids = clip.translation_segment_ids?.length
      ? clip.translation_segment_ids
      : clip.translation_segment_id
        ? [clip.translation_segment_id]
        : [];
    for (const id of ids) {
      map.set(id, clip);
    }
  }
  return map;
}

export function isTtsFitProblem(status: string | null | undefined): boolean {
  return status === "slightly_long" || status === "too_long" || status === "too_short";
}
