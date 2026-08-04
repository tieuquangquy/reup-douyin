import assert from "node:assert/strict";

import {
  estimatedViewsRangeMatches,
  formatCaptureInboxTileMetadataGap,
  getComparableEstimatedViews,
  getDouyinItemMetadataForFilters,
  getDouyinMetadataCompletenessForItem,
  getEstimatedViewsForItem,
  metadataHealthCounts,
  metadataHealthMatches,
  parseCompactNumberInput,
  parseEstimatedViewsText,
  type MetadataHealthFilter
} from "../lib/captureInboxFilterMetadata";
import { calculateDouyinReupScore, getReupScoreForCaptureItem } from "../lib/captureInboxReupScore";
import { getDouyinReviewPresetCounts, matchesDouyinReviewPreset } from "../lib/captureInboxReviewPresets";
import type { CapturedItem } from "../types/capture-inbox";

const baseItem: CapturedItem = {
  id: "item-1",
  workspace_id: "workspace-1",
  capture_session_id: "session-1",
  source_platform: "douyin",
  status: "RAW",
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
  matches_intake: null,
  intake_failed_rules_json: null,
  intake_missing_requirements_json: null,
  intake_filter_version: null,
  intake_preset_name: null,
  last_intake_evaluated_at: null,
  intake_evaluation_error: null,
  excluded_reason: null,
  error_code: null,
  error_message: null,
  raw_payload_json: {},
  created_at: "2026-04-28T00:00:00.000Z",
  updated_at: "2026-04-28T00:00:00.000Z"
};

const compactNumberCases: Array<[string, number | null, boolean]> = [
  ["", null, true],
  ["10000", 10000, true],
  ["20K", 20000, true],
  ["1.2M", 1200000, true],
  ["3万", 30000, true],
  ["1,000", 1000, true],
  ["abc", null, false],
  ["10KK", null, false],
  ["-1", null, false]
];
for (const [input, expectedValue, expectedValid] of compactNumberCases) {
  const parsed = parseCompactNumberInput(input);
  assert.equal(parsed.valid, expectedValid, `${input} validity must match`);
  assert.equal(parsed.value, expectedValue, `${input} value must match`);
}

const rangeCases: Array<[string, number, number, number]> = [
  ["9K–43K", 26000, 9000, 43000],
  ["9K-43K", 26000, 9000, 43000],
  ["9K — 43K", 26000, 9000, 43000],
  ["9K to 43K", 26000, 9000, 43000],
  ["9K 至 43K", 26000, 9000, 43000],
  ["24K–118K", 71000, 24000, 118000],
  ["432K", 432000, 432000, 432000],
  ["1.2M", 1200000, 1200000, 1200000],
  ["3万", 30000, 30000, 30000],
  ["10万-20万", 150000, 100000, 200000],
  ["86K–432K", 259000, 86000, 432000],
  ["1K", 1000, 1000, 1000],
  ["999", 999, 999, 999],
  ["1,200", 1200, 1200, 1200]
];
for (const [input, expectedMid, expectedMin, expectedMax] of rangeCases) {
  const parsed = parseEstimatedViewsText(input);
  assert.equal(parsed.value, expectedMid, `${input} must parse to a comparable midpoint/value`);
  assert.equal(parsed.min, expectedMin);
  assert.equal(parsed.max, expectedMax);
}

const normalizedItem: CapturedItem = { ...baseItem, estimated_views_mid: 12000, estimated_views_min: 9000, estimated_views_max: 43000, estimated_views_display: null, estimated_views_text_raw: null, like_count: 999 };
assert.deepEqual(
  (({ min, max, mid, source, confidence }) => ({ min, max, mid, source, confidence }))(getEstimatedViewsForItem(normalizedItem)),
  { min: 12000, max: 12000, mid: 12000, source: "normalized", confidence: "high" },
  "Normalized midpoint has highest priority"
);

const displayOnlyItem: CapturedItem = {
  ...baseItem,
  estimated_views_mid: null,
  estimated_views_min: null,
  estimated_views_max: null,
  estimated_views_display: "9K–43K",
  estimated_views_text_raw: "9K–43K",
  view_count: null
};
const displayEstimate = getEstimatedViewsForItem(displayOnlyItem);
assert.equal(displayEstimate.source, "backend_display");
assert.equal(displayEstimate.mid, 26000);
assert.equal(displayEstimate.min, 9000);
assert.equal(displayEstimate.max, 43000);

