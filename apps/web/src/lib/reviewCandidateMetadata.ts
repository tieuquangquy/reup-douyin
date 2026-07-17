import { buildCapturedItemFromReviewCandidate } from "./operatorReupScore";
import { getOperatorTileScoreBadge } from "./operatorTileScore";
import type { Candidate } from "../types/review-board";

export type ReviewCandidateMetadata = {
  captureItemId: string | null;
  captureSessionId: string | null;
  source: string | null;
  sourceModule: string | null;
  awemeId: string | null;
  sourceVideoExternalId: string | null;
  sourceUrl: string | null;
  videoUrl: string | null;
  profileUrl: string | null;
  profileName: string | null;
  caption: string | null;
  title: string | null;
  description: string | null;
  thumbnailUrl: string | null;
  postedDisplay: string | null;
  postedSource: string;
  postedText: string | null;
  postedTextRaw: string | null;
  durationSeconds: number | null;
  durationText: string | null;
  durationSource: string;
  viewCount: number | null;
  viewCountText: string | null;
  estimatedViewsDisplay: string | null;
  estimatedViewsMin: number | null;
  estimatedViewsMax: number | null;
  estimatedViewsMid: number | null;
  likeCount: number | null;
  likeCountText: string | null;
  commentCount: number | null;
  commentCountText: string | null;
  shareCount: number | null;
  shareCountText: string | null;
  favoriteCount: number | null;
  favoriteCountText: string | null;
  engagementRate: number | null;
  reupScore: number | null;
  reupScoreLabel: string | null;
  reupScoreLevel: string | null;
  missingMetadataFields: string[] | null;
  capture_item_id: string | null;
  capture_session_id: string | null;
  source_video_external_id: string | null;
  source_url: string | null;
  thumbnail_url: string | null;
  posted_display: string | null;
  posted_text: string | null;
  duration_text: string | null;
  view_count: number | null;
  view_count_text: string | null;
  estimated_views_display: string | null;
  estimated_views_mid: number | null;
  like_count: number | null;
  like_count_text: string | null;
  comment_count: number | null;
  comment_count_text: string | null;
  share_count: number | null;
  share_count_text: string | null;
  favorite_count: number | null;
  favorite_count_text: string | null;
  engagement_rate: number | null;
  reup_score: number | null;
  reup_score_label: string | null;
  reup_score_level: string | null;
};

