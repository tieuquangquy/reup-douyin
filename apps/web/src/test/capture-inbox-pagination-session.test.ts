import assert from "node:assert/strict";

import {
  captureItemMergeKey,
  computeSessionNeedsActionCount,
  hasMoreCapturedItems,
  hasMoreCapturedItemsAfterPage,
  mergeCapturedItemsPage,
  pickProfileMatchedSessionId,
  reconcileGalleryTotalAfterStall,
  resolveGalleryTotalCount,
  resolveItemsLoadScopeForSession,
  shouldAutoLoadCaptureTail,
  shouldKeepManualSessionSelection,
  shouldUseProfileItemsScope
} from "../lib/captureInboxPagination";

assert.equal(hasMoreCapturedItems(1000, 1008), true, "Gallery must keep loading when items remain");
assert.equal(hasMoreCapturedItems(1008, 1008), false, "Gallery must stop when all items are loaded");
assert.equal(
  hasMoreCapturedItemsAfterPage(1000, 1008, 8, 8),
  true,
  "Tail page with new items must keep hasMore until loaded count reaches total"
);
assert.equal(
  hasMoreCapturedItemsAfterPage(1000, 1008, 0, 0),
  false,
  "Empty tail page must stop infinite load-more loop"
);
assert.equal(
  hasMoreCapturedItemsAfterPage(1000, 1008, 8, 0),
  false,
  "Duplicate-only tail page must stop infinite load-more loop"
);
assert.equal(shouldAutoLoadCaptureTail(1000, 1008, 100), true, "Small tail gap must auto-load without relying on sentinel only");
assert.equal(shouldAutoLoadCaptureTail(100, 5000, 100), false, "Large backlogs must not auto-drain entirely");
assert.equal(
  shouldKeepManualSessionSelection("session-b", "session-a", "session-b"),
  true,
  "Manual session selection must block profile deep-link auto-switch"
);
assert.equal(
  shouldUseProfileItemsScope("https://www.douyin.com/user/foo", "profile"),
  true,
  "Profile deep-link with profile scope must use profile-items API"
);
assert.equal(
  shouldUseProfileItemsScope("https://www.douyin.com/user/foo", "session"),
  false,
  "Manual session override must use session-scoped items API"
);
assert.equal(
  resolveItemsLoadScopeForSession("https://www.douyin.com/user/foo", "session-a", "session-a"),
  "profile",
  "Matched profile session must load profile-wide items"
);
assert.equal(
  resolveItemsLoadScopeForSession("https://www.douyin.com/user/foo", "session-b", "session-a"),
  "session",
  "Different session must load session-scoped items"
);
assert.equal(
  resolveItemsLoadScopeForSession("https://www.douyin.com/user/foo", "session-a", "session-a", true),
  "session",
  "Manual ribbon selection must always load session-scoped items"
);
assert.equal(
  computeSessionNeedsActionCount({
    captured_item_count: 1008,
    ready_item_count: 1008,
    duplicate_item_count: 0,
    failed_item_count: 0,
    promoted_item_count: 0
  }),
  0,
  "Fully ready session must report zero needs-action"
);

const firstPage = [
  { id: "row-1", source_video_external_id: "aweme-1", aweme_id: "aweme-1" },
  { id: "row-2", source_video_external_id: "aweme-2", aweme_id: "aweme-2" }
];
const duplicateAwemePage = [
  { id: "row-3", source_video_external_id: "aweme-1", aweme_id: "aweme-1" },
  { id: "row-4", source_video_external_id: "aweme-3", aweme_id: "aweme-3" }
];
const profileMerged = mergeCapturedItemsPage(firstPage, duplicateAwemePage, "profile");
assert.equal(profileMerged.merged.length, 3, "Profile scope must dedupe by aweme id across sessions");
assert.equal(profileMerged.appendedCount, 1, "Only one new aweme should append from duplicate tail page");
const sessionMerged = mergeCapturedItemsPage(firstPage, duplicateAwemePage, "session");
assert.equal(sessionMerged.merged.length, 4, "Session scope must keep distinct staged rows");
assert.equal(
  captureItemMergeKey({ id: "row-1", source_video_external_id: "aweme-1", aweme_id: "aweme-1" }, "profile"),
  "aweme-1",
  "Profile merge key must prefer aweme identity"
);

assert.equal(
  resolveGalleryTotalCount("profile", 1008, 1000),
  1000,
  "Gallery total in profile scope must use unique video count when provided"
);
assert.equal(
  reconcileGalleryTotalAfterStall(1000, 1008),
  1000,
  "Stalled pagination must reconcile displayed total to loaded unique count"
);

const matched = pickProfileMatchedSessionId(
  [
    {
      id: "session-small",
      captured_item_count: 70,
      normalized_profile_identifier: "profile-a",
      submitted_profile_url: "https://www.douyin.com/user/profile-a"
    },
    {
      id: "session-large",
      captured_item_count: 1008,
      normalized_profile_identifier: "profile-a",
      submitted_profile_url: "https://www.douyin.com/user/profile-a"
    }
  ],
  "https://www.douyin.com/user/profile-a",
  "profile-a"
);
assert.equal(matched, "session-large", "Profile match must prefer the fullest capture session");

console.log("capture-inbox-pagination-session.test.ts passed");
