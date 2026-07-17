import assert from "node:assert/strict";

import { applyClosedUnreachableTailGapToState, HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON } from "./wholeProfileHarvest/hybridUnreachableTailGap.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";
import { getScannerControlPanelViewModel, isCollectJobVisiblyLive } from "./wholeProfileHarvest/viewModel.js";

const at = "2026-07-10T03:00:00.000Z";
const idle = createWholeProfileHarvestIdleState(at);

/**
 * Stuck 736/739 UI: hybrid mode, empty harvest queue, fossil unreachable stop,
 * and trusted inbox still reporting 3 collectable (phantom gap). Without the
 * readiness-gate guard, finalize overwrites Close with "Collect 3 remaining".
 */
let state = {
  ...idle,
  profile_url: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
  source_url: "https://www.douyin.com/user/MS4wLjABAAAA-tail",
  status: "harvest_ready" as const,
  phase: "batch_safe_mode_completed" as const,
  profile_scan: {
    ...idle.profile_scan,
    status: "success" as const,
    diagnostics: {
      displayed_profile_count: 739,
      queue_total_persisted: 739,
      scan_job_total_persisted: 739,
      profile_already_collected_count: 736
    }
  },
  scan_job: {
    ...idle.scan_job,
    status: "completed" as const,
    total_persisted: 739
  },
  classification: {
    ...idle.classification,
    status: "success" as const
  },
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
  target_status: {
    ...idle.target_status,
    complete: 736
  },
  harvest: {
    ...idle.harvest,
    updated: 736,
    queue: [] as typeof idle.harvest.queue
  },
  debug: {
    ...idle.debug,
    last_response_summary: {
      hybrid_network_cache_mode_flag: "enabled",
      hybrid_network_cache_mode: true,
      hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
      hybrid_tail_gap_live_remaining: 3,
      hybrid_runner_post_run_tile_new: 3,
      hybrid_runner_post_run_tile_already: 736,
      hybrid_unreachable_tail_gap_offer: "yes"
    }
  },
  harvest_options: {
    ...idle.harvest_options,
    mode: "new_and_incomplete" as const
  }
};

state = applyHybridNetworkCacheModeFlagToState(state, true);

const vm = getScannerControlPanelViewModel(state, {
  active_profile_inbox_summary: {
    trusted: true,
    profile_identifier: "test",
    captured_total: 736,
    already_collected: 736,
    ready_count: 736,
    needs_action_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    total_count: 739,
    // Phantom: UI still thinks 3 are collectable even though IDs are unreachable.
    new_count: 3,
    queue_count: 3,
    incomplete_count: 0,
    inbox_needs_review_count: 0,
    need_retry_count: 0
  }
});

assert.equal(
  vm.primaryAction.key,
  "close_unreachable_tail_gap",
  `expected close_unreachable_tail_gap, got ${vm.primaryAction.key} / ${vm.primaryAction.label}`
);
assert.match(vm.primaryAction.label, /Close 3 unreachable/i);
assert.equal(
  /Collect 3 remaining/i.test(vm.primaryAction.label),
  false,
  `primary must not be Collect remaining, got ${vm.primaryAction.label}`
);

{
  const failedCollect = {
    ...state,
    status: "failed" as const,
    phase: "failed" as const,
    collect_job: {
      ...state.collect_job,
      state: "failed" as const,
      last_error: "Could not resolve 3 missing video ID(s)."
    },
    debug: {
      ...state.debug,
      last_response_summary: {
        hybrid_network_cache_mode_flag: "enabled",
        hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
        hybrid_unreachable_tail_gap_offer: "yes",
        hybrid_tail_gap_live_remaining: 3,
        hybrid_runner_post_run_tile_new: 3,
        hybrid_runner_post_run_tile_already: 736,
        hybrid_runner_loop_phase: "pre_skip_failed"
      }
    }
  };
  const vmFailed = getScannerControlPanelViewModel(
    applyHybridNetworkCacheModeFlagToState(failedCollect, true),
    {
      active_profile_inbox_summary: {
        trusted: true,
        profile_identifier: "test",
        captured_total: 736,
        already_collected: 736,
        ready_count: 736,
        needs_action_count: 0,
        duplicate_count: 0,
        failed_count: 0,
        total_count: 739,
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0
      }
    }
  );
  assert.equal(vmFailed.primaryAction.key, "close_unreachable_tail_gap");
  assert.match(vmFailed.primaryAction.label, /Close 3 unreachable/i);
}

