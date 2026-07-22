import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  CAPTURE_INBOX_SIMPLE_DEFAULT_FILTER,
  CAPTURE_INBOX_SIMPLE_DEFAULT_SORT,
  captureInboxDetailsActionModel,
  isCaptureInboxPromotableItem,
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
  { id: "a", status: "READY", matches_intake: true } as CapturedItem,
  { id: "b", status: "PROMOTED" } as CapturedItem,
  { id: "c", status: "READY", matches_intake: false } as CapturedItem,
  { id: "d", status: "PREVIEW_MISSING", matches_intake: true } as CapturedItem
];
assert.deepEqual(selectTopPromotableCaptureItems(items, 1).map((item) => item.id), ["a"]);
assert.equal(isCaptureInboxPromotableStatus("ENRICHED"), true);
assert.equal(isCaptureInboxPromotableStatus("PREVIEW_MISSING"), false);
assert.equal(isCaptureInboxPromotableItem(items[2]), false);
assert.equal(CAPTURE_INBOX_SIMPLE_DEFAULT_FILTER, "ready");
assert.equal(CAPTURE_INBOX_SIMPLE_DEFAULT_SORT, "highest_reup_score");

{
  const readyModel = captureInboxDetailsActionModel({ id: "ready-1", status: "READY", matches_intake: true } as CapturedItem);
  assert.equal(readyModel.kind, "ready");
  assert.equal(readyModel.showPromote, true);
  assert.equal(readyModel.showRecheck, true);
  assert.equal(readyModel.showDelete, true);

  const failedModel = captureInboxDetailsActionModel({ id: "fail-1", status: "FAILED", matches_intake: true } as CapturedItem);
  assert.equal(failedModel.kind, "recover");
  assert.equal(failedModel.showPromote, false, "Failed items must not tease a disabled Promote CTA");
  assert.equal(failedModel.showRecheck, true);
  assert.equal(failedModel.showDelete, true);

  const duplicateModel = captureInboxDetailsActionModel({ id: "dup-1", status: "DUPLICATE", matches_intake: true } as CapturedItem);
  assert.equal(duplicateModel.kind, "recover");
  assert.equal(duplicateModel.showPromote, false);

  const promotedModel = captureInboxDetailsActionModel({
    id: "promoted-1",
    status: "PROMOTED",
    promoted_video_candidate_id: "cand-1"
  } as CapturedItem);
  assert.equal(promotedModel.kind, "promoted");
  assert.match(promotedModel.reviewBoardHref ?? "", /candidate=cand-1/);

  const excludedModel = captureInboxDetailsActionModel({ id: "ex-1", status: "EXCLUDED" } as CapturedItem);
  assert.equal(excludedModel.kind, "excluded");
  assert.equal(excludedModel.showPromote, false);
  assert.equal(excludedModel.showRecheck, false);
  assert.equal(excludedModel.showDelete, true);
}

const actionsSource = readFileSync(resolve(import.meta.dirname, "../components/capture-inbox/CaptureInboxTileActions.tsx"), "utf8");
assert.match(actionsSource, /captureInboxDetailsActionModel/, "Capture Inbox tile/details must use stage-aware action model");
assert.doesNotMatch(
  actionsSource,
  /disabled=\{disabled \|\| !promotable\}/,
  "Capture Inbox must hide Promote when not promotable instead of leaving a disabled primary CTA"
);
const pageSource = readFileSync(resolve(import.meta.dirname, "../components/capture-inbox/CaptureInboxPage.tsx"), "utf8");
const promoteSplitSource = readFileSync(resolve(import.meta.dirname, "../components/capture-inbox/CaptureInboxPromoteSplitButton.tsx"), "utf8");
const captureInboxSource = pageSource + promoteSplitSource;
assert.match(pageSource, /capture-inbox-hero-action-rail/, "Capture Inbox must render its quick action rail");
assert.match(captureInboxSource, /CAPTURE_INBOX_PROMOTE_TOP_BATCHES/, "Quick path must expose promote-top-N actions");
assert.doesNotMatch(pageSource, /Ready focus|toggleReadyFocus/, "Capture Inbox must rely on the authoritative Ready status card instead of a duplicate focus toggle");
assert.match(promoteSplitSource, /if \(!readyViewActive\)/, "Promote controls must be context-gated outside the Ready tab");
assert.match(promoteSplitSource, /Go to Ready \(\$\{readyCount\}\)/, "Non-Ready tabs must offer an explicit transition to Ready");
assert.match(pageSource, /readyViewActive=\{filter === "ready"\}/, "Hero promote controls must receive the authoritative active Ready context");
assert.doesNotMatch(pageSource, /capture-inbox-filter-drawer/, "Capture Inbox must use inline advanced filters");
assert.match(pageSource, /Studio filters/, "Capture Inbox must use studio filter toolbar");
assert.match(pageSource, /Latest/, "Session ribbon must mark latest session");

console.log("capture-inbox-ux tests passed");
