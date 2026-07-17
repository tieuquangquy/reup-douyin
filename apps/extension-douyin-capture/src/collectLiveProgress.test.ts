import assert from "node:assert/strict";

import { resolveHybridProfileCollectRemaining } from "./wholeProfileHarvest/controller.js";
import { buildCollectLiveProgressPresentation, computeProfileCollectPercent, resolveHybridProfileCapturedNumerator, shouldShowCollectBatchCard } from "./wholeProfileHarvest/collectLiveProgress.js";
import { applyCollectDisplaySmoothing, buildSmoothedCollectViewModelFromSession, resetCollectDisplaySmoothing, tickCollectDisplaySession } from "./wholeProfileHarvest/collectDisplaySmoothing.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { getScannerControlPanelViewModel, isCollectJobVisiblyLive } from "./wholeProfileHarvest/viewModel.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

const at = new Date().toISOString();

function scannedProfileState(queueSize = 10): WholeProfileHarvestState {
  const base = createWholeProfileHarvestIdleState(at);
  const queue = Array.from({ length: queueSize }, (_, index) => ({
    index: index + 1,
    aweme_id: `7000000000000000${String(index).padStart(3, "0")}`,
    capture_status: "new" as const,
    status: "pending" as const,
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: `https://www.douyin.com/video/7000000000000000${String(index).padStart(3, "0")}`,
    profile_card_evidence: {}
  }));
  return applyHybridNetworkCacheModeFlagToState({
    ...base,
    status: "verified",
    profile_url: "https://www.douyin.com/user/test-profile",
    classification: { ...base.classification, status: "success", sec_uid: "test-profile", total_candidates: queueSize },
    profile_scan: { ...base.profile_scan, status: "success", accepted_target_count: queueSize },
    scan_job: { ...base.scan_job, status: "completed", total_persisted: queueSize, expected_count: queueSize, has_more_state: false },
    verify: { ...base.verify, status: "success", accepted_target_count: queueSize },
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "success", started_at: at, updated_at: at, completed_at: at, last_error: null }
    },
    harvest: { ...base.harvest, pending: queueSize, queue },
    post_scan_counter_snapshot: {
      status: "applied",
      scanned_total: queueSize,
      already_collected: 0,
      new: queueSize,
      queue: queueSize,
      applied_at: at
    }
  }, true);
}

function liveCollectState(
  queueSize: number,
  patch: Partial<WholeProfileHarvestState["collect_job"]> & { workflowCollectionStatus?: WholeProfileHarvestState["workflow"]["collection"]["status"] }
): WholeProfileHarvestState {
  const { workflowCollectionStatus = "running", ...collectPatch } = patch;
  const base = scannedProfileState(queueSize);
  return {
    ...base,
    status: "harvesting",
    workflow: {
      ...base.workflow,
      active_task: "collect_videos",
      action_lock: "collect_videos",
      collection: {
        ...base.workflow.collection,
        status: workflowCollectionStatus,
        updated_at: at
      }
    },
    harvest: {
      ...base.harvest,
      status: "running",
      updated_at: at
    },
    collect_job: {
      ...base.collect_job,
      job_id: "collect-live-test",
      state: "running",
      selected_count: queueSize,
      runner_ack_at: at,
      heartbeat_at: at,
      updated_at: at,
      ...collectPatch
    }
  };
}

// --- Phase labels ---
{
  const preparing = liveCollectState(139, {
    current_step: "starting",
    attempted_count: 0,
    succeeded_count: 0,
    skipped_count: 0
  });
  const prepPresentation = buildCollectLiveProgressPresentation(preparing);
  assert.ok(prepPresentation);
  assert.equal(prepPresentation.phase, "preparing");
  assert.equal(prepPresentation.headerLabel, "Preparing…");
  assert.equal(prepPresentation.profileIndeterminate, true);
}