{
  const blockedPreflight = {
    ...state,
    debug: {
      ...state.debug,
      last_action_clicked: "start_collecting" as const,
      last_action_result: "blocked" as const,
      last_response_summary: {
        hybrid_network_cache_mode_flag: "enabled",
        hybrid_tail_gap_live_remaining: 3,
        hybrid_runner_post_run_tile_new: 3,
        hybrid_runner_post_run_tile_already: 736,
        start_collecting_blocked_reason: "unreachable_tail_gap_offer_active"
      }
    },
    harvest: {
      ...state.harvest,
      queue: [
        { aweme_id: "phantom-1", status: "pending" as const, capture_status: "new" as const },
        { aweme_id: "phantom-2", status: "pending" as const, capture_status: "new" as const },
        { aweme_id: "phantom-3", status: "pending" as const, capture_status: "new" as const }
      ]
    }
  };
  const vmBlocked = getScannerControlPanelViewModel(
    applyHybridNetworkCacheModeFlagToState(blockedPreflight, true),
    {
      active_profile_inbox_summary: {
        trusted: true,
        profile_identifier: "test",
        captured_total: 736,
        already_collected: 736,
        ready_count: 736,
        needs_action_count: 0,
        duplicate_count: 0,
        failed_count: 0,
        total_count: 739,
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0
      }
    }
  );
  assert.equal(vmBlocked.primaryAction.key, "close_unreachable_tail_gap");
  assert.match(vmBlocked.primaryAction.label, /Close 3 unreachable/i);
  assert.equal(vmBlocked.emptyState, null, "Close card description must not duplicate in emptyState banner");
}

{
  const zombieStartingCollect = {
    ...state,
    status: "harvesting" as const,
    phase: "collecting" as const,
    collect_job: {
      ...state.collect_job,
      state: "starting" as const,
      current_step: "starting",
      attempted_count: 0,
      succeeded_count: 0
    },
    workflow: {
      ...state.workflow,
      collection: {
        ...state.workflow.collection,
        status: "running" as const
      },
      active_task: "collect_videos" as const
    }
  };
  const vmZombie = getScannerControlPanelViewModel(
    applyHybridNetworkCacheModeFlagToState(zombieStartingCollect, true),
    {
      active_profile_inbox_summary: {
        trusted: true,
        profile_identifier: "test",
        captured_total: 736,
        already_collected: 736,
        ready_count: 736,
        needs_action_count: 0,
        duplicate_count: 0,
        failed_count: 0,
        total_count: 739,
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0
      }
    }
  );
  assert.equal(vmZombie.primaryAction.key, "close_unreachable_tail_gap");
  assert.equal(vmZombie.collectProgress?.active, undefined, "unreachable offer must not show Checking progress");
  assert.equal(isCollectJobVisiblyLive(zombieStartingCollect), false, "tail-gap authority must suppress live collect chrome");
}

{
  const closedState = applyClosedUnreachableTailGapToState(
    {
      ...state,
      debug: {
        ...state.debug,
        last_response_summary: {
          hybrid_network_cache_mode_flag: "enabled",
          hybrid_tail_gap_discovery_stop_reason: HYBRID_UNREACHABLE_TAIL_GAP_STOP_REASON,
          hybrid_unreachable_tail_gap_offer: "yes",
          hybrid_tail_gap_live_remaining: 3
        }
      }
    },
    at,
    3
  );
  const vmClosed = getScannerControlPanelViewModel(
    applyHybridNetworkCacheModeFlagToState(closedState, true),
    {
      active_profile_inbox_summary: {
        trusted: true,
        profile_identifier: "test",
        captured_total: 736,
        already_collected: 736,
        ready_count: 736,
        needs_action_count: 0,
        duplicate_count: 0,
        failed_count: 0,
        total_count: 739,
        // Backend inbox API may still report phantom gap after local Close.
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0
      }
    }
  );
  assert.equal(vmClosed.primaryAction.key, "open_capture_inbox");
  assert.match(vmClosed.primaryAction.label, /Open Capture Inbox/i);
  assert.equal(vmClosed.counts.newCount, 0);
  assert.equal(vmClosed.counts.alreadyCollectedCount, 736);
  assert.equal(
    /Collect 3 remaining/i.test(vmClosed.primaryAction.label),
    false,
    "closed gap must not show Collect remaining when inbox still has phantom new_count"
  );
}

console.info("hybridUnreachableTailGapViewModel.test.ts: all assertions passed");
