// Batch 2 regression: when every actionable target is still metrics-miss after
// pre-loop profile_post + detail hydration, abort before the interleaved loop
// instead of mass-skipping 88 items with write_ok_count=0.

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildHybridMetricsMissBatchAbortMessage,
  countHybridFlushReadyActionableTargets,
  evaluateHybridMetricsMissBatchAbortGate,
  type HybridPreLoopHydrationRecoverySummary
} from "./wholeProfileHarvest/controller.js";
import type { NetworkVideoMetadata } from "./types.js";

function thinTarget(id: string) {
  return {
    aweme_id: id,
    source_url: `https://www.douyin.com/video/${id}`,
    profile_card_evidence: { aweme_id: id, caption: "tail" }
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

const noRecovery: HybridPreLoopHydrationRecoverySummary = {
  detail_attempted: 0,
  detail_recovered: 0,
  detail_fetched: 0,
  profile_post_recovered: 0,
  profile_post_attempted: false,
  detail_hydration_available: false
};

test("gate does not abort when at least one target is flush-ready after caches", () => {
  const targets = [thinTarget("7000000000000000001"), thinTarget("7000000000000000002")];
  const networkCacheByAwemeId = new Map<string, unknown>([["7000000000000000001", realDetail("7000000000000000001")]]);
  assert.equal(countHybridFlushReadyActionableTargets(targets, networkCacheByAwemeId, new Map()), 1);
  const gate = evaluateHybridMetricsMissBatchAbortGate({
    actionableTargets: targets,
    networkCacheByAwemeId,
    passiveByAwemeId: new Map(),
    recovery: { ...noRecovery, detail_attempted: 2, detail_hydration_available: true }
  });
  assert.equal(gate.should_abort, false);
});

test("gate aborts when recovery ran but zero targets are flush-ready", () => {
  const targets = Array.from({ length: 88 }, (_, index) => thinTarget(`724960301389829252${index}`));
  const gate = evaluateHybridMetricsMissBatchAbortGate({
    actionableTargets: targets,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    recovery: {
      detail_attempted: 88,
      detail_recovered: 0,
      detail_fetched: 0,
      profile_post_recovered: 0,
      profile_post_attempted: true,
      detail_hydration_available: true
    }
  });
  assert.equal(gate.should_abort, true);
  assert.equal(gate.stub_only_count, 88);
  assert.match(gate.message, /88 videos need metrics/i);
  assert.match(buildHybridMetricsMissBatchAbortMessage(88), /refresh/i);
});

test("post-hydration flush-ready subset can proceed without aborting whole batch", () => {
  const targets = [thinTarget("stub-1"), thinTarget("stub-2")];
  const networkCacheByAwemeId = new Map<string, unknown>([["stub-1", realDetail("stub-1")]]);
  const gate = evaluateHybridMetricsMissBatchAbortGate({
    actionableTargets: targets,
    networkCacheByAwemeId,
    passiveByAwemeId: new Map(),
    recovery: {
      detail_attempted: 2,
      detail_recovered: 1,
      detail_fetched: 1,
      profile_post_recovered: 0,
      profile_post_attempted: true,
      detail_hydration_available: true
    }
  });
  assert.equal(gate.should_abort, false);
  assert.equal(countHybridFlushReadyActionableTargets(targets, networkCacheByAwemeId, new Map()), 1);
});

test("gate does not abort when detail hydration is unavailable (tab path handles separately)", () => {
  const targets = [thinTarget("7000000000000000003")];
  const gate = evaluateHybridMetricsMissBatchAbortGate({
    actionableTargets: targets,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    recovery: noRecovery
  });
  assert.equal(gate.should_abort, false);
});
