import assert from "node:assert/strict";
import { buildCapturedItemFromReupQueueItem, buildCapturedItemFromReviewCandidate, getOperatorReupScoreForReupQueueItem, getOperatorReupScoreForReviewCandidate } from "../lib/operatorReupScore";
import { getReupScoreForCaptureItem, calculateDouyinReupScore } from "../lib/captureInboxReupScore";
import { queueTileScoreBadge } from "../lib/reupQueueStudioState";
import { reviewCandidateDisplayScore } from "../lib/reviewCandidateMetadata";
import type { CapturedItem } from "../types/capture-inbox";
import type { Candidate } from "../types/review-board";
import type { ReupQueueItem } from "../types/reup-queue";
const sharedMetrics = {
  aweme_id: "7658958713592992100",
  source_video_external_id: "7658958713592992100",
  duration_seconds: 42,
  duration_text: "00:42",
  posted_display: "19:30:00 5/7/2026",
  thumbnail_url: "https://p3-pc.douyinpic.com/img/cover.jpeg",
  estimated_views_display: "12.8K-64.1K",
  estimated_views_min: 12_800,
  estimated_views_max: 64_100,
  estimated_views_mid: 38_450,
  like_count: 641,
  comment_count: 32,
  share_count: 80,
  engagement_rate: 0.02
};

const captureItem = {
  id: "capture-1",
  workspace_id: "workspace-1",
  capture_session_id: "session-1",
  source_platform: "douyin",
  status: "PROMOTED",
  raw_item_index: 0,
  source_profile_external_id: null,
  profile_url: null,
  source_url: "https://www.douyin.com/video/7658958713592992100",
  share_url: null,
  caption: "牛肉鸡蛋面",
  title: "牛肉鸡蛋面",
  poster_aspect_ratio: null,
  posted_at: null,
  posted_text: null,
  posted_text_raw: null,
  view_count: null,
  view_count_text: null,
  like_count_text: null,
  comment_count_text: null,
  share_count_text: null,
  engagement_score: null,
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
  metadata_json: null,
  reup_score: 52,
  reup_score_label: "Average",
  reup_score_level: "average",
  ...sharedMetrics
} as CapturedItem;

const reviewCandidate: Candidate = {
  id: "candidate-1",
  source_video_id: "video-1",
  status: "ARCHIVED",
  score: 52,
  score_version: null,
  score_label: "usable",
  score_breakdown_json: null,
  score_reason: null,
  preset_name: null,
  filter_config_json: null,
  inclusion_reasons_json: null,
  exclusion_reasons_json: null,
  warnings_json: null,
  evaluated_at: null,
  priority: 52,
  metadata_json: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  reup_score: 52,
  source_metadata: sharedMetrics,
  ...sharedMetrics,
  source_video: {
    id: "video-1",
    source_profile_id: "profile-1",
    source_video_external_id: sharedMetrics.source_video_external_id,
    source_url: `https://www.douyin.com/video/${sharedMetrics.source_video_external_id}`,
    caption: "Beef egg noodles",
    posted_at: null,
    duration_seconds: sharedMetrics.duration_seconds,
    metadata_json: sharedMetrics
  }
};

const captureScore = getReupScoreForCaptureItem(captureItem).reup_score;
const reviewScore = reviewCandidateDisplayScore(reviewCandidate);
assert.equal(
  reviewScore,
  captureScore,
  "Review Board operator score must match Capture Inbox for the same metadata inputs"
);
assert.notEqual(reviewScore, 52, "Operator score must not use stale persisted reup_score");

const rebuilt = buildCapturedItemFromReviewCandidate(reviewCandidate);
assert.equal(getReupScoreForCaptureItem(rebuilt).reup_score, captureScore);
assert.equal(getOperatorReupScoreForReviewCandidate(reviewCandidate).reup_score, captureScore);