export function getReviewCandidateMetadata(candidate: Candidate): ReviewCandidateMetadata {
  const rawCandidate = candidate as unknown as Record<string, unknown>;
  const candidateMetadata = recordValue(candidate.metadata_json) ?? recordValue(rawCandidate.metadata);
  const sourceVideoMetadata = recordValue(candidate.source_video?.metadata_json);
  const sourceMetadata = recordValue(candidate.source_metadata) ?? recordValue(rawCandidate.sourceMetadata) ?? recordValue(candidateMetadata?.source_metadata) ?? recordValue(sourceVideoMetadata?.source_metadata) ?? sourceVideoMetadata ?? {};
  const sourceVideoId = stringValue(sourceMetadata.source_video_external_id, sourceMetadata.aweme_id, candidate.source_video_external_id, candidate.aweme_id, candidate.source_video?.source_video_external_id, candidateMetadata?.source_video_external_id, candidateMetadata?.aweme_id, sourceVideoMetadata?.source_video_external_id, sourceVideoMetadata?.aweme_id);
  const sourceUrl = stringValue(sourceMetadata.source_url, sourceMetadata.video_url, candidate.source_url, candidate.video_url, candidate.source_video?.source_url, candidateMetadata?.source_url, candidateMetadata?.video_url, sourceVideoMetadata?.source_url, sourceVideoMetadata?.video_url);
  const estimatedViewsDisplay = stringValue(sourceMetadata.estimated_views_display, sourceMetadata.estimated_views_text, sourceMetadata.estimated_views, candidate.estimated_views_display, candidateMetadata?.estimated_views_display, candidateMetadata?.estimated_views_text, candidateMetadata?.estimated_views, sourceVideoMetadata?.estimated_views_display, sourceVideoMetadata?.estimated_views_text, sourceVideoMetadata?.estimated_views);
  const estimatedViewsMin = numberValue(sourceMetadata.estimated_views_min, candidate.estimated_views_min, candidateMetadata?.estimated_views_min);
  const estimatedViewsMax = numberValue(sourceMetadata.estimated_views_max, candidate.estimated_views_max, candidateMetadata?.estimated_views_max);
  let estimatedViewsMid = numberValue(sourceMetadata.estimated_views_mid, sourceMetadata.views_mid, candidate.estimated_views_mid, candidateMetadata?.estimated_views_mid, candidate.views_mid, candidateMetadata?.views_mid, sourceVideoMetadata?.views_mid, candidate.view_count, candidateMetadata?.view_count, sourceVideoMetadata?.view_count);
  if (estimatedViewsMid === null && estimatedViewsMin !== null && estimatedViewsMax !== null) {
    estimatedViewsMid = Math.round((estimatedViewsMin + estimatedViewsMax) / 2);
  }
  const likeCount = numberValue(sourceMetadata.like_count, sourceMetadata.likes, candidate.like_count, candidate.likes, candidateMetadata?.like_count, candidateMetadata?.likes, sourceVideoMetadata?.like_count, sourceVideoMetadata?.likes, scoreMetric(candidate, "likes"));
  const commentCount = numberValue(sourceMetadata.comment_count, sourceMetadata.comments, candidate.comment_count, candidate.comments, candidateMetadata?.comment_count, candidateMetadata?.comments, sourceVideoMetadata?.comment_count, sourceVideoMetadata?.comments, scoreMetric(candidate, "comments"));
  const shareCount = numberValue(sourceMetadata.share_count, sourceMetadata.shares, candidate.share_count, candidate.shares, candidateMetadata?.share_count, candidateMetadata?.shares, sourceVideoMetadata?.share_count, sourceVideoMetadata?.shares, scoreMetric(candidate, "shares"));
  const reupScore = numberValue(sourceMetadata.reup_score, candidate.reup_score, candidateMetadata?.reup_score, sourceVideoMetadata?.reup_score);
  const postedChoice = firstStringChoice(
    ["source_metadata.posted_display_exact", sourceMetadata.posted_display_exact],
    ["source_metadata.posted_display", sourceMetadata.posted_display],
    ["candidate.posted_display_exact", candidate.posted_display_exact],
    ["candidate.posted_display", candidate.posted_display],
    ["candidate.postedDisplay", candidate.postedDisplay],
    ["candidate.metadata_json.posted_display_exact", candidateMetadata?.posted_display_exact],
    ["candidate.metadata_json.posted_display", candidateMetadata?.posted_display],
    ["candidate.metadata_json.postedDisplay", candidateMetadata?.postedDisplay],
    ["source_metadata.posted_text_raw", sourceMetadata.posted_text_raw],
    ["candidate.posted_text_raw", candidate.posted_text_raw],
    ["candidate.metadata_json.posted_text_raw", candidateMetadata?.posted_text_raw],
    ["source_metadata.posted", sourceMetadata.posted],
    ["source_metadata.posted_text", sourceMetadata.posted_text],
    ["candidate.posted", candidate.posted],
    ["candidate.posted_text", candidate.posted_text],
    ["candidate.metadata_json.posted", candidateMetadata?.posted],
    ["candidate.metadata_json.posted_text", candidateMetadata?.posted_text],
    ["candidate.posted_at", candidate.posted_at],
    ["source_video.posted_at", candidate.source_video?.posted_at]
  );
  const durationTextChoice = firstStringChoice(
    ["source_metadata.duration_text", sourceMetadata.duration_text],
    ["candidate.duration_text", candidate.duration_text],
    ["candidate.durationText", candidate.durationText],
    ["candidate.metadata_json.duration_text", candidateMetadata?.duration_text],
    ["source_metadata.duration", sourceMetadata.duration],
    ["candidate.duration", candidate.duration],
    ["candidate.metadata_json.duration", candidateMetadata?.duration]
  );
  const durationSecondsChoice = firstNumberChoice(
    ["source_metadata.duration_seconds", sourceMetadata.duration_seconds],
    ["candidate.duration_seconds", candidate.duration_seconds],
    ["candidate.durationSeconds", candidate.durationSeconds],
    ["candidate.metadata_json.duration_seconds", candidateMetadata?.duration_seconds],
    ["source_video.duration_seconds", candidate.source_video?.duration_seconds]
  );
  const durationText = durationTextChoice.value ?? formatDurationSeconds(durationSecondsChoice.value);
  const durationSource = durationTextChoice.source ?? (durationText ? durationSecondsChoice.source ?? "missing" : "missing");
  let engagementRate = numberValue(sourceMetadata.engagement_rate, candidate.engagement_rate, candidateMetadata?.engagement_rate);
  if (engagementRate === null && estimatedViewsMid !== null && estimatedViewsMid > 0) {
    const totalEngagement = (likeCount ?? 0) + (commentCount ?? 0) + (shareCount ?? 0);
    if (totalEngagement > 0) engagementRate = totalEngagement / estimatedViewsMid;
  }
  const metadata = {
    captureItemId: stringValue(sourceMetadata.capture_item_id, candidate.capture_item_id, candidateMetadata?.capture_item_id),
    captureSessionId: stringValue(sourceMetadata.capture_session_id, candidate.capture_session_id, candidateMetadata?.capture_session_id),
    source: stringValue(sourceMetadata.source, candidate.source, candidateMetadata?.source),
    sourceModule: stringValue(sourceMetadata.source_module, candidate.source_module, candidateMetadata?.source_module),
    awemeId: stringValue(sourceMetadata.aweme_id, candidate.aweme_id, sourceVideoId, candidateMetadata?.aweme_id),
    sourceVideoExternalId: sourceVideoId,
    sourceUrl,
    videoUrl: stringValue(sourceMetadata.video_url, candidate.video_url, sourceUrl, candidateMetadata?.video_url),
    profileUrl: stringValue(sourceMetadata.profile_url, candidate.profile_url, candidateMetadata?.profile_url),
    profileName: stringValue(sourceMetadata.profile_name, candidate.profile_name, candidateMetadata?.profile_name),
    caption: stringValue(sourceMetadata.caption, candidate.caption, candidate.source_video?.caption, candidateMetadata?.caption),
    title: stringValue(sourceMetadata.title, candidate.title, candidateMetadata?.title),
    description: stringValue(sourceMetadata.description, candidate.description, candidateMetadata?.description),
    thumbnailUrl: stringValue(sourceMetadata.thumbnail_url, sourceMetadata.thumbnail, candidate.thumbnail_url, candidate.thumbnail, candidateMetadata?.thumbnail_url, candidateMetadata?.thumbnail),
    postedDisplay: postedChoice.value,
    postedSource: postedChoice.source ?? "missing",
    postedText: stringValue(sourceMetadata.posted_text, candidate.posted_text, candidateMetadata?.posted_text),
    postedTextRaw: stringValue(sourceMetadata.posted_text_raw, candidate.posted_text_raw, candidateMetadata?.posted_text_raw),
    durationSeconds: durationSecondsChoice.value,
    durationText,
    durationSource,
    viewCount: numberValue(sourceMetadata.view_count, candidate.view_count, candidateMetadata?.view_count),
    viewCountText: stringValue(sourceMetadata.view_count_text, candidate.view_count_text, candidateMetadata?.view_count_text),
    estimatedViewsDisplay,
    estimatedViewsMin,
    estimatedViewsMax,
    estimatedViewsMid,
    likeCount,
    likeCountText: stringValue(sourceMetadata.like_count_text, candidate.like_count_text, candidateMetadata?.like_count_text),
    commentCount,
    commentCountText: stringValue(sourceMetadata.comment_count_text, candidate.comment_count_text, candidateMetadata?.comment_count_text),
    shareCount,
    shareCountText: stringValue(sourceMetadata.share_count_text, candidate.share_count_text, candidateMetadata?.share_count_text),
    favoriteCount: numberValue(sourceMetadata.favorite_count, candidate.favorite_count, candidateMetadata?.favorite_count),
    favoriteCountText: stringValue(sourceMetadata.favorite_count_text, candidate.favorite_count_text, candidateMetadata?.favorite_count_text),
    engagementRate,
    reupScore,
    reupScoreLabel: stringValue(sourceMetadata.reup_score_label, candidate.reup_score_label, candidateMetadata?.reup_score_label),
    reupScoreLevel: stringValue(sourceMetadata.reup_score_level, candidate.reup_score_level, candidateMetadata?.reup_score_level),
    missingMetadataFields: stringArrayValue(sourceMetadata.missing_metadata_fields, candidate.missing_metadata_fields, candidateMetadata?.missing_metadata_fields)
  };
  return {
    ...metadata,
    capture_item_id: metadata.captureItemId,
    capture_session_id: metadata.captureSessionId,
    source_video_external_id: metadata.sourceVideoExternalId,
    source_url: metadata.sourceUrl,
    thumbnail_url: metadata.thumbnailUrl,
    posted_display: metadata.postedDisplay,
    posted_text: metadata.postedText,
    duration_text: metadata.durationText,
    view_count: metadata.viewCount,
    view_count_text: metadata.viewCountText,
    estimated_views_display: metadata.estimatedViewsDisplay,
    estimated_views_mid: metadata.estimatedViewsMid,
    like_count: metadata.likeCount,
    like_count_text: metadata.likeCountText,
    comment_count: metadata.commentCount,
    comment_count_text: metadata.commentCountText,
    share_count: metadata.shareCount,
    share_count_text: metadata.shareCountText,
    favorite_count: metadata.favoriteCount,
    favorite_count_text: metadata.favoriteCountText,
    engagement_rate: metadata.engagementRate,
    reup_score: metadata.reupScore,
    reup_score_label: metadata.reupScoreLabel,
    reup_score_level: metadata.reupScoreLevel
  };
}

