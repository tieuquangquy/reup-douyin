/**
 * Operator regression matrix — automated coverage for high-risk extension flows.
 * Each block maps to a manual QA scenario; extend when a production bug is found.
 */
import assert from "node:assert/strict";

import { parseAppBackendAuthStatus } from "./wholeProfileHarvest/appBackendAuth.js";
import { hybridCollectionDoneSignalProvesTerminal } from "./wholeProfileHarvest/authoritativePopupState.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { isCollectJobVisiblyLive } from "./wholeProfileHarvest/viewModel.js";
import { expectedCollectContinuationRemaining, hybridProfileCollectFullyComplete } from "./wholeProfileHarvest/profileContext.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import {
  clearStaleLocalCollectedQueueItems,
  collectQueueReadinessBlockReason,
  evaluateCollectJobWriteGuard,
  getFirstPendingTargetForOneItemCollect,
  needsHarvestQueueRepopulateForCollect,
  pauseWholeProfileHarvestOnAuthLoss,
  reconcileHarvestStateWhenBackendEmpty,
  reconcileStateIfBackendEmpty,
  repairHarvestQueueForCollectIfNeeded,
  ensureHarvestQueueReadyForStartCollecting,
  formatStartCollectingSessionBlockReason,
  shouldRunHybridUnattendedCollectAll,
  primeHybridCollectContinuationRestart,
  persistentCollectJobTerminalReached,
  finalizeStartCollectingBlockedState,
  resolveHybridNetworkCacheRunnerEnabled,
  writeHybridLoopHeartbeat,
  type WholeProfileHarvestRuntime
} from "./wholeProfileHarvest/controller.js";
import {
  createProfileTargetRepository,
  InMemoryProfileTargetRepository,
  profileIdentifierFromUrl,
  setProfileTargetRepositoryFactoryForTests
} from "./wholeProfileHarvest/profileTargetRepository.js";
import { detectProfileContextMismatch, emptyTrustedInboxSummary, expectedCollectContinuationRemaining, parseActiveProfileInboxSummary } from "./wholeProfileHarvest/profileContext.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { wholeProfileHarvestError } from "./wholeProfileHarvest/errors.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import {
  createWholeProfileHarvestIdleState,
  WHOLE_PROFILE_HARVEST_STATE_KEY,
  type WholeProfileHarvestState
} from "./wholeProfileHarvest/state.js";

class MemoryStorage {
  values: Record<string, unknown> = {};
  async get(key: string | string[] | Record<string, unknown> | null): Promise<Record<string, unknown>> {
    if (typeof key === "string") return { [key]: this.values[key] };
    if (Array.isArray(key)) {
      const out: Record<string, unknown> = {};
      for (const entry of key) out[entry] = this.values[entry];
      return out;
    }
    return { ...this.values };
  }
  async set(items: Record<string, unknown>): Promise<void> {
    Object.assign(this.values, items);
  }
}

const at = "2026-07-05T17:00:00.000Z";

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
    harvest: { ...base.harvest, pending: queueSize, queue }
  }, true);
}

// --- Auth matrix ---
{
  assert.equal(parseAppBackendAuthStatus({ apiAuthToken: "t", apiAuthRequired: false }).loggedIn, true);
  assert.equal(parseAppBackendAuthStatus({ apiAuthToken: "", apiAuthRequired: false }).loggedIn, false);
  assert.equal(parseAppBackendAuthStatus({ apiAuthToken: "t", apiAuthRequired: true }).loggedIn, false);
}

// --- Logout mid-collect: background must pause runner + terminalize collect_job ---
{
  const storage = new MemoryStorage();
  storage.values.apiAuthToken = "";
  storage.values.apiAuthRequired = true;
  storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
    ...scannedProfileState(5),
    status: "harvesting",
    workflow: {
      ...scannedProfileState(5).workflow,
      collection: { ...scannedProfileState(5).workflow.collection, status: "running", updated_at: at }
    },
    collect_job: {
      ...scannedProfileState(5).collect_job,
      job_id: "job-logout-mid-collect",
      state: "running",
      current_step: "hybrid_loop_hydrating",
      attempted_count: 3,
      selected_count: 5,
      batch_limit: 5
    },
    harvest: { ...scannedProfileState(5).harvest, status: "running", updated_at: at }
  };
  const runtime = { storage, now: () => at } as unknown as WholeProfileHarvestRuntime;
  const paused = await pauseWholeProfileHarvestOnAuthLoss(runtime);
  assert.ok(paused);
  assert.equal(paused.harvest.paused_reason, "backend_auth_required");
  assert.equal(paused.collect_job.state, "stuck");
  const stored = storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState;
  assert.equal(stored.harvest.paused_reason, "backend_auth_required");
}

// --- Heartbeat must not revive running UI after auth pause ---
{
  const storage = new MemoryStorage();
  storage.values.apiAuthToken = "";
  storage.values.apiAuthRequired = true;
  const pausedState: WholeProfileHarvestState = {
    ...scannedProfileState(5),
    status: "paused",
    harvest: {
      ...scannedProfileState(5).harvest,
      status: "paused",
      paused_reason: "backend_auth_required",
      resume_available: true,
      updated_at: at
    },
    collect_job: {
      ...scannedProfileState(5).collect_job,
      job_id: "job-heartbeat-guard",
      state: "stuck",
      runtime_generation: 2,
      current_step: "auth_pause",
      attempted_count: 5,
      selected_count: 5,
      batch_limit: 5,
      updated_at: at,
      heartbeat_at: at
    }
  };
  storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = pausedState;
  const zombieHeartbeat: WholeProfileHarvestState = {
    ...pausedState,
    collect_job: {
      ...pausedState.collect_job,
      state: "running",
      current_step: "hybrid_loop_hydrating",
      attempted_count: 3,
      heartbeat_at: at,
      updated_at: at
    },
    updated_at: at
  };
  const afterHeartbeat = await writeHybridLoopHeartbeat(storage, zombieHeartbeat);
  assert.equal(afterHeartbeat.collect_job.state, "stuck", "heartbeat must not downgrade auth-paused collect_job");
  assert.equal(afterHeartbeat.harvest.paused_reason, "backend_auth_required");
}

// --- Terminal guard: stuck job cannot revert to running at same generation ---
{
  const stored = scannedProfileState(3);
  const stuck: WholeProfileHarvestState = {
    ...stored,
    collect_job: {
      ...stored.collect_job,
      job_id: "job-terminal-guard",
      state: "stuck",
      runtime_generation: 4
    }
  };
  const zombie: WholeProfileHarvestState = {
    ...stored,
    collect_job: {
      ...stored.collect_job,
      job_id: "job-terminal-guard",
      state: "running",
      runtime_generation: 4
    }
  };
  const decision = evaluateCollectJobWriteGuard(stuck, zombie, null);
  assert.equal(decision.reject, true);
  assert.equal(decision.reason, "terminal_collect_job_revert");
}