const promotedFixtureMetrics = {
  aweme_id: "7528769486280576282",
  source_video_external_id: "7528769486280576282",
  duration_seconds: 37,
  duration_text: "00:37",
  posted_display: "19:30:47 19/7/2025",
  thumbnail_url: "https://p3-pc.douyinpic.com/img/cover.jpeg",
  estimated_views_display: "32.2K—161.1K",
  estimated_views_min: 32_200,
  estimated_views_max: 161_100,
  like_count: 1611,
  comment_count: 45,
  share_count: 523
};

const promotedCaptureItem = {
  ...captureItem,
  id: "capture-promoted-fixture",
  status: "PROMOTED",
  caption: "包菜肉丝饭",
  reup_score: null,
  reup_score_label: null,
  reup_score_level: null,
  estimated_views_mid: null,
  ...promotedFixtureMetrics,
  engagement_rate: (1611 + 45 + 523) / ((32_200 + 161_100) / 2)
} as CapturedItem;

const promotedReviewCandidate: Candidate = {
  id: "candidate-promoted-fixture",
  source_video_id: "video-promoted-fixture",
  status: "SHORTLISTED",
  score: 53,
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
  priority: 53,
  metadata_json: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
  reup_score: null,
  caption: "包菜肉丝饭",
  ...promotedFixtureMetrics,
  source_video: {
    id: "video-promoted-fixture",
    source_profile_id: "profile-1",
    source_video_external_id: promotedFixtureMetrics.source_video_external_id,
    source_url: "https://www.douyin.com/video/7528769486280576282",
    caption: "包菜肉丝饭",
    posted_at: null,
    duration_seconds: 37,
    metadata_json: promotedFixtureMetrics
  }
};

const promotedCaptureScore = getReupScoreForCaptureItem(promotedCaptureItem).reup_score;
const promotedReviewScore = reviewCandidateDisplayScore(promotedReviewCandidate);
assert.equal(
  promotedReviewScore,
  promotedCaptureScore,
  "Promoted summary candidates must operator-score the same as Capture Inbox without stored engagement_rate"
);
assert.ok(promotedCaptureScore >= 40, "Fixture should score well when metadata is complete under viral-focused formula");

function makeReupQueueItem(metrics: Record<string, unknown>, staleReupScore?: number): ReupQueueItem {
  const metadata = staleReupScore == null ? metrics : { ...metrics, reup_score: staleReupScore };
  return {
    id: "queue-promoted-fixture",
    workspace_id: "workspace-1",
    video_candidate_id: "candidate-promoted-fixture",
    source_video_id: "video-promoted-fixture",
    status: "READY_FOR_PROCESSING",
    bucket: "READY_FOR_PROCESSING",
    next_action: "Start processing",
    priority: 100,
    queued_reason: "review_board_approved",
    operator_note: null,
    last_error_code: null,
    last_error_message: null,
    media_prep_status: "NOT_STARTED",
    media_prep_notes: null,
    media_ready_at: null,
    blocked_reason: null,
    blocked_at: null,
    held_at: null,
    failed_at: null,
    last_action: null,
    last_action_at: null,
    last_action_note: null,
    available_actions: [],
    queued_at: "2026-07-01T00:00:00Z",
    started_at: null,
    completed_at: null,
    cancelled_at: null,
    job_id: null,
    render_output_id: null,
    publish_draft_id: null,
    metadata_json: null,
    source_video: {
      id: "video-promoted-fixture",
      source_profile_id: "profile-1",
      source_video_external_id: String(metrics.source_video_external_id ?? ""),
      source_url: "https://www.douyin.com/video/7528769486280576282",
      caption: "包菜肉丝饭",
      posted_at: null,
      duration_seconds: Number(metrics.duration_seconds ?? 0),
      metadata_json: metadata
    },
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z"
  };
}

const promotedQueueItem = makeReupQueueItem(promotedFixtureMetrics);
const promotedQueueScore = queueTileScoreBadge(promotedQueueItem).score;
assert.equal(
  promotedQueueScore,
  promotedCaptureScore,
  "Reup Queue tile score must match Capture Inbox and Review Board for the same metadata"
);
assert.equal(getOperatorReupScoreForReupQueueItem(promotedQueueItem).reup_score, promotedCaptureScore);

console.log("operator-reup-score-sync tests passed");