export function reviewCandidateViewsForSort(candidate: Candidate): number {
  const metadata = getReviewCandidateMetadata(candidate);
  return metadata.estimatedViewsMid ?? metadata.viewCount ?? -1;
}

export function reviewCandidateDisplayScore(candidate: Candidate): number | null {
  return getOperatorTileScoreBadge(buildCapturedItemFromReviewCandidate(candidate)).score;
}

export function formatReviewPostedLabel(metadata: ReviewCandidateMetadata): string {
  const value = metadata.postedDisplay;
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value)) {
    const date = new Date(value);
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
    }
  }
  return value;
}

export function formatReviewEstimatedViews(metadata: ReviewCandidateMetadata): string {
  if (metadata.estimatedViewsDisplay) return metadata.estimatedViewsDisplay;
  if (metadata.estimatedViewsMin != null && metadata.estimatedViewsMax != null) {
    return `${formatReviewNumber(metadata.estimatedViewsMin)}-${formatReviewNumber(metadata.estimatedViewsMax)}`;
  }
  if (metadata.estimatedViewsMid != null) {
    return formatReviewNumber(metadata.estimatedViewsMid);
  }
  if (metadata.likeCount != null && metadata.likeCount > 0) {
    const low = Math.round(metadata.likeCount * 20);
    const high = Math.round(metadata.likeCount * 100);
    return `${formatReviewNumber(low)}-${formatReviewNumber(high)}`;
  }
  return "—";
}

