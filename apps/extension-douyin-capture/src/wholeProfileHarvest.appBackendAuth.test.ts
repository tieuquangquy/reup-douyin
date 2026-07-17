import assert from "node:assert/strict";
import { parseAppBackendAuthStatus, reconcileExtensionAuthWithWebTabToken } from "./wholeProfileHarvest/appBackendAuth.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { getScannerControlPanelViewModel, hybridCollectRunnerLikelyStale, isCollectJobVisiblyLive } from "./wholeProfileHarvest/viewModel.js";
import { getCanonicalScannerPrimaryAction } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState, WHOLE_PROFILE_HARVEST_STATE_KEY, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import {
  runBatchCollectHybridNetworkCacheMode,
  type WholeProfileHarvestRuntime
} from "./wholeProfileHarvest/controller.js";

assert.deepEqual(
  parseAppBackendAuthStatus({ apiAuthToken: "token", apiAuthRequired: false }),
  { tokenPresent: true, authRequired: false, loggedIn: true }
);
assert.deepEqual(
  parseAppBackendAuthStatus({ apiAuthToken: "", apiAuthRequired: false }),
  { tokenPresent: false, authRequired: false, loggedIn: false }
);
assert.deepEqual(
  parseAppBackendAuthStatus({ apiAuthToken: "token", apiAuthRequired: true }),
  { tokenPresent: true, authRequired: true, loggedIn: false }
);

assert.deepEqual(
  reconcileExtensionAuthWithWebTabToken("stale-token", true, null),
  { token: null, source: "web_tab_logged_out_cleared_stale", clearedStaleExtensionToken: true }
);
assert.deepEqual(
  reconcileExtensionAuthWithWebTabToken(null, true, null),
  { token: null, source: "web_tab_logged_out", clearedStaleExtensionToken: false }
);
assert.deepEqual(
  reconcileExtensionAuthWithWebTabToken("same", true, "same"),
  { token: "same", source: "chrome_storage_local", clearedStaleExtensionToken: false }
);
assert.deepEqual(
  reconcileExtensionAuthWithWebTabToken("old", true, "fresh"),
  { token: "fresh", source: "background_web_local_storage_22C13A", clearedStaleExtensionToken: false }
);
assert.deepEqual(
  reconcileExtensionAuthWithWebTabToken("keep-me", false, null),
  { token: "keep-me", source: "chrome_storage_local", clearedStaleExtensionToken: false }
);

const at = "2026-07-05T15:00:00.000Z";
const base = createWholeProfileHarvestIdleState(at);

const idleLoggedOutVm = getScannerControlPanelViewModel(base, { app_backend_logged_in: false });
assert.equal(idleLoggedOutVm.health.api, "App login", "idle logged-out operator must see App login chip");
assert.equal(idleLoggedOutVm.headerStatus, "Ready", "idle logged-out header stays Ready; chip carries auth state");
assert.equal(idleLoggedOutVm.emptyState, "Scan a profile to build the collection plan.", "idle logged-out must not duplicate sign-in in empty state");
assert.match(idleLoggedOutVm.primaryAction.description, /Sign in to the Web Dashboard/i, "idle logged-out sign-in hint belongs in primary description only");

const queue = Array.from({ length: 10 }, (_, index) => ({
  index: index + 1,
  aweme_id: `700000000000000000${index}`,
  capture_status: "new" as const,
  status: "pending" as const,
  attempts: 0,
  checkpoint_sequence: null,
  extraction_result: null,
  last_error: null,
  capture_inbox_item_id: null,
  source_url: `https://www.douyin.com/video/700000000000000000${index}`,
  profile_card_evidence: {}
}));
const scannedReady: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
  ...base,
  status: "verified",
  profile_url: "https://www.douyin.com/user/test-profile",
  classification: { ...base.classification, status: "success", sec_uid: "test-profile", total_candidates: 10 },
  profile_scan: { ...base.profile_scan, status: "success", accepted_target_count: 10 },
  scan_job: { ...base.scan_job, status: "completed", total_persisted: 10, expected_count: 10, has_more_state: false },
  verify: { ...base.verify, status: "success", accepted_target_count: 10 },
  workflow: {
    ...base.workflow,
    scan: {
      ...base.workflow.scan,
      status: "success",
      started_at: at,
      updated_at: at,
      completed_at: at,
      last_error: null
    }
  },
  harvest: {
    ...base.harvest,
    pending: 10,
    queue
  }
}, true);

