import { calculateDouyinReupScore, type DouyinReupScore } from "./captureInboxReupScore";
import { getReviewCandidateMetadata } from "./reviewCandidateMetadata";
import type { CapturedItem } from "../types/capture-inbox";
import type { Candidate } from "../types/review-board";
import type { ReupQueueItem } from "../types/reup-queue";

type ScoreOptions = {
  now?: Date;
};

function emptyCapturedItem(): CapturedItem {
  return {
    id: "operator-score-fixture",
    workspace_id: "operator-score-fixture",
    capture_session_id: "operator-score-fixture",
    source_platform: "douyin",
    status: "READY",
    raw_item_index: 0,
    source_profile_external_id: null,
    profile_url: null,
    source_video_external_id: null,
    aweme_id: null,
    source_url: null,
    share_url: null,
    caption: null,
    title: null,
    poster_aspect_ratio: null,
    duration_seconds: null,
    duration_text: null,
    posted_at: null,
    posted_text: null,
    posted_text_raw: null,
    posted_display: null,
    thumbnail_url: null,
    view_count: null,
    view_count_text: null,
    like_count: null,
    like_count_text: null,
    comment_count: null,
    comment_count_text: null,
    share_count: null,
    share_count_text: null,
    engagement_rate: null,
    preview_url: null,
    preview_status: null,
    source_link_status: null,
    media_asset_status: null,
    media_status: null,
    preview_ready: false,
    media_ready: false,
    readiness_reasons_json: null,
    dedupe_key: null,
    duplicate_of_item_id: null,
    existing_source_video_id: null,
    promoted_source_video_id: null,
    promoted_video_candidate_id: null,
    promoted_crawl_session_id: null,
    enrichment_json: null,
    metadata_json: null
  };
}

export function buildCapturedItemFromReviewCandidate(candidate: Candidate): CapturedItem {
  const metadata = getReviewCandidateMetadata(candidate);
  const raw = candidate as unknown as Record<string, unknown>;
  const captureStatus = candidate.status === "ARCHIVED" ? "PROMOTED" : "READY";
  return {
    ...emptyCapturedItem(),
    id: metadata.captureItemId ?? candidate.id,
    workspace_id: typeof raw.workspace_id === "string" ? raw.workspace_id : emptyCapturedItem().workspace_id,
    capture_session_id: metadata.captureSessionId ?? emptyCapturedItem().capture_session_id,
    status: captureStatus,
    profile_url: metadata.profileUrl,
    source_video_external_id: metadata.sourceVideoExternalId,
    aweme_id: metadata.awemeId,
    source_url: metadata.sourceUrl,
    caption: metadata.caption,
    title: metadata.title,
    duration_seconds: metadata.durationSeconds,
    duration_text: metadata.durationText,
    posted_at: candidate.source_video?.posted_at ?? null,
    posted_text: metadata.postedText,
    posted_display: metadata.postedDisplay,
    engagement_rate: metadata.engagementRate,
    thumbnail_url: metadata.thumbnailUrl,
    view_count: metadata.viewCount,
    view_count_text: metadata.viewCountText,
    estimated_views_display: metadata.estimatedViewsDisplay,
    estimated_views_min: metadata.estimatedViewsMin,
    estimated_views_max: metadata.estimatedViewsMax,
    estimated_views_mid: metadata.estimatedViewsMid,
    like_count: metadata.likeCount,
    like_count_text: metadata.likeCountText,
    comment_count: metadata.commentCount,
    comment_count_text: metadata.commentCountText,
    share_count: metadata.shareCount,
    share_count_text: metadata.shareCountText,
    favorite_count: metadata.favoriteCount,
    favorite_count_text: metadata.favoriteCountText,
    missing_metadata_fields: metadata.missingMetadataFields ?? [],
    has_all_core_metadata: !(metadata.missingMetadataFields?.length ?? 0)
  };
}

export function getOperatorReupScoreForReviewCandidate(
  candidate: Candidate,
  options: ScoreOptions = {}
): DouyinReupScore {
  return calculateDouyinReupScore(buildCapturedItemFromReviewCandidate(candidate), options);
}

const SNAPSHOT_FIELDS = [
  "aweme_id",
  "source_video_external_id",
  "source_url",
  "caption",
  "thumbnail_url",
  "posted_display",
  "posted_text",
  "duration_text",
  "duration_seconds",
  "like_count",
  "comment_count",
  "share_count",
  "favorite_count",
  "engagement_rate",
  "estimated_views_display",
  "estimated_views_min",
  "estimated_views_max",
  "estimated_views_mid"
] as const;

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

export function buildCandidateFromReupQueueItem(item: ReupQueueItem): Candidate {
  const source = item.source_video;
  const metadata = recordValue(source?.metadata_json);
  const nested = recordValue(metadata?.source_metadata) ?? metadata;
  const candidate: Candidate = {
    id: item.video_candidate_id,
    source_video_id: item.source_video_id,
    status: "APPROVED",
    score: null,
    score_version: null,
    score_label: null,
    score_breakdown_json: null,
    score_reason: null,
    preset_name: null,
    filter_config_json: null,
    inclusion_reasons_json: null,
    exclusion_reasons_json: null,
    warnings_json: null,
    evaluated_at: null,
    priority: item.priority,
    metadata_json: metadata,
    created_at: item.created_at,
    updated_at: item.updated_at,
    source_video: source,
    source_metadata: nested,
    caption: source?.caption ?? null,
    aweme_id: source?.source_video_external_id ?? null,
    source_video_external_id: source?.source_video_external_id ?? null,
    source_url: source?.source_url ?? null,
    duration_seconds: source?.duration_seconds ?? null,
    posted_at: source?.posted_at ?? null
  };
  const raw = candidate as unknown as Record<string, unknown>;
  for (const field of SNAPSHOT_FIELDS) {
    if (raw[field] != null) continue;
    const value = nested?.[field] ?? metadata?.[field];
    if (value !== undefined && value !== null) raw[field] = value;
  }
  return candidate;
}

export function buildCapturedItemFromReupQueueItem(item: ReupQueueItem): CapturedItem {
  return buildCapturedItemFromReviewCandidate(buildCandidateFromReupQueueItem(item));
}

export function getOperatorReupScoreForReupQueueItem(item: ReupQueueItem, options: ScoreOptions = {}): DouyinReupScore {
  return calculateDouyinReupScore(buildCapturedItemFromReupQueueItem(item), options);
}
