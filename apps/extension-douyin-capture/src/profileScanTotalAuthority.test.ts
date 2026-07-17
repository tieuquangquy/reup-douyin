import assert from "node:assert/strict";

import { computeProfileCollectPercent } from "./wholeProfileHarvest/collectLiveProgress.js";
import { deriveReconciledPopupMetrics } from "./wholeProfileHarvest/authoritativePopupState.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import { buildCollectLiveProgressPresentation } from "./wholeProfileHarvest/collectLiveProgress.js";

const at = new Date().toISOString();

function profile738Snapshot735State(patch: Partial<WholeProfileHarvestState> = {}): WholeProfileHarvestState {
  const base = createWholeProfileHarvestIdleState(at);
  const state = applyHybridNetworkCacheModeFlagToState({
    ...base,
    status: "verified",
    profile_url: "https://www.douyin.com/user/test-profile-738",
    classification: {
      ...base.classification,
      status: "success",
      sec_uid: "test-profile-738",
      total_candidates: 738
    },
    profile_scan: {
      ...base.profile_scan,
      status: "success",
      accepted_target_count: 738
    },
    scan_job: {
      ...base.scan_job,
      status: "completed",
      total_persisted: 735,
      expected_count: 738,
      has_more_state: false
    },
    verify: {
      ...base.verify,
      status: "success",
      accepted_target_count: 738,
      verified_target_count: 738
    },
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "success", started_at: at, updated_at: at, completed_at: at, last_error: null }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "test-profile-738",
      scanned_total: 735,
      already_collected: 500,
      new: 238,
      queue: 238,
      backend_captured: 500,
      backend_ready: 500,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      backend_captured_aweme_ids: [],
      applied_at: at
    },
    harvest: {
      ...base.harvest,
      pending: 238,
      planned_total: 735,
      queue: Array.from({ length: 238 }, (_, index) => ({
        index: index + 1,
        aweme_id: `7100000000000000${String(index).padStart(3, "0")}`,
        capture_status: "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/7100000000000000${String(index).padStart(3, "0")}`,
        profile_card_evidence: {}
      }))
    },
    ...patch
  }, true);
  return state;
}

// Popup metrics must use scan authority (738), not inbox snapshot scanned_total (735).
{
  const state = profile738Snapshot735State();
  const metrics = deriveReconciledPopupMetrics(state);
  assert.equal(metrics.profile.profile_total_count, 738, "popup profile_total_count must follow scan authority 738");
  assert.equal(metrics.diagnostics.popup_metrics_profile_total_source, "scan_authority");
  assert.equal(metrics.diagnostics.popup_metrics_snapshot_applied, "yes");
}

// Preparing header must show 738 videos in profile, not 735.
{
  const state = profile738Snapshot735State({
    status: "harvesting",
    workflow: {
      ...profile738Snapshot735State().workflow,
      active_task: "collect_videos",
      action_lock: "collect_videos",
      collection: {
        ...profile738Snapshot735State().workflow.collection,
        status: "running",
        updated_at: at
      }
    },
    harvest: {
      ...profile738Snapshot735State().harvest,
      status: "running",
      updated_at: at
    },
    collect_job: {
      ...profile738Snapshot735State().collect_job,
      job_id: "collect-preparing-738",
      state: "running",
      selected_count: 238,
      attempted_count: 0,
      succeeded_count: 0,
      skipped_count: 0,
      current_step: "queue_filtering",
      runner_ack_at: at,
      started_at: at,
      updated_at: at,
      heartbeat_at: at
    }
  });
  const presentation = buildCollectLiveProgressPresentation(state);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.match(presentation.description, /738 videos in profile/);

  const panel = getScannerControlPanelViewModel(state);
  assert.ok(panel.collectProgress?.active);
  assert.equal(panel.collectProgress?.profileTotal, 738);
}

// Batch 2 completion at 735 backend writes must not show 100% when scan total is 738.
{
  const state = profile738Snapshot735State({
    status: "harvesting",
    workflow: {
      ...profile738Snapshot735State().workflow,
      active_task: "collect_videos",
      action_lock: "collect_videos",
      collection: {
        ...profile738Snapshot735State().workflow.collection,
        status: "running",
        updated_at: at
      }
    },
    harvest: {
      ...profile738Snapshot735State().harvest,
      status: "running",
      updated_at: at
    },
    collect_job: {
      ...profile738Snapshot735State().collect_job,
      job_id: "collect-batch2-end",
      state: "running",
      selected_count: 238,
      attempted_count: 235,
      succeeded_count: 235,
      skipped_count: 0,
      current_step: "hybrid_network_cache_flush",
      runner_ack_at: at,
      started_at: at,
      updated_at: at,
      heartbeat_at: at
    },
    debug: {
      ...profile738Snapshot735State().debug,
      last_response_summary: {
        hybrid_runner_batch_prior_already: 500,
        hybrid_runner_loop_index: 235
      }
    }
  });
  const presentation = buildCollectLiveProgressPresentation(state);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.equal(presentation.profileNumerator, 735);
  assert.notEqual(presentation.headerLabel, "Collecting 735 / 735");
  assert.equal(presentation.headerLabel, "Collecting 735 / 738");
  const percent = computeProfileCollectPercent(735, 738);
  assert.ok(percent != null && percent < 100, "735 of 738 must not read as 100% complete");
}

// Idle scan UI must show one profile total (738) in header, tiles, and empty state — not 735 collectable vs 738 ready.
{
  const state = profile738Snapshot735State({
    classification: {
      ...profile738Snapshot735State().classification,
      total_candidates: 0
    },
    profile_scan: {
      ...profile738Snapshot735State().profile_scan,
      diagnostics: {
        displayed_profile_count: 738,
        collectable_count: 735,
        count_semantics_status: "completed_with_displayed_count_mismatch",
        scan_finalization_result: "completed_with_warning"
      }
    },
    scan_job: {
      ...profile738Snapshot735State().scan_job,
      expected_count: null,
      total_persisted: 735
    },
    post_scan_counter_snapshot: {
      ...profile738Snapshot735State().post_scan_counter_snapshot!,
      already_collected: 0,
      new: 735,
      queue: 735,
      backend_captured: 0,
      backend_ready: 0
    },
    harvest: {
      ...profile738Snapshot735State().harvest,
      pending: 735,
      planned_total: 735,
      queue: Array.from({ length: 735 }, (_, index) => ({
        index: index + 1,
        aweme_id: `7200000000000000${String(index).padStart(3, "0")}`,
        capture_status: "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/7200000000000000${String(index).padStart(3, "0")}`,
        profile_card_evidence: {}
      }))
    }
  });
  const panel = getScannerControlPanelViewModel(state, { app_backend_logged_in: true });
  assert.equal(panel.headerStatus, "738 videos", "header must use scan profile total, not collectable-only label");
  assert.equal(panel.counts.newCount, 738, "New tile must match scan authority");
  assert.equal(panel.counts.queueCount, 738, "Queue tile must match scan authority");
  assert.match(panel.emptyState ?? "", /738 videos ready to collect/, "empty state must match header/tiles");
}

console.info("profileScanTotalAuthority.test.ts: all assertions passed");