const legacyDisplayItem: CapturedItem = { ...baseItem, estimated_views_mid: null, estimated_views_display: null, estimated_views_text_raw: "24K–118K", view_count: null };
assert.equal(getEstimatedViewsForItem(legacyDisplayItem).source, "legacy_display");

const viewCountItem: CapturedItem = { ...baseItem, estimated_views_display: null, estimated_views_text_raw: null, like_count: 500, view_count: 18000, view_count_source: "network_json" };
assert.equal(getEstimatedViewsForItem(viewCountItem).source, "view_count");
assert.equal(getEstimatedViewsForItem(viewCountItem).mid, 18000);

const likesDerivedItem: CapturedItem = { ...baseItem, estimated_views_mid: null, estimated_views_min: null, estimated_views_max: null, estimated_views_display: null, estimated_views_text_raw: null, view_count: null, like_count: 432 };
const likesDerivedEstimate = getEstimatedViewsForItem(likesDerivedItem);
assert.equal(likesDerivedEstimate.source, "derived_from_likes", "Tile Gallery like-derived estimate must be in the shared helper");
assert.equal(likesDerivedEstimate.min, 8640);
assert.equal(likesDerivedEstimate.mid, 14256);
assert.equal(likesDerivedEstimate.max, 43200);

const missingViewsItem: CapturedItem = { ...baseItem, estimated_views_mid: null, estimated_views_min: null, estimated_views_max: null, estimated_views_display: null, estimated_views_text_raw: null, view_count: null, like_count: null };
assert.equal(getEstimatedViewsForItem(missingViewsItem).source, "missing");
assert.equal(getEstimatedViewsForItem(missingViewsItem).mid, null);

const comparable = getComparableEstimatedViews(displayOnlyItem);
assert.equal(comparable.value, 26000, "Display ranges must produce midpoint comparable views");
assert.equal(comparable.source, "estimated_views_display", "Display fallback must expose its source field");
assert.equal(comparable.min, 9000);
assert.equal(comparable.max, 43000);

assert.equal(estimatedViewsRangeMatches(displayEstimate, 10000, 20000), true, "9K-43K must overlap 10K-20K");
assert.equal(estimatedViewsRangeMatches(displayEstimate, 44000, null), false, "Min-only filters compare against item max");
assert.equal(estimatedViewsRangeMatches(displayEstimate, null, 8000), false, "Max-only filters compare against item min");
assert.equal(estimatedViewsRangeMatches(missingViewsItem ? getEstimatedViewsForItem(missingViewsItem) : displayEstimate, 1, null), false, "Missing estimated views are hidden when estimated-view filter is active");

const metadata = getDouyinItemMetadataForFilters(displayOnlyItem);
assert.equal(metadata.sourceDiagnostics.filter_adapter_used, true);
assert.equal(metadata.sourceDiagnostics.views_source_field, "estimated_views_display");
assert.equal(metadata.sourceDiagnostics.views_comparable_value, 26000);
assert.equal(metadata.hasEstimatedViews, true);
assert.equal(metadataHealthMatches(metadata, ["complete"]), true, "Complete health should use adapter-derived views");
assert.equal(getDouyinItemMetadataForFilters(likesDerivedItem).hasEstimatedViews, true, "Metadata health must count Tile Gallery Est. Views as present");