{
  const checking = liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 25,
    succeeded_count: 20,
    skipped_count: 5,
    selected_count: 139
  });
  checking.debug = {
    ...checking.debug,
    last_response_summary: {
      ...(checking.debug.last_response_summary && typeof checking.debug.last_response_summary === "object"
        ? checking.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_loop_index: 25
    }
  };
  const checkPresentation = buildCollectLiveProgressPresentation(checking);
  assert.ok(checkPresentation);
  assert.equal(checkPresentation.phase, "collecting");
  assert.equal(checkPresentation.headerLabel, "Collecting 20 / 139");
  assert.equal(checkPresentation.showBatchCard, false);
}

{
  const saving = liveCollectState(139, {
    current_step: "hybrid_loop_flushing",
    attempted_count: 50,
    succeeded_count: 45,
    skipped_count: 5,
    selected_count: 139
  });
  const savePresentation = buildCollectLiveProgressPresentation(saving);
  assert.ok(savePresentation);
  assert.equal(savePresentation.phase, "collecting");
  assert.equal(savePresentation.headerLabel, "Collecting 45 / 139");
  assert.equal(savePresentation.tiles.alreadyCollectedCount, 45);
}

// --- Batch card hidden for full-profile hybrid ---
{
  const state = liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 10,
    succeeded_count: 8,
    skipped_count: 2,
    selected_count: 139,
    batch_limit: 139
  });
  assert.equal(shouldShowCollectBatchCard(state, 139, 139), false);
  const partial = liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 3,
    succeeded_count: 2,
    skipped_count: 1,
    selected_count: 10,
    batch_limit: 10
  });
  assert.equal(shouldShowCollectBatchCard(partial, 139, 10), false, "hybrid mode never shows batch card");
}

// --- Tile invariant: already + new (+ skipped) ≈ total ---
{
  const state = liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 40,
    succeeded_count: 35,
    skipped_count: 5,
    selected_count: 139
  });
  const presentation = buildCollectLiveProgressPresentation(state);
  assert.ok(presentation);
  const tileSum = presentation.tiles.alreadyCollectedCount + presentation.tiles.newCount + presentation.skippedCount;
  assert.equal(tileSum, presentation.profileTotal);
}

// --- View model exposes three-phase collect progress ---
{
  const state = liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 15,
    succeeded_count: 12,
    skipped_count: 3,
    selected_count: 139
  });
  const vm = getScannerControlPanelViewModel(state, { app_backend_logged_in: true });
  assert.equal(vm.collectProgress?.active, true);
  assert.equal(vm.collectProgress?.phase, "collecting");
  assert.equal(vm.collectProgress?.showBatchCard, false);
}

// --- Display smoothing is monotonic ---
{
  resetCollectDisplaySmoothing();
  const baseVm = getScannerControlPanelViewModel(liveCollectState(139, {
    current_step: "hybrid_loop_collecting",
    attempted_count: 10,
    succeeded_count: 8,
    skipped_count: 2,
    selected_count: 139
  }), { app_backend_logged_in: true });
  const first = applyCollectDisplaySmoothing(baseVm, "collect-live-test");
  const bumped = {
    ...baseVm,
    collectProgress: baseVm.collectProgress
      ? {
        ...baseVm.collectProgress,
        profileTargetNumerator: 20,
        profileAlready: 20,
        profilePercent: Math.round((20 / 139) * 100)
      }
      : null
  };
  const second = applyCollectDisplaySmoothing(bumped, "collect-live-test");
  assert.ok((second.collectProgress?.profileAlready ?? 0) >= (first.collectProgress?.profileAlready ?? 0));
  resetCollectDisplaySmoothing();
}

