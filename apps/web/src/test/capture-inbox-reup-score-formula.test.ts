import assert from "node:assert/strict";

import { calculateDouyinReupScore, getReupScoreForCaptureItem } from "../lib/captureInboxReupScore";
import type { CapturedItem } from "../types/capture-inbox";

const NOW = new Date("2026-04-28T00:00:00.000Z");

function baseItem(overrides: Partial<CapturedItem> = {}): CapturedItem {
  return {
    id: "item-1",
    workspace_id: "workspace-1",
    capture_session_id: "session-1",
    source_platform: "douyin",
    status: "READY",
    raw_item_index: 0,
    source_profile_external_id: "profile-1",
    profile_url: "https://www.douyin.com/user/profile-1",
    source_video_external_id: "7420000000000000000",
    aweme_id: "7420000000000000000",
    source_url: "https://www.douyin.com/video/7420000000000000000",
    share_url: "https://v.douyin.com/example/",
    caption: "Captured item",
    title: "Captured item",
    poster_aspect_ratio: null,
    duration_seconds: 42,
    duration_text: "00:42",
    posted_at: "2026-04-27T10:30:00.000Z",
    posted_text: "27/04/2026",
    posted_text_raw: "1 day ago",
    posted_display: "27/04/2026",
    thumbnail_url: "https://p3-pc.douyinpic.com/img/cover.jpeg",
    view_count: null,
    view_count_text: null,
    like_count: 120,
    like_count_text: "120",
    comment_count: 12,
    comment_count_text: "12",
    share_count: 6,
    share_count_text: "6",
    favorite_count: 4,
    engagement_rate: 0.05,
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
    metadata_status: "complete",
    time_status: "captured",
    performance_status: "captured",
    processing_fit_status: "captured",
    metadata_missing_reason: null,
    time_missing_reason: null,
    performance_missing_reason: null,
    processing_fit_missing_reason: null,
    metadata_source_summary: "Normalized Douyin metadata captured.",
    last_metadata_hydrated_at: null,
    intake_evaluation_status: "NOT_EVALUATED",
    matches_intake: true,
    intake_failed_rules_json: null,
    has_thumbnail: true,
    has_duration: true,
    has_posted: true,
    has_views: true,
    has_all_core_metadata: true,
    missing_metadata_fields: [],
    ...overrides
  };
}

// Performance sweet spot (100K–3M views)
assert.equal(
  calculateDouyinReupScore(baseItem({ estimated_views_mid: 500_000 }), { now: NOW }).reup_score_components.performance,
  20,
  "100K–3M views must score 20 performance points"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ estimated_views_mid: 99_999 }), { now: NOW }).reup_score_components.performance,
  15,
  "10K–<100K views must score 15 performance points"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ estimated_views_mid: 5_000_000 }), { now: NOW }).reup_score_components.performance,
  10,
  ">3M–10M views must score 10 performance points"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ estimated_views_mid: 15_000_000 }), { now: NOW }).reup_score_components.performance,
  5,
  ">10M views must score 5 performance points (saturation)"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ estimated_views_mid: 5_000 }), { now: NOW }).reup_score_components.performance,
  2,
  "<10K views must score 2 performance points"
);

// Engagement uses (likes + comments) / views; low-view cap at 10
const lowViewHighEngagement = calculateDouyinReupScore(
  baseItem({
    estimated_views_mid: 5_000,
    like_count: 400,
    comment_count: 100,
    share_count: 0,
    favorite_count: 0
  }),
  { now: NOW }
);
assert.equal(lowViewHighEngagement.reup_score_components.engagement, 10, "Views <10K must cap engagement at 10 even with high rate");

const highViewEngagement = calculateDouyinReupScore(
  baseItem({
    estimated_views_mid: 200_000,
    like_count: 16_000,
    comment_count: 4_000,
    share_count: 0,
    favorite_count: 0
  }),
  { now: NOW }
);
assert.equal(highViewEngagement.reup_score_components.engagement, 20, "Views >=10K with >=8% (likes+comments)/views must score 20 engagement");

// Virality & retention: (shares*1.5 + favorites*2) / views
const viralityScore = calculateDouyinReupScore(
  baseItem({
    estimated_views_mid: 100_000,
    share_count: 2_000,
    favorite_count: 500,
    like_count: 1_000,
    comment_count: 100
  }),
  { now: NOW }
);
assert.equal(
  viralityScore.reup_score_components.virality_retention,
  20,
  "Viral rate >=3% must score 20 virality points"
);

// Duration fit
assert.equal(
  calculateDouyinReupScore(baseItem({ duration_seconds: 60 }), { now: NOW }).reup_score_components.duration_fit,
  10,
  "12–75s duration must score 10"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ duration_seconds: 90 }), { now: NOW }).reup_score_components.duration_fit,
  7,
  "6–120s duration must score 7"
);

// Recency
assert.equal(
  calculateDouyinReupScore(baseItem({ posted_at: "2026-04-27T12:00:00.000Z" }), { now: NOW }).reup_score_components.recency,
  20,
  "<=48h recency must score 20"
);
assert.equal(
  calculateDouyinReupScore(baseItem({ posted_at: "2026-04-24T00:00:00.000Z" }), { now: NOW }).reup_score_components.recency,
  15,
  "<=7d recency must score 15"
);

// Outlier bonus when views/followers > 10
const outlier = calculateDouyinReupScore(
  baseItem({
    estimated_views_mid: 500_000,
    follower_count: 10_000,
    like_count: 20_000,
    comment_count: 5_000,
    share_count: 8_000,
    favorite_count: 4_000
  }),
  { now: NOW }
);
assert.equal(outlier.reup_score_components.outlier_bonus, 15, "Views/followers >10 must add 15 outlier bonus");
assert.ok(outlier.reup_score <= 100, "Final score must never exceed 100");

const noFollowers = calculateDouyinReupScore(
  baseItem({ estimated_views_mid: 500_000, follower_count: null }),
  { now: NOW }
);
assert.equal(noFollowers.reup_score_components.outlier_bonus, 0, "Missing follower count must skip outlier bonus");

const staleItem = baseItem({ reup_score: 88, reup_score_label: "Excellent", reup_score_level: "excellent" });
const backendPreferred = getReupScoreForCaptureItem(staleItem, { now: NOW });
assert.notEqual(backendPreferred.reup_score, 88, "Stale persisted reup_score must not override canonical formula");
assert.equal(backendPreferred.reup_score, calculateDouyinReupScore(staleItem, { now: NOW }).reup_score, "Operator score must match live canonical calculation");

console.log("capture-inbox-reup-score-formula tests passed");