const completeButStaleBackendItem: CapturedItem = {
  ...displayOnlyItem,
  has_all_core_metadata: false,
  missing_metadata_fields: ["thumbnail", "posted", "duration", "views", "likes", "comments", "shares"]
};
const computedCompleteness = getDouyinMetadataCompletenessForItem(completeButStaleBackendItem);
assert.equal(computedCompleteness.hasAllCoreMetadata, true, "Visible card fields must override stale backend missing flags");
assert.deepEqual(computedCompleteness.missingFields, [], "Complete computed metadata must clear stale missing fields");
assert.equal(computedCompleteness.sourceDiagnostics.needs_metadata_stale_backend_flag_ignored, "true");
assert.equal(getDouyinItemMetadataForFilters(completeButStaleBackendItem).hasAllCoreMetadata, true, "Filter adapter must use computed completeness");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, posted_at: null, posted_display: null, posted_text: null }).missingFields.includes("posted"), true, "Missing posted must be detected");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, thumbnail_url: null }).missingFields.includes("thumbnail"), true, "Missing thumbnail must be detected");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, duration_seconds: null, duration_text: null }).missingFields.includes("duration"), true, "Missing duration must be detected");
assert.equal(getDouyinMetadataCompletenessForItem(missingViewsItem).missingFields.includes("views"), true, "Missing estimated views must be detected");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, like_count: 0, comment_count: 0, share_count: 0 }).hasCoreMetrics, true, "Zero metrics are present metrics");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, posted_at: null, posted_display: null, posted_text: "1 day ago" }).sourceDiagnostics.posted, "posted_text", "Posted text must count as posted metadata");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, posted_at: null, posted_display: "27/04/2026", posted_text: null }).sourceDiagnostics.posted, "posted_display", "Posted display must count as posted metadata");
assert.equal(getDouyinMetadataCompletenessForItem({ ...displayOnlyItem, duration_seconds: null, duration_text: "00:42" }).sourceDiagnostics.duration, "duration_text", "Duration text must count as duration metadata");

const fixture59 = Array.from({ length: 59 }, (_, index): CapturedItem => ({
  ...baseItem,
  id: `fixture-${index + 1}`,
  aweme_id: `fixture-aweme-${index + 1}`,
  source_video_external_id: `fixture-aweme-${index + 1}`,
  estimated_views_mid: null,
  estimated_views_min: null,
  estimated_views_max: null,
  estimated_views_display: null,
  estimated_views_text_raw: null,
  view_count: null,
  like_count: index + 1
}));
assert.equal(metadataHealthCounts(fixture59).missing_views, 0, "59 like-derived Est. Views cards must not be counted as missing views");
const minOneThousandMatches = fixture59.filter((item) => estimatedViewsRangeMatches(getEstimatedViewsForItem(item), 1000, null));
assert.ok(minOneThousandMatches.length > 0, "Min estimated views 1000 must show like-derived items");
assert.ok(minOneThousandMatches.length < 59, "Min estimated views 1000 must not hide-or-show all fixture items blindly");

const healthCounts = metadataHealthCounts([
  displayOnlyItem,
  missingViewsItem,
  { ...displayOnlyItem, id: "missing-posted", posted_at: null, posted_text: null, posted_display: null, has_posted: false }
]);
assert.equal(healthCounts.missing_views, 1);
assert.equal(healthCounts.missing_posted, 1);
assert.equal(healthCounts.actionable, 2);

const selected: MetadataHealthFilter[] = ["missing_views", "missing_posted"];
assert.equal(metadataHealthMatches(getDouyinItemMetadataForFilters(displayOnlyItem), selected), false, "Metadata health selections use OR semantics and exclude non-matching complete items");

const strongScore = calculateDouyinReupScore(
  { ...baseItem, estimated_views_mid: 120000, like_count: 5000, comment_count: 600, share_count: 400, favorite_count: 300, engagement_rate: 0.052, metadata_status: "complete", status: "READY", has_all_core_metadata: true, missing_metadata_fields: [] },
  { now: new Date("2026-04-28T00:00:00.000Z") }
);
assert.equal(strongScore.reup_score_components.performance, 20, "Performance component must use the 0-20 sweet-spot weight");
assert.equal(strongScore.reup_score_components.engagement, 10, "Engagement component must use likes+comments rate with 0-20 weight");
assert.equal(strongScore.reup_score_components.virality_retention, 10, "Virality component must use shares+favorites rate with 0-20 weight");
assert.equal(strongScore.reup_score_components.duration_fit, 10, "Duration-fit component must use the 0-10 weight");
assert.equal(strongScore.reup_score_components.recency, 20, "Recency component must use the 0-20 weight");
assert.equal(strongScore.reup_score_components.metadata_quality, 10, "Metadata-quality component must use the 0-10 weight");
assert.equal(strongScore.reup_score_components.penalty, 0, "Complete ready items should avoid metadata penalties");
assert.equal(strongScore.reup_score_label, "Excellent");
assert.ok(strongScore.reup_score_reasons.includes("Sweet-spot view range"));
assert.ok(strongScore.reup_score_reasons.length <= 4, "Score reasons must stay compact");

