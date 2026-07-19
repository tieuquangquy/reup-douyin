import type {
  ChecklistState,
  CompareMode,
  MediaAssetManifestEntry,
  RenderOutput,
  SourceVideoAssetManifest
} from "../types/final-review";

export const DEFAULT_FINAL_REVIEW_CHECKLIST: ChecklistState = {
  narration_clear: false,
  subtitle_ok: false,
  timing_ok: false,
  render_clean: false,
  playable: false,
  warnings_checked: false
};

export function getRenderWarnings(render: RenderOutput | null): string[] {
  if (!render) return [];
  const warningSummary = render.warning_summary_json ?? {};
  const metadata = render.metadata_json ?? {};
  const manifest = asRecord(metadata.manifest);
  const manifestWarnings = toStringArray(manifest?.warnings);
  const summaryWarnings = toStringArray(warningSummary.warnings);
  return [...summaryWarnings, ...manifestWarnings].filter((warning, index, all) => all.indexOf(warning) === index);
}

export function getFinalReviewMetadata(render: RenderOutput | null): Record<string, unknown> {
  return asRecord(render?.metadata_json?.final_review) ?? {};
}

export function isPublishReady(render: RenderOutput | null): boolean {
  const finalReview = getFinalReviewMetadata(render);
  return typeof finalReview.publish_ready_at === "string" && finalReview.publish_ready_at.length > 0;
}

export function isApproved(render: RenderOutput | null): boolean {
  return render?.status === "APPROVED";
}

export function findCurrentSourceVideoAsset(manifest: SourceVideoAssetManifest | null): MediaAssetManifestEntry | null {
  const assets = manifest?.assets ?? [];
  return (
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO_RAW" && asset.is_current !== false) ??
    assets.find((asset) => asset.asset_type === "SOURCE_VIDEO" && asset.is_current !== false) ??
    null
  );
}

export function buildOriginalPreviewUrl(
  manifest: SourceVideoAssetManifest | null,
  mediaAssetContentUrl: (assetId: string) => string
): string | null {
  const rawAsset = findCurrentSourceVideoAsset(manifest);
  if (rawAsset?.id) return mediaAssetContentUrl(rawAsset.id);
  return manifest?.source_video?.source_url ?? null;
}

export function nextCompareMode(mode: CompareMode): CompareMode {
  if (mode === "side_by_side") return "final_only";
  if (mode === "final_only") return "original_only";
  return "side_by_side";
}

export function checklistComplete(checklist: ChecklistState): boolean {
  return Object.values(checklist).every(Boolean);
}

export function formatRenderDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  const wholeSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(wholeSeconds / 60);
  const rest = wholeSeconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

export type RenderTechSpecs = {
  width: number | null;
  height: number | null;
  fps: number | null;
  duration_seconds: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  output_format: string | null;
  audio_strategy: string | null;
  subtitle_burned: boolean;
  render_version: string | null;
  status: string;
  size_bytes: number | null;
  job_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  approved_at: string | null;
  publish_ready_at: string | null;
};

/** Prefer render columns; fall back to persisted manifest probe / source duration. */
export function resolveRenderTechSpecs(
  render: RenderOutput,
  manifest: SourceVideoAssetManifest | null = null
): RenderTechSpecs {
  const meta = asRecord(render.metadata_json) ?? {};
  const manifestRecord = asRecord(meta.manifest) ?? {};
  const probe = asRecord(manifestRecord.probe) ?? {};
  const outputProbe = asRecord(probe.output) ?? {};
  const inputProbe = asRecord(probe.input) ?? {};
  const outputAsset = asRecord(manifestRecord.output) ?? {};
  const finalReview = asRecord(meta.final_review) ?? {};

  const width = render.width ?? asPositiveInt(outputProbe.width) ?? asPositiveInt(inputProbe.width);
  const height = render.height ?? asPositiveInt(outputProbe.height) ?? asPositiveInt(inputProbe.height);
  const fps = render.fps ?? asPositiveNumber(outputProbe.fps) ?? asPositiveNumber(inputProbe.fps);
  const duration_seconds =
    render.duration_seconds ??
    asPositiveNumber(outputProbe.duration_seconds) ??
    asPositiveNumber(inputProbe.duration_seconds) ??
    asPositiveNumber(manifest?.source_video?.duration_seconds);

  const linkedAsset =
    (manifest?.assets ?? []).find((asset) => asset.id === render.media_asset_id) ??
    (manifest?.assets ?? []).find((asset) => asset.asset_type === "FINAL_RENDER_VIDEO");

  const size_bytes =
    asPositiveInt(render.size_bytes) ??
    asPositiveInt(outputAsset.size_bytes) ??
    asPositiveInt(meta.size_bytes) ??
    asPositiveInt(linkedAsset?.size_bytes);

  const job_id =
    render.created_by_job_id ??
    asNonEmptyString(meta.created_by_job_id) ??
    asNonEmptyString(manifestRecord.job_id) ??
    asNonEmptyString(linkedAsset?.created_by_job_id) ??
    asNonEmptyString(asRecord(linkedAsset?.metadata_json)?.created_by_job_id);

  return {
    width,
    height,
    fps,
    duration_seconds,
    video_codec: render.video_codec ?? asNonEmptyString(outputProbe.video_codec),
    audio_codec: render.audio_codec ?? asNonEmptyString(outputProbe.audio_codec),
    output_format: render.output_format,
    audio_strategy: render.audio_strategy,
    subtitle_burned: Boolean(render.subtitle_burned),
    render_version: render.render_version ?? `v${render.version}`,
    status: render.status,
    size_bytes,
    job_id,
    started_at: render.started_at,
    finished_at: render.finished_at,
    approved_at: asNonEmptyString(finalReview.approved_at),
    publish_ready_at: asNonEmptyString(finalReview.publish_ready_at)
  };
}

export function formatResolution(width: number | null, height: number | null): string | null {
  if (width == null || height == null) return null;
  return `${width}×${height}`;
}

export function formatFps(fps: number | null): string | null {
  if (fps == null) return null;
  if (Number.isInteger(fps)) return String(fps);
  return String(Math.round(fps * 100) / 100);
}

export function formatBytes(sizeBytes: number | null): string | null {
  if (sizeBytes == null || sizeBytes <= 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${(sizeBytes / 1024).toFixed(1)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}

function asPositiveInt(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) && n > 0 ? Math.round(n) : null;
}

function asPositiveNumber(value: unknown): number | null {
  const n = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(n) && n > 0 ? n : null;
}

function asNonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}
