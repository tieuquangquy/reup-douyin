import assert from "node:assert/strict";

import {
  hybridLastRunWasMetricsMiss,
  shouldOfferHybridMetricsMissSkip
} from "./wholeProfileHarvest/hybridMetricsMiss.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const at = new Date().toISOString();

function stateWithSummary(summary: Record<string, unknown>) {
  const base = createWholeProfileHarvestIdleState(at);
  return {
    ...base,
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "profile",
      scanned_total: 739,
      already_collected: 571,
      new: 168,
      queue: 168,
      backend_captured: 571,
      backend_ready: 571,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      backend_captured_aweme_ids: [],
      applied_at: at
    },
    debug: {
      ...base.debug,
      last_response_summary: summary
    }
  };
}

// All metrics miss on tail backlog still offers skip
{
  const state = stateWithSummary({
    hybrid_runner_outcome: "phase_4_4c_write_pending",
    hybrid_runner_write_ok_count: 0,
    hybrid_runner_per_item_count: 8,
    hybrid_runner_flush_ready_count: 0
  });
  state.post_scan_counter_snapshot = {
    ...state.post_scan_counter_snapshot!,
    new: 8,
    queue: 8,
    already_collected: 731,
    backend_captured: 731,
    scanned_total: 739
  };
  assert.equal(hybridLastRunWasMetricsMiss(state), true);
  assert.equal(shouldOfferHybridMetricsMissSkip(state), true);
}

// Partial metrics miss on tail backlog
{
  const state = stateWithSummary({
    hybrid_runner_outcome: "phase_4_4d_loop_partial",
    hybrid_runner_write_ok_count: 71,
    hybrid_runner_loop_pending_so_far: 12,
    hybrid_runner_per_item_count: 83
  });
  state.post_scan_counter_snapshot = {
    ...state.post_scan_counter_snapshot!,
    new: 12,
    queue: 12,
    already_collected: 727,
    backend_captured: 727,
    scanned_total: 739
  };
  assert.equal(hybridLastRunWasMetricsMiss(state), true);
  assert.equal(shouldOfferHybridMetricsMissSkip(state), true);
}

// Large backlog must not offer skip-as-primary
{
  const state = stateWithSummary({
    hybrid_runner_outcome: "phase_4_4c_write_pending",
    hybrid_runner_write_ok_count: 0,
    hybrid_runner_per_item_count: 236,
    hybrid_runner_flush_ready_count: 0
  });
  assert.equal(hybridLastRunWasMetricsMiss(state), true);
  assert.equal(shouldOfferHybridMetricsMissSkip(state), false);
}

// Completed with no pending must not offer skip
{
  const state = stateWithSummary({
    hybrid_runner_outcome: "phase_4_4d_loop_completed",
    hybrid_runner_write_ok_count: 71,
    hybrid_runner_loop_pending_so_far: 0,
    hybrid_runner_per_item_count: 71
  });
  assert.equal(hybridLastRunWasMetricsMiss(state), false);
}

// Pre-loop fail-fast when detail recovery could not hydrate any metrics (tail only)
{
  const state = stateWithSummary({
    hybrid_runner_outcome: "phase_4_4c_metrics_miss_unrecoverable",
    hybrid_runner_write_ok_count: 0,
    hybrid_runner_flush_ready_count: 0,
    hybrid_runner_metrics_miss_stub_only_count: 20
  });
  state.post_scan_counter_snapshot = {
    ...state.post_scan_counter_snapshot!,
    new: 20,
    queue: 20,
    already_collected: 719,
    backend_captured: 719,
    scanned_total: 739
  };
  assert.equal(hybridLastRunWasMetricsMiss(state), true);
  assert.equal(shouldOfferHybridMetricsMissSkip(state), true);
}

// Large backlog: one metrics-miss stub must not hijack primary action (batch 2 on 1004 profile)
{
  const state = {
    ...stateWithSummary({
      hybrid_runner_outcome: "phase_4_4c_write_pending",
      hybrid_runner_write_ok_count: 0,
      hybrid_runner_per_item_count: 1,
      hybrid_runner_pre_skip_pending: 1,
      hybrid_runner_flush_ready_count: 0,
      hybrid_runner_post_run_tile_new: 505,
      hybrid_runner_post_run_tile_already: 499
    }),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "profile",
      scanned_total: 1004,
      already_collected: 499,
      new: 505,
      queue: 505,
      backend_captured: 499,
      backend_ready: 499,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 1,
      need_retry: 0,
      backend_captured_aweme_ids: [],
      applied_at: at
    },
    harvest: {
      ...createWholeProfileHarvestIdleState(at).harvest,
      queue: [
        {
          aweme_id: "7145666719011376000",
          status: "needs_metadata",
          capture_status: "incomplete",
          profile_card_evidence: { hybrid_uncollectable: false }
        }
      ]
    }
  };
  assert.equal(hybridLastRunWasMetricsMiss(state), true);
  assert.equal(shouldOfferHybridMetricsMissSkip(state, 505), false, "505-video backlog must keep Continue Collecting primary");
}

console.info("hybridMetricsMiss.test.ts: all assertions passed");
