import { resolveEngagementCountNumber, resolveEstimatedViews, resolveKnownViewCountValue, resolveThumbnailUrl } from "./captureInboxCanonical";
import type { CapturedItem } from "../types/capture-inbox";

export type MetadataHealthFilter =
  | "complete"
  | "missing_posted"
  | "missing_thumbnail"
  | "missing_duration"
  | "missing_views"
  | "missing_metrics"
  | "actionable";

export type EstimatedViewsSource = "normalized" | "backend_display" | "legacy_display" | "derived_from_likes" | "view_count" | "missing";
export type EstimatedViewsConfidence = "high" | "medium" | "low" | "none";

export type EstimatedViewsForItem = {
  min: number | null;
  max: number | null;
  mid: number | null;
  display: string | null;
  source: EstimatedViewsSource;
  confidence: EstimatedViewsConfidence;
  sourceField: string;
  sourceValue?: unknown;
};

export type ComparableEstimatedViews = {
  value: number | null;
  source: string;
  display: string | null;
  min?: number | null;
  max?: number | null;
  sourceValue?: unknown;
};

export type DouyinMetadataCompleteness = {
  hasThumbnail: boolean;
  hasPosted: boolean;
  hasDuration: boolean;
  hasEstimatedViews: boolean;
  hasLikes: boolean;
  hasComments: boolean;
  hasShares: boolean;
  hasCoreMetrics: boolean;
  hasAllCoreMetadata: boolean;
  missingFields: string[];
  sourceDiagnostics: Record<string, string>;
};

export type DouyinFilterMetadata = {
  awemeId: string | null;
  caption: string | null;
  postedAt: string | null;
  postedDisplay: string | null;
  durationSeconds: number | null;
  estimatedViewsMin: number | null;
  estimatedViewsMax: number | null;
  estimatedViewsMid: number | null;
  estimatedViewsDisplay: string | null;
  likeCount: number | null;
  commentCount: number | null;
  shareCount: number | null;
  favoriteCount: number | null;
  engagementScore: number | null;
  engagementRate: number | null;
  hasThumbnail: boolean;
  hasPosted: boolean;
  hasDuration: boolean;
  hasEstimatedViews: boolean;
  hasAllCoreMetadata: boolean;
  missingMetadataFields: string[];
  sourceDiagnostics: {
    filter_adapter_used: true;
    views_source_field: string;
    views_source_value: unknown;
    views_comparable_value: number | null;
  };
  comparableViews: ComparableEstimatedViews;
};

type AnyRecord = Record<string, unknown>;

const ESTIMATED_VIEWS_ERROR = "Invalid estimated views format. Try 10000, 10K, 1.2M, or 3万.";

export type CompactNumberParseResult = {
  value: number | null;
  valid: boolean;
  error?: string;
  normalizedDisplay?: string;
};

export type EstimatedViewsTextParseResult = CompactNumberParseResult & {
  min?: number | null;
  max?: number | null;
};

export function parseCompactNumberInput(value: string | null | undefined): CompactNumberParseResult {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) return { value: null, valid: true };
  const parsed = parseCompactNumberToken(trimmed);
  if (parsed === null) return { value: null, valid: false, error: ESTIMATED_VIEWS_ERROR };
  return { value: parsed, valid: true, normalizedDisplay: formatCompactNumber(parsed) };
}

export function parseCompactNumber(value: string): number | null {
  const result = parseCompactNumberInput(value);
  return result.valid ? result.value : null;
}

export function parseEstimatedViewsText(value: string | null | undefined): EstimatedViewsTextParseResult {
  const trimmed = value?.trim() ?? "";
  if (!trimmed) return { value: null, valid: true };
  const normalized = trimmed.replaceAll("，", ",");
  const parts = normalized.split(/\s*(?:-|–|—|~|to|至|到)\s*/i).filter(Boolean);
  if (parts.length >= 2) {
    const low = parseCompactNumberToken(parts[0]);
    const high = parseCompactNumberToken(parts[1]);
    if (low !== null && high !== null) {
      const min = Math.min(low, high);
      const max = Math.max(low, high);
      const value = Math.round((min + max) / 2);
      return { value, min, max, valid: true, normalizedDisplay: `${formatCompactNumber(min)}–${formatCompactNumber(max)}` };
    }
  }
  const single = parseCompactNumberToken(normalized);
  if (single !== null) return { value: single, min: single, max: single, valid: true, normalizedDisplay: formatCompactNumber(single) };
  return { value: null, valid: false, error: ESTIMATED_VIEWS_ERROR };
}