{
  const batch2 = applyHybridNetworkCacheModeFlagToState(liveCollectState(503, {
    state: "running",
    current_step: "queue_filtering",
    attempted_count: 86,
    succeeded_count: 0,
    skipped_count: 0,
    selected_count: 500,
    runtime_generation: 4
  }), true);
  batch2.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch2.profile_url ?? "profile",
    scanned_total: 1003,
    already_collected: 500,
    new: 503,
    queue: 503,
    backend_captured: 500,
    backend_ready: 500,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  batch2.debug = {
    ...batch2.debug,
    last_response_summary: {
      ...(batch2.debug.last_response_summary && typeof batch2.debug.last_response_summary === "object"
        ? batch2.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_batch_prior_already: 500
    }
  };
  const presentation = buildCollectLiveProgressPresentation(batch2);
  assert.ok(presentation);
  assert.equal(presentation.phase, "collecting");
  assert.equal(presentation.headerLabel, "Collecting 500 / 1003");
}

{
  resetCollectDisplaySmoothing();
  const baseVm = getScannerControlPanelViewModel(liveCollectState(1003, {
    job_id: "same-job",
    runtime_generation: 2,
    current_step: "hybrid_loop_collecting",
    attempted_count: 500,
    succeeded_count: 500,
    selected_count: 500
  }), { app_backend_logged_in: true });
  baseVm.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: "profile",
    scanned_total: 1003,
    already_collected: 500,
    new: 503,
    queue: 503,
    backend_captured: 500,
    backend_ready: 500,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  applyCollectDisplaySmoothing(baseVm, "same-job:2");
  for (let i = 0; i < 600; i += 1) tickCollectDisplaySession();
  const batch2Vm = getScannerControlPanelViewModel({
    ...liveCollectState(503, {
      job_id: "same-job",
      runtime_generation: 3,
      current_step: "hybrid_loop_collecting",
      attempted_count: 50,
      succeeded_count: 0,
      selected_count: 500
    }),
    post_scan_counter_snapshot: baseVm.post_scan_counter_snapshot
  }, { app_backend_logged_in: true });
  const smoothed = applyCollectDisplaySmoothing(batch2Vm, "same-job:3");
  assert.ok((smoothed.collectProgress?.profileAlready ?? 0) >= 500);
  assert.ok((smoothed.collectProgress?.profileAlready ?? 0) < 600);
  resetCollectDisplaySmoothing();
}

// --- Manual hybrid batch must stop live progress at the batch ceiling ---
{
  resetCollectDisplaySmoothing();
  const vm = getScannerControlPanelViewModel(liveCollectState(1003, {
    job_id: "batch-cap-job",
    runtime_generation: 2,
    current_step: "hybrid_loop_collecting",
    attempted_count: 900,
    succeeded_count: 500,
    selected_count: 500
  }), { app_backend_logged_in: true });
  applyCollectDisplaySmoothing(vm, "batch-cap-job:2");
  for (let i = 0; i < 800; i += 1) tickCollectDisplaySession();
  const capped = buildSmoothedCollectViewModelFromSession();
  assert.ok(capped?.collectProgress != null);
  assert.equal(capped?.collectProgress?.profileAlready, 500);
  resetCollectDisplaySmoothing();
}

// --- Display smoothing must never exceed profile total (retry accumulation) ---
{
  resetCollectDisplaySmoothing();
  const inflatedVm = getScannerControlPanelViewModel(liveCollectState(1003, {
    job_id: "cap-job",
    runtime_generation: 9,
    current_step: "hybrid_loop_collecting",
    attempted_count: 2000,
    succeeded_count: 2000,
    selected_count: 1003
  }), { app_backend_logged_in: true });
  const smoothed = applyCollectDisplaySmoothing(inflatedVm, "cap-job:9");
  for (let i = 0; i < 1200; i += 1) tickCollectDisplaySession();
  const capped = buildSmoothedCollectViewModelFromSession();
  assert.ok(capped != null);
  assert.ok((capped?.collectProgress?.profileAlready ?? 0) <= 1003);
  assert.equal(capped?.collectProgress?.profileAlready, 1003);
  resetCollectDisplaySmoothing();
}

// --- Profile percent must not round up to 100% before profile is complete ---
{
  assert.equal(computeProfileCollectPercent(1000, 1003), 99);
  assert.equal(computeProfileCollectPercent(1003, 1003), 100);
}

// --- Applied snapshot is authoritative over stale local queue size ---
{
  const state = applyHybridNetworkCacheModeFlagToState(scannedProfileState(500), true);
  state.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: "profile",
    scanned_total: 1003,
    already_collected: 1000,
    new: 3,
    queue: 3,
    backend_captured: 1000,
    backend_ready: 1000,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  assert.equal(resolveHybridProfileCollectRemaining(state, 500), 3);
}

// --- Scan total 738 must win over inbox snapshot scanned_total 735 during live collect ---
{
  const batch2 = applyHybridNetworkCacheModeFlagToState(liveCollectState(238, {
    state: "running",
    current_step: "queue_filtering",
    attempted_count: 120,
    succeeded_count: 0,
    skipped_count: 0,
    selected_count: 238,
    runtime_generation: 2
  }), true);
  batch2.classification = {
    ...batch2.classification,
    status: "success",
    total_candidates: 738
  };
  batch2.profile_scan = {
    ...batch2.profile_scan,
    accepted_target_count: 738
  };
  batch2.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch2.profile_url ?? "profile",
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
  };
  batch2.debug = {
    ...batch2.debug,
    last_response_summary: {
      ...(batch2.debug.last_response_summary && typeof batch2.debug.last_response_summary === "object"
        ? batch2.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_batch_prior_already: 500
    }
  };
  const presentation = buildCollectLiveProgressPresentation(batch2);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.equal(presentation.phase, "collecting");
  assert.equal(presentation.headerLabel, "Collecting 500 / 738");
  assert.notEqual(presentation.headerLabel, "Checking 735 / 735");
}

// Douyin displayed 738 must win when persisted/API only has 735 (user production scenario).
{
  const batch1Collect = applyHybridNetworkCacheModeFlagToState(liveCollectState(685, {
    state: "running",
    current_step: "hybrid_network_cache_flush",
    attempted_count: 50,
    succeeded_count: 50,
    skipped_count: 0,
    selected_count: 685,
    runtime_generation: 1
  }), true);
  batch1Collect.classification = {
    ...batch1Collect.classification,
    status: "success",
    total_candidates: 735
  };
  batch1Collect.profile_scan = {
    ...batch1Collect.profile_scan,
    status: "success",
    accepted_target_count: 735,
    diagnostics: {
      ...(batch1Collect.profile_scan.diagnostics && typeof batch1Collect.profile_scan.diagnostics === "object"
        ? batch1Collect.profile_scan.diagnostics as Record<string, unknown>
        : {}),
      displayed_profile_count: 738,
      expected_profile_video_count: 738,
      scan_profile_total_authority_peak: 738
    }
  };
  batch1Collect.scan_job = {
    ...batch1Collect.scan_job,
    expected_count: 738,
    total_persisted: 735
  };
  batch1Collect.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch1Collect.profile_url ?? "profile",
    scanned_total: 735,
    already_collected: 0,
    new: 735,
    queue: 735,
    backend_captured: 0,
    backend_ready: 0,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  const presentation = buildCollectLiveProgressPresentation(batch1Collect);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.equal(presentation.headerLabel, "Collecting 50 / 738");
  assert.match(presentation.description, /Collecting videos 50 \/ 738/);
}

// --- Batch 2 must not double-count snapshot captured + batch succeeded (738/738 bug) ---
{
  const batch2End = applyHybridNetworkCacheModeFlagToState(liveCollectState(238, {
    state: "running",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 235,
    succeeded_count: 235,
    skipped_count: 0,
    selected_count: 238,
    runtime_generation: 2
  }), true);
  batch2End.classification = { ...batch2End.classification, status: "success", total_candidates: 738 };
  batch2End.profile_scan = { ...batch2End.profile_scan, accepted_target_count: 738 };
  batch2End.scan_job = { ...batch2End.scan_job, expected_count: 738, total_persisted: 735 };
  batch2End.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch2End.profile_url ?? "profile",
    scanned_total: 738,
    already_collected: 735,
    new: 3,
    queue: 3,
    backend_captured: 735,
    backend_ready: 570,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 165,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  batch2End.debug = {
    ...batch2End.debug,
    last_response_summary: {
      ...(batch2End.debug.last_response_summary && typeof batch2End.debug.last_response_summary === "object"
        ? batch2End.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_batch_prior_already: 500,
      hybrid_runner_batch_target_count: 235,
      hybrid_runner_actionable_count: 235
    }
  };
  assert.equal(
    resolveHybridProfileCapturedNumerator(batch2End, 235),
    735,
    "must not add snapshot 735 + succeeded 235"
  );
  const presentation = buildCollectLiveProgressPresentation(batch2End);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.equal(presentation.profileNumerator, 735);
  assert.equal(presentation.headerLabel, "Collecting 735 / 738");
  assert.notEqual(presentation.headerLabel, "Collecting 738 / 738");
  assert.notEqual(computeProfileCollectPercent(presentation.profileNumerator, presentation.profileTotal), 100);
}

// --- Smoothing must not animate past backend captured when batch ceiling is higher ---
{
  resetCollectDisplaySmoothing();
  const baseState = liveCollectState(238, {
    job_id: "double-count-job",
    runtime_generation: 2,
    current_step: "hybrid_loop_hydrating",
    attempted_count: 235,
    succeeded_count: 235,
    selected_count: 238
  });
  const batch2Vm = getScannerControlPanelViewModel(applyHybridNetworkCacheModeFlagToState({
    ...baseState,
    classification: { ...baseState.classification, status: "success", total_candidates: 738 },
    profile_scan: { ...baseState.profile_scan, accepted_target_count: 738 },
    scan_job: { ...baseState.scan_job, expected_count: 738, total_persisted: 735 },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "profile",
      scanned_total: 738,
      already_collected: 735,
      new: 3,
      queue: 3,
      backend_captured: 735,
      backend_ready: 570,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 165,
      need_retry: 0,
      backend_captured_aweme_ids: [],
      applied_at: at
    },
    debug: {
      ...baseState.debug,
      last_response_summary: {
        hybrid_runner_batch_prior_already: 500,
        hybrid_runner_batch_target_count: 235,
        hybrid_runner_actionable_count: 235
      }
    }
  }, true), { app_backend_logged_in: true });
  applyCollectDisplaySmoothing(batch2Vm, "double-count-job:2");
  for (let i = 0; i < 400; i += 1) tickCollectDisplaySession();
  const smoothed = buildSmoothedCollectViewModelFromSession();
  assert.ok(smoothed?.collectProgress);
  assert.equal(smoothed?.collectProgress?.profileAlready, 735);
  assert.equal(smoothed?.headerStatus, "Collecting 735 / 738");
  resetCollectDisplaySmoothing();
}

// --- Terminal frame: batch_prior_already absent, snapshot refreshed → must use stable pre-batch baseline (735 not 738) ---
{
  const terminal = applyHybridNetworkCacheModeFlagToState(liveCollectState(238, {
    state: "running_tab_inactive",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 235,
    succeeded_count: 235,
    selected_count: 238,
    runtime_generation: 2,
    pre_batch_backend_captured: 500
  }), true);
  terminal.classification = { ...terminal.classification, status: "success", total_candidates: 738 };
  terminal.profile_scan = { ...terminal.profile_scan, accepted_target_count: 738 };
  terminal.scan_job = { ...terminal.scan_job, expected_count: 738, total_persisted: 735 };
  // Snapshot already refreshed mid/post-run to include this batch's writes.
  terminal.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: terminal.profile_url ?? "profile",
    scanned_total: 738,
    already_collected: 735,
    new: 3,
    queue: 3,
    backend_captured: 735,
    backend_ready: 570,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 165,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  // No hybrid_runner_batch_prior_already in summary (post-run refresh replaced it).
  terminal.debug = {
    ...terminal.debug,
    last_response_summary: {
      ...(terminal.debug.last_response_summary && typeof terminal.debug.last_response_summary === "object"
        ? terminal.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_actionable_count: 235
    }
  };
  assert.equal(
    resolveHybridProfileCapturedNumerator(terminal, 235),
    735,
    "terminal frame must use stable pre-batch baseline (500) + succeeded, capped by backend"
  );
  const presentation = buildCollectLiveProgressPresentation(terminal);
  assert.ok(presentation);
  assert.equal(presentation.profileTotal, 738);
  assert.equal(presentation.profileNumerator, 735);
  assert.equal(presentation.phase, "collecting");
  assert.equal(presentation.headerLabel, "Collecting 735 / 738");
  assert.notEqual(presentation.headerLabel, "Collecting 738 / 738");
  assert.notEqual(computeProfileCollectPercent(presentation.profileNumerator, presentation.profileTotal), 100);
}

// --- Continuation frame reset (succeeded 0) after backend advanced must stay "collecting", never "preparing" ---
{
  const continuation = applyHybridNetworkCacheModeFlagToState(liveCollectState(238, {
    state: "running_tab_inactive",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 0,
    succeeded_count: 0,
    selected_count: 238,
    runtime_generation: 2,
    pre_batch_backend_captured: 500
  }), true);
  continuation.classification = { ...continuation.classification, status: "success", total_candidates: 738 };
  continuation.profile_scan = { ...continuation.profile_scan, accepted_target_count: 738 };
  continuation.scan_job = { ...continuation.scan_job, expected_count: 738, total_persisted: 735 };
  continuation.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: continuation.profile_url ?? "profile",
    scanned_total: 738,
    already_collected: 735,
    new: 3,
    queue: 3,
    backend_captured: 735,
    backend_ready: 570,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 165,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  const presentation = buildCollectLiveProgressPresentation(continuation);
  assert.ok(presentation);
  assert.equal(presentation.profileIndeterminate, false, "backend advanced past pre-batch baseline → not indeterminate");
  assert.equal(presentation.phase, "collecting");
  assert.equal(presentation.profileNumerator, 735);
  assert.notEqual(presentation.headerLabel, "Preparing…");
}

// --- Smoothing must render "Collecting" (never "Preparing"/"Checking") once progress is visible ---
// Reproduces production ảnh 2: a transient reset frame (succeeded/attempted = 0, snapshot not yet
// refreshed) returns phase "preparing" while the monotonic session still shows ~735 → old code
// rendered "PREPARING" card + "Checking 735/738". Must show "Collecting 735 / 738".
{
  resetCollectDisplaySmoothing();
  const makeBatch2 = (attempted: number, succeeded: number, withSummaryPrior: boolean): WholeProfileHarvestState => {
    const s = applyHybridNetworkCacheModeFlagToState(liveCollectState(238, {
      job_id: "batch2-preparing",
      runtime_generation: 2,
      state: "running",
      current_step: "hybrid_loop_hydrating",
      attempted_count: attempted,
      succeeded_count: succeeded,
      selected_count: 238,
      pre_batch_backend_captured: 500
    }), true);
    s.classification = { ...s.classification, status: "success", total_candidates: 738 };
    s.profile_scan = { ...s.profile_scan, accepted_target_count: 738 };
    s.scan_job = { ...s.scan_job, expected_count: 738, total_persisted: 735 };
    s.post_scan_counter_snapshot = {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: s.profile_url ?? "profile",
      scanned_total: 738,
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
    };
    s.debug = {
      ...s.debug,
      last_response_summary: {
        ...(s.debug.last_response_summary && typeof s.debug.last_response_summary === "object"
          ? s.debug.last_response_summary as Record<string, unknown>
          : {}),
        ...(withSummaryPrior ? { hybrid_runner_batch_prior_already: 500, hybrid_runner_actionable_count: 235 } : {})
      }
    };
    return s;
  };

  // Drive the session up to 735 with a real "collecting" frame.
  const collectingVm = getScannerControlPanelViewModel(makeBatch2(235, 235, true), { app_backend_logged_in: true });
  applyCollectDisplaySmoothing(collectingVm, "batch2-preparing:2");
  for (let i = 0; i < 800; i += 1) tickCollectDisplaySession();
  const drivenUp = buildSmoothedCollectViewModelFromSession();
  assert.equal(drivenUp?.collectProgress?.profileAlready, 735, "collecting frame drives display to 735");

  // Transient reset frame: presentation returns phase "preparing" while session holds 735.
  const preparingState = makeBatch2(0, 0, false);
  const preparingRaw = buildCollectLiveProgressPresentation(preparingState);
  assert.ok(preparingRaw);
  assert.equal(preparingRaw.phase, "preparing", "reset-before-refresh frame is preparing at source");

  const preparingVm = getScannerControlPanelViewModel(preparingState, { app_backend_logged_in: true });
  const smoothed = applyCollectDisplaySmoothing(preparingVm, "batch2-preparing:2");
  assert.equal(smoothed.headerStatus, "Collecting 735 / 738", "must not render Checking/Preparing with a visible numerator");
  assert.notEqual(smoothed.headerStatus, "Checking 735 / 738");
  assert.equal(smoothed.collectProgress?.phase, "collecting", "card tag must be Collecting, not PREPARING");
  assert.equal(smoothed.collectProgress?.profileAlready, 735);
  assert.equal(smoothed.collectProgress?.profileIndeterminate, false);
  resetCollectDisplaySmoothing();
}

// --- Production batch 2: optimistic local snapshot (728) must not beat write_ok (571) during live collect ---
{
  const batch2Live = applyHybridNetworkCacheModeFlagToState(liveCollectState(239, {
    state: "running",
    current_step: "hybrid_loop_collecting",
    attempted_count: 228,
    succeeded_count: 71,
    skipped_count: 165,
    selected_count: 236,
    runtime_generation: 2,
    pre_batch_backend_captured: 500
  }), true);
  batch2Live.classification = { ...batch2Live.classification, status: "success", total_candidates: 739 };
  batch2Live.profile_scan = { ...batch2Live.profile_scan, accepted_target_count: 739 };
  batch2Live.scan_job = { ...batch2Live.scan_job, expected_count: 739, total_persisted: 739 };
  batch2Live.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch2Live.profile_url ?? "profile",
    scanned_total: 739,
    already_collected: 728,
    new: 11,
    queue: 11,
    backend_captured: 728,
    backend_ready: 571,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };
  batch2Live.debug = {
    ...batch2Live.debug,
    last_response_summary: {
      ...(batch2Live.debug.last_response_summary && typeof batch2Live.debug.last_response_summary === "object"
        ? batch2Live.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_batch_prior_already: 500,
      hybrid_runner_actionable_count: 236,
      hybrid_runner_loop_index: 228,
      hybrid_runner_loop_succeeded_so_far: 71,
      hybrid_runner_loop_pending_so_far: 165
    }
  };
  assert.equal(
    resolveHybridProfileCapturedNumerator(batch2Live, 71),
    571,
    "live collect must use pre-batch baseline + write_ok, not inflated local snapshot"
  );
  const presentation = buildCollectLiveProgressPresentation(batch2Live);
  assert.ok(presentation);
  assert.equal(presentation.profileNumerator, 571);
  assert.equal(presentation.headerLabel, "Collecting 571 / 739");
  assert.notEqual(presentation.headerLabel, "Collecting 728 / 739");

  resetCollectDisplaySmoothing();
  const liveVm = getScannerControlPanelViewModel(batch2Live, { app_backend_logged_in: true });
  const smoothed = applyCollectDisplaySmoothing(liveVm, "batch2-live:2");
  for (let i = 0; i < 400; i += 1) tickCollectDisplaySession();
  const smoothedVm = buildSmoothedCollectViewModelFromSession();
  assert.ok(smoothedVm);
  assert.equal(smoothedVm?.emptyState, null, "polish must not inject stale remainder copy during live collect");
  assert.equal(smoothedVm?.counts.alreadyCollectedCount, 571, "tiles must track write_ok, not pre-batch floor");
  assert.equal(smoothedVm?.counts.newCount, 739 - 571 - 165, "remaining tiles use live captured + skipped");
  resetCollectDisplaySmoothing();
}

// --- Batch-2 retry: stale succeeded_count at job start must not flash batch ceiling (739/739) ---
{
  const batch2RetryStart = applyHybridNetworkCacheModeFlagToState(liveCollectState(168, {
    state: "starting",
    current_step: "starting",
    attempted_count: 0,
    succeeded_count: 168,
    selected_count: 168,
    runtime_generation: 4,
    pre_batch_backend_captured: 571
  }), true);
  batch2RetryStart.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: batch2RetryStart.profile_url ?? "profile",
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
  };
  batch2RetryStart.debug = {
    ...batch2RetryStart.debug,
    last_response_summary: {
      ...(batch2RetryStart.debug.last_response_summary && typeof batch2RetryStart.debug.last_response_summary === "object"
        ? batch2RetryStart.debug.last_response_summary as Record<string, unknown>
        : {}),
      hybrid_runner_batch_prior_already: 571,
      hybrid_runner_batch_target_count: 168
    }
  };
  assert.equal(
    resolveHybridProfileCapturedNumerator(batch2RetryStart, 168),
    571,
    "starting frame must ignore stale succeeded_count until runner heartbeat"
  );
  const presentation = buildCollectLiveProgressPresentation(batch2RetryStart);
  assert.ok(presentation);
  assert.equal(presentation.profileNumerator, 571);
  assert.equal(presentation.headerLabel, "Collecting 571 / 739");
  assert.notEqual(presentation.headerLabel, "Collecting 739 / 739");
  resetCollectDisplaySmoothing();
}

// --- Live collect must stay locked through hydration heartbeats (30–45s) and finalize pipeline ---
{
  const hydrationAt = new Date(Date.now() - 35_000).toISOString();
  const hydrating = applyHybridNetworkCacheModeFlagToState(liveCollectState(2403, {
    current_step: "hybrid_loop_hydrating",
    attempted_count: 12,
    succeeded_count: 0,
    skipped_count: 0,
    selected_count: 88,
    heartbeat_at: hydrationAt,
    updated_at: hydrationAt
  }), true);
  hydrating.classification = { ...hydrating.classification, status: "success", total_candidates: 3303 };
  hydrating.profile_scan = {
    ...hydrating.profile_scan,
    status: "success",
    accepted_target_count: 3303,
    diagnostics: {
      queue_total_persisted: 3303,
      scan_profile_total_authority_peak: 3381
    }
  };
  hydrating.scan_job = { ...hydrating.scan_job, status: "completed", total_persisted: 3303, expected_count: 3381 };
  hydrating.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: hydrating.profile_url ?? "profile",
    scanned_total: 3381,
    already_collected: 900,
    new: 2403,
    queue: 2403,
    backend_captured: 900,
    backend_ready: 900,
    backend_dup: 0,
    backend_fail: 0,
    incomplete: 0,
    need_retry: 0,
    backend_captured_aweme_ids: [],
    applied_at: at
  };

  assert.equal(isCollectJobVisiblyLive(hydrating), true, "hydration step must stay visibly live before 45s heartbeat stale");

  const panel = getScannerControlPanelViewModel(hydrating, { app_backend_logged_in: true });
  assert.equal(panel.collectProgress?.active, true);
  assert.equal(panel.primaryAction.enabled, false, "primary action must stay disabled during live collect");
  assert.match(panel.primaryAction.label, /Collecting/);

  const smoothed = applyCollectDisplaySmoothing(panel, "hydration-lock-test");
  assert.equal(smoothed.primaryAction?.enabled, false, "smoothing must not re-enable primary action");
}

console.info("collectLiveProgress.test.ts: all assertions passed");