// --- Profile switch: stale collect progress must not show on wrong tab ---
{
  const state = {
    ...scannedProfileState(20),
    profile_url: "https://www.douyin.com/user/profile-a",
    collect_job: {
      ...scannedProfileState(20).collect_job,
      state: "running" as const,
      current_step: "hybrid_loop_hydrating",
      attempted_count: 10,
      selected_count: 20,
      batch_limit: 20
    }
  };
  const mismatch = detectProfileContextMismatch(state, "https://www.douyin.com/user/profile-b");
  assert.equal(mismatch, true);
  const vm = getScannerControlPanelViewModel(state, {
    app_backend_logged_in: true,
    active_tab_url: "https://www.douyin.com/user/profile-b"
  });
  assert.notEqual(vm.primaryAction.key, "pause", "wrong profile tab must not show Collecting pause state from another profile");
  assert.equal(vm.counts.newCount, 0, "profile mismatch must not show stale New count from stored profile");
  assert.equal(vm.counts.queueCount, 0, "profile mismatch must not show stale Queue count from stored profile");
  assert.equal(vm.primaryAction.key, "scan_profile");
  assert.equal(vm.headerStatus, "Not scanned", "profile mismatch must show fresh scan state, not Scan required");
  assert.notEqual(vm.headerStatus, "Scan required");
  assert.equal(vm.emptyState, null, "profile mismatch must not duplicate scan-failure warning banner");
  assert.match(vm.primaryAction.description, /Different creator|Discover videos/i);
}

// --- Failed scan on new profile must not show stale persisted counters from previous profile ---
{
  const staleSucceeded = scannedProfileState(191);
  const failedNewProfileScan: WholeProfileHarvestState = {
    ...staleSucceeded,
    profile_url: "https://www.douyin.com/user/new-profile-b",
    source_url: "https://www.douyin.com/user/new-profile-b",
    workflow: {
      ...staleSucceeded.workflow,
      scan: { status: "failed", started_at: at, updated_at: at, completed_at: at, last_error: "active_profile_post_response_status_non_zero_terminal" },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...staleSucceeded.scan_job,
      scan_job_id: "scan_profile_22C11B_new_profile_failed",
      status: "failed",
      total_persisted: 0,
      expected_count: 191,
      last_status_code: 5,
      last_error: "active_profile_post_response_status_non_zero_terminal"
    },
    profile_scan: {
      ...staleSucceeded.profile_scan,
      status: "failed",
      targets: [],
      target_details: [],
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 191,
        scan_job_total_persisted: 191,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_template_found: "no",
        scan_finalization_result: "failed"
      }
    },
    verify: {
      ...staleSucceeded.verify,
      status: "failed",
      targets: [],
      target_details: [],
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 191,
        scan_job_total_persisted: 191,
        active_profile_post_fetch_response_status_code: 5,
        scan_finalization_result: "failed"
      }
    },
    harvest: {
      ...staleSucceeded.harvest,
      queue: [],
      queue_preview: [],
      pending: 0,
      planned_total: 0
    },
    classification: { ...staleSucceeded.classification, status: "idle", sec_uid: null, total_candidates: 0, counts: { complete: 0, incomplete: 0, failed: 0, skipped: 0 } },
    post_scan_counter_snapshot: null
  };
  const vm = getScannerControlPanelViewModel(failedNewProfileScan, {
    app_backend_logged_in: true,
    active_tab_url: "https://www.douyin.com/user/new-profile-b"
  });
  assert.equal(vm.primaryAction.key, "scan_profile");
  assert.equal(vm.primaryAction.disabledReason, null, "Scan Profile must stay clickable without Action blocked banner");
  assert.match(vm.primaryAction.description, /didn't finish|Previous scan had an issue/i);
  assert.equal(vm.headerStatus, "Scan required", "same-profile failed scan must keep Scan required header");
  assert.equal(vm.emptyState, null, "scan failure hint belongs in primary description only");
  assert.equal(vm.counts.newCount, 0, "failed new-profile scan must not show stale New count from previous profile");
  assert.equal(vm.counts.queueCount, 0, "failed new-profile scan must not show stale Queue count from previous profile");
}