export function getEstimatedViewsForItem(item: CapturedItem): EstimatedViewsForItem {
  return resolveEstimatedViewsForItem(item);
}

export function getComparableEstimatedViews(item: CapturedItem): ComparableEstimatedViews {
  const metadata = getDouyinItemMetadataForFilters(item);
  return metadata.comparableViews;
}

export function estimatedViewsRangeMatches(estimatedViews: EstimatedViewsForItem | ComparableEstimatedViews, minFilter: number | null, maxFilter: number | null): boolean {
  if (minFilter === null && maxFilter === null) return true;
  const min = "mid" in estimatedViews ? estimatedViews.min : estimatedViews.min ?? null;
  const max = "mid" in estimatedViews ? estimatedViews.max : estimatedViews.max ?? null;
  const mid = "mid" in estimatedViews ? estimatedViews.mid : estimatedViews.value;
  if (min === null && max === null && mid === null) return false;

  if (minFilter !== null && maxFilter !== null) {
    const itemMax = max ?? mid;
    const itemMin = min ?? mid;
    return itemMax !== null && itemMin !== null && itemMax >= minFilter && itemMin <= maxFilter;
  }
  if (minFilter !== null) {
    const itemMax = max ?? mid;
    return itemMax !== null && itemMax >= minFilter;
  }
  const itemMin = min ?? mid;
  return itemMin !== null && itemMin <= (maxFilter as number);
}

export function getDouyinItemMetadataForFilters(item: CapturedItem): DouyinFilterMetadata {
  const comparableViews = resolveComparableEstimatedViews(item);
  const completeness = getDouyinMetadataCompletenessForItem(item, comparableViews);
  const likeCount = firstNumber(item.like_count, valueAt(item, "metrics.like_count"), valueAt(item, "metrics.likes"));
  const commentCount = resolveEngagementCountNumber(item, "comment")
    ?? firstNumber(item.comment_count, valueAt(item, "metrics.comment_count"), valueAt(item, "metrics.comments"));
  const shareCount = resolveEngagementCountNumber(item, "share")
    ?? firstNumber(item.share_count, valueAt(item, "metrics.share_count"), valueAt(item, "metrics.shares"));
  const favoriteCount = firstNumber(item.favorite_count, valueAt(item, "metrics.favorite_count"), valueAt(item, "metrics.favorites"));
  const engagementRate = deriveEngagementRate(
    likeCount,
    commentCount,
    shareCount,
    comparableViews.value,
    firstNumber(item.engagement_rate)
  );

  return {
    awemeId: item.aweme_id ?? item.source_video_external_id ?? null,
    caption: item.caption ?? item.title ?? null,
    postedAt: item.posted_at ?? null,
    postedDisplay: item.posted_display ?? item.posted_text ?? null,
    durationSeconds: numberFromUnknown(item.duration_seconds),
    estimatedViewsMin: comparableViews.min ?? null,
    estimatedViewsMax: comparableViews.max ?? null,
    estimatedViewsMid: comparableViews.value,
    estimatedViewsDisplay: comparableViews.display,
    likeCount,
    commentCount,
    shareCount,
    favoriteCount,
    engagementScore: firstNumber(item.engagement_score),
    engagementRate,
    hasThumbnail: completeness.hasThumbnail,
    hasPosted: completeness.hasPosted,
    hasDuration: completeness.hasDuration,
    hasEstimatedViews: completeness.hasEstimatedViews,
    hasAllCoreMetadata: completeness.hasAllCoreMetadata,
    missingMetadataFields: completeness.missingFields,
    sourceDiagnostics: {
      filter_adapter_used: true,
      views_source_field: comparableViews.source,
      views_source_value: comparableViews.sourceValue ?? null,
      views_comparable_value: comparableViews.value
    },
    comparableViews
  };
}