function formatReviewNumber(value: number): string {
  return new Intl.NumberFormat("en", { notation: value >= 10000 ? "compact" : "standard", maximumFractionDigits: value >= 10000 ? 1 : 0 }).format(value);
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function firstStringChoice(...values: Array<[string, unknown]>): { value: string | null; source: string | null } {
  for (const [source, value] of values) {
    if (typeof value === "string" && value.trim()) return { value, source };
  }
  return { value: null, source: null };
}

function firstNumberChoice(...values: Array<[string, unknown]>): { value: number | null; source: string | null } {
  for (const [source, value] of values) {
    if (typeof value === "number" && Number.isFinite(value)) return { value, source };
  }
  return { value: null, source: null };
}

function formatDurationSeconds(value: number | null): string | null {
  if (value == null) return null;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function stringValue(...values: unknown[]): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function numberValue(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function stringArrayValue(...values: unknown[]): string[] | null {
  for (const value of values) {
    if (Array.isArray(value)) return value.filter((item): item is string => typeof item === "string");
  }
  return null;
}

function scoreMetric(candidate: Candidate, key: "likes" | "comments" | "shares"): number | null {
  const value = candidate.score_breakdown_json?.engagement_quality?.raw_input?.[key];
  return typeof value === "number" && Number.isFinite(value) && value !== 0 ? value : null;
}
