// Part B regression: when a collect batch contains targets whose real metrics are
// NOT available from the in-tab network cache / passive probe / repository evidence
// (the oldest "tail" videos evicted from the 240-item cache), the runner must
// actively fetch each pending video's real detail evidence and merge it into the
// hydration cache BEFORE skipping — so the tail is collected with REAL data instead
// of being stuck as uncollectable.

import assert from "node:assert/strict";
import test from "node:test";

import {
  applyDetailHydratedEvidenceToHarvestState,
  attemptLazyHybridDetailHydrationForTarget,
  chunkDetailHydrationDiscoveries,
  isHybridMetricsMissPendingReason,
  recoverPendingTargetsViaDetailHydration,
  resolveHybridDetailHydrationCap,
  resolveHybridDetailHydrationTimeoutMs
} from "./wholeProfileHarvest/controller.js";
import { hydrateNonModalForAwemeId, enrichQueueItemEvidenceFromHydrationCaches, evidenceIsHybridFlushReady } from "./wholeProfileHarvest/hybridHydration.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";
import type { NetworkVideoMetadata } from "./types.js";

function thinTarget(id: string): { aweme_id: string; source_url: string; profile_card_evidence: Record<string, unknown> } {
  return {
    aweme_id: id,
    source_url: `https://www.douyin.com/video/${id}`,
    // Thin evidence: only identity, no metrics/thumbnail/posted → NOT flush-ready.
    profile_card_evidence: { aweme_id: id, source_url: `https://www.douyin.com/video/${id}`, caption: "tail" }
  };
}

function realDetail(id: string): NetworkVideoMetadata {
  return {
    aweme_id: id,
    title: "real",
    desc: "real",
    share_url: `https://www.douyin.com/video/${id}`,
    thumbnail_url: `https://p3-sign.douyinpic.com/tos-cn-i/${id}~tplv.jpeg?x-signature=sig`,
    cover_url: `https://p3-sign.douyinpic.com/tos-cn-i/${id}~tplv.jpeg?x-signature=sig`,
    origin_cover: null,
    dynamic_cover: null,
    url_list: [],
    duration_text: "15s",
    duration_seconds: 15,
    posted_at: "2023-01-02T00:00:00.000Z",
    view_count: null,
    like_count: 4321,
    comment_count: 21,
    favorite_count: 3,
    share_count: 9,
    view_count_text: null,
    like_count_text: null,
    comment_count_text: null,
    engagement_rate: null,
    raw_source: "detail_hydrate",
    raw_network_aweme: null,
    raw_detail_aweme: null,
    observed_at: "2023-01-02T00:00:00.000Z",
    context: null,
    context_mismatch_codes: []
  } as unknown as NetworkVideoMetadata;
}

test("pending tail targets are recovered by injected detail hydration", async () => {
  const targets = [thinTarget("7000000000000000001"), thinTarget("7000000000000000002")];
  const networkCacheByAwemeId = new Map<string, unknown>();
  const passiveByAwemeId = new Map<string, Record<string, unknown>>();

  // Sanity: both targets are pending before hydration.
  for (const t of targets) {
    const evidence = enrichQueueItemEvidenceFromHydrationCaches(t, null, null);
    const h = hydrateNonModalForAwemeId(t.aweme_id, {
      profile_repository: evidence,
      network_cache: null,
      passive_aweme: null,
      profile_post_api: null,
      calibrated_non_modal_dom: null
    });
    assert.ok(h.pending_reason, `${t.aweme_id} must start pending`);
  }

  const requested: string[][] = [];
  const result = await recoverPendingTargetsViaDetailHydration({
    targets,
    networkCacheByAwemeId,
    passiveByAwemeId,
    hydrateDetail: async (discoveries) => {
      requested.push(discoveries.map((d) => d.aweme_id));
      return discoveries.map((d) => realDetail(d.aweme_id));
    }
  });

  assert.deepEqual(result.pending_before.sort(), targets.map((t) => t.aweme_id).sort());
  assert.deepEqual(result.recovered.sort(), targets.map((t) => t.aweme_id).sort(), "both tail targets recovered");
  assert.equal(requested.length, 1, "one batched detail fetch");
  // Cache now carries real detail so the main loop hydrates them.
  assert.ok(networkCacheByAwemeId.has("7000000000000000001"));
  assert.ok(networkCacheByAwemeId.has("7000000000000000002"));
});