const loggedOutVm = getScannerControlPanelViewModel(scannedReady, { app_backend_logged_in: false });
assert.equal(loggedOutVm.health.api, "App login", "logged-out operator must see App login chip");
assert.equal(loggedOutVm.primaryAction.key, "sign_in_to_app", "logged-out post-scan must offer sign in, not start collecting");
assert.match(loggedOutVm.primaryAction.description, /not in Capture Inbox yet/i, "sign-in primary must clarify videos are local-only");
assert.equal(loggedOutVm.emptyState, null, "sign-in primary must not duplicate the same copy in empty state");

const loggedInVm = getScannerControlPanelViewModel(scannedReady, { app_backend_logged_in: true });
assert.equal(loggedInVm.health.api, "App OK", "logged-in operator must see App OK chip");
assert.notEqual(loggedInVm.primaryAction.key, "sign_in_to_app", "logged-in operator must not be forced to sign in");

const staleCollectedSnapshot: WholeProfileHarvestState = {
  ...scannedReady,
  post_scan_counter_snapshot: {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: "test-profile",
    scanned_total: 10,
    backend_captured: 10,
    backend_ready: 10,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 10,
    incomplete: 0,
    need_retry: 0,
    new: 0,
    queue: 0,
    applied_at: at
  }
};
const loggedOutStaleVm = getScannerControlPanelViewModel(staleCollectedSnapshot, { app_backend_logged_in: false });
assert.equal(loggedOutStaleVm.primaryAction.key, "sign_in_to_app", "logout must not keep Open Capture Inbox from stale snapshot");
assert.equal(loggedOutStaleVm.counts.alreadyCollectedCount, 0, "logout must not show phantom already-collected tiles");

