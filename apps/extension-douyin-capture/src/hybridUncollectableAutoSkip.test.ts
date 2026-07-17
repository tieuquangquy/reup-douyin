import assert from "node:assert/strict";

import {
  isUncollectableHybridPendingRecord,
  shouldAutoSkipHybridMetricsMissBatch
} from "./wholeProfileHarvest/hybridMetricsMiss.js";
import {
  harvestQueueActionableCount,
  reopenHybridMetricsMissSkippedForCollect
} from "./wholeProfileHarvest/controller.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const metricsMissRecord = {
  status: "skipped_pending",
  pending_reason: "missing_required_fields:duration_seconds,like_count"
};

assert.equal(isUncollectableHybridPendingRecord(metricsMissRecord), true);
assert.equal(isUncollectableHybridPendingRecord({ status: "write_ok" }), false);

assert.equal(
  shouldAutoSkipHybridMetricsMissBatch({
    perItemRecords: [metricsMissRecord],
    loopWriteOkCount: 0,
    loopFinalizedCount: 0,
    loopLazyDetailAttemptedCount: 0,
    preLoopDetailHydrationAttempted: 0,
    tabId: 123,
    detailHydrationAvailable: true
  }),
  false,
  "must not auto-skip when detail hydration was never attempted"
);

assert.equal(
  shouldAutoSkipHybridMetricsMissBatch({
    perItemRecords: [metricsMissRecord],
    loopWriteOkCount: 0,
    loopFinalizedCount: 0,
    loopLazyDetailAttemptedCount: 5,
    preLoopDetailHydrationAttempted: 0,
    tabId: null,
    detailHydrationAvailable: true
  }),
  false,
  "must not auto-skip without a Douyin tab for detail fetch"
);

assert.equal(
  shouldAutoSkipHybridMetricsMissBatch({
    perItemRecords: [metricsMissRecord],
    loopWriteOkCount: 0,
    loopFinalizedCount: 0,
    loopLazyDetailAttemptedCount: 3,
    preLoopDetailHydrationAttempted: 0,
    tabId: 99,
    detailHydrationAvailable: true
  }),
  false,
  "must never auto-skip metrics-miss batches; operator skip only"
);

{
  const at = "2026-07-08T19:30:00.000Z";
  const base = createWholeProfileHarvestIdleState(at);
  const poisoned = reopenHybridMetricsMissSkippedForCollect({
    ...base,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-reopen",
    harvest: {
      ...base.harvest,
      queue: [{
        aweme_id: "7163593122105052429",
        index: 1,
        status: "skipped",
        capture_status: "skipped",
        last_error: "missing_hybrid_metrics",
        profile_card_evidence: {
          hybrid_uncollectable: true,
          hybrid_uncollectable_reason: "missing_required_fields:like_count"
        }
      }],
      pending: 0
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "https://www.douyin.com/user/MS4wLjABAAAA-reopen",
      scanned_total: 739,
      already_collected: 571,
      new: 3,
      queue: 3,
      backend_captured: 571,
      backend_ready: 571,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      backend_captured_aweme_ids: [],
      applied_at: at
    }
  }, at).state;
  assert.equal(poisoned.post_scan_counter_snapshot?.new, 4, "reopen restores snapshot new count");
  assert.equal(harvestQueueActionableCount(poisoned), 1);
}

console.info("hybridUncollectableAutoSkip.test.ts: all assertions passed");
