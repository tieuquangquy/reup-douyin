export type TtsVoiceConfig = {
  voice_id: string;
  language_code: string;
  speaking_rate: number;
};

export type TtsCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
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
    if (clip.translation_segment_id) {
      map.set(clip.translation_segment_id, clip);
    }
  }
  return map;
}

export function isTtsFitProblem(status: string | null | undefined): boolean {
  return status === "slightly_long" || status === "too_long" || status === "too_short";
}