const emptyBackendVm = getScannerControlPanelViewModel(staleCollectedSnapshot, {
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
assert.equal(emptyBackendVm.primaryAction.key, "start_collecting", "empty backend must reconcile stale collected UI to start collecting");
assert.equal(emptyBackendVm.counts.alreadyCollectedCount, 0, "empty backend must clear phantom already-collected count");

const loggedInStaleCompleteVm = getScannerControlPanelViewModel(staleCollectedSnapshot, {
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
assert.notEqual(loggedInStaleCompleteVm.primaryAction.key, "open_capture_inbox", "deleted backend must not show Open Capture Inbox from stale snapshot");
assert.equal(loggedInStaleCompleteVm.counts.alreadyCollectedCount, 0, "deleted backend must zero already-collected tiles");
assert.equal(loggedInStaleCompleteVm.counts.queueCount, 10, "deleted backend must restore scan queue from device");

const authPaused: WholeProfileHarvestState = {
  ...scannedReady,
  status: "paused",
  harvest: {
    ...scannedReady.harvest,
    status: "paused",
    paused_reason: "backend_auth_required",
    pause_message: "Backend login expired.",
    resume_available: true
  }
};
const checkedWithoutSaveVm = getScannerControlPanelViewModel(authPaused, { app_backend_logged_in: false });
assert.equal(checkedWithoutSaveVm.headerStatus, "0 saved · 10 waiting", "auth pause must show saved vs waiting header");
assert.match(checkedWithoutSaveVm.primaryAction.description, /0 saved/i, "auth pause must explain nothing was saved yet");
assert.equal(checkedWithoutSaveVm.emptyState, null, "auth pause must not duplicate primary description in empty state");

class MemoryStorage {
  values: Record<string, unknown> = {};
  async get(key: string): Promise<Record<string, unknown>> {
    return { [key]: this.values[key] };
  }
  async set(items: Record<string, unknown>): Promise<void> {
    Object.assign(this.values, items);
  }
}

const storage = new MemoryStorage();
storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = scannedReady;
storage.values.apiAuthRequired = true;
const runtime = {
  storage,
  now: () => at,
  getActiveTab: async () => ({ url: scannedReady.profile_url })
} as unknown as WholeProfileHarvestRuntime;

const pausedAtEntry = await runBatchCollectHybridNetworkCacheMode(runtime, {});
assert.equal(pausedAtEntry.harvest.paused_reason, "backend_auth_required", "hybrid runner must pause immediately when app auth is missing");
assert.equal(pausedAtEntry.status, "paused", "hybrid runner must not run local checking when app auth is missing");

storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
  ...scannedReady,
  status: "harvesting",
  workflow: {
    ...scannedReady.workflow,
    collection: { ...scannedReady.workflow.collection, status: "running", updated_at: at }
  },
  collect_job: {
    ...scannedReady.collect_job,
    job_id: "collect-job-auth-pause",
    state: "running",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 135,
    selected_count: 438,
    batch_limit: 438
  },
  harvest: { ...scannedReady.harvest, status: "running", updated_at: at }
};
const pausedMidRun = await runBatchCollectHybridNetworkCacheMode(runtime, {});
assert.equal(pausedMidRun.harvest.paused_reason, "backend_auth_required", "hybrid runner must pause mid-run when app auth is missing");
assert.equal(pausedMidRun.collect_job.state, "stuck", "auth pause must terminalize collect_job so UI cannot keep Checking");

const collectingWhileLoggedOut: WholeProfileHarvestState = {
  ...scannedReady,
  status: "harvesting",
  workflow: {
    ...scannedReady.workflow,
    collection: { ...scannedReady.workflow.collection, status: "running", updated_at: at }
  },
  collect_job: {
    ...scannedReady.collect_job,
    state: "running",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 135,
    selected_count: 438,
    batch_limit: 438
  },
  harvest: { ...scannedReady.harvest, status: "running", updated_at: at }
};
const collectingLoggedOutVm = getScannerControlPanelViewModel(collectingWhileLoggedOut, { app_backend_logged_in: false });
assert.equal(collectingLoggedOutVm.collectProgress?.active, undefined, "logged-out UI must not show active Checking progress");
assert.equal(collectingLoggedOutVm.primaryAction.key, "sign_in_to_app", "logged-out active collect_job must offer sign in");

const zombieHybrid135: WholeProfileHarvestState = {
  ...scannedReady,
  status: "harvesting",
  workflow: {
    ...scannedReady.workflow,
    collection: { ...scannedReady.workflow.collection, status: "running", updated_at: at },
    active_task: "collect_videos",
    action_lock: "collect_videos"
  },
  collect_job: {
    ...scannedReady.collect_job,
    job_id: "job-zombie-135",
    state: "running",
    current_step: "hybrid_loop_hydrating",
    attempted_count: 135,
    succeeded_count: 135,
    selected_count: 438,
    batch_limit: 438,
    heartbeat_at: "2026-07-05T14:00:00.000Z",
    updated_at: "2026-07-05T14:00:00.000Z"
  },
  harvest: { ...scannedReady.harvest, status: "running", updated_at: at },
  active_collect_runtime: {
    ...scannedReady.active_collect_runtime,
    job_id: "job-zombie-135",
    canonical_state: "running",
    current_step: "hybrid_loop_hydrating"
  }
};
assert.equal(hybridCollectRunnerLikelyStale(zombieHybrid135, Date.parse("2026-07-05T16:00:00.000Z")), true, "135/438 zombie must be stale when heartbeat is old");
const zombieVm = getScannerControlPanelViewModel(zombieHybrid135, { app_backend_logged_in: true });
assert.equal(zombieVm.collectProgress?.active, undefined, "stale hybrid zombie must not show Checking 135/438");
assert.notEqual(zombieVm.primaryAction.key, "pause", "stale hybrid zombie must not keep Collecting pause primary");

const startingCollect: WholeProfileHarvestState = {
  ...scannedReady,
  status: "harvesting",
  workflow: {
    ...scannedReady.workflow,
    collection: { ...scannedReady.workflow.collection, status: "idle", active_task: null },
    active_task: null,
    action_lock: null
  },
  collect_job: {
    ...scannedReady.collect_job,
    state: "starting",
    current_step: "starting",
    attempted_count: 0,
    succeeded_count: 0,
    heartbeat_at: "2026-07-05T15:00:01.000Z",
    updated_at: "2026-07-05T15:00:01.000Z"
  }
};
assert.equal(isCollectJobVisiblyLive(startingCollect, Date.parse("2026-07-05T15:00:02.000Z")), true, "collect_job starting must keep Collecting UI before hybrid_loop heartbeat");
const startingVm = getScannerControlPanelViewModel(startingCollect, { app_backend_logged_in: true });
assert.notEqual(startingVm.primaryAction.key, "start_collecting", "starting collect must not flash back to Start Collecting primary");
assert.match(startingVm.primaryAction.label, /Checking|Collecting/i, "starting collect must show in-progress label");

const hybridStartAction = getCanonicalScannerPrimaryAction(applyHybridNetworkCacheModeFlagToState(scannedReady, true));
assert.equal(hybridStartAction.key, "start_collecting");
assert.equal(hybridStartAction.title, "Start Collecting", "hybrid must not show two-step Create Save Session title");
assert.match(hybridStartAction.description, /automatically/i, "hybrid must explain session is auto-created on one click");

console.log("wholeProfileHarvest.appBackendAuth.test.ts: PASS");
