import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  CAPTURE_INBOX_SIMPLE_DEFAULT_FILTER,
  CAPTURE_INBOX_SIMPLE_DEFAULT_SORT,
  isCaptureInboxPromotableStatus,
  pickLatestCaptureSessionId,
  selectTopPromotableCaptureItems,
  sortCaptureSessionsNewestFirst
} from "../lib/captureInboxUx";
import type { CapturedItem, CaptureSession } from "../types/capture-inbox";

const session = (id: string, createdAt: string): CaptureSession => ({
  id,
  workspace_id: "ws",
  capture_id: "cap",
  source_platform: "douyin",
  capture_source: "douyin_extension",
  status: "READY_FOR_REVIEW",
  detected_page_type: "profile",
  page_url: "https://www.douyin.com/user/test",
  page_title: null,
  submitted_profile_url: "https://www.douyin.com/user/test",
  normalized_profile_identifier: "test",
  visible_item_count: 10,
  captured_item_count: 10,
  normalized_item_count: 10,
  duplicate_item_count: 0,
  ready_item_count: 10,
  skipped_item_count: 0,
  promoted_item_count: 0,
  candidate_created_count: 0,
  failed_item_count: 0,
  started_at: createdAt,
  finished_at: createdAt,
  created_at: createdAt,
  updated_at: createdAt
});

assert.equal(pickLatestCaptureSessionId(sortCaptureSessionsNewestFirst([
  session("old", "2026-07-10T10:00:00.000Z"),
  session("new", "2026-07-11T12:00:00.000Z")
])), "new");

const items: CapturedItem[] = [
  { id: "a", status: "READY" } as CapturedItem,
  { id: "b", status: "PROMOTED" } as CapturedItem,
  { id: "c", status: "READY" } as CapturedItem
];
assert.deepEqual(selectTopPromotableCaptureItems(items, 1).map((item) => item.id), ["a"]);
assert.equal(isCaptureInboxPromotableStatus("ENRICHED"), true);
assert.equal(CAPTURE_INBOX_SIMPLE_DEFAULT_FILTER, "ready");
assert.equal(CAPTURE_INBOX_SIMPLE_DEFAULT_SORT, "highest_reup_score");

const pageSource = readFileSync(resolve(import.meta.dirname, "../components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
assert.match(pageSource, /capture-inbox-quick-path/, "Capture Inbox must render quick path bar");
assert.match(pageSource, /Promote top \$\{n\}/, "Quick path must expose promote-top-N actions");
assert.match(pageSource, /Ready focus/, "Capture Inbox must expose Ready focus toggle");
assert.doesNotMatch(pageSource, /capture-inbox-filter-drawer/, "Capture Inbox must use inline advanced filters");
assert.match(pageSource, /Studio filters/, "Capture Inbox must use studio filter toolbar");
assert.match(pageSource, /Latest/, "Session ribbon must mark latest session");

console.log("capture-inbox-ux tests passed");