test("targets stay pending when detail hydration returns nothing (honest skip, no fabrication)", async () => {
  const targets = [thinTarget("7000000000000000003")];
  const networkCacheByAwemeId = new Map<string, unknown>();
  const passiveByAwemeId = new Map<string, Record<string, unknown>>();

  const result = await recoverPendingTargetsViaDetailHydration({
    targets,
    networkCacheByAwemeId,
    passiveByAwemeId,
    hydrateDetail: async () => []
  });

  assert.deepEqual(result.pending_before, ["7000000000000000003"]);
  assert.deepEqual(result.recovered, [], "no recovery without real data");
  assert.equal(networkCacheByAwemeId.has("7000000000000000003"), false, "no fabricated cache entry");
});

test("already flush-ready targets are not fetched", async () => {
  const ready = {
    aweme_id: "7000000000000000004",
    source_url: "https://www.douyin.com/video/7000000000000000004",
    profile_card_evidence: {
      aweme_id: "7000000000000000004",
      source_url: "https://www.douyin.com/video/7000000000000000004",
      duration_seconds: 20,
      like_count: 10,
      comment_count: 1,
      favorite_count: 1,
      share_count: 1,
      thumbnail_url: "https://p3-sign.douyinpic.com/x~tplv.jpeg?x-signature=s",
      posted_at: "2023-05-05T00:00:00.000Z"
    }
  };
  let fetched = false;
  const result = await recoverPendingTargetsViaDetailHydration({
    targets: [ready],
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    hydrateDetail: async () => {
      fetched = true;
      return [];
    }
  });
  assert.equal(result.pending_before.length, 0, "flush-ready target is not pending");
  assert.equal(fetched, false, "no network fetch for flush-ready targets");
});

test("maxTargets caps how many pending targets are fetched per run", async () => {
  const targets = [
    thinTarget("7000000000000000005"),
    thinTarget("7000000000000000006"),
    thinTarget("7000000000000000007")
  ];
  const requested: string[] = [];
  const result = await recoverPendingTargetsViaDetailHydration({
    targets,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    maxTargets: 2,
    hydrateDetail: async (discoveries) => {
      requested.push(...discoveries.map((d) => d.aweme_id));
      return discoveries.map((d) => realDetail(d.aweme_id));
    }
  });
  assert.equal(result.attempted.length, 2, "only maxTargets attempted");
  assert.equal(requested.length, 2);
});

test("detail hydration cap scales with actionable batch window", () => {
  assert.equal(resolveHybridDetailHydrationCap(10), 50, "floor stays at legacy minimum");
  assert.equal(resolveHybridDetailHydrationCap(236), 236, "batch 2 must attempt full window");
  assert.equal(resolveHybridDetailHydrationCap(739), 500, "absolute ceiling");
});

test("detail hydration timeout scales with attempt cap", () => {
  assert.equal(resolveHybridDetailHydrationTimeoutMs(50), 200_000);
  assert.equal(resolveHybridDetailHydrationTimeoutMs(236), 900_000, "large tail batches need up to 15 minutes");
});

test("isHybridMetricsMissPendingReason detects metrics-miss skip reasons", () => {
  assert.equal(isHybridMetricsMissPendingReason("missing_required_fields:like_count"), true);
  assert.equal(isHybridMetricsMissPendingReason("no_capture_session_id"), false);
});

test("chunkDetailHydrationDiscoveries splits large batches", () => {
  const items = Array.from({ length: 52 }, (_, index) => index);
  const chunks = chunkDetailHydrationDiscoveries(items, 25);
  assert.equal(chunks.length, 3);
  assert.equal(chunks[0]?.length, 25);
  assert.equal(chunks[1]?.length, 25);
  assert.equal(chunks[2]?.length, 2);
});

