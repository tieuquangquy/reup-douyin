// Regression: profile_repository-only rows with all-zero engagement must not pass
// hydrate → flush. They previously skipped detail/profile_post recovery and wrote
// Ready stubs to the backend.

import assert from "node:assert/strict";
import test from "node:test";

import {
  evidenceIsHybridFlushReady,
  hydrateNonModalForAwemeId,
  hydrationEngagementIsTrustedForFlush,
  mergeHydrationFields,
  buildFinalizedMetadataFromHybridHydration
} from "./wholeProfileHarvest/hybridHydration.js";
import type { NetworkVideoMetadata } from "./types.js";

const AWEME = "7000000000000000001";

function repositoryZeroStub() {
  return {
    aweme_id: AWEME,
    source_url: `https://www.douyin.com/video/${AWEME}`,
    duration_seconds: 82,
    like_count: 0,
    comment_count: 0,
    favorite_count: 0,
    share_count: 0,
    thumbnail_url: "https://p3-sign.douyinpic.com/obj/cover.jpg",
    posted_at: "2025-10-28T00:25:20.000Z"
  };
}

test("all-zero profile_repository stub is not trusted for backend flush", () => {
  const hydration = hydrateNonModalForAwemeId(AWEME, {
    profile_repository: repositoryZeroStub(),
    network_cache: null,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(hydrationEngagementIsTrustedForFlush(hydration), false);
  assert.match(hydration.pending_reason ?? "", /stub_engagement_untrusted/);
  assert.equal(evidenceIsHybridFlushReady(repositoryZeroStub()), false);
  assert.equal(buildFinalizedMetadataFromHybridHydration(hydration, { profile_url: "https://www.douyin.com/user/x" }), null);
});

test("profile_repository with positive scan metrics is trusted for flush", () => {
  const evidence = {
    ...repositoryZeroStub(),
    like_count: 46,
    comment_count: 5,
    share_count: 14,
    favorite_count: 2
  };
  const hydration = hydrateNonModalForAwemeId(AWEME, {
    profile_repository: evidence,
    network_cache: null,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(hydrationEngagementIsTrustedForFlush(hydration), true);
  assert.equal(hydration.pending_reason, null);
  assert.equal(evidenceIsHybridFlushReady(evidence), true);
});

test("mergeHydrationFields prefers network engagement over repository zero stubs", () => {
  const merged = mergeHydrationFields(
    { duration_seconds: 82, duration_text: null, like_count: 0, comment_count: 0, favorite_count: 0, share_count: 0 },
    { duration_seconds: 82, duration_text: null, like_count: 46, comment_count: 5, favorite_count: 2, share_count: 14 }
  );
  assert.equal(merged.like_count, 46);
  assert.equal(merged.comment_count, 5);
});

test("network_cache engagement is trusted even when repository is thin", () => {
  const network: NetworkVideoMetadata = {
    aweme_id: AWEME,
    title: "t",
    desc: "t",
    share_url: `https://www.douyin.com/video/${AWEME}`,
    thumbnail_url: "https://p3-sign.douyinpic.com/obj/cover.jpg",
    cover_url: "https://p3-sign.douyinpic.com/obj/cover.jpg",
    origin_cover: null,
    dynamic_cover: null,
    url_list: [],
    duration_text: "1:22",
    duration_seconds: 82,
    posted_at: "2025-10-28T00:25:20.000Z",
    view_count: null,
    like_count: 46,
    comment_count: 5,
    favorite_count: 2,
    share_count: 14,
    view_count_text: null,
    like_count_text: null,
    comment_count_text: null,
    engagement_rate: null,
    raw_source: "network_cache",
    raw_network_aweme: null,
    raw_detail_aweme: null,
    observed_at: "2025-10-28T00:25:20.000Z",
    context: null,
    context_mismatch_codes: []
  } as unknown as NetworkVideoMetadata;
  const hydration = hydrateNonModalForAwemeId(AWEME, {
    profile_repository: repositoryZeroStub(),
    network_cache: network,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(hydrationEngagementIsTrustedForFlush(hydration), true);
  assert.equal(hydration.pending_reason, null);
  assert.notEqual(buildFinalizedMetadataFromHybridHydration(hydration, { profile_url: "https://www.douyin.com/user/x" }), null);
});