// --- Rescan in flight must show Scanning, not stale Scan required block ---
{
  const failed = scannedProfileState(10);
  const rescanning: WholeProfileHarvestState = {
    ...failed,
    status: "verifying",
    phase: "ensuring_content_script",
    workflow: {
      ...failed.workflow,
      scan: { status: "running", started_at: at, updated_at: at, completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    profile_scan: { ...failed.profile_scan, status: "running", accepted_target_count: 0, targets: [] },
    scan_job: { ...failed.scan_job, status: "running", total_persisted: 0, expected_count: 0, last_status_code: null, last_error: null },
    verify: { ...failed.verify, status: "running", verified_target_count: 0, accepted_target_count: 0 }
  };
  const vm = getScannerControlPanelViewModel(rescanning, { app_backend_logged_in: true });
  assert.equal(vm.scanProgress.active, true, "rescan in flight must activate scan progress");
  assert.notEqual(vm.headerStatus, "Scan required");
  assert.equal(vm.primaryAction.disabledReason, null);
  assert.match(vm.primaryAction.label, /Scanning/i);
}

// --- B5: same-profile rescan must not show stale expected count from another profile session ---
{
  const profileP2 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p2";
  const p2Stored = {
    ...scannedProfileState(111),
    profile_url: profileP2,
    scan_job: {
      ...scannedProfileState(111).scan_job,
      status: "completed" as const,
      expected_count: 111,
      total_persisted: 111,
      profile_identifier: profileIdentifierFromUrl(profileP2)
    },
    layer: { ...scannedProfileState(111).layer, profile_scan_ready: true }
  };
  const staleRescanProgress: WholeProfileHarvestState = {
    ...p2Stored,
    status: "verifying",
    run_id: "scan_profile_22C11B_p2_rescan",
    workflow: {
      ...p2Stored.workflow,
      scan: { status: "running", started_at: at, updated_at: at, completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...p2Stored.scan_job,
      scan_job_id: "scan_profile_22C11B_p2_rescan",
      status: "running",
      expected_count: 140,
      total_persisted: 0
    },
    profile_scan: {
      ...p2Stored.profile_scan,
      status: "running",
      accepted_target_count: 0,
      diagnostics: {
        scan_run_id: "scan_profile_22C11B_p1_old",
        expected_profile_video_count: 140,
        current_run_found_count: 140,
        scan_progress_discovered: 140
      }
    },
    verify: { ...p2Stored.verify, status: "running", verified_target_count: 0 }
  };
  const vm = getScannerControlPanelViewModel(staleRescanProgress, {
    app_backend_logged_in: true,
    active_tab_url: profileP2
  });
  assert.equal(vm.scanProgress.active, true);
  assert.notEqual(vm.scanProgress.expected, 140, "stale P1 expected count must not bleed into P2 rescan");
  assert.notEqual(vm.scanProgress.discovered, 140, "stale P1 discovered count must not bleed into P2 rescan");
}

// --- Profile switch: stale persisted queue total from another profile must not show collect tiles ---
{
  const profileP1 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p1";
  const profileP2 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p2";
  const idle = createWholeProfileHarvestIdleState(at);
  const stalePersistedBleed: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
    ...idle,
    status: "verified",
    profile_url: profileP2,
    classification: {
      ...idle.classification,
      status: "success",
      sec_uid: "profile-p2",
      total_candidates: 111,
      collect_aweme_ids: []
    },
    profile_scan: {
      ...idle.profile_scan,
      status: "success",
      accepted_target_count: 111,
      diagnostics: {
        large_profile_mode: "yes",
        scan_job_total_persisted: 140,
        queue_total_persisted: 140
      }
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed",
      total_persisted: 140,
      expected_count: 111,
      profile_identifier: profileIdentifierFromUrl(profileP1),
      has_more_state: false
    },
    verify: { ...idle.verify, status: "success", accepted_target_count: 111 },
    workflow: {
      ...idle.workflow,
      scan: { ...idle.workflow.scan, status: "success", started_at: at, updated_at: at, completed_at: at, last_error: null }
    },
    harvest: { ...idle.harvest, queue: [], queue_preview: [], pending: 0 },
    post_scan_counter_snapshot: null
  }, true);
  const vmBleed = getScannerControlPanelViewModel(stalePersistedBleed, {
    app_backend_logged_in: true,
    active_tab_url: profileP2
  });
  assert.notEqual(vmBleed.counts.newCount, 140, "stale other-profile persisted total must not paint New tiles");
  assert.notEqual(vmBleed.counts.queueCount, 140, "stale other-profile persisted total must not paint Queue tiles");
}

// --- Active scan must show scan_job counters even when runtime diagnostics channel is missing ---
{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-active-scan-progress";
  const scanRunId = "scan_profile_22C11B_active_progress";
  const activeScan: WholeProfileHarvestState = {
    ...createWholeProfileHarvestIdleState(at),
    status: "verifying",
    phase: "scan_running",
    run_id: scanRunId,
    profile_url: profileUrl,
    workflow: {
      ...createWholeProfileHarvestIdleState(at).workflow,
      scan: { status: "running", started_at: at, updated_at: at, completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...createWholeProfileHarvestIdleState(at).scan_job,
      scan_job_id: scanRunId,
      profile_identifier: profileIdentifierFromUrl(profileUrl),
      status: "running",
      page_count: 4,
      request_count: 5,
      total_persisted: 37,
      expected_count: 140
    },
    profile_scan: {
      ...createWholeProfileHarvestIdleState(at).profile_scan,
      status: "running",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: scanRunId,
        expected_profile_video_count: 140
      }
    },
    debug: {
      ...createWholeProfileHarvestIdleState(at).debug,
      last_response_summary: {
        scan_progress_discovered: 37,
        scan_progress_pages: 4,
        scan_progress_requests: 5
      }
    }
  };
  const vm = getScannerControlPanelViewModel(activeScan, { active_tab_url: profileUrl, app_backend_logged_in: true });
  assert.equal(vm.scanProgress.active, true);
  assert.equal(vm.scanProgress.discovered, 37);
  assert.equal(vm.scanProgress.pagesFetched, 4);
  assert.equal(vm.scanProgress.requestCount, 5);
}

// --- Ghost collect tiles must not show when queue is empty and collect is blocked ---
{
  const profileUrl = "https://www.douyin.com/user/ghost-collect-tiles";
  const ghost: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
    ...scannedProfileState(0),
    profile_url: profileUrl,
    harvest: { ...scannedProfileState(0).harvest, queue: [], pending: 0 },
    post_scan_counter_snapshot: null,
    profile_scan: { ...scannedProfileState(0).profile_scan, status: "success", target_details: [] },
    classification: { ...scannedProfileState(0).classification, collect_aweme_ids: [] },
    scan_job: {
      ...scannedProfileState(0).scan_job,
      status: "completed",
      total_persisted: 140,
      profile_identifier: profileIdentifierFromUrl(profileUrl)
    },
    layer: { ...scannedProfileState(0).layer, profile_scan_ready: true }
  }, true);
  const vm = getScannerControlPanelViewModel(ghost, { active_tab_url: profileUrl, app_backend_logged_in: true });
  assert.notEqual(vm.primaryAction.key, "start_collecting", "empty queue with collect block must reroute away from Start Collecting");
  assert.equal(vm.emptyState, null, "empty queue with collect block must not show No pending video copy");
  assert.equal(vm.counts.newCount, 0, "ghost New tile must be suppressed when queue is empty");
  assert.equal(vm.counts.queueCount, 0, "ghost Queue tile must be suppressed when queue is empty");
}

