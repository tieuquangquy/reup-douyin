import assert from "node:assert/strict";

import {
  harvestQueueActionableCount,
  reopenHybridMetricsMissSkippedForCollect
} from "./wholeProfileHarvest/controller.js";
import {
  createWholeProfileHarvestIdleState,
  type WholeProfileHarvestQueueItem,
  type WholeProfileHarvestState
} from "./wholeProfileHarvest/state.js";

const PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAA-stale-queue";
const at = "2026-07-08T17:49:00.000Z";

function skippedMetricsMissItem(awemeId: string, index: number): WholeProfileHarvestQueueItem {
  return {
    aweme_id: awemeId,
    index,
    status: "skipped",
    capture_status: "skipped",
    last_error: "missing_hybrid_metrics",
    profile_card_evidence: {
      aweme_id: awemeId,
      hybrid_uncollectable: true,
      hybrid_uncollectable_reason: "missing_required_fields:like_count"
    }
  };
}

function stateWithSkippedQueue(skippedCount: number): WholeProfileHarvestState {
  const base = createWholeProfileHarvestIdleState(PROFILE_URL);
  const queue = Array.from({ length: skippedCount }, (_, index) =>
    skippedMetricsMissItem(`7330000000000000${String(index + 1).padStart(2, "0")}`, index + 1)
  );
  return {
    ...base,
    profile_url: PROFILE_URL,
    harvest: {
      ...base.harvest,
      queue,
      pending: 0
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: PROFILE_URL,
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
    }
  };
}

{
  const poisoned = stateWithSkippedQueue(165);
  assert.equal(harvestQueueActionableCount(poisoned), 0, "metrics-miss skips block collect");
  const reopened = reopenHybridMetricsMissSkippedForCollect(poisoned, at);
  assert.equal(reopened.reopened_aweme_ids.length, 165);
  assert.equal(harvestQueueActionableCount(reopened.state), 165, "reopen restores actionable queue");
  const first = reopened.state.harvest.queue[0]!;
  assert.equal(first.status, "needs_metadata");
  assert.equal(first.profile_card_evidence?.hybrid_uncollectable, false);
}

console.info("hybridStaleQueueRecovery.test.ts: all assertions passed");
