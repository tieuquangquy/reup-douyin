import assert from "node:assert/strict";

import {
  formatMetadataGroupStatus,
  inspectorMetadataQualityItems,
  itemNeedsInspectorHydration
} from "../lib/captureInboxInspector";
import type { CapturedItem } from "../types/capture-inbox";

const slimProfileItem = {
  id: "item-slim",
  workspace_id: "workspace-1",
  capture_session_id: "session-1",
  source_platform: "douyin",
  status: "READY_FOR_REVIEW",
  raw_item_index: 0,
  source_video_external_id: "7420000000000000000",
  aweme_id: "7420000000000000000",
  caption: "Slim profile tile",
  duration_seconds: 741,
  like_count: 32000,
  comment_count: 638,
  share_count: 5000,
  view_count: 697300,
  posted_at: "2026-06-05T10:20:00.000Z",
  thumbnail_url: "https://example.invalid/thumb.jpg",
  metadata_status: "complete",
  created_at: "2026-07-13T06:00:00.000Z",
  updated_at: "2026-07-13T06:00:00.000Z"
} as CapturedItem;

const fullItem: CapturedItem = {
  ...slimProfileItem,
  raw_payload_json: {},
  metadata_json: {
    duration_source: "profile_card",
    posted_source: "profile_card",
    view_count_source: "profile_card",
    like_count_source: "profile_card",
    comment_count_source: "network_json",
    share_count_source: "network_json"
  },
  time_status: "captured",
  performance_status: "captured",
  processing_fit_status: "pending",
  metadata_source_summary: "profile_card + network_json",
  has_all_core_metadata: true,
  missing_metadata_fields: [],
  duration_source: "profile_card",
  posted_source: "profile_card",
  view_count_source: "profile_card",
  like_count_source: "profile_card",
  comment_count_source: "network_json",
  share_count_source: "network_json",
  engagement_rate_source: "derived_from_counts",
  preview_status: "ready",
  source_link_status: "captured",
  media_asset_status: "not_generated",
  has_speech: false,
  text_density: "low",
  has_heavy_watermark: false,
  processing_complexity: "low",
  copyright_risk: "low",
  intake_evaluation_status: "NOT_EVALUATED",
  preview_ready: true,
  media_ready: false
};

assert.equal(itemNeedsInspectorHydration(slimProfileItem), true, "slim profile items must trigger inspector hydration");
assert.equal(itemNeedsInspectorHydration(fullItem), false, "full items must not trigger redundant hydration");

const qualityItems = inspectorMetadataQualityItems(fullItem);
const byLabel = Object.fromEntries(qualityItems.map((entry) => [entry.label, entry.value]));

assert.equal(byLabel["Core metadata complete"], "Yes");
assert.equal(byLabel["Time status"], "Captured");
assert.equal(byLabel["Performance status"], "Captured");
assert.equal(byLabel["Duration source"], "profile card");
assert.equal(byLabel["Comments source"], "network json");
assert.equal(byLabel["Missing fields"], "None");

const derivedSlim = inspectorMetadataQualityItems(slimProfileItem);
const derivedByLabel = Object.fromEntries(derivedSlim.map((entry) => [entry.label, entry.value]));
assert.equal(derivedByLabel["Core metadata complete"], "Yes");
assert.equal(derivedByLabel["Time status"], "Captured");
assert.equal(derivedByLabel["Performance status"], "Captured");
assert.match(derivedByLabel["Duration source"], /Captured \(source not recorded\)|profile card/);
assert.equal(formatMetadataGroupStatus("captured"), "Captured");
assert.equal(formatMetadataGroupStatus(null), "Not captured");

console.log("capture-inbox-inspector.test.ts passed");