{
  const staleSucceeded = scannedProfileState(191);
  const failedWithPersistedQueue: WholeProfileHarvestState = {
    ...staleSucceeded,
    profile_url: "https://www.douyin.com/user/new-profile-c",
    source_url: "https://www.douyin.com/user/new-profile-c",
    workflow: {
      ...staleSucceeded.workflow,
      scan: { status: "failed", started_at: at, updated_at: at, completed_at: at, last_error: "active_profile_post_response_status_non_zero_terminal" },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...staleSucceeded.scan_job,
      scan_job_id: "scan_profile_22C11B_rescan_failed",
      status: "failed",
      total_persisted: 191,
      expected_count: 188,
      last_status_code: 5,
      last_error: "active_profile_post_response_status_non_zero_terminal"
    },
    profile_scan: {
      ...staleSucceeded.profile_scan,
      status: "failed",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 188,
        scan_job_total_persisted: 191,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_template_found: "no",
        scan_finalization_result: "failed"
      }
    },
    verify: { ...staleSucceeded.verify, status: "failed", targets: [], target_details: [] },
    harvest: { ...staleSucceeded.harvest, queue: staleSucceeded.harvest.queue.slice(0, 3), pending: 3 },
    classification: { ...staleSucceeded.classification, status: "idle", sec_uid: null, total_candidates: 0, counts: { complete: 0, incomplete: 0, failed: 0, skipped: 0 } },
    post_scan_counter_snapshot: null
  };
  const vmPersisted = getScannerControlPanelViewModel(failedWithPersistedQueue, {
    app_backend_logged_in: true,
    active_tab_url: "https://www.douyin.com/user/new-profile-c"
  });
  assert.equal(vmPersisted.counts.newCount, 0, "failed rescan with stale persisted queue must not show collectable tiles");
  assert.equal(vmPersisted.emptyStateTone, "warning");
  assert.equal(vmPersisted.emptyState, null, "scan failure hint belongs in primary description only");
  assert.match(vmPersisted.primaryAction.description, /didn't finish|Previous scan had an issue/i);
  assert.equal(vmPersisted.primaryAction.disabledReason, null);
  assert.doesNotMatch(vmPersisted.primaryAction.description, /ready to collect/i, "failed scan must not show ready-to-collect copy");
  assert.notEqual(vmPersisted.primaryAction.key, "start_collecting", "failed scan must not offer Start Collecting");
}

// --- Backend wipe: snapshot shows collect work but harvest.queue is empty (phantom 139 ready) ---
{
  const profileUrl = "https://www.douyin.com/user/backend-wipe-phantom-queue";
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  setProfileTargetRepositoryFactoryForTests(() => new InMemoryProfileTargetRepository());
  const repository = createProfileTargetRepository();
  const base = scannedProfileState(5);
  const collectedQueue = base.harvest.queue.map((item, index) => ({
    ...item,
    status: "already_collected" as const,
    capture_status: "complete" as const,
    capture_inbox_item_id: `stale-${index}`
  }));
  await repository.upsertProfileTargets(profileIdentifier, collectedQueue, base.profile_scan.target_details, at);
  const storage = new MemoryStorage();
  const phantom: WholeProfileHarvestState = {
    ...base,
    profile_url: profileUrl,
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_empty_disproves_snapshot",
      profile_identifier: profileIdentifier,
      scanned_total: 5,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 5,
      queue: 5,
      applied_at: at
    },
    harvest: {
      ...base.harvest,
      queue: [],
      queue_preview: [],
      pending: 0
    }
  };
  assert.equal(needsHarvestQueueRepopulateForCollect(phantom), true, "phantom snapshot must be detected");
  const runtime: WholeProfileHarvestRuntime = { storage };
  const repaired = await repairHarvestQueueForCollectIfNeeded(runtime, phantom, at);
  assert.ok(repaired.harvest.queue.length > 0, "repair must repopulate harvest queue from repository");
  assert.equal(
    repaired.harvest.queue.every((item) => item.status === "pending" || item.status === "new"),
    true,
    "repaired queue items must be actionable pending"
  );
  const vm = getScannerControlPanelViewModel(repaired, {
    app_backend_logged_in: true,
    active_tab_url: profileUrl,
    active_profile_inbox_summary: emptyTrustedInboxSummary(profileUrl)
  });
  assert.equal(vm.primaryAction.key, "start_collecting");
  assert.match(vm.emptyState ?? "", /Backend data was cleared/i);
  setProfileTargetRepositoryFactoryForTests(null);
}

// --- Orphan snapshot (tiles show work, no queue evidence) must block collect ---
{
  const base = createWholeProfileHarvestIdleState(at);
  const orphan: WholeProfileHarvestState = {
    ...base,
    profile_url: "https://www.douyin.com/user/orphan-snapshot",
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_empty_disproves_snapshot",
      profile_identifier: "orphan-snapshot",
      scanned_total: 139,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 139,
      queue: 139,
      applied_at: at
    },
    harvest: {
      ...base.harvest,
      queue: [],
      queue_preview: [],
      pending: 0
    },
    profile_scan: {
      ...base.profile_scan,
      target_details: []
    },
    classification: {
      ...base.classification,
      status: "idle",
      collect_aweme_ids: []
    }
  };
  const reason = collectQueueReadinessBlockReason(orphan);
  assert.ok(reason, "orphan snapshot without actionable queue must block");
  assert.match(reason ?? "", /queue could not be prepared|Scan Profile again/i);
}

// --- Fresh queue items with status "new" must pass one-item preflight target pick ---
{
  const base = scannedProfileState(3);
  const allNew: WholeProfileHarvestState = {
    ...base,
    harvest: {
      ...base.harvest,
      queue: base.harvest.queue.map((item) => ({
        ...item,
        status: "new" as const,
        capture_status: "new" as const
      }))
    }
  };
  const target = getFirstPendingTargetForOneItemCollect(allNew);
  assert.ok(target, "status=new queue items must be selectable for Start Collecting preflight");
  assert.equal(target?.aweme_id, allNew.harvest.queue[0]?.aweme_id);
}

// --- Post re-collect: stale empty inbox cache must not show backend-wipe message ---
{
  const profileUrl = "https://www.douyin.com/user/post-recollect-authority";
  const base = scannedProfileState(139);
  const postCollect: WholeProfileHarvestState = {
    ...base,
    profile_url: profileUrl,
    collect_job: { ...base.collect_job, state: "completed", succeeded_count: 139 },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: profileIdentifierFromUrl(profileUrl),
      scanned_total: 139,
      backend_captured: 139,
      backend_ready: 139,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 139,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: at
    },
    harvest: {
      ...base.harvest,
      queue: base.harvest.queue.map((item) => ({
        ...item,
        status: "already_collected" as const,
        capture_status: "complete" as const
      })),
      pending: 0
    }
  };
  const vm = getScannerControlPanelViewModel(postCollect, {
    app_backend_logged_in: true,
    active_tab_url: profileUrl,
    active_profile_inbox_summary: {
      ...emptyTrustedInboxSummary(profileUrl),
      total_count: 139,
      already_collected: 139,
      captured_total: 139
    }
  });
  assert.doesNotMatch(vm.emptyState ?? "", /Backend data was cleared/i);
  assert.ok(vm.counts.alreadyCollectedCount >= 139 || vm.headerStatus.includes("139"), "post-collect must not regress to wipe-ready tiles");
}