test("detail hydration aborts after consecutive empty chunks when tab cannot fetch", async () => {
  let chunkCalls = 0;
  const targets = Array.from({ length: 75 }, (_, index) => thinTarget(`7000000000000000${String(index).padStart(3, "0")}`));
  const result = await recoverPendingTargetsViaDetailHydration({
    targets,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    maxTargets: 75,
    hydrateDetail: async () => {
      chunkCalls += 1;
      return [];
    }
  });
  assert.equal(chunkCalls, 2, "must stop after two consecutive empty chunks");
  assert.equal(result.attempted.length, 50, "two chunks attempted before abort");
  assert.equal(result.recovered.length, 0);
});

test("lazy in-loop detail hydration recovers metrics-miss target", async () => {
  const target = thinTarget("7000000000000000100");
  const networkCacheByAwemeId = new Map<string, unknown>();
  const passiveByAwemeId = new Map<string, Record<string, unknown>>();
  const result = await attemptLazyHybridDetailHydrationForTarget({
    aweme_id: target.aweme_id,
    source_url: target.source_url,
    profile_card_evidence: target.profile_card_evidence,
    networkCacheByAwemeId,
    passiveByAwemeId,
    hydrateDetail: async (discoveries) => discoveries.map((d) => realDetail(d.aweme_id))
  });
  assert.equal(result.recovered, true);
  assert.ok(networkCacheByAwemeId.has("7000000000000000100"));
  const evidence = enrichQueueItemEvidenceFromHydrationCaches(target, null, result.networkCacheItem);
  const hydration = hydrateNonModalForAwemeId(target.aweme_id, {
    profile_repository: evidence,
    network_cache: result.networkCacheItem,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(hydration.pending_reason, null, "lazy fetch must clear metrics-miss pending");
});

test("lazy detail hydration stays honest when fetch returns nothing", async () => {
  const target = thinTarget("7000000000000000101");
  const result = await attemptLazyHybridDetailHydrationForTarget({
    aweme_id: target.aweme_id,
    source_url: target.source_url,
    profile_card_evidence: target.profile_card_evidence,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    hydrateDetail: async () => []
  });
  assert.equal(result.recovered, false);
  assert.equal(result.networkCacheItem, null);
});

test("recovered detail evidence is merged into harvest queue state", () => {
  const at = new Date().toISOString();
  const awemeId = "7000000000000000999";
  const base = createWholeProfileHarvestIdleState(at);
  const thinItem = {
    index: 1,
    aweme_id: awemeId,
    capture_status: "new" as const,
    status: "pending" as const,
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: `https://www.douyin.com/video/${awemeId}`,
    profile_card_evidence: { aweme_id: awemeId, caption: "thin" }
  };
  const state = {
    ...base,
    profile_url: "https://www.douyin.com/user/test-profile",
    harvest: {
      ...base.harvest,
      queue: [thinItem],
      queue_preview: [],
      pending: 1
    },
    profile_scan: {
      ...base.profile_scan,
      target_details: [{
        index: 1,
        aweme_id: awemeId,
        source_url: thinItem.source_url,
        profile_url: null,
        thumbnail_url: null,
        title: null,
        caption: "thin",
        text_sample: null,
        posted_text: null,
        posted_at: null,
        duration_text: null,
        duration_seconds: null,
        capture_status: "new" as const,
        backend_item: null
      }]
    }
  };
  const networkCacheByAwemeId = new Map<string, unknown>([[awemeId, realDetail(awemeId)]]);
  const next = applyDetailHydratedEvidenceToHarvestState({
    state,
    recoveredAwemeIds: [awemeId],
    networkCacheByAwemeId,
    passiveByAwemeId: new Map(),
    at
  });
  const evidence = next.harvest.queue[0]?.profile_card_evidence;
  assert.equal(evidenceIsHybridFlushReady(evidence), true, "queue evidence must become flush-ready after detail merge");
});