export function metadataHealthMatches(metadata: DouyinFilterMetadata, filters: MetadataHealthFilter[]): boolean {
  if (!filters.length) return true;
  return filters.some((filter) => {
    if (filter === "complete") return metadata.hasAllCoreMetadata;
    if (filter === "missing_posted") return !metadata.hasPosted;
    if (filter === "missing_thumbnail") return !metadata.hasThumbnail;
    if (filter === "missing_duration") return !metadata.hasDuration;
    if (filter === "missing_views") return !metadata.hasEstimatedViews;
    if (filter === "missing_metrics") return metadata.likeCount === null || metadata.commentCount === null || metadata.shareCount === null;
    return metadata.missingMetadataFields.length > 0;
  });
}

export function metadataHealthCounts(items: CapturedItem[]): Record<MetadataHealthFilter, number> {
  const counts: Record<MetadataHealthFilter, number> = {
    complete: 0,
    missing_posted: 0,
    missing_thumbnail: 0,
    missing_duration: 0,
    missing_views: 0,
    missing_metrics: 0,
    actionable: 0
  };
  for (const item of items) {
    const metadata = getDouyinItemMetadataForFilters(item);
    for (const key of Object.keys(counts) as MetadataHealthFilter[]) {
      if (metadataHealthMatches(metadata, [key])) counts[key] += 1;
    }
  }
  return counts;
}

export function getDouyinMetadataCompletenessForItem(item: CapturedItem, comparableViews: ComparableEstimatedViews = resolveComparableEstimatedViews(item)): DouyinMetadataCompleteness {
  const likeCount = firstNumber(item.like_count, valueAt(item, "metrics.like_count"), valueAt(item, "metrics.likes"));
  const commentCount = resolveEngagementCountNumber(item, "comment")
    ?? firstNumber(item.comment_count, valueAt(item, "metrics.comment_count"), valueAt(item, "metrics.comments"));
  const shareCount = resolveEngagementCountNumber(item, "share")
    ?? firstNumber(item.share_count, valueAt(item, "metrics.share_count"), valueAt(item, "metrics.shares"));
  const durationSeconds = numberFromUnknown(item.duration_seconds);
  const durationText = typeof item.duration_text === "string" ? item.duration_text.trim() : "";
  const hasThumbnail = Boolean(resolveThumbnailUrl(item));
  const hasPosted = Boolean(item.posted_at || item.posted_display || item.posted_text);
  const hasDuration = durationSeconds !== null || durationText.length > 0;
  const hasEstimatedViews = comparableViews.value !== null;
  const hasLikes = likeCount !== null;
  const hasComments = commentCount !== null;
  const hasShares = shareCount !== null;
  const hasCoreMetrics = hasLikes && hasComments && hasShares;
  const flags = { hasThumbnail, hasPosted, hasDuration, hasEstimatedViews, hasLikes, hasComments, hasShares };
  const missingFields = computedMissingFields(flags);
  const hasAllCoreMetadata = missingFields.length === 0;
  const staleBackendMissing = Array.isArray(item.missing_metadata_fields) && item.missing_metadata_fields.length > 0 && hasAllCoreMetadata;

  return {
    hasThumbnail,
    hasPosted,
    hasDuration,
    hasEstimatedViews,
    hasLikes,
    hasComments,
    hasShares,
    hasCoreMetrics,
    hasAllCoreMetadata,
    missingFields,
    sourceDiagnostics: {
      thumbnail: hasThumbnail ? "thumbnail resolver" : "missing",
      posted: hasPosted ? (item.posted_at ? "posted_at" : item.posted_display ? "posted_display" : "posted_text") : "missing",
      duration: hasDuration ? (durationSeconds !== null ? "duration_seconds" : "duration_text") : "missing",
      estimatedViews: hasEstimatedViews ? comparableViews.source : "missing",
      likes: hasLikes ? "like_count" : "missing",
      comments: hasComments ? "comment_count" : "missing",
      shares: hasShares ? "share_count" : "missing",
      needs_metadata_computed_has_all_core_metadata: String(hasAllCoreMetadata),
      needs_metadata_stale_backend_flag_ignored: String(staleBackendMissing)
    }
  };
}

function resolveComparableEstimatedViews(item: CapturedItem): ComparableEstimatedViews {
  const estimatedViews = getEstimatedViewsForItem(item);
  return {
    value: estimatedViews.mid,
    source: estimatedViews.sourceField,
    display: estimatedViews.display,
    min: estimatedViews.min,
    max: estimatedViews.max,
    sourceValue: estimatedViews.sourceValue ?? null
  };
}

