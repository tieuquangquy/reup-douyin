import type { CapturedItem } from "../types/capture-inbox";
import { parseDouyinEngagementCount } from "./douyinEngagementZeroSentinels";

export type CaptureInboxResolvedStatus = "Ready" | "Pending" | "Missing" | "Captured" | "Not generated" | "Failed";
export type CaptureInboxEstimatedViews = {
  estimated_view_count_low: number | null;
  estimated_view_count_base: number | null;
  estimated_view_count_high: number | null;
  estimated_view_source: "like_count_estimation" | null;
};

const THUMBNAIL_PRIORITY_KEYS = [
  "thumbnail_url",
  "poster_url",
  "poster",
  "cover_url",
  "cover",
  "origin_cover",
  "dynamic_cover",
  "animated_cover",
  "thumb_url",
  "thumbnail",
  "image_url",
  "image",
  "url_list"
];

const IMAGE_HOST_MARKERS = ["douyinpic.com", "byteimg.com", "douyinstatic.com"];

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";

export function resolveThumbnailUrl(item: CapturedItem): string | null {
  return firstThumbnailCandidate(
    item.thumbnail_url,
    isImageLikeUrl(item.preview_url ?? "") ? item.preview_url : null,
    thumbnailCandidateFromRecord(item.metadata_json),
    thumbnailCandidateFromRecord(item.raw_payload_json)
  );
}

/** Browser-safe thumbnail src: Douyin CDN hotlink protection is bypassed via API proxy. */
export function resolveThumbnailDisplayUrl(item: CapturedItem): string | null {
  const direct = resolveThumbnailUrl(item);
  if (!direct) return null;
  if (!needsDouyinThumbnailProxy(direct)) return direct;
  const base = API_BASE_URL.replace(/\/$/, "");
  return `${base}/capture-inbox/items/${item.id}/thumbnail`;
}

function needsDouyinThumbnailProxy(url: string): boolean {
  const lower = url.toLowerCase();
  return lower.includes("douyin.com")
    || lower.includes("douyinpic.com")
    || lower.includes("byteimg.com")
    || lower.includes("douyinstatic.com")
    || lower.includes("/tos-");
}

export function resolveDuration(item: CapturedItem): string {
  const text = canonicalString(item, "duration_text");
  if (text) return text;
  if (typeof item.duration_seconds === "number") return formatDuration(item.duration_seconds);
  return "Not captured";
}

export function resolvePosted(item: CapturedItem): string {
  if (item.posted_at) return formatDateTime(item.posted_at);
  const postedText = validPostedText(canonicalString(item, "posted_text"));
  return postedText ?? "Not captured";
}

export function resolveViewCount(item: CapturedItem): string {
  return resolveMetric(item, "view_count", "view_count_text", "play_count");
}

export function resolveKnownViewCountValue(item: CapturedItem): number | null {
  const directViewCount = typeof item.view_count === "number" ? item.view_count : null;
  const metadataViewCount = numberMetadata(item.metadata_json, "view_count");
  const stats = recordMetadata(item.raw_payload_json, "statistics") ?? recordMetadata(item.raw_payload_json, "stats");
  const statsViewCount = numberMetadata(stats, "view_count");
  const statsPlayCount = numberMetadata(stats, "play_count");
  const fallbackKnownValue = metadataViewCount ?? statsViewCount ?? statsPlayCount;

  if (directViewCount === null) {
    return fallbackKnownValue;
  }

  if (directViewCount !== 0) {
    if (hasTrustedViewSource(item.view_count_source) || fallbackKnownValue !== null || metadataSummaryMentionsViewCount(item.metadata_source_summary)) {
      return directViewCount;
    }
    return null;
  }

  if (hasTrustedViewSource(item.view_count_source)) {
    return 0;
  }

  if (fallbackKnownValue === 0 || metadataSummaryMentionsViewCount(item.metadata_source_summary)) {
    return 0;
  }

  return null;
}

export function resolveEstimatedViews(item: CapturedItem): CaptureInboxEstimatedViews {
  const hasRealViewCount = resolveKnownViewCountValue(item) !== null;
  const likeCount = canonicalNumber(item, "like_count", "digg_count");

  if (hasRealViewCount || likeCount === null || likeCount <= 0) {
    return {
      estimated_view_count_low: null,
      estimated_view_count_base: null,
      estimated_view_count_high: null,
      estimated_view_source: null
    };
  }

  return {
    estimated_view_count_low: Math.round(likeCount * 20),
    estimated_view_count_base: Math.round(likeCount * 33),
    estimated_view_count_high: Math.round(likeCount * 100),
    estimated_view_source: "like_count_estimation"
  };
}

