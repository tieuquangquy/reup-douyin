import assert from "node:assert/strict";

import {
  recoverPendingTargetsViaProfilePostPagination,
  discoverMissingAwemeIdsViaProfilePost,
  resolveHybridProfilePostTailPageBudget,
  resolveHybridProfilePostTailPageBudgetForPending,
  targetNeedsProfilePostTailHydration,
  verifiedDetailToPassiveProfilePostTarget
} from "./wholeProfileHarvest/hybridProfilePostTailHydration.js";

const thinTarget = {
  aweme_id: "7163593122105052429",
  profile_card_evidence: {
    aweme_id: "7163593122105052429",
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-tail"
  }
};

const richDetail = {
  aweme_id: "7163593122105052429",
  source_url: "https://www.douyin.com/video/7163593122105052429",
  thumbnail_url: "https://p3.douyinpic.com/cover.jpg",
  caption: "tail video",
  duration_seconds: 42,
  profile_card_evidence: {
    aweme_id: "7163593122105052429",
    thumbnail_url: "https://p3.douyinpic.com/cover.jpg",
    cover_url: "https://p3.douyinpic.com/cover.jpg",
    duration_seconds: 42,
    like_count: 1200,
    comment_count: 88,
    favorite_count: 55,
    share_count: 12,
    create_time: 1_700_000_000,
    posted_at: "2023-11-14T22:13:20.000Z"
  }
};

assert.equal(
  targetNeedsProfilePostTailHydration(thinTarget, new Map(), new Map()),
  true,
  "thin repository evidence should need profile-post tail hydration"
);

{
  const passive = verifiedDetailToPassiveProfilePostTarget(
    richDetail,
    "https://www.douyin.com/user/MS4wLjABAAAA-tail",
    "2026-07-08T20:00:00.000Z"
  );
  assert.ok(passive);
  assert.equal(passive.like_count, 1200);
  assert.equal(passive.endpoint_kind, "profile_post");
}

assert.equal(resolveHybridProfilePostTailPageBudget(739), 44, "739 scanned videos need enough pages to reach tail");
assert.equal(resolveHybridProfilePostTailPageBudgetForPending(500, 3303), 31, "pending batch scales page budget down from full profile depth");

{
  const networkCacheByAwemeId = new Map<string, unknown>();
  const passiveByAwemeId = new Map<string, Record<string, unknown>>();
  const pages: Array<{ cursor: string | number | null; details: Array<Record<string, unknown>>; has_more: boolean; next_cursor: string | number | null }> = [
  {
    cursor: 0,
    details: [
      { aweme_id: "7000000000000000001", profile_card_evidence: { aweme_id: "7000000000000000001", duration_seconds: 10, like_count: 1, comment_count: 1, favorite_count: 1, share_count: 1, thumbnail_url: "https://p3.douyinpic.com/a.jpg", posted_at: "2024-01-01T00:00:00.000Z" } }
    ],
    has_more: true,
    next_cursor: 20
  },
  {
    cursor: 20,
    details: [richDetail],
    has_more: false,
    next_cursor: null
  }
  ];
  let pageCalls = 0;
  const result = await recoverPendingTargetsViaProfilePostPagination({
    targets: [thinTarget],
    profileUrl: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
    networkCacheByAwemeId,
    passiveByAwemeId,
    maxPages: 8,
    capturedAt: "2026-07-08T20:00:00.000Z",
    fetchPage: async (cursor) => {
      const page = pages[pageCalls]!;
      pageCalls += 1;
      assert.equal(cursor, page.cursor);
      return {
        ok: true,
        verified_target_details: page.details,
        has_more: page.has_more,
        next_cursor: page.next_cursor,
        stop_reason: page.has_more ? "page_ok_has_more" : "has_more_false"
      };
    }
  });
  assert.equal(result.pages_fetched, 2);
  assert.equal(result.recovered.includes("7163593122105052429"), true);
  assert.equal(result.stop_reason, "all_missing_found");
}

{
  const captured = new Set(["7000000000000000001"]);
  const discovery = await discoverMissingAwemeIdsViaProfilePost({
    capturedIds: captured,
    limit: 2,
    profileUrl: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
    maxPages: 4,
    capturedAt: "2026-07-08T20:00:00.000Z",
    fetchPage: async (cursor) => ({
      ok: true,
      verified_target_details: cursor === 0
        ? [{ aweme_id: "7000000000000000001", profile_card_evidence: { aweme_id: "7000000000000000001" } }]
        : [richDetail],
      has_more: cursor === 0,
      next_cursor: cursor === 0 ? 20 : null,
      stop_reason: cursor === 0 ? "page_ok_has_more" : "has_more_false"
    })
  });
  assert.deepEqual(discovery.aweme_ids, ["7163593122105052429"]);
  assert.equal(discovery.pages_fetched, 2);
}

{
  let calls = 0;
  const discovery = await discoverMissingAwemeIdsViaProfilePost({
    capturedIds: new Set(["7000000000000000001"]),
    limit: 1,
    profileUrl: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
    maxPages: 4,
    capturedAt: "2026-07-08T20:00:00.000Z",
    fetchPage: async () => {
      calls += 1;
      if (calls <= 2) {
        return {
          ok: false,
          verified_target_details: [],
          has_more: null,
          next_cursor: null,
          stop_reason: "extractor_no_targets"
        };
      }
      return {
        ok: true,
        verified_target_details: [richDetail],
        has_more: false,
        next_cursor: null,
        stop_reason: "has_more_false"
      };
    }
  });
  assert.deepEqual(discovery.aweme_ids, ["7163593122105052429"]);
  assert.ok(calls >= 3, "extractor_no_targets must retry before giving up");
}

console.info("hybridProfilePostTailHydration.test.ts: all assertions passed");
