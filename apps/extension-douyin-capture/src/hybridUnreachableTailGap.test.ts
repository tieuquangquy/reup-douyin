import assert from "node:assert/strict";

import {
  applyClosedUnreachableTailGapToState,
  applyUnreachableTailGapOfferToState,
  buildHybridUnreachableTailGapUi,
  buildUnreachableTailGapSkipDiscoveryDiagnostics,
  getHybridTailGapPresentation,
  HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME,
  HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
  isHybridTailGapAuthorityLocked,
  isHybridTailGapClosed,
  isHybridTailGapCollectBlocked,
  isHybridUnreachableTailGapOffer,
  isProvenUnreachableTailGapEvidence,
  mergeUnreachableTailGapFossilIntoState,
  resolveUnreachableTailGapRemaining,
  shouldSkipTailGapRediscovery
} from "./wholeProfileHarvest/hybridUnreachableTailGap.js";
import { applyHybridNetworkCacheModeFlagToState, getDouyinScannerWorkflowReadiness } from "./wholeProfileHarvest/readiness.js";
import { expectedCollectContinuationRemaining } from "./wholeProfileHarvest/profileContext.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const at = "2026-07-10T01:40:00.000Z";

{
  const state = {
    ...createWholeProfileHarvestIdleState(at),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    },
    debug: {
      ...createWholeProfileHarvestIdleState(at).debug,
      last_response_summary: {
        hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
        hybrid_tail_gap_live_remaining: 3,
        hybrid_runner_post_run_tile_new: 3,
        hybrid_runner_post_run_tile_already: 736
      }
    }
  };
  assert.equal(resolveUnreachableTailGapRemaining(state), 3);
  assert.equal(isHybridUnreachableTailGapOffer(state), true);
  const ui = buildHybridUnreachableTailGapUi(3);
  assert.equal(ui.buttonLabel, "Close 3 unreachable");

  const closed = applyClosedUnreachableTailGapToState(state, at, 3);
  assert.equal(closed.post_scan_counter_snapshot?.new, 0);
  assert.equal(closed.post_scan_counter_snapshot?.queue, 0);
  assert.equal(closed.post_scan_counter_snapshot?.already_collected, 736);
  assert.equal(closed.post_scan_counter_snapshot?.scanned_total, 736);
  assert.equal(isHybridUnreachableTailGapOffer(closed), false);
  const summary = closed.debug.last_response_summary as Record<string, unknown>;
  assert.equal(summary.hybrid_unreachable_tail_gap_closed, "yes");
  assert.equal(summary.hybrid_runner_post_run_tile_new, 0);
}

{
  const idle = createWholeProfileHarvestIdleState(at);
  assert.equal(isHybridUnreachableTailGapOffer(idle), false);
}

{
  const base = {
    ...createWholeProfileHarvestIdleState(at),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    }
  };
  assert.equal(isHybridUnreachableTailGapOffer(base), false);
  const merged = mergeUnreachableTailGapFossilIntoState(base, {
    hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
    hybrid_tail_gap_live_remaining: 3
  });
  assert.equal(isHybridUnreachableTailGapOffer(merged), true);
}

{
  const idle = createWholeProfileHarvestIdleState(at);
  assert.equal(
    shouldSkipTailGapRediscovery({
      state: idle,
      remaining: 3,
      fossil: { hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON }
    }),
    true
  );
  assert.equal(
    shouldSkipTailGapRediscovery({
      state: idle,
      remaining: 3,
      fossil: { hybrid_tail_gap_discovery_stop_reason: "ids_resolved" }
    }),
    false
  );
  // Compound fossil from operator log (has_more_false + DOM already captured).
  assert.equal(
    shouldSkipTailGapRediscovery({
      state: idle,
      remaining: 3,
      fossil: {
        hybrid_tail_gap_discovery_stop_reason: "has_more_false",
        hybrid_tail_gap_tail_reconcile_stop_reason: "all_tail_reconcile_candidates_already_captured",
        hybrid_tail_gap_discovery_found: 0,
        hybrid_tail_gap_live_remaining: 3
      }
    }),
    true,
    "has_more_false + DOM already-captured must skip rediscovery"
  );
  const skip = buildUnreachableTailGapSkipDiscoveryDiagnostics(3);
  assert.equal(skip.hybrid_tail_gap_rediscovery_skipped, "yes");
  assert.equal(skip.hybrid_tail_gap_discovery_stop_reason, HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON);
  assert.equal(skip.hybrid_unreachable_tail_gap_offer, "yes");
  assert.equal(skip.hybrid_tail_gap_live_remaining, 3);
}