function resolveEstimatedViewsForItem(item: CapturedItem): EstimatedViewsForItem {
  const numericSources: Array<[string, unknown]> = [
    ["estimated_views_mid", item.estimated_views_mid],
    ["estimatedViewsMid", valueAt(item, "estimatedViewsMid")],
    ["metrics.estimated_views_mid", valueAt(item, "metrics.estimated_views_mid")],
    ["performance.estimated_views_mid", valueAt(item, "performance.estimated_views_mid")]
  ];
  for (const [sourceField, candidate] of numericSources) {
    const value = numberFromUnknown(candidate);
    if (value !== null) return estimated(value, value, value, formatCompactNumber(value), "normalized", "high", sourceField, candidate);
  }

  const snakeAverage = averagePair(item.estimated_views_min, item.estimated_views_max);
  if (snakeAverage) return estimated(snakeAverage.min, snakeAverage.max, snakeAverage.value, `${formatCompactNumber(snakeAverage.min)}–${formatCompactNumber(snakeAverage.max)}`, "normalized", "high", "estimated_views_min/estimated_views_max", `${item.estimated_views_min}/${item.estimated_views_max}`);
  const camelAverage = averagePair(valueAt(item, "estimatedViewsMin"), valueAt(item, "estimatedViewsMax"));
  if (camelAverage) return estimated(camelAverage.min, camelAverage.max, camelAverage.value, `${formatCompactNumber(camelAverage.min)}–${formatCompactNumber(camelAverage.max)}`, "normalized", "high", "estimatedViewsMin/estimatedViewsMax", `${String(valueAt(item, "estimatedViewsMin"))}/${String(valueAt(item, "estimatedViewsMax"))}`);

  const backendDisplaySources: Array<[string, unknown]> = [
    ["estimated_views_display", item.estimated_views_display],
    ["estimatedViewsDisplay", valueAt(item, "estimatedViewsDisplay")]
  ];
  for (const [sourceField, candidate] of backendDisplaySources) {
    const parsed = estimatedFromDisplayCandidate(candidate, sourceField, "backend_display", "high");
    if (parsed) return parsed;
  }

  const legacyDisplaySources: Array<[string, unknown]> = [
    ["estimated_views_text_raw", item.estimated_views_text_raw],
    ["estimated_views", valueAt(item, "estimated_views")],
    ["est_views", valueAt(item, "est_views")],
    ["views_estimate", valueAt(item, "views_estimate")],
    ["estimated_view_count", valueAt(item, "estimated_view_count")],
    ["estimated_view_mid", valueAt(item, "estimated_view_mid")],
    ["metrics.estimated_views_display", valueAt(item, "metrics.estimated_views_display")],
    ["performance.estimated_views_display", valueAt(item, "performance.estimated_views_display")],
    ["metadata_json.estimated_views_display", valueAt(item, "metadata_json.estimated_views_display")],
    ["raw_payload_json.estimated_views_display", valueAt(item, "raw_payload_json.estimated_views_display")]
  ];
  for (const [sourceField, candidate] of legacyDisplaySources) {
    const parsed = estimatedFromDisplayCandidate(candidate, sourceField, "legacy_display", "medium");
    if (parsed) return parsed;
  }

  const knownViewCount = resolveKnownViewCountValue(item);
  if (knownViewCount !== null) return estimated(knownViewCount, knownViewCount, knownViewCount, formatCompactNumber(knownViewCount), "view_count", "high", "view_count", item.view_count);
  for (const [sourceField, candidate] of [["view_count", item.view_count], ["views", valueAt(item, "views")], ["metrics.views", valueAt(item, "metrics.views")]] as Array<[string, unknown]>) {
    const value = numberFromUnknown(candidate);
    if (value !== null) return estimated(value, value, value, formatCompactNumber(value), "view_count", "high", sourceField, candidate);
  }

  const likeEstimate = resolveEstimatedViews(item);
  if (likeEstimate.estimated_view_count_base !== null) {
    const mid = likeEstimate.estimated_view_count_base;
    const min = likeEstimate.estimated_view_count_low ?? mid;
    const max = likeEstimate.estimated_view_count_high ?? mid;
    return estimated(min, max, mid, min === max ? formatCompactNumber(mid) : `${formatCompactNumber(min)}–${formatCompactNumber(max)}`, "derived_from_likes", "low", "resolveEstimatedViews.like_count_estimation", item.like_count);
  }

  return estimated(null, null, null, null, "missing", "none", "missing", null);
}