const missingMetadataScore = calculateDouyinReupScore({ ...missingViewsItem, thumbnail_url: null, duration_seconds: null, duration_text: null, posted_at: null, posted_text: null, posted_display: null, like_count: null, comment_count: null, share_count: null, favorite_count: null, metadata_status: "missing", has_thumbnail: false, has_duration: false, has_posted: false, has_views: false, missing_metadata_fields: ["thumbnail", "duration", "posted", "views", "likes", "comments", "shares"] });
assert.equal(missingMetadataScore.reup_score, 0, "Almost-empty metadata should score zero rather than null");
assert.equal(missingMetadataScore.reup_score_label, "Needs metadata");
assert.equal(missingMetadataScore.reup_score_level, "needs_metadata");
assert.equal(missingMetadataScore.reup_score_components.penalty, -30, "Penalty must clamp at -30");

const staleItem = {
  ...baseItem,
  estimated_views_mid: 120_000,
  like_count: 5000,
  comment_count: 600,
  share_count: 400,
  favorite_count: 300,
  engagement_rate: 0.052,
  metadata_status: "complete",
  status: "READY",
  has_all_core_metadata: true,
  missing_metadata_fields: [],
  reup_score: 88,
  reup_score_label: "Excellent",
  reup_score_level: "excellent",
  reup_score_components: strongScore.reup_score_components,
  reup_score_reasons: ["Backend score"]
};
const backendScore = getReupScoreForCaptureItem(staleItem, { now: new Date("2026-04-28T00:00:00.000Z") });
assert.equal(backendScore.reup_score, strongScore.reup_score, "Stale persisted reup_score must be ignored; operator score always recomputes");
assert.notEqual(backendScore.reup_score, 88, "Persisted legacy score must not override canonical formula");

const derivedEngagementMetadata = getDouyinItemMetadataForFilters({
  ...baseItem,
  engagement_rate: null,
  estimated_views_min: 32_200,
  estimated_views_max: 161_100,
  like_count: 1611,
  comment_count: 45,
  share_count: 523
});
assert.ok(
  derivedEngagementMetadata.engagementRate !== null && derivedEngagementMetadata.engagementRate > 0,
  "Filter metadata must derive engagement_rate from metrics when backend omits it"
);

const completeReadyItem: CapturedItem = { ...displayOnlyItem, status: "READY", matches_intake: true, reup_score: 76, reup_score_label: "Good", reup_score_level: "good", reup_score_components: strongScore.reup_score_components, reup_score_reasons: ["Strong score"], has_all_core_metadata: true, missing_metadata_fields: [], like_count: 1500, comment_count: 80, share_count: 55, engagement_rate: 4, engagement_score: 1200, duration_seconds: 60 };
const failedHighScoreItem: CapturedItem = { ...completeReadyItem, id: "failed-high", status: "FAILED" };
const promotedReadyItem: CapturedItem = { ...completeReadyItem, id: "promoted-ready", status: "PROMOTED" };
const shortStrongItem: CapturedItem = { ...completeReadyItem, id: "short-strong", duration_seconds: 600, reup_score: 58, share_count: 21, like_count: 600 };
const missingDurationItem: CapturedItem = { ...completeReadyItem, id: "missing-duration", duration_seconds: null, duration_text: null, has_duration: false };
const needsActionItem: CapturedItem = { ...completeReadyItem, id: "needs-action", status: "NEEDS_ENRICHMENT", intake_evaluation_status: "MISSING_REQUIREMENTS" };
const lowPriorityItem: CapturedItem = {
  ...completeReadyItem,
  id: "low-priority",
  reup_score: null,
  reup_score_label: null,
  reup_score_level: null,
  estimated_views_mid: 1200,
  estimated_views_min: 900,
  estimated_views_max: 1500,
  engagement_score: 40,
  engagement_rate: 0.004,
  like_count: 12,
  comment_count: 1,
  share_count: 0,
  duration_seconds: 240
};
assert.ok(getReupScoreForCaptureItem(lowPriorityItem).reup_score < 40, "Low priority fixture must calculate below 40");