// --- Backend deleted: reconcile phantom collected counts ---
{
  const stale = {
    ...scannedProfileState(8),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "test-profile",
      scanned_total: 8,
      backend_captured: 8,
      backend_ready: 8,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 8,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: at
    }
  };
  const vm = getScannerControlPanelViewModel(stale, {
    app_backend_logged_in: true,
    active_tab_url: "https://www.douyin.com/user/test-profile",
    active_profile_inbox_summary: {
      total_count: 0,
      already_collected: 0,
      new_count: 0,
      queue_count: 0,
      incomplete_count: 0,
      inbox_needs_review_count: 0,
      need_retry_count: 0,
      captured_total: 0,
      trusted: true
    }
  });
  assert.equal(vm.counts.alreadyCollectedCount, 0);
  assert.equal(vm.primaryAction.key, "start_collecting");
}

// --- Backend deleted: stale local complete markers must reset before collect ---
{
  const staleCollected = {
    ...scannedProfileState(3),
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test-profile",
      scanned_total: 3,
      backend_captured: 3,
      backend_ready: 3,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 3,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: at
    },
    harvest: {
      ...scannedProfileState(3).harvest,
      queue: scannedProfileState(3).harvest.queue.map((item, index) => ({
        ...item,
        status: "already_collected" as const,
        capture_status: "complete" as const,
        capture_inbox_item_id: `stale-item-${index}`
      }))
    }
  };
  const reconciled = reconcileHarvestStateWhenBackendEmpty(staleCollected, at);
  assert.equal(reconciled.post_scan_counter_snapshot?.already_collected, 0, "backend wipe must zero snapshot already_collected");
  assert.equal(reconciled.post_scan_counter_snapshot?.new, 3, "backend wipe must restore device queue count");
  assert.equal(reconciled.harvest.queue.every((item) => item.status === "pending"), true, "backend wipe must reset queue to pending");

  const scope = new Set(staleCollected.harvest.queue.map((item) => item.aweme_id));
  const cleared = clearStaleLocalCollectedQueueItems(staleCollected, scope, new Set(), at, "test_verify_empty");
  assert.equal(cleared.harvest.queue.filter((item) => item.status === "pending").length, 3, "verify-empty must clear stale local complete markers");
}

{
  const at = new Date().toISOString();
  const profileUrl = "https://www.douyin.com/user/test-large-profile";
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  setProfileTargetRepositoryFactoryForTests(() => new InMemoryProfileTargetRepository());
  const repository = createProfileTargetRepository();
  const collectedQueue = scannedProfileState(5).harvest.queue.map((item, index) => ({
    ...item,
    status: "already_collected" as const,
    capture_status: "complete" as const,
    capture_inbox_item_id: `stale-${index}`
  }));
  const targetDetails = scannedProfileState(5).profile_scan.target_details;
  await repository.upsertProfileTargets(profileIdentifier, collectedQueue, targetDetails, at);
  const reset = await repository.resetCollectedTargetsToPending(profileIdentifier, at);
  assert.equal(reset.reset_count, 5, "repository must reset collected markers after backend wipe");
  const pendingWindow = await repository.getProfileTargetsByStatus(profileIdentifier, ["new", "pending", "processing", "retry", "incomplete", "needs_metadata", "failed_recoverable"], 500, 0);
  assert.equal(pendingWindow.total, 5, "reset repository items must become pending for large-profile hydrate");
  assert.equal(pendingWindow.records.every((record) => record.status === "pending"), true, "repository records must be pending after reset");
  setProfileTargetRepositoryFactoryForTests(null);
}

{
  const profileUrl = "https://www.douyin.com/user/backend-wipe-session";
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  setProfileTargetRepositoryFactoryForTests(() => new InMemoryProfileTargetRepository());
  const repository = createProfileTargetRepository();
  const base = scannedProfileState(5);
  const collectedQueue = base.harvest.queue.map((item, index) => ({
    ...item,
    status: "already_collected" as const,
    capture_status: "complete" as const,
    capture_inbox_item_id: `stale-${index}`
  }));
  await repository.upsertProfileTargets(profileIdentifier, collectedQueue, base.profile_scan.target_details, at);
  const storage = new MemoryStorage();
  const stale: WholeProfileHarvestState = {
    ...base,
    profile_url: profileUrl,
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_empty_disproves_snapshot",
      profile_identifier: profileIdentifier,
      scanned_total: 5,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 5,
      queue: 5,
      applied_at: at
    },
    harvest: {
      ...base.harvest,
      queue: []
    }
  };
  const runtime: WholeProfileHarvestRuntime = {
    storage,
    async listCaptureInboxProfileSummary() {
      return {
        ok: true,
        status: 200,
        total_count: 1,
        counts: { captured: 0, ready: 0, needs_action: 0, dup: 0, fail: 0 },
        profile_identifier: profileIdentifier
      };
    }
  };
  const reconciled = await reconcileStateIfBackendEmpty(runtime, stale, at);
  assert.ok(reconciled.harvest.queue.length > 0, "empty session total_count must not block repository repopulate");
  assert.equal(
    reconciled.harvest.queue.every((item) => item.status === "pending" || item.status === "new"),
    true,
    "repository reset must yield pending queue after backend wipe"
  );
  setProfileTargetRepositoryFactoryForTests(null);
}

{
  const base = scannedProfileState(3);
  const collectedQueue = base.harvest.queue.map((item) => ({
    ...item,
    status: "already_collected" as const,
    capture_status: "complete" as const,
    capture_inbox_item_id: "stale-session-item"
  }));
  const stale: WholeProfileHarvestState = {
    ...base,
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_empty_disproves_snapshot",
      profile_identifier: "test-profile",
      scanned_total: 3,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    },
    harvest: { ...base.harvest, queue: collectedQueue, pending: 0 }
  };
  const scopeIds = new Set(stale.harvest.queue.map((item) => item.aweme_id));
  const recovered = clearStaleLocalCollectedQueueItems(stale, scopeIds, new Set(), at, "start_collecting_queue_recovery");
  assert.equal(recovered.harvest.queue.every((item) => item.status === "pending"), true, "stale already_collected queue must reset to pending before collect");
}

// --- Backend wipe: stale scan-time backend_item must not block Start Collecting preflight ---
{
  const base = scannedProfileState(3);
  const staleMetadataTargets = base.profile_scan.target_details.map((target, index) => ({
    ...target,
    backend_item: {
      item_id: `stale-backend-item-${index}`,
      metadata_status: "ready" as const,
      missing_fields: [] as string[],
      existing_fields: {},
      updated_at: at
    }
  }));
  const staleMetadata: WholeProfileHarvestState = {
    ...base,
    profile_scan: { ...base.profile_scan, target_details: staleMetadataTargets },
    verify: { ...base.verify, target_details: staleMetadataTargets },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_empty_disproves_snapshot",
      profile_identifier: "test-profile",
      scanned_total: 3,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    }
  };
  const scopeIds = new Set(staleMetadata.harvest.queue.map((item) => item.aweme_id));
  const cleared = clearStaleLocalCollectedQueueItems(staleMetadata, scopeIds, new Set(), at, "test_stale_metadata");
  assert.equal(
    cleared.profile_scan.target_details.every((target) => !target.backend_item?.item_id),
    true,
    "backend wipe must clear stale backend_item markers from target_details"
  );
}