{
  const base = {
    ...createWholeProfileHarvestIdleState(at),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    }
  };
  const merged = mergeUnreachableTailGapFossilIntoState(base, {
    hybrid_tail_gap_discovery_stop_reason: "has_more_false",
    hybrid_tail_gap_tail_reconcile_stop_reason: "all_tail_reconcile_candidates_already_captured",
    hybrid_tail_gap_discovery_found: 0,
    hybrid_tail_gap_live_remaining: 3
  });
  assert.equal(isHybridUnreachableTailGapOffer(merged), true, "compound fossil must offer Close without another Collect");
  const summary = merged.debug.last_response_summary as Record<string, unknown>;
  assert.equal(summary.hybrid_tail_gap_discovery_stop_reason, HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON);
}

{
  const idle = createWholeProfileHarvestIdleState(at);
  assert.equal(
    isProvenUnreachableTailGapEvidence({
      hybrid_unreachable_tail_gap_offer: "yes",
      hybrid_tail_gap_live_remaining: 3
    }),
    true,
    "offer flag alone must count as proven unreachable"
  );
  assert.equal(
    isHybridUnreachableTailGapOffer({
      ...idle,
      post_scan_counter_snapshot: {
        status: "applied" as const,
        source: "backend_capture_inbox_profile_summary" as const,
        profile_identifier: "test",
        scanned_total: 739,
        backend_captured_aweme_ids: [] as string[],
        backend_captured: 736,
        already_collected: 736,
        backend_ready: 736,
        backend_dup: 0,
        backend_fail: 0,
        incomplete: 0,
        need_retry: 0,
        new: 3,
        queue: 3,
        applied_at: at
      },
      debug: {
        ...idle.debug,
        last_response_summary: {
          hybrid_unreachable_tail_gap_offer: "yes",
          hybrid_tail_gap_live_remaining: 3
        }
      }
    }),
    true
  );
}

{
  const idle = createWholeProfileHarvestIdleState(at);
  const withPhantomQueue = {
    ...idle,
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    },
    harvest: {
      ...idle.harvest,
      queue: [
        { aweme_id: "phantom-1", status: "pending" as const, capture_status: "new" as const },
        { aweme_id: "phantom-2", status: "pending" as const, capture_status: "new" as const },
        { aweme_id: "phantom-3", status: "pending" as const, capture_status: "new" as const }
      ]
    },
    debug: {
      ...idle.debug,
      last_response_summary: {
        hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
        hybrid_tail_gap_live_remaining: 3,
        hybrid_unreachable_tail_gap_offer: "yes"
      }
    }
  };
  assert.equal(
    isHybridUnreachableTailGapOffer(withPhantomQueue),
    true,
    "proven unreachable must win over phantom actionable queue rows"
  );
}

