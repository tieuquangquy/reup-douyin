import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  buildReupScoreBreakdownBars,
  shouldShowCaptureInboxTileMetrics
} from "../lib/captureInboxPresentation";
import { getReupScoreForCaptureItem } from "../lib/captureInboxReupScore";
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
  caption: "Captured item",
  title: "Captured item",
  duration_seconds: 42,
  duration_text: "00:42",
  posted_at: "2026-04-27T10:30:00.000Z",
  posted_display: "27/04/2026",
  thumbnail_url: "https://p3-pc.douyinpic.com/img/cover.jpeg",
  like_count: 1500,
  comment_count: 80,
  share_count: 55,
  estimated_views_display: "9K–43K",
  estimated_views_text_raw: "9K–43K",
  has_thumbnail: true,
  has_duration: true,
  has_posted: true,
  has_views: true,
  has_likes: true,
  has_comments: true,
  has_shares: true,
  metadata_status: "complete",
  reup_score: 76,
  reup_score_label: "Good",
  reup_score_level: "good",
  reup_score_components: {
    performance: 22,
    engagement: 21,
    shareability: 10,
    duration_fit: 15,
    recency: 8,
    metadata_quality: 10,
    penalty: 0
  },
  reup_score_reasons: ["Strong score"]
} as CapturedItem;

const readyItem: CapturedItem = {
  ...baseItem,
  id: "ready-1",
  status: "READY",
  has_all_core_metadata: true,
  missing_metadata_fields: []
};

const needsActionItem: CapturedItem = {
  ...readyItem,
  id: "needs-1",
  status: "NEEDS_ENRICHMENT",
  metadata_status: "partial"
};

assert.equal(shouldShowCaptureInboxTileMetrics(readyItem), true, "Tiles always show metric strip so Ready cards do not look metadata-empty");
assert.equal(shouldShowCaptureInboxTileMetrics(needsActionItem), true, "Needs-action items keep metric strip visible");

const score = getReupScoreForCaptureItem(readyItem);
const bars = buildReupScoreBreakdownBars(score);
assert.equal(bars.length, 6, "Positive score components render as bars");
assert.equal(bars[0]?.key, "performance");
assert.ok(bars.every((bar) => bar.max > 0));

const penalized = buildReupScoreBreakdownBars({
  ...score,
  reup_score_components: { ...score.reup_score_components, penalty: -8 }
});
assert.equal(penalized.at(-1)?.key, "penalty");
assert.equal(penalized.at(-1)?.tone, "penalty");

const pageSource = readFileSync(resolve(import.meta.dirname, "../components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
assert.match(pageSource, /shouldShowCaptureInboxTileMetrics/, "Tiles must gate metric strip visibility");
assert.match(pageSource, /ReupScoreBreakdown/, "Inspector must render Reup Score mini bars");
assert.match(pageSource, /capture-inbox-reup-score-breakdown/, "Inspector must use breakdown surface class");
assert.doesNotMatch(pageSource, /OpsDetailSection title="Live capture fields"/, "Live capture fields must merge into Overview");

console.log("capture-inbox-presentation tests passed");