// --- Backend wipe with empty session (total_count>0, captured=0) must not block backend-empty detection ---
{
  const provesZero = (summary: { summaryStatus: string; captured: number; totalCount: number }) =>
    summary.summaryStatus.startsWith("success") && summary.captured === 0;
  assert.equal(provesZero({ summaryStatus: "success_runtime_client", captured: 0, totalCount: 1 }), true, "empty session row must not block backend-empty detection");
  assert.equal(provesZero({ summaryStatus: "success_runtime_client", captured: 5, totalCount: 5 }), false);
}

// --- Post-collect API lag: summary captured=0 must not clear floor when writes succeeded ---
{
  const { computeHybridCollectCompletionTimeoutMs } = await import("./wholeProfileHarvest/controller.js");
  assert.ok(computeHybridCollectCompletionTimeoutMs(139) >= 120_000, "139-item hybrid collect needs generous completion timeout");
  assert.ok(computeHybridCollectCompletionTimeoutMs(10) >= 120_000, "even small batches need at least startup timeout");
}

// --- Post-collect: empty inbox must not revert UI to "ready" after backend wipe re-collect ---
{
  const { hybridPostCollectAuthorityActive, shouldTrustSnapshotAlreadyCollected, emptyTrustedInboxSummary } = await import("./wholeProfileHarvest/profileContext.js");
  const at = new Date().toISOString();
  const completedState = {
    collect_job: { state: "completed" as const, completed_at: at },
    post_scan_counter_snapshot: {
      status: "applied" as const,
      source: "backend_capture_inbox_profile_summary" as const,
      profile_identifier: "test",
      scanned_total: 139,
      backend_captured: 139,
      backend_ready: 139,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 139,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: at
    },
    debug: {
      last_response_summary: {
        hybrid_collector_completed: "yes",
        hybrid_runner_write_ok_count: 139,
        hybrid_runner_post_run_tile_already: 139
      }
    }
  } as unknown as import("./wholeProfileHarvest/state.js").WholeProfileHarvestState;
  const emptyInbox = emptyTrustedInboxSummary("https://www.douyin.com/user/test");
  assert.equal(hybridPostCollectAuthorityActive(completedState), true, "recent hybrid write_ok must activate post-collect authority");
  assert.equal(
    shouldTrustSnapshotAlreadyCollected(completedState, { active_profile_inbox_summary: emptyInbox, app_backend_logged_in: true }),
    true,
    "empty inbox must not discard trusted snapshot right after hybrid collect"
  );
  const wipeReadyState = {
    ...completedState,
    collect_job: { state: "completed" as const, completed_at: new Date(Date.now() - 24 * 60 * 60_000).toISOString() },
    post_scan_counter_snapshot: {
      ...completedState.post_scan_counter_snapshot,
      source: "backend_empty_disproves_snapshot" as const,
      already_collected: 0,
      backend_captured: 0,
      new: 139,
      queue: 139,
      applied_at: new Date(Date.now() - 24 * 60 * 60_000).toISOString()
    },
    debug: { last_response_summary: { hybrid_collector_completed: "yes", hybrid_runner_write_ok_count: 139 } }
  } as unknown as import("./wholeProfileHarvest/state.js").WholeProfileHarvestState;
  assert.equal(hybridPostCollectAuthorityActive(wipeReadyState), false, "stale completed job after backend wipe must not block re-ready UI");
  const staleCompleteState = {
    ...completedState,
    collect_job: { state: "completed" as const, completed_at: new Date(Date.now() - 24 * 60 * 60_000).toISOString() }
  } as unknown as import("./wholeProfileHarvest/state.js").WholeProfileHarvestState;
  assert.equal(
    hybridPostCollectAuthorityActive(staleCompleteState),
    false,
    "backend_capture_inbox snapshot must not grant permanent post-collect authority"
  );
}

{
  const base = scannedProfileState(1002);
  assert.equal(shouldRunHybridUnattendedCollectAll(base, {}, 1002), false, "manual hybrid collect must stay batch-bounded by default");
  assert.equal(
    shouldRunHybridUnattendedCollectAll({ ...base, harvest_options: { ...base.harvest_options, unattended_safe_mode: true } }, {}, 1002),
    false,
    "unattended safe mode must keep manual 500-per-click batches"
  );
  assert.equal(shouldRunHybridUnattendedCollectAll(base, {}, 120), false, "profiles under 500 must not auto-chain");
  assert.equal(
    shouldRunHybridUnattendedCollectAll({
      ...base,
      harvest: { ...base.harvest, pending: 503 },
      post_scan_counter_snapshot: {
        ...base.post_scan_counter_snapshot!,
        scanned_total: 1003,
        already_collected: 500,
        new: 503,
        queue: 503
      }
    }, {}, 500),
    false,
    "queue window size alone must not force unattended all-remaining"
  );
}