function hasTrustedViewSource(source: CapturedItem["view_count_source"]): boolean {
  return Boolean(source && source !== "missing" && source !== "fallback_none");
}

function metadataSummaryMentionsViewCount(summary: string | null | undefined): boolean {
  if (!summary) return false;
  return /view count|view_count|play count|play_count|views/i.test(summary);
}

export function resolveLikeCount(item: CapturedItem): string {
  return resolveMetric(item, "like_count", "like_count_text", "digg_count");
}

export function resolveCommentCount(item: CapturedItem): string {
  return resolveMetric(item, "comment_count", "comment_count_text");
}

export function resolveShareCount(item: CapturedItem): string {
  return resolveMetric(item, "share_count", "share_count_text");
}

export function exactEngagementMetricDisplay(
  value: number | null | undefined,
  resolvedValue: string
): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString("en-US");
  }
  if (resolvedValue === "Not captured") {
    return "\u2014";
  }
  const parsedCompact = parseEngagementMetricToken(resolvedValue);
  if (parsedCompact !== null) {
    return parsedCompact.toLocaleString("en-US");
  }
  const parsed = Number(resolvedValue.replace(/,/g, ""));
  if (Number.isFinite(parsed)) {
    return parsed.toLocaleString("en-US");
  }
  return resolvedValue;
}

export function formatExactEngagementMetric(
  count: number | null | undefined,
  text: string | null | undefined,
  fallback = "\u2014"
): string {
  const resolved = text?.trim() || "Not captured";
  if (resolved === "Not captured") {
    return typeof count === "number" && Number.isFinite(count) ? count.toLocaleString("en-US") : fallback;
  }
  return exactEngagementMetricDisplay(count ?? null, resolved);
}

export function resolveEngagementCountNumber(item: CapturedItem, metric: "comment" | "share"): number | null {
  const countKey = metric === "comment" ? "comment_count" : "share_count";
  const textKey = metric === "comment" ? "comment_count_text" : "share_count_text";
  const direct = canonicalNumber(item, countKey);
  if (typeof direct === "number") return direct;

  const textCandidates = engagementTextCandidates(item, textKey);
  for (const text of textCandidates) {
    const zero = parseDouyinEngagementCount(metric, text, {
      shareIconContext: metric === "share" && text === "分享"
    });
    if (zero === 0) return 0;
  }
  return null;
}

export function resolvePreviewStatus(item: CapturedItem): CaptureInboxResolvedStatus {
  if (item.preview_status === "ready" || item.preview_ready) return "Ready";
  if (item.preview_status === "pending") return "Pending";
  if (item.preview_status === "missing") return "Missing";
  if (resolveThumbnailUrl(item) || (item.preview_url && isImageLikeUrl(item.preview_url))) return "Ready";
  return "Missing";
}

export function resolveSourceLinkStatus(item: CapturedItem): CaptureInboxResolvedStatus {
  if (item.source_link_status === "captured" || item.source_url || item.share_url) return "Captured";
  return "Missing";
}

export function resolveMediaAssetStatus(item: CapturedItem): CaptureInboxResolvedStatus {
  if (item.media_asset_status === "ready" || item.media_ready) return "Ready";
  if (item.media_asset_status === "failed") return "Failed";
  return "Not generated";
}

export function resolveMediaStatus(item: CapturedItem): CaptureInboxResolvedStatus {
  return resolveMediaAssetStatus(item);
}

export function formatCaptureInboxDateTime(value: string | null): string {
  return formatDateTime(value);
}

function resolveMetric(item: CapturedItem, valueKey: keyof CapturedItem & string, textKey: keyof CapturedItem & string, alternateKey?: string): string {
  const metric = valueKey === "comment_count" ? "comment" : valueKey === "share_count" ? "share" : null;
  if (metric) {
    const resolved = resolveEngagementCountNumber(item, metric);
    if (typeof resolved === "number") return formatNumber(resolved);
  }
  const numeric = canonicalNumber(item, valueKey, alternateKey);
  if (typeof numeric === "number") return formatNumber(numeric);
  return canonicalString(item, textKey) ?? "Not captured";
}

function engagementTextCandidates(item: CapturedItem, textKey: "comment_count_text" | "share_count_text"): string[] {
  const candidates: string[] = [];
  const push = (value: string | null | undefined) => {
    const trimmed = value?.trim();
    if (trimmed && !candidates.includes(trimmed)) candidates.push(trimmed);
  };
  push(canonicalString(item, textKey));
  for (const container of [
    item.metadata_json,
    item.raw_payload_json,
    recordMetadata(item.metadata_json, "raw_dom_detail_metrics"),
    recordMetadata(item.raw_payload_json, "raw_dom_detail_metrics")
  ]) {
    push(stringMetadata(container, textKey));
    push(stringMetadata(container, textKey.replace("_count_text", "_text")));
  }
  return candidates;
}