{
  const phantomGapSnapshot = {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test",
    scanned_total: 739,
    backend_captured_aweme_ids: [] as string[],
    backend_captured: 736,
    already_collected: 736,
    backend_ready: 736,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    new: 3,
    queue: 3,
    applied_at: at
  };
  const idle = createWholeProfileHarvestIdleState(at);
  const durableOnly = {
    ...idle,
    hybrid_tail_gap_presentation: "unreachable_offer" as const,
    post_scan_counter_snapshot: phantomGapSnapshot,
    harvest: { ...idle.harvest, queue: [] }
  };
  assert.equal(isHybridUnreachableTailGapOffer(durableOnly), true, "durable presentation must survive without summary offer flag");
  assert.equal(getHybridTailGapPresentation(durableOnly), "unreachable_offer");

  const offered = applyUnreachableTailGapOfferToState({
    ...createWholeProfileHarvestIdleState(at),
    post_scan_counter_snapshot: phantomGapSnapshot,
    debug: {
      ...createWholeProfileHarvestIdleState(at).debug,
      last_response_summary: {
        hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
        hybrid_tail_gap_live_remaining: 3
      }
    }
  }, at);
  assert.equal(offered.hybrid_tail_gap_presentation, "unreachable_offer");
  const summary = offered.debug.last_response_summary as Record<string, unknown>;
  assert.equal(summary.hybrid_unreachable_tail_gap_offer, "yes");

  const hybridReady = applyHybridNetworkCacheModeFlagToState({
    ...offered,
    profile_url: "https://www.douyin.com/user/test",
    profile_scan: { ...createWholeProfileHarvestIdleState(at).profile_scan, status: "success" as const },
    classification: { ...createWholeProfileHarvestIdleState(at).classification, status: "success" as const },
    scan_job: { ...createWholeProfileHarvestIdleState(at).scan_job, status: "completed" as const },
    calibration: {
      ...createWholeProfileHarvestIdleState(at).calibration,
      status: "calibrated" as const,
      ready: true,
      point_count: 4,
      points: { like: { x: 1, y: 1 }, comment: { x: 2, y: 2 }, favorite: { x: 3, y: 3 }, share: { x: 4, y: 4 } }
    },
    harvest: { ...offered.harvest, queue: [] }
  }, true);
  assert.equal(getDouyinScannerWorkflowReadiness(hybridReady).nextActionKey, "close_unreachable_tail_gap");
}

{
  const closed = applyClosedUnreachableTailGapToState({
    ...createWholeProfileHarvestIdleState(at),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    }
  }, at, 3);
  assert.equal(isHybridTailGapClosed(closed), true);
  assert.equal(closed.hybrid_tail_gap_presentation, "closed");
  const summary = closed.debug.last_response_summary as Record<string, unknown>;
  assert.equal(summary.hybrid_runner_probe_step, HYBRID_UNREACHABLE_TAIL_GAP_CLOSED_OUTCOME);
  assert.equal(summary.hybrid_runner_loop_phase, "closed_unreachable");
  assert.equal(
    expectedCollectContinuationRemaining(closed, {
      active_profile_inbox_summary: {
        trusted: true,
        total_count: 739,
        already_collected: 736,
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0,
        captured_total: 736
      }
    }),
    0,
    "closed tail gap must ignore phantom inbox new_count"
  );
}

{
  const inconsistent = {
    ...createWholeProfileHarvestIdleState(at),
    hybrid_tail_gap_presentation: "closed" as const,
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [] as string[],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    },
    debug: {
      ...createWholeProfileHarvestIdleState(at).debug,
      last_response_summary: {
        hybrid_runner_loop_phase: "closed_unreachable",
        hybrid_runner_post_run_tile_new: 3,
        hybrid_runner_post_run_tile_already: 736
      }
    }
  };
  assert.equal(isHybridTailGapClosed(inconsistent), false, "tile_new>0 must not show closed-complete UI");
  assert.equal(
    isHybridTailGapCollectBlocked(inconsistent, {
      hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
      hybrid_tail_gap_tail_reconcile_stop_reason: "all_tail_reconcile_candidates_already_captured",
      hybrid_tail_gap_discovery_found: 0,
      hybrid_tail_gap_live_remaining: 3
    }),
    true,
    "proven unreachable fossil must block collect even when loop_phase says closed_unreachable"
  );
  assert.equal(isHybridTailGapAuthorityLocked(inconsistent), false);
}

console.info("hybridUnreachableTailGap.test.ts: all assertions passed");