// --- Large profile partial batch: empty in-memory queue must still show Continue collecting ---
{
  const profileUrl = "https://www.douyin.com/user/large-profile-1002";
  const at = "2026-07-06T12:00:00.000Z";
  const partialBatch: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
    ...scannedProfileState(0),
    profile_url: profileUrl,
    phase: "batch_safe_mode_completed",
    status: "harvest_ready",
    harvest: {
      ...scannedProfileState(0).harvest,
      queue: [],
      queue_preview: [],
      pending: 0,
      planned_total: 1002,
      updated: 500,
      failed: 0
    },
    scan_job: {
      ...scannedProfileState(0).scan_job,
      status: "completed",
      total_persisted: 1002,
      profile_identifier: profileIdentifierFromUrl(profileUrl)
    },
    profile_scan: {
      ...scannedProfileState(0).profile_scan,
      status: "success",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 1002,
        profile_already_collected_count: 500
      }
    },
    target_status: { ...scannedProfileState(0).target_status, complete: 500 },
    layer: { ...scannedProfileState(0).layer, profile_scan_ready: true }
  }, true);
  const inboxSummary = parseActiveProfileInboxSummary(
    {
      counts: { ready: 500, captured: 500, needs_action: 0, fail: 0 },
      total_count: 1002,
      normalized_profile_url: profileUrl,
      scanned_total: 1002
    },
    profileUrl,
    1002
  );
  assert.ok(inboxSummary);
  assert.equal(collectQueueReadinessBlockReason(partialBatch), null, "partial batch must not block when persisted work remains");
  const vm = getScannerControlPanelViewModel(partialBatch, {
    active_tab_url: profileUrl,
    app_backend_logged_in: true,
    active_profile_inbox_summary: inboxSummary
  });
  assert.equal(vm.primaryAction.key, "start_collecting", "partial batch must keep Continue collecting primary action");
  assert.match(vm.primaryAction.label, /Collect (next 500|502 remaining)/, "partial batch button must invite next batch");
  assert.equal(vm.counts.alreadyCollectedCount, 500);
  assert.equal(vm.statsTileMode, "large_profile_batch", "large profile must use Remaining/Next batch tiles");
  assert.equal(vm.statsLargeProfile?.remaining, 502);
  assert.equal(vm.statsLargeProfile?.nextBatchCap, 500);
  assert.equal(vm.headerProgress?.collected, 500);
  assert.equal(vm.headerProgress?.total, 1002);
  assert.equal(vm.headerProgress?.percent, 49);
  assert.match(vm.headerStatus, /500\/1002 \(49%\)/);
}

{
  assert.match(
    formatStartCollectingSessionBlockReason(wholeProfileHarvestError("backend_auth_required")),
    /Sign in to the Web Dashboard/
  );
  assert.match(
    formatStartCollectingSessionBlockReason(wholeProfileHarvestError("capture_session_network_error")),
    /Cannot reach API/
  );
  assert.match(
    formatStartCollectingSessionBlockReason(wholeProfileHarvestError("capture_session_backend_error")),
    /Backend error while creating Capture Inbox session/
  );
}

// --- Complete profile: trusted inbox must beat stale snap.new for header progress ---
{
  const profileUrl = "https://www.douyin.com/user/complete-140-header";
  const base = scannedProfileState(140);
  const completeState: WholeProfileHarvestState = {
    ...base,
    profile_url: profileUrl,
    phase: "profile_collection_complete",
    harvest: {
      ...base.harvest,
      updated: 140,
      pending: 0,
      queue: []
    },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: { large_profile_mode: "yes" }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "local_scan",
      profile_identifier: profileIdentifierFromUrl(profileUrl),
      scanned_total: 140,
      backend_captured: 140,
      backend_ready: 140,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 140,
      incomplete: 0,
      need_retry: 0,
      new: 140,
      queue: 140,
      applied_at: at
    }
  };
  const renderContext = {
    app_backend_logged_in: true,
    active_tab_url: profileUrl,
    active_profile_inbox_summary: {
      ...emptyTrustedInboxSummary(profileUrl),
      total_count: 140,
      already_collected: 140,
      captured_total: 140,
      new_count: 0,
      queue_count: 0,
      need_retry_count: 0
    }
  };
  assert.equal(expectedCollectContinuationRemaining(completeState, renderContext), 0, "trusted complete inbox must ignore stale snap.new");
  const vm = getScannerControlPanelViewModel(completeState, renderContext);
  assert.equal(vm.headerProgress, null, "complete profile must not show header fraction bar");
  assert.equal(vm.primaryAction.key, "open_capture_inbox");
  assert.match(vm.primaryAction.title, /Collection complete/);
  assert.doesNotMatch(vm.headerStatus, /\d+\/\d+/, "header must not show collected/total fraction after complete");
  assert.equal(vm.statsCompact?.percent, 100);
}

// --- Small profile partial batch: header fraction bar (100/140) ---
{
  const profileUrl = "https://www.douyin.com/user/partial-small-140";
  const base = scannedProfileState(140);
  const partialState: WholeProfileHarvestState = {
    ...base,
    profile_url: profileUrl,
    phase: "batch_safe_mode_completed",
    harvest: {
      ...base.harvest,
      updated: 100,
      pending: 40,
      queue: []
    },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: { large_profile_mode: "yes" }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "local_scan",
      profile_identifier: profileIdentifierFromUrl(profileUrl),
      scanned_total: 140,
      backend_captured: 100,
      backend_ready: 100,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 100,
      incomplete: 0,
      need_retry: 0,
      new: 40,
      queue: 40,
      applied_at: at
    }
  };
  const renderContext = {
    app_backend_logged_in: true,
    active_tab_url: profileUrl,
    active_profile_inbox_summary: {
      ...emptyTrustedInboxSummary(profileUrl),
      total_count: 140,
      already_collected: 100,
      new_count: 40,
      queue_count: 40,
      captured_total: 100
    }
  };
  assert.equal(expectedCollectContinuationRemaining(partialState, renderContext), 40);
  const vm = getScannerControlPanelViewModel(partialState, renderContext);
  assert.equal(vm.headerProgress?.collected, 100);
  assert.equal(vm.headerProgress?.total, 140);
  assert.equal(vm.headerProgress?.percent, 71);
  assert.match(vm.headerStatus, /100\/140 \(71%\)/);
}

// --- Continuation restart must bump generation so terminal_collect_job_revert guard passes ---
{
  const at = "2026-07-07T04:30:00.000Z";
  const base = scannedProfileState(503);
  const completed: WholeProfileHarvestState = {
    ...base,
    collect_job: {
      ...base.collect_job,
      job_id: "hybrid_collect_job",
      state: "completed",
      runtime_generation: 3,
      completed_at: at
    },
    active_collect_runtime: {
      ...base.active_collect_runtime,
      runtime_generation: 4
    },
    debug: {
      ...base.debug,
      last_response_summary: {
        ...(base.debug.last_response_summary as Record<string, unknown>),
        hybrid_collector_completed: "yes"
      }
    }
  };
  const primed = primeHybridCollectContinuationRestart(completed, at);
  const restarted = {
    ...primed,
    collect_job: {
      ...primed.collect_job,
      state: "starting" as const,
      runtime_generation: primed.collect_job.runtime_generation
    }
  };
  const guard = evaluateCollectJobWriteGuard(completed, restarted, null);
  assert.equal(guard.reject, false, "continuation restart with bumped generation must not be terminal_collect_job_revert");
  assert.ok((primed.collect_job.runtime_generation ?? 0) > (completed.collect_job.runtime_generation ?? 0));
}

