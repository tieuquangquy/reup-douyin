import assert from "node:assert/strict";

import {
  diffAwemeIdsMissingFromCaptured,
  diffAwemeIdsMissingFromCapturedTailFirst,
  isHybridTailGapCollect,
  resolveHybridCollectTailGapHint,
  resolveHybridDisplayedProfileCollectGapUncapped,
  resolveHybridExactTailGapCandidate,
  resolveHybridOperatorCollectBacklog,
  resolveHybridDisplayedProfileTailGap,
  resolveHybridOperatorVisibleTailGap,
  tailGapFromFossilRecord
} from "./wholeProfileHarvest/hybridBackendGapAwemeIds.js";
import { resolveHybridCollectBatchLimits } from "./wholeProfileHarvest/hybridCollectBatchLimits.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

assert.equal(isHybridTailGapCollect(3), true, "3 remaining is exact tail-gap territory");
assert.equal(isHybridTailGapCollect(25), true, "25 is the tail-gap cap");
assert.equal(isHybridTailGapCollect(236), false, "236 must not activate nuclear tail-gap mode");

assert.deepEqual(
  resolveHybridCollectBatchLimits(3, 3),
  { writeBatchLimit: 3, preSkipScanLimit: 3 },
  "exact tail queue length matches gap"
);

const captured = new Set(["1", "2", "4"]);
const scanned = ["1", "2", "3", "4", "5"];
assert.deepEqual(diffAwemeIdsMissingFromCaptured(scanned, captured, 2), ["3", "5"]);
assert.deepEqual(diffAwemeIdsMissingFromCapturedTailFirst(scanned, captured, 2), ["3", "5"]);

const tailState = {
  ...createWholeProfileHarvestIdleState(new Date().toISOString()),
  debug: {
    last_request_summary: null,
    last_response_summary: {
      hybrid_runner_post_run_tile_new: 3,
      hybrid_runner_post_run_tile_already: 736
    },
    last_action_clicked: null,
    last_action_result: null,
    last_action_error: null,
    last_action_started_at: null,
    last_action_finished_at: null,
    trace: []
  }
};
assert.equal(resolveHybridOperatorVisibleTailGap(tailState), 3, "post-run tile_new must drive tail-gap activation");

assert.equal(tailGapFromFossilRecord({ hybrid_runner_post_run_tile_new: 3 }), 3);
assert.equal(tailGapFromFossilRecord({ hybrid_runner_post_run_tile_new: 236 }), null);

const displayedGapState = {
  ...createWholeProfileHarvestIdleState(new Date().toISOString()),
  profile_scan: {
    ...createWholeProfileHarvestIdleState(new Date().toISOString()).profile_scan,
    diagnostics: { displayed_profile_count: 739 }
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "test" as const,
    profile_identifier: "test",
    scanned_total: 735,
    backend_captured_aweme_ids: [] as string[],
    backend_captured: 736,
    already_collected: 736,
    backend_ready: 736,
    backend_dup: 0,
    backend_fail: 0,
    new: 0,
    queue: 0,
    applied_at: new Date().toISOString()
  }
};
assert.equal(resolveHybridDisplayedProfileTailGap(displayedGapState), 3, "739 displayed minus 736 captured");
assert.equal(resolveHybridCollectTailGapHint(displayedGapState, { hybrid_runner_post_run_tile_new: 3 }), 3);

const largeBacklogState = {
  ...createWholeProfileHarvestIdleState(new Date().toISOString()),
  profile_scan: {
    ...createWholeProfileHarvestIdleState(new Date().toISOString()).profile_scan,
    diagnostics: { displayed_profile_count: 116 }
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "test" as const,
    profile_identifier: "test",
    scanned_total: 116,
    backend_captured_aweme_ids: [] as string[],
    backend_captured: 40,
    already_collected: 40,
    backend_ready: 40,
    backend_dup: 0,
    backend_fail: 0,
    new: 76,
    queue: 76,
    applied_at: new Date().toISOString()
  },
  debug: {
    last_request_summary: null,
    last_response_summary: {
      hybrid_runner_post_run_tile_new: 76,
      hybrid_tail_gap_live_remaining: 8,
      hybrid_runner_post_run_backend_captured: 40
    },
    last_action_clicked: null,
    last_action_result: null,
    last_action_error: null,
    last_action_started_at: null,
    last_action_finished_at: null,
    trace: []
  }
};
assert.equal(resolveHybridOperatorCollectBacklog(largeBacklogState), 76, "operator backlog must use tile_new / displayed gap");
assert.equal(
  resolveHybridExactTailGapCandidate(largeBacklogState, { hybrid_runner_post_run_tile_new: 76, hybrid_tail_gap_live_remaining: 8 }),
  null,
  "small backend live_remaining must not activate exact tail-gap when 76 videos remain"
);
assert.equal(tailGapFromFossilRecord({ hybrid_runner_post_run_tile_new: 76, hybrid_tail_gap_live_remaining: 8 }), null);
assert.equal(resolveHybridDisplayedProfileCollectGapUncapped(largeBacklogState), 76);

console.info("hybridExactTailGapPrepare.test.ts: all assertions passed");
