import assert from "node:assert/strict";
import test from "node:test";

import { evaluateHybridMetricsMissBatchAbortGate } from "./wholeProfileHarvest/controller.js";

function thinTarget(id: string) {
  return {
    aweme_id: id,
    source_url: `https://www.douyin.com/video/${id}`,
    profile_card_evidence: {
      aweme_id: id,
      duration_seconds: 30,
      like_count: 0,
      comment_count: 0,
      favorite_count: 0,
      share_count: 0,
      thumbnail_url: "https://p3-sign.douyinpic.com/obj/cover.jpg",
      posted_at: "2025-01-01T00:00:00.000Z"
    }
  };
}

test("gate aborts when recovery reported progress but zero targets are flush-ready", () => {
  const targets = [thinTarget("7000000000000000001"), thinTarget("7000000000000000002")];
  const gate = evaluateHybridMetricsMissBatchAbortGate({
    actionableTargets: targets,
    networkCacheByAwemeId: new Map(),
    passiveByAwemeId: new Map(),
    recovery: {
      detail_attempted: 2,
      detail_recovered: 2,
      detail_fetched: 2,
      profile_post_recovered: 0,
      profile_post_attempted: true,
      detail_hydration_available: true
    }
  });
  assert.equal(gate.should_abort, true);
  assert.equal(gate.flush_ready_count, 0);
});