function firstThumbnailCandidate(...values: Array<unknown>): string | null {
  for (const value of values) {
    const found = findImageLikeUrl(value, false);
    if (found) return found;
  }
  return null;
}

function thumbnailCandidateFromRecord(value: Record<string, unknown> | null | undefined): string | null {
  if (!value) return null;
  for (const key of THUMBNAIL_PRIORITY_KEYS) {
    if (key in value) {
      const found = findImageLikeUrl(value[key], true);
      if (found) return found;
    }
  }
  return null;
}

function findImageLikeUrl(value: unknown, preferAnyString: boolean): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed && (isImageLikeUrl(trimmed) || (preferAnyString && isAllowedThumbnailCandidate(trimmed)))) return trimmed;
    return null;
  }
  if (Array.isArray(value)) {
    for (const entry of value) {
      const found = findImageLikeUrl(entry, preferAnyString);
      if (found) return found;
    }
    return null;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const prioritized = thumbnailCandidateFromRecord(record);
    if (prioritized) return prioritized;
    for (const [key, nested] of Object.entries(record)) {
      const normalizedKey = key.toLowerCase();
      if (normalizedKey.includes("thumb") || normalizedKey.includes("cover") || normalizedKey.includes("poster") || normalizedKey.includes("image") || normalizedKey === "url_list") {
        const found = findImageLikeUrl(nested, true);
        if (found) return found;
      }
    }
    for (const nested of Object.values(record)) {
      const found = findImageLikeUrl(nested, false);
      if (found) return found;
    }
  }
  return null;
}

function isAllowedThumbnailCandidate(value: string): boolean {
  const normalized = value.trim().toLowerCase();
  return (normalized.startsWith("http://") || normalized.startsWith("https://")) && IMAGE_HOST_MARKERS.some((marker) => normalized.includes(marker));
}

function isImageLikeUrl(value: string): boolean {
  const normalized = value.trim().toLowerCase().split("?", 1)[0];
  return normalized.startsWith("data:image/") || ((normalized.startsWith("http://") || normalized.startsWith("https://")) && /\.(jpe?g|png|webp|gif|avif)$/.test(normalized));
}

function canonicalString(item: CapturedItem, key: keyof CapturedItem & string): string | null {
  const direct = item[key];
  if (typeof direct === "string" && direct.trim()) return direct;
  return stringMetadata(item.metadata_json, key);
}

function canonicalNumber(item: CapturedItem, key: keyof CapturedItem & string, alternateKey?: string): number | null {
  const direct = item[key];
  if (typeof direct === "number") return direct;
  const stats = recordMetadata(item.raw_payload_json, "statistics") ?? recordMetadata(item.raw_payload_json, "stats") ?? {};
  return numberMetadata(item.metadata_json, key) ?? numberMetadata(stats, key) ?? (alternateKey ? numberMetadata(stats, alternateKey) : null);
}

function stringMetadata(payload: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = payload?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function recordMetadata(payload: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  const value = payload?.[key];
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function numberMetadata(payload: Record<string, unknown> | null | undefined, key: string): number | null {
  const value = payload?.[key];
  if (typeof value === "number") return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function parseEngagementMetricToken(value: string): number | null {
  let text = value.trim().replaceAll(",", "").replaceAll("，", "");
  text = text.replace(/(?:次播放|播放|views?|likes?|comments?|shares?|赞|评论|分享|收藏)/gi, "").trim();
  const match = text.match(/^((?:\d+)(?:\.\d+)?)\s*([kKmMbB万亿]?)$/i);
  if (!match) return null;
  const numeric = Number(match[1]);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  const suffix = match[2]?.toLowerCase() ?? "";
  const multiplier = suffix === "万" ? 10000 : suffix === "亿" ? 100000000 : suffix === "k" ? 1000 : suffix === "m" ? 1000000 : suffix === "b" ? 1000000000 : 1;
  return Math.round(numeric * multiplier);
}

function formatDuration(value: number): string {
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function validPostedText(value: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d+(?:\.\d+)?$/.test(trimmed)) return null;
  const looksLikeDate = /\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2}(?:\s+\d{1,2}:\d{2})?/i.test(trimmed);
  const looksLikeCnRelative = /\d+\s*(?:分钟前|小时前|天前|周前|月前|年前)|昨天|前天/i.test(trimmed);
  const looksLikeEnRelative = /\b\d+\s+(?:minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago\b/i.test(trimmed);
  return looksLikeDate || looksLikeCnRelative || looksLikeEnRelative ? trimmed : null;
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not captured";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes} ${date.getDate()}/${date.getMonth() + 1}/${date.getFullYear()}`;
}
