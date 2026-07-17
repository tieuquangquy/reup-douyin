import assert from "node:assert/strict";

import { resolveCommentCount, resolveEngagementCountNumber, resolveShareCount } from "../lib/captureInboxCanonical";
import type { CapturedItem } from "../types/capture-inbox";

const baseItem = {
  id: "item-zero",
  workspace_id: "workspace-1",
  capture_session_id: "session-1",
  source_platform: "douyin",
  status: "READY",
  raw_item_index: 0,
  source_video_external_id: "7420000000000000000",
  comment_count: null,
  share_count: null,
  like_count: 24,
  created_at: "2026-07-13T06:00:00.000Z",
  updated_at: "2026-07-13T06:00:00.000Z"
} as CapturedItem;

const commentSentinelItem: CapturedItem = {
  ...baseItem,
  comment_count_text: "抢首评"
};

const shareSentinelItem: CapturedItem = {
  ...baseItem,
  share_count_text: "分享"
};

assert.equal(resolveEngagementCountNumber(commentSentinelItem, "comment"), 0);
assert.equal(resolveEngagementCountNumber(shareSentinelItem, "share"), 0);
assert.equal(resolveCommentCount(commentSentinelItem), "0");
assert.equal(resolveShareCount(shareSentinelItem), "0");

console.log("capture-inbox-engagement-zero.test.ts passed");