function estimatedFromDisplayCandidate(candidate: unknown, sourceField: string, source: EstimatedViewsSource, confidence: EstimatedViewsConfidence): EstimatedViewsForItem | null {
  const numeric = numberFromUnknown(candidate);
  if (numeric !== null) return estimated(numeric, numeric, numeric, formatCompactNumber(numeric), source, confidence, sourceField, candidate);
  if (typeof candidate !== "string") return null;
  const parsed = parseEstimatedViewsText(candidate);
  if (parsed.valid && parsed.value !== null) return estimated(parsed.min ?? parsed.value, parsed.max ?? parsed.value, parsed.value, parsed.normalizedDisplay ?? candidate, source, confidence, sourceField, candidate);
  return null;
}

function estimated(min: number | null, max: number | null, mid: number | null, display: string | null, source: EstimatedViewsSource, confidence: EstimatedViewsConfidence, sourceField: string, sourceValue: unknown): EstimatedViewsForItem {
  return { min, max, mid, display, source, confidence, sourceField, sourceValue };
}

function averagePair(left: unknown, right: unknown): { value: number; min: number; max: number } | null {
  const minCandidate = numberFromUnknown(left);
  const maxCandidate = numberFromUnknown(right);
  if (minCandidate === null || maxCandidate === null) return null;
  const min = Math.min(minCandidate, maxCandidate);
  const max = Math.max(minCandidate, maxCandidate);
  return { value: Math.round((min + max) / 2), min, max };
}

function parseCompactNumberToken(value: string): number | null {
  let text = value.trim().replaceAll(",", "").replaceAll("，", "");
  text = text.replace(/(?:次播放|播放|views?|likes?|comments?|shares?|赞|评论|分享|收藏)/gi, "").trim();
  const match = text.match(/^((?:\d+)(?:\.\d+)?)\s*([kKmMbB万亿]?)$/);
  if (!match) return null;
  const numeric = Number(match[1]);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  const suffix = match[2];
  const multiplier = suffix === "万" ? 10000 : suffix === "亿" ? 100000000 : suffix.toLowerCase() === "k" ? 1000 : suffix.toLowerCase() === "m" ? 1000000 : suffix.toLowerCase() === "b" ? 1000000000 : 1;
  return Math.round(numeric * multiplier);
}

function valueAt(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => (isRecord(current) ? current[key] : undefined), value);
}

function isRecord(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberFromUnknown(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) return value;
  if (typeof value !== "string") return null;
  return parseCompactNumberToken(value);
}

function firstNumber(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = numberFromUnknown(value);
    if (parsed !== null) return parsed;
  }
  return null;
}

function deriveEngagementRate(
  likeCount: number | null,
  commentCount: number | null,
  shareCount: number | null,
  viewsMid: number | null,
  existingRate: number | null
): number | null {
  if (existingRate !== null) return existingRate;
  if (viewsMid === null || viewsMid <= 0) return null;
  const totalEngagement = (likeCount ?? 0) + (commentCount ?? 0) + (shareCount ?? 0);
  if (totalEngagement <= 0) return null;
  return totalEngagement / viewsMid;
}

function computedMissingFields(flags: Record<string, boolean>): string[] {
  const missing: string[] = [];
  if (!flags.hasThumbnail) missing.push("thumbnail");
  if (!flags.hasPosted) missing.push("posted");
  if (!flags.hasDuration) missing.push("duration");
  if (!flags.hasEstimatedViews) missing.push("views");
  if (!flags.hasLikes) missing.push("likes");
  if (!flags.hasComments) missing.push("comments");
  if (!flags.hasShares) missing.push("shares");
  return missing;
}

/** Tile missing-metadata line — same authority as filters/score (canonical resolvers). */
export function formatCaptureInboxTileMetadataGap(item: CapturedItem): string | null {
  const { missingFields } = getDouyinMetadataCompletenessForItem(item);
  return missingFields.length > 0 ? missingFields.join(", ") : null;
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits: 1, notation: "compact" }).format(value);
}