// --- Stale hybrid_collection_done must not short-circuit a continuation restart ---
{
  const at = "2026-07-07T05:00:00.000Z";
  const jobId = "run_1_batch_collect_safe";
  const base = scannedProfileState(503);
  const restarting: WholeProfileHarvestState = {
    ...base,
    collect_job: {
      ...base.collect_job,
      job_id: jobId,
      state: "starting",
      runtime_generation: 5,
      completed_at: null,
      runner_ack_at: null
    }
  };
  const staleDone = {
    job_id: jobId,
    runtime_generation: 4,
    completed_at: "2026-07-07T04:00:00.000Z",
    outcome: "completed"
  };
  assert.equal(hybridCollectionDoneSignalProvesTerminal(restarting, staleDone), false);
  assert.equal(persistentCollectJobTerminalReached(restarting, jobId, staleDone), false);
  const terminal: WholeProfileHarvestState = {
    ...restarting,
    collect_job: {
      ...restarting.collect_job,
      state: "completed",
      runtime_generation: 4,
      completed_at: staleDone.completed_at
    }
  };
  assert.equal(persistentCollectJobTerminalReached(terminal, jobId, staleDone), true);
  assert.equal(persistentCollectJobTerminalReached(terminal, jobId, staleDone, 5), false);
}

// --- Stale pre-dispatch terminal must not satisfy ack/terminal wait for newer generation ---
{
  const jobId = "run_1_batch_collect_safe";
  const staleTerminal: WholeProfileHarvestState = {
    ...scannedProfileState(503),
    collect_job: {
      ...scannedProfileState(503).collect_job,
      job_id: jobId,
      state: "completed",
      runtime_generation: 4,
      completed_at: "2026-07-07T04:00:00.000Z",
      runner_ack_at: "2026-07-07T04:00:00.000Z"
    }
  };
  assert.equal(persistentCollectJobTerminalReached(staleTerminal, jobId, null), true);
  assert.equal(persistentCollectJobTerminalReached(staleTerminal, jobId, null, 5), false);
}

// --- Preflight blocked must release optimistic collect_job.starting ---
{
  const at = "2026-07-07T06:00:00.000Z";
  const base = scannedProfileState(100);
  const stuckStarting: WholeProfileHarvestState = {
    ...base,
    status: "harvesting",
    phase: "collecting",
    collect_job: {
      ...base.collect_job,
      state: "starting",
      current_step: "starting",
      heartbeat_at: at
    },
    workflow: {
      ...base.workflow,
      collection: {
        ...base.workflow.collection,
        status: "failed",
        last_error: "Calibrate 4 Points first."
      }
    },
    debug: {
      ...base.debug,
      last_action_result: "blocked"
    }
  };
  const released = finalizeStartCollectingBlockedState(stuckStarting, "Calibrate 4 Points first.", at);
  assert.equal(released.collect_job.state, "idle");
  assert.equal(released.phase, "blocked");
  assert.equal(released.workflow.collection.status, "failed");
}

// --- Hybrid runner enabled when state mirror says enabled (preflight/UI parity) ---
{
  const hybridState = applyHybridNetworkCacheModeFlagToState(scannedProfileState(100), true);
  const enabled = await resolveHybridNetworkCacheRunnerEnabled({ storage: new MemoryStorage() } as WholeProfileHarvestRuntime, hybridState);
  assert.equal(enabled, true);
}

// --- Blocked start_collecting must not keep Preparing UI live ---
{
  const at = "2026-07-07T06:05:00.000Z";
  const blocked = finalizeStartCollectingBlockedState({
    ...scannedProfileState(10),
    collect_job: {
      ...scannedProfileState(10).collect_job,
      state: "starting",
      current_step: "starting",
      heartbeat_at: at
    }
  }, "Calibrate 4 Points first.", at);
  assert.equal(isCollectJobVisiblyLive(blocked), false);
}

// --- Backend finished 1003/1003 must not show Continue collecting (500/503 stale tiles) ---
{
  const at = "2026-07-07T07:00:00.000Z";
  const profileUrl = "https://www.douyin.com/user/profile-1003";
  const completed: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
    ...scannedProfileState(0),
    profile_url: profileUrl,
    phase: "profile_collection_complete",
    status: "harvest_ready",
    collect_job: {
      ...scannedProfileState(0).collect_job,
      state: "completed",
      completed_at: at
    },
    scan_job: {
      ...scannedProfileState(0).scan_job,
      status: "completed",
      total_persisted: 1003
    },
    profile_scan: {
      ...scannedProfileState(0).profile_scan,
      status: "success",
      diagnostics: {
        large_profile_mode: "yes",
        queue_total_persisted: 1003
      }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: profileUrl,
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
    },
    debug: {
      ...scannedProfileState(0).debug,
      last_response_summary: {
        hybrid_network_cache_mode_flag: "enabled",
        hybrid_collector_completed: "yes",
        hybrid_runner_post_run_tile_already: 1003,
        hybrid_runner_post_run_tile_new: 0,
        hybrid_runner_post_run_summary_status: "success_runtime_client"
      }
    }
  }, true);
  assert.equal(hybridProfileCollectFullyComplete(completed, {}), true);
  assert.equal(expectedCollectContinuationRemaining(completed, {}), 0);
  const vm = getScannerControlPanelViewModel(completed, {});
  assert.notEqual(vm.primaryAction.label, "Collect next 500");
  assert.match(vm.headerStatus, /1003 collected/);
}

// --- Continuation click must run unattended for all profile remaining (503 left) ---
{
  const base = scannedProfileState(500);
  const continuationState: WholeProfileHarvestState = {
    ...base,
    harvest: { ...base.harvest, pending: 0, queue: [] },
    post_scan_counter_snapshot: {
      ...base.post_scan_counter_snapshot!,
      scanned_total: 1003,
      already_collected: 500,
      new: 503,
      queue: 503
    },
    harvest_options: { ...base.harvest_options, unattended_safe_mode: true }
  };
  assert.equal(
    shouldRunHybridUnattendedCollectAll(continuationState, { diagnostics: { hybrid_continuation_collect: "yes" } }, 500),
    false,
    "continuation collect alone must not force unattended all-remaining"
  );
  assert.equal(
    shouldRunHybridUnattendedCollectAll(continuationState, { batch_limit: "all" }, 500),
    true,
    "batch_limit all must run unattended for remaining 503"
  );
  assert.equal(
    shouldRunHybridUnattendedCollectAll(continuationState, { diagnostics: { hybrid_force_unattended_collect_all: "yes" } }, 500),
    true,
    "explicit unattended-all flag must still route through the unattended runner"
  );
}

console.log("wholeProfileHarvest.operatorRegression.test.ts: PASS");
