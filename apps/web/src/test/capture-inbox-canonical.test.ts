import assert from "node:assert/strict";

import {
  resolveCommentCount,
  resolveDuration,
  resolveEstimatedViews,
  resolveKnownViewCountValue,
  resolveLikeCount,
  resolveMediaAssetStatus,
  resolvePosted,
  resolveSourceLinkStatus,
  resolvePreviewStatus,
  resolveThumbnailDisplayUrl,
  resolveThumbnailUrl,
  resolveViewCount
} from "../lib/captureInboxCanonical";
import type { CapturedItem } from "../types/capture-inbox";

const baseItem: CapturedItem = {
  id: "item-1",
  workspace_id: "workspace-1",
  capture_session_id: "session-1",
  source_platform: "douyin",
  status: "RAW",
  raw_item_index: 0,
  source_profile_external_id: "MS4wLjABAAAAprofile",
  profile_url: "https://www.douyin.com/user/MS4wLjABAAAAprofile",
  source_video_external_id: "7420000000000000000",
  aweme_id: "7420000000000000000",
  source_url: "https://www.douyin.com/video/7420000000000000000",
  share_url: "https://v.douyin.com/example/",
  title: "Visible profile-grid card",
  caption: "Visible profile-grid card",
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
  poster_aspect_ratio: null,
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
  metadata_status: "pending_hydration",
  time_status: "pending",
  performance_status: "pending",
  processing_fit_status: "pending",
  metadata_missing_reason: "Metadata hydration has not been attempted.",
  time_missing_reason: "Metadata hydration has not been attempted.",
  performance_missing_reason: "Metadata hydration has not been attempted.",
  processing_fit_missing_reason: "Metadata hydration has not been attempted.",
  metadata_source_summary: "No metadata source evidence captured.",
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

const visibleProfileGridItem: CapturedItem = {
  ...baseItem,
  thumbnail_url: "https://p3-pc.douyinpic.com/img/aweme-cover-visible-profile-grid.jpeg?from=327834062",
  duration_seconds: 42,
  duration_text: "00:42",
  posted_at: "2026-04-27T10:30:00.000Z",
  posted_text: "27/04/2026",
  posted_text_raw: "1 day ago",
  posted_display: "27/04/2026",
  view_count: 123456,
  view_count_text: "12.3万观看",
  like_count: 7890,
  like_count_text: "7890赞",
  comment_count: 321,
  comment_count_text: "321评论",
  preview_status: "ready",
  source_link_status: "captured",
  media_asset_status: "not_generated",
  media_status: "source_link_captured",
  raw_payload_json: {
    thumbnail_url: "https://p9-sign.douyinpic.com/img/raw-fallback.jpeg",
    statistics: {
      play_count: 1,
      digg_count: 2
    }
  }
};

assert.equal(
  resolveThumbnailUrl(visibleProfileGridItem),
  "https://p3-pc.douyinpic.com/img/aweme-cover-visible-profile-grid.jpeg?from=327834062",
  "Canonical thumbnail_url must render before raw fallback aliases for real visible profile-grid captures"
);

const douyinProxyItem: CapturedItem = {
  ...baseItem,
  id: "item-proxy-1",
  thumbnail_url: "https://p3-sign.douyinpic.com/obj/cover~noop.jpeg?from=327834062"
};

assert.equal(
  resolveThumbnailDisplayUrl(douyinProxyItem),
  "/api/capture-inbox/items/item-proxy-1/thumbnail",
  "Douyin CDN thumbnails must route through the API proxy so the browser can load them"
);

assert.equal(
  resolveThumbnailDisplayUrl({
    ...baseItem,
    thumbnail_url: "https://cdn.example.com/preview/thumb.jpg"
  }),
  "https://cdn.example.com/preview/thumb.jpg",
  "Non-Douyin thumbnails should keep the direct URL"
);
assert.equal(resolveDuration(visibleProfileGridItem), "00:42", "Duration resolver must prefer canonical duration_text when available");
assert.notEqual(resolvePosted(visibleProfileGridItem), "1 day ago", "Posted resolver must format canonical posted_at before posted_text");
assert.equal(
  resolvePosted({ ...visibleProfileGridItem, posted_at: "2026-07-10T19:30:29" }),
  "19:30 10/7/2026",
  "Posted datetime must use HH:mm D/M/YYYY without seconds"
);
assert.equal(resolveViewCount(visibleProfileGridItem), "123,456", "Views resolver must prefer canonical numeric view_count");
assert.equal(resolveLikeCount(visibleProfileGridItem), "7,890", "Likes resolver must prefer canonical numeric like_count");
assert.deepEqual(resolveEstimatedViews(visibleProfileGridItem), {
  estimated_view_count_low: null,
  estimated_view_count_base: null,
  estimated_view_count_high: null,
  estimated_view_source: null
}, "Estimated views must stay empty when real canonical view_count exists");
assert.equal(resolveCommentCount(visibleProfileGridItem), "321", "Comments resolver must prefer canonical numeric comment_count");
assert.equal(resolvePreviewStatus(visibleProfileGridItem), "Ready", "Preview resolver must render ready when canonical thumbnail/preview exists");
assert.equal(resolveSourceLinkStatus(visibleProfileGridItem), "Captured", "Source-link resolver must render captured source links separately from media assets");
assert.equal(resolveMediaAssetStatus(visibleProfileGridItem), "Not generated", "Media-asset resolver must not call source-link-only captures ready media assets");

const textOnlyMetricItem: CapturedItem = {
  ...baseItem,
  view_count_text: "12.3万观看",
  like_count_text: "8千赞",
  comment_count_text: "评论很多"
};

assert.equal(resolveViewCount(textOnlyMetricItem), "12.3万观看", "Views resolver must preserve canonical raw text when numeric count is absent");
assert.equal(resolveLikeCount(textOnlyMetricItem), "8千赞", "Likes resolver must preserve canonical raw text when numeric count is absent");
assert.deepEqual(resolveEstimatedViews(textOnlyMetricItem), {
  estimated_view_count_low: null,
  estimated_view_count_base: null,
  estimated_view_count_high: null,
  estimated_view_source: null
}, "Estimated views must stay empty when like_count is not numeric");
assert.equal(resolveCommentCount(textOnlyMetricItem), "评论很多", "Comments resolver must preserve canonical raw text when numeric count is absent");

const missingAssetsItem: CapturedItem = {
  ...baseItem,
  source_url: null,
  share_url: null,
  preview_status: "missing",
  source_link_status: "missing",
  media_asset_status: "not_generated",
  media_status: "missing"
};

assert.deepEqual(resolveEstimatedViews({ ...missingAssetsItem, like_count: 278 }), {
  estimated_view_count_low: 5560,
  estimated_view_count_base: 9174,
  estimated_view_count_high: 27800,
  estimated_view_source: "like_count_estimation"
}, "Estimated views must derive from like_count only when real views are missing");
assert.equal(resolveThumbnailUrl(missingAssetsItem), null, "Thumbnail resolver must not fake values when no true image exists");
assert.equal(resolveViewCount(missingAssetsItem), "Not captured", "Missing metrics must be Not captured, not generic Pending");
assert.equal(resolvePreviewStatus(missingAssetsItem), "Missing", "Preview resolver must truthfully render canonical missing status");
assert.equal(resolveSourceLinkStatus(missingAssetsItem), "Missing", "Source-link resolver must truthfully render canonical missing status");
assert.equal(resolveMediaAssetStatus(missingAssetsItem), "Not generated", "Media-asset resolver must truthfully render not-generated status when no downstream asset exists");

const pendingPreviewItem: CapturedItem = {
  ...baseItem,
  source_url: null,
  share_url: null,
  preview_status: "pending",
  source_link_status: "missing",
  media_asset_status: "not_generated",
  media_status: "pending"
};

assert.equal(resolvePreviewStatus(pendingPreviewItem), "Pending", "Preview resolver must preserve canonical pending status");
assert.equal(resolveMediaAssetStatus({ ...pendingPreviewItem, media_asset_status: "failed" }), "Failed", "Media-asset resolver must preserve canonical failed status");

const zeroValueItem: CapturedItem = {
  ...baseItem,
  id: "item-zero-values",
  duration_seconds: 0,
  duration_text: null,
  view_count: 0,
  like_count: 0,
  comment_count: 0,
  metadata_json: {
    duration_seconds: 999,
    view_count: 999,
    like_count: 888,
    comment_count: 777
  },
  raw_payload_json: {
    statistics: {
      play_count: 999,
      view_count: 999,
      digg_count: 888,
      like_count: 888,
      comment_count: 777
    }
  }
};

assert.equal(resolveDuration(zeroValueItem), "0:00", "Duration resolver must render canonical zero seconds as a real value");
assert.equal(resolveViewCount(zeroValueItem), "0", "Views resolver must render canonical zero views before fallback aliases");
assert.equal(resolveKnownViewCountValue(zeroValueItem), null, "Zero view_count without trusted provenance must stay unknown for card rendering");
assert.equal(resolveLikeCount(zeroValueItem), "0", "Likes resolver must render canonical zero likes before fallback aliases");
assert.equal(resolveCommentCount(zeroValueItem), "0", "Comments resolver must render canonical zero comments before fallback aliases");
assert.deepEqual(resolveEstimatedViews(zeroValueItem), {
  estimated_view_count_low: null,
  estimated_view_count_base: null,
  estimated_view_count_high: null,
  estimated_view_source: null
}, "Estimated views must not overwrite real canonical view_count values");

assert.deepEqual(resolveEstimatedViews({
  ...zeroValueItem,
  view_count_source: "missing",
  like_count: 269
}), {
  estimated_view_count_low: 5380,
  estimated_view_count_base: 8877,
  estimated_view_count_high: 26900,
  estimated_view_source: "like_count_estimation"
}, "Estimated views must recover when zero view_count is only a missing-source placeholder");
assert.equal(resolveKnownViewCountValue({
  ...zeroValueItem,
  view_count_source: "existing_canonical"
}), 0, "Zero view_count with trusted provenance must remain a real known view count");
assert.equal(resolveKnownViewCountValue({
  ...baseItem,
  view_count: 12345,
  view_count_source: "existing_canonical"
}), 12345, "Non-zero canonical view_count with trusted provenance must remain a real known value for card rendering");
assert.equal(resolveKnownViewCountValue({
  ...baseItem,
  view_count: 12345
}), null, "Non-zero canonical view_count without trusted provenance must not be treated as captured automatically");

const canonicalNestedStatsItem: CapturedItem = {
  ...baseItem,
  id: "item-nested-stats",
  view_count: null,
  like_count: null,
  comment_count: null,
  metadata_json: null,
  raw_payload_json: {
    statistics: {
      play_count: 999,
      view_count: 101,
      digg_count: 888,
      like_count: 202,
      comment_count: 303
    }
  }
};

assert.equal(resolveViewCount(canonicalNestedStatsItem), "101", "Views resolver must prefer canonical nested view_count before play_count alias");
assert.equal(resolveLikeCount(canonicalNestedStatsItem), "202", "Likes resolver must prefer canonical nested like_count before digg_count alias");
assert.equal(resolveCommentCount(canonicalNestedStatsItem), "303", "Comments resolver must resolve item-local nested comment_count");

const firstNetworkItem: CapturedItem = {
  ...baseItem,
  id: "item-network-1",
  source_video_external_id: "7420000000000000101",
  aweme_id: "7420000000000000101",
  thumbnail_url: null,
  duration_text: "00:11",
  posted_text: "09/05/2026",
  posted_text_raw: "1 hour ago",
  posted_display: "09/05/2026",
  view_count: 101,
  like_count: 1101,
  comment_count: 2101,
  preview_status: "ready",
  source_link_status: "captured",
  media_asset_status: "not_generated",
  metadata_json: {
    thumbnail_url: "https://p3.douyinpic.com/img/network-item-1.jpeg",
    thumbnail_source: "network_json"
  },
  raw_payload_json: { thumbnail_url: "https://p3.douyinpic.com/img/raw-item-1.jpeg", network_source: "network_json" }
};
const secondNetworkItem: CapturedItem = {
  ...baseItem,
  id: "item-network-2",
  source_video_external_id: "7420000000000000102",
  aweme_id: "7420000000000000102",
  thumbnail_url: null,
  duration_text: "00:22",
  posted_text: "09/05/2026",
  posted_text_raw: "2 hours ago",
  posted_display: "09/05/2026",
  view_count: 102,
  like_count: 1202,
  comment_count: 2202,
  preview_status: "missing",
  source_link_status: "missing",
  media_asset_status: "failed",
  metadata_json: {
    thumbnail_url: "https://p3.douyinpic.com/img/network-item-2.jpeg",
    thumbnail_source: "network_json"
  },
  raw_payload_json: { thumbnail_url: "https://p3.douyinpic.com/img/raw-item-2.jpeg", network_source: "network_json" }
};

assert.equal(resolveThumbnailUrl(firstNetworkItem), "https://p3.douyinpic.com/img/network-item-1.jpeg", "Resolver must keep first item metadata scoped to its own aweme_id item");
assert.equal(resolveThumbnailUrl(secondNetworkItem), "https://p3.douyinpic.com/img/network-item-2.jpeg", "Resolver must keep second item metadata scoped to its own aweme_id item");
assert.notEqual(resolveThumbnailUrl(firstNetworkItem), resolveThumbnailUrl(secondNetworkItem), "Resolver must not fan out one item's thumbnail across distinct aweme_id items");
assert.equal(resolveDuration(firstNetworkItem), "00:11", "Resolver must keep first item duration scoped to its own item");
assert.equal(resolveDuration(secondNetworkItem), "00:22", "Resolver must keep second item duration scoped to its own item");
assert.notEqual(resolveDuration(firstNetworkItem), resolveDuration(secondNetworkItem), "Resolver must not fan out one item's duration across distinct aweme_id items");
assert.equal(resolvePosted(firstNetworkItem), "09/05/2026", "Resolver must keep first item posted display scoped to its own item");
assert.equal(resolvePosted(secondNetworkItem), "09/05/2026", "Resolver must keep second item posted display scoped to its own item");
assert.notEqual(resolveViewCount(firstNetworkItem), resolveViewCount(secondNetworkItem), "Resolver must not fan out one item's views across distinct aweme_id items");
assert.notEqual(resolveLikeCount(firstNetworkItem), resolveLikeCount(secondNetworkItem), "Resolver must not fan out one item's likes across distinct aweme_id items");
assert.notEqual(resolveCommentCount(firstNetworkItem), resolveCommentCount(secondNetworkItem), "Resolver must not fan out one item's comments across distinct aweme_id items");
assert.equal(resolvePreviewStatus(firstNetworkItem), "Ready", "Resolver must keep first item preview status scoped to its own item");
assert.equal(resolvePreviewStatus(secondNetworkItem), "Missing", "Resolver must keep second item preview status scoped to its own item");
assert.equal(resolveSourceLinkStatus(firstNetworkItem), "Captured", "Resolver must keep first item source-link status scoped to its own item");
assert.equal(resolveSourceLinkStatus(secondNetworkItem), "Captured", "Resolver must fall back to item-local source/share URL evidence when status metadata says missing but links exist");
assert.equal(resolveMediaAssetStatus(firstNetworkItem), "Not generated", "Resolver must keep first item media-asset status scoped to its own item");
assert.equal(resolveMediaAssetStatus(secondNetworkItem), "Failed", "Resolver must keep second item media-asset status scoped to its own item");

const invalidPostedTextItem: CapturedItem = {
  ...baseItem,
  id: "item-invalid-posted-text",
  posted_at: null,
  posted_text: "13.0"
};

assert.equal(resolvePosted(invalidPostedTextItem), "Not captured", "Posted resolver must suppress malformed numeric posted_text noise instead of rendering junk");

console.log("capture inbox canonical resolver behavior tests passed");
