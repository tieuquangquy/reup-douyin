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
  if (seconds == null) return "unknown";
  const wholeSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(wholeSeconds / 60);
  const rest = wholeSeconds % 60;
  return `${minutes}:${rest.toString().padStart(2, "0")}`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.length > 0);
}