assert.equal(matchesDouyinReviewPreset(completeReadyItem, "high_potential"), true, "High potential matches reup_score >= 70");
assert.equal(matchesDouyinReviewPreset(failedHighScoreItem, "high_potential"), false, "High potential excludes failed items");
assert.equal(matchesDouyinReviewPreset(completeReadyItem, "ready_to_promote"), true, "Ready to promote matches ready complete items with score >= 50");
assert.equal(matchesDouyinReviewPreset(promotedReadyItem, "ready_to_promote"), false, "Ready to promote excludes already promoted items");
assert.equal(matchesDouyinReviewPreset(completeReadyItem, "high_engagement"), true, "High engagement matches engagement_rate >= 3 and engagement_score >= 1000");
assert.equal(matchesDouyinReviewPreset({ ...completeReadyItem, engagement_rate: 1, engagement_score: 1200 }, "high_engagement"), true, "High engagement matches engagement_score >= 1000");
assert.equal(matchesDouyinReviewPreset(completeReadyItem, "high_share"), true, "High share matches share_count >= 50");
assert.equal(matchesDouyinReviewPreset(shortStrongItem, "short_strong"), true, "Short & strong matches duration 30-900s and score >= 55");
assert.equal(matchesDouyinReviewPreset(missingDurationItem, "short_strong"), false, "Short & strong excludes missing duration");
assert.equal(matchesDouyinReviewPreset({ ...completeReadyItem, posted_at: null, posted_display: null, posted_text: null, has_posted: false }, "needs_cleanup"), true, "Needs cleanup matches missing posted");
assert.equal(matchesDouyinReviewPreset({ ...completeReadyItem, thumbnail_url: null, has_thumbnail: false }, "needs_cleanup"), true, "Needs cleanup matches missing thumbnail");
assert.equal(matchesDouyinReviewPreset(missingDurationItem, "needs_cleanup"), true, "Needs cleanup matches missing duration");
assert.equal(matchesDouyinReviewPreset(needsActionItem, "needs_cleanup"), true, "Needs cleanup matches needs_action items");
assert.equal(matchesDouyinReviewPreset(lowPriorityItem, "low_priority"), true, "Low priority matches score < 40");
assert.equal(lowPriorityItem.status, "READY", "Low priority preset must not mutate or delete items");
const presetCounts = getDouyinReviewPresetCounts([completeReadyItem, failedHighScoreItem, promotedReadyItem, missingDurationItem, lowPriorityItem]);
assert.equal(presetCounts.high_potential, 2, "Preset counts are based on matching loaded fixture items");
assert.equal(presetCounts.ready_to_promote, 1, "Preset counts exclude promoted, failed, incomplete, and low-score ready items");
assert.doesNotThrow(() => getDouyinReviewPresetCounts([{ ...baseItem, like_count: null, comment_count: null, share_count: null, estimated_views_mid: null }]), "Preset counts do not crash with missing fields");

const staleBackendStatusItem: CapturedItem = {
  ...baseItem,
  time_status: "pending",
  performance_status: "pending",
  processing_fit_status: "pending",
  metadata_status: "pending_hydration"
};
assert.equal(formatCaptureInboxTileMetadataGap(staleBackendStatusItem), null, "Tile gap must use canonical completeness, not stale backend group status");

const missingThumbnailItem: CapturedItem = {
  ...baseItem,
  thumbnail_url: null,
  preview_url: null,
  metadata_json: null,
  time_status: "missing",
  performance_status: "missing",
  processing_fit_status: "missing"
};
assert.equal(
  formatCaptureInboxTileMetadataGap(missingThumbnailItem),
  null,
  "Tile gap must not repeat Missing thumbnail — media placeholder already owns that signal"
);
assert.equal(
  getDouyinMetadataCompletenessForItem(missingThumbnailItem).missingFields.includes("thumbnail"),
  true,
  "Canonical completeness must still detect missing thumbnail for filters/score"
);

const missingPostedOnlyItem: CapturedItem = {
  ...baseItem,
  posted_at: null,
  posted_display: null,
  posted_text: null,
  posted_text_raw: null
};
assert.equal(
  formatCaptureInboxTileMetadataGap(missingPostedOnlyItem),
  "posted",
  "Tile gap must still list non-visual missing fields such as posted"
);
assert.doesNotMatch(
  formatCaptureInboxTileMetadataGap({ ...missingPostedOnlyItem, thumbnail_url: null, preview_url: null, has_thumbnail: false }) ?? "",
  /\bthumbnail\b/,
  "Tile gap must omit thumbnail even when other gaps remain"
);

console.log("capture-inbox-filter-metadata tests passed");
