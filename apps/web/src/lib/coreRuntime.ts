/**
 * Browser-side expectations for the server-authoritative core runtime.
 *
 * The API rejects stale values with HTTP 409. This prevents an old frontend
 * bundle from starting a different recipe while keeping implementation details
 * and all final authority on the server/worker.
 */
export const CORE_STAGE_RUNTIME = {
  DOWNLOAD_VIDEO: "DOWNLOAD_V2",
  ANALYZE_AUDIO: "AUDIO_ANALYSIS_V5",
  BUILD_TRANSLATION_DRAFT: "TRANSLATION_V5",
  SYNTHESIZE_TTS: "TTS_TEMPORAL_V6",
  ANALYZE_OCR: "OCR-V34",
  RENDER_PREVIEW: "QUALITY_LOCALIZATION_V24_1",
  RENDER_FINAL: "RENDER_PIPELINE_V1"
} as const;

export type CoreStageRuntimeMap = typeof CORE_STAGE_RUNTIME;
