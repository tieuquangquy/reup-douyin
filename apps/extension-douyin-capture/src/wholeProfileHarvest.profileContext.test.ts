import assert from "node:assert/strict";

import {
  activeProfileInboxSummaryIsComplete,
  activeProfileInboxSummaryIsResumeEligible,
  clearStaleCollectBlockDiagnostics,
  clearStaleOvercollectionDiagnostics,
  collectPresentationSuppressed,
  detectProfileContextMismatch,
  deriveProfileContextViewModel,
  emptyTrustedInboxSummary,
  inboxSummaryHasReviewOnlyBacklog,
  orphanedPostCollectSnapshot,
  parseActiveProfileInboxSummary,
  partialCollectTileCounts,
  profileContextCollectableRemaining,
  profileContextHeaderStatus,
  resolveScanProfileResetMode,
  shouldGateScannerPanelForProfileContext,
  shouldHoldScanPresentationForRescan,
  scanQueueProvesSessionCompleteForPresentation,
  shouldTrustSnapshotAlreadyCollected,
  staleLocalCollectedDisprovenByBackendEmpty,
  storedScanSessionAppliesToActiveTab
} from "./wholeProfileHarvest/profileContext.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import { applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { profileIdentifierFromUrl } from "./wholeProfileHarvest/profileTargetRepository.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

function completedProfileState(profileSuffix: string, collected: number): WholeProfileHarvestState {
  const profileUrl = `https://www.douyin.com/user/MS4wLjABAAAA-${profileSuffix}`;
  const idle = createWholeProfileHarvestIdleState("2026-05-06T12:00:00.000Z");
  return {
    ...idle,
    status: "verified",
    profile_url: profileUrl,
    classification: {
      ...idle.classification,
      status: "success",
      sec_uid: `MS4wLjABAAAA-${profileSuffix}`
    },
    profile_scan: {
      ...idle.profile_scan,
      status: "success",
      accepted_target_count: collected
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed",
      total_persisted: collected,
      expected_count: collected,
      has_more_state: false
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: `MS4wLjABAAAA-${profileSuffix}`,
      scanned_total: collected,
      backend_captured: collected,
      backend_ready: collected,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: collected,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: "2026-05-06T12:00:00.000Z"
    }
  };
}

{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b";
  const summary = parseActiveProfileInboxSummary(
    {
      counts: { ready: 96, captured: 128, needs_action: 32, fail: 1 },
      total_count: 128,
      normalized_profile_url: profileUrl
    },
    profileUrl
  );
  assert.ok(summary);
  assert.equal(summary.already_collected, 96);
  assert.equal(summary.queue_count, 0, "needs_action is inbox backlog, not collect queue");
  assert.equal(summary.inbox_needs_review_count, 32);
  assert.equal(summary.need_retry_count, 1);
  assert.equal(profileContextHeaderStatus(summary), "96 collected · 1 left");
}

{
  const tiles = partialCollectTileCounts(502, 500);
  assert.equal(tiles.newCount, 502);
  assert.equal(tiles.queueCount, 500, "queue tile shows next batch cap after partial collect");
  const fresh = partialCollectTileCounts(1002, 0);
  assert.equal(fresh.newCount, 1002);
  assert.equal(fresh.queueCount, 1002);
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-large-profile";
  const summary = parseActiveProfileInboxSummary(
    { counts: { ready: 500, captured: 500 }, total_count: 1002, normalized_profile_url: profileUrl },
    profileUrl,
    1002
  );
  assert.ok(summary);
  assert.equal(summary.already_collected, 500);
  assert.equal(summary.new_count, 502);
  assert.equal(summary.queue_count, 500);
  assert.equal(profileContextCollectableRemaining(summary), 502);
}

{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-review-one";
  const summary = parseActiveProfileInboxSummary(
    {
      counts: { ready: 364, captured: 365, needs_action: 1, fail: 0, dup: 0 },
      total_count: 365,
      normalized_profile_url: profileUrl
    },
    profileUrl
  );
  assert.ok(summary);
  assert.equal(summary.queue_count, 0);
  assert.equal(summary.inbox_needs_review_count, 1);
  assert.equal(inboxSummaryHasReviewOnlyBacklog(summary), true);
  assert.equal(activeProfileInboxSummaryIsComplete(summary), true);
  assert.equal(profileContextHeaderStatus(summary), "364 collected · 1 needs review");
}

{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-earth-tour";
  const summary = parseActiveProfileInboxSummary(
    {
      counts: { ready: 0, captured: 60, needs_action: 60 },
      total_count: 110,
      normalized_profile_url: profileUrl
    },
    profileUrl
  );
  assert.ok(summary);
  assert.equal(summary.already_collected, 0);
  assert.equal(summary.queue_count, 0);
  assert.equal(activeProfileInboxSummaryIsResumeEligible(summary), false);
}

{
  const stored = completedProfileState("done-profile", 0);
  stored.profile_url = "https://www.douyin.com/user/MS4wLjABAAAA-done-profile";
  const profileUrl = stored.profile_url;
  const vm = getScannerControlPanelViewModel(stored, {
    active_tab_url: profileUrl,
    active_profile_inbox_summary: parseActiveProfileInboxSummary(
      {
        counts: { ready: 364, captured: 365, needs_action: 1, fail: 0, dup: 0 },
        total_count: 365,
        normalized_profile_url: profileUrl
      },
      profileUrl
    )
  });
  assert.equal(vm.primaryAction.key, "open_capture_inbox");
  assert.equal(vm.primaryAction.title, "Review 1 video in Capture Inbox");
  assert.equal(vm.counts.queueCount, 0);
  assert.equal(vm.counts.incompleteCount, 1);
  assert.match(vm.headerStatus, /needs review/);
}

{
  const stored = completedProfileState("done-profile", 733);
  const profileUrl = stored.profile_url;
  const vm = getScannerControlPanelViewModel(stored, {
    active_tab_url: profileUrl,
    active_profile_inbox_summary: parseActiveProfileInboxSummary(
      {
        counts: { ready: 733, captured: 733, needs_action: 0, fail: 0 },
        total_count: 733,
        normalized_profile_url: profileUrl
      },
      profileUrl
    )
  });
  assert.equal(vm.primaryAction.key, "open_capture_inbox");
  assert.equal(vm.primaryActionCardTone, "success");
}

// --- Post batch-2: 165 needs_action dominates 3 not-in-API; must not offer Start Collecting ---
{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-batch2-review";
  const idle = createWholeProfileHarvestIdleState("2026-07-08T12:00:00.000Z");
  const stored: WholeProfileHarvestState = applyHybridNetworkCacheModeFlagToState({
    ...idle,
    status: "verified",
    profile_url: profileUrl,
    classification: { ...idle.classification, status: "success", sec_uid: "batch2-review", total_candidates: 738 },
    profile_scan: { ...idle.profile_scan, status: "success", accepted_target_count: 738 },
    scan_job: { ...idle.scan_job, status: "completed", total_persisted: 735, expected_count: 738, has_more_state: false },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "batch2-review",
      scanned_total: 738,
      backend_captured: 735,
      backend_ready: 570,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 735,
      incomplete: 165,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: "2026-07-08T12:00:00.000Z"
    }
  }, true);
  const vm = getScannerControlPanelViewModel(stored, {
    active_tab_url: profileUrl,
    app_backend_logged_in: true,
    active_profile_inbox_summary: parseActiveProfileInboxSummary(
      {
        counts: { ready: 570, captured: 735, needs_action: 165, fail: 0, dup: 0 },
        total_count: 738,
        normalized_profile_url: profileUrl,
        scanned_total: 738
      },
      profileUrl,
      738
    )
  });
  assert.equal(vm.primaryAction.key, "open_capture_inbox");
  assert.match(vm.headerStatus, /need review/);
  assert.doesNotMatch(vm.primaryAction.label, /Start Collecting/i);
  assert.equal(vm.counts.incompleteCount, 165);
  assert.equal(vm.counts.newCount, 3);
}

{
  const stored = completedProfileState("profile-a", 365);
  const activeUrl = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b";
  const vm = getScannerControlPanelViewModel(stored, {
    active_tab_url: activeUrl,
    active_profile_inbox_summary: parseActiveProfileInboxSummary(
      {
        counts: { ready: 100, captured: 100, needs_action: 0 },
        total_count: 100,
        normalized_profile_url: activeUrl
      },
      activeUrl,
      200
    )
  });
  assert.equal(vm.primaryAction.key, "scan_profile");
  assert.equal(vm.scanDataVisible, false);
}

{
  const stored = completedProfileState("profile-a", 365);
  const activeUrl = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b";
  const zombieCollect: WholeProfileHarvestState = {
    ...stored,
    status: "harvesting",
    phase: "collecting",
    workflow: {
      ...stored.workflow,
      collection: {
        ...stored.workflow.collection,
        status: "running",
        started_at: "2026-05-06T12:10:00.000Z",
        updated_at: "2026-05-06T12:10:00.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "collect_videos",
      action_lock: "collect_videos"
    },
    collect_job: {
      ...stored.collect_job,
      state: "running",
      attempted_count: 438,
      selected_count: 438,
      succeeded_count: 438,
      current_step: "hybrid_loop_hydrate",
      heartbeat_at: "2026-05-06T12:10:30.000Z",
      updated_at: "2026-05-06T12:10:30.000Z"
    },
    harvest: {
      ...stored.harvest,
      status: "running",
      pending: 438,
      updated_at: "2026-05-06T12:10:30.000Z"
    }
  };
  const vm = getScannerControlPanelViewModel(zombieCollect, { active_tab_url: activeUrl });
  assert.equal(vm.primaryAction.key, "scan_profile", "profile mismatch must override zombie Checking 438/438 with Scan this profile");
  assert.equal(vm.collectProgress, null, "profile mismatch must clear stale collect progress");
  assert.equal(vm.profileContext?.mismatch, true);
  assert.equal(vm.scanDataVisible, false);
}

{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-backend-wipe";
  const stored = completedProfileState("backend-wipe", 438);
  stored.post_scan_counter_snapshot = {
    status: "applied",
    source: "backend_capture_inbox_profile_summary",
    profile_identifier: "MS4wLjABAAAA-backend-wipe",
    scanned_total: 438,
    backend_captured: 438,
    backend_ready: 438,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 438,
    incomplete: 0,
    need_retry: 0,
    new: 0,
    queue: 0,
    applied_at: "2026-05-06T12:00:00.000Z"
  };
  const emptyInbox = emptyTrustedInboxSummary(profileUrl);
  assert.equal(staleLocalCollectedDisprovenByBackendEmpty(stored, { active_profile_inbox_summary: emptyInbox }), true);
  assert.equal(shouldTrustSnapshotAlreadyCollected(stored, { active_profile_inbox_summary: emptyInbox }), false);
  const liveCollect: WholeProfileHarvestState = {
    ...stored,
    status: "harvesting",
    workflow: {
      ...stored.workflow,
      collection: { status: "running", started_at: "2026-05-06T12:10:00.000Z", updated_at: "2026-05-06T12:10:00.000Z", completed_at: null, last_error: null },
      active_task: "collect_videos",
      action_lock: "collect_videos"
    },
    collect_job: {
      ...stored.collect_job,
      state: "running",
      current_step: "hybrid_loop_hydrating",
      attempted_count: 438,
      succeeded_count: 438,
      selected_count: 438,
      batch_limit: 438
    }
  };
  const vm = getScannerControlPanelViewModel(liveCollect, {
    active_tab_url: profileUrl,
    active_profile_inbox_summary: emptyInbox,
    app_backend_logged_in: true
  });
  assert.equal(vm.counts.alreadyCollectedCount, 0, "backend wipe must not flash Already=438 during live collect");
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-06T03:30:00.000Z");
  const orphan: WholeProfileHarvestState = {
    ...idle,
    profile_url: null,
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "unknown",
      scanned_total: 139,
      backend_captured_aweme_ids: [],
      backend_captured: 139,
      backend_ready: 139,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 139,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: "2026-07-06T03:30:00.000Z"
    },
    collect_job: {
      ...idle.collect_job,
      state: "completed",
      completed_at: "2026-07-06T03:30:00.000Z"
    }
  };
  assert.equal(orphanedPostCollectSnapshot(orphan), true);
  const vm = getScannerControlPanelViewModel(orphan, {
    active_tab_url: "https://www.douyin.com/",
    app_backend_logged_in: true
  });
  assert.notEqual(vm.primaryAction.key, "open_capture_inbox");
  assert.equal(vm.statsCompact, null);
  assert.equal(vm.health.profile, "No profile");
}

{
  const profileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-stuck-profile";
  const stored = completedProfileState("stuck-profile", 139);
  assert.equal(
    shouldGateScannerPanelForProfileContext(stored, "https://www.douyin.com/"),
    true
  );
  const vm = getScannerControlPanelViewModel(stored, {
    active_tab_url: "https://www.douyin.com/",
    app_backend_logged_in: true
  });
  assert.equal(vm.primaryAction.key, "scan_profile");
  assert.equal(vm.statsCompact, null);
}

{
  const stored = completedProfileState("profile-a", 50);
  const profileB = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b";
  assert.equal(detectProfileContextMismatch(stored, profileB), true);
  assert.equal(storedScanSessionAppliesToActiveTab(stored, profileB), false);
  assert.equal(storedScanSessionAppliesToActiveTab(stored, stored.profile_url), true);
}

{
  const profileA = "https://www.douyin.com/user/MS4wLjABAAAA-profile-a-1007";
  const profileB = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b-1127";
  const syncedUrlStaleJob = {
    ...completedProfileState("profile-b-1127", 1127),
    profile_url: profileA,
    scan_job: {
      ...completedProfileState("profile-b-1127", 1127).scan_job,
      profile_identifier: profileIdentifierFromUrl(profileB),
      total_persisted: 1127,
      expected_count: 1127
    }
  };
  assert.equal(
    detectProfileContextMismatch(syncedUrlStaleJob, profileA),
    true,
    "synced profile_url with stale scan_job.profile_identifier must count as mismatch"
  );
  assert.equal(storedScanSessionAppliesToActiveTab(syncedUrlStaleJob, profileA), false);
}

{
  const profileP1 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p1";
  const profileP2 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p2";
  const p2Scanned = {
    ...completedProfileState("profile-p2", 111),
    profile_url: profileP2,
    layer: { ...completedProfileState("profile-p2", 111).layer, profile_scan_ready: true }
  };
  assert.equal(resolveScanProfileResetMode(p2Scanned, profileP2), "current_profile_rescan", "same-profile rescan after success must reset stale session");
  assert.equal(
    resolveScanProfileResetMode(p2Scanned, profileP2, { lastPresentedProfileUrl: profileP1 }),
    "current_profile_rescan",
    "rescan after visiting another profile tab must reset stale counters"
  );
  assert.equal(resolveScanProfileResetMode(p2Scanned, profileP1), "new_profile", "mismatch must switch profile reset");
  const fresh = createWholeProfileHarvestIdleState("2026-07-06T12:00:00.000Z");
  assert.equal(resolveScanProfileResetMode(fresh, profileP2), "none", "first scan on clean state must not reset");
  const p2WithStalePageContext = {
    ...p2Scanned,
    page_context: {
      ...p2Scanned.page_context,
      current_url: profileP1,
      page_type: "profile" as const
    }
  };
  assert.equal(
    resolveScanProfileResetMode(p2WithStalePageContext, profileP2),
    "current_profile_rescan",
    "stale page_context from another profile tab must force rescan reset"
  );
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-06T12:00:00.000Z");
  const scanning = {
    ...idle,
    status: "verifying" as const,
    workflow: {
      ...idle.workflow,
      scan: { status: "running" as const, started_at: "2026-07-06T12:00:00.000Z", updated_at: "2026-07-06T12:00:00.000Z", completed_at: null, last_error: null },
      active_task: "scan_profile" as const
    },
    scan_job: { ...idle.scan_job, status: "running" as const }
  };
  assert.equal(collectPresentationSuppressed(scanning), true, "running scan must suppress collect presentation");
  const terminalProfileUrl = "https://www.douyin.com/user/MS4wLjABAAAA-terminal-complete";
  const terminalCompleteStaleWorkflow = {
    ...idle,
    profile_url: terminalProfileUrl,
    workflow: {
      ...idle.workflow,
      scan: { status: "running" as const, started_at: "2026-07-06T12:00:00.000Z", updated_at: "2026-07-06T12:00:00.000Z", completed_at: null, last_error: null }
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed" as const,
      profile_identifier: profileIdentifierFromUrl(terminalProfileUrl),
      total_persisted: 143,
      expected_count: 143
    },
    profile_scan: { ...idle.profile_scan, status: "success" as const, accepted_target_count: 143 }
  };
  assert.equal(
    collectPresentationSuppressed(terminalCompleteStaleWorkflow),
    false,
    "terminal completed scan must not keep collect presentation suppressed when workflow.scan is stale running"
  );
  const cleared = clearStaleCollectBlockDiagnostics({
    start_collecting_blocked_reason: "No pending video is available for collection.",
    scan_progress_discovered: 140
  });
  assert.equal(cleared.start_collecting_blocked_reason, null);
  assert.equal(cleared.scan_progress_discovered, 140, "clearStaleCollectBlockDiagnostics must preserve non-collect fields");
  const overcleared = clearStaleOvercollectionDiagnostics({
    over_displayed_count: 1,
    count_semantics_status: "overcollected_needs_validation",
    hybrid_network_cache_mode_flag: "enabled"
  });
  assert.equal(overcleared.over_displayed_count, null);
  assert.equal(overcleared.count_semantics_status, null);
  assert.equal(overcleared.hybrid_network_cache_mode_flag, "enabled", "clearStaleOvercollectionDiagnostics must preserve unrelated fields");
}

{
  const profileP1 = "https://www.douyin.com/user/MS4wLjABAAAA41XPPYoeuqQyDtXDLltg7aBWchubmMBfEErR88VDm99210SJeDG1Qp1YattZ7Qnv";
  const profileP2 = "https://www.douyin.com/user/MS4wLjABAAAAb-BPHWbjdOJEohoTQ8CE2LINAaJNTh7FWpJIk8y4hsqzKBYhfnu2t52ak5cp9O4h";
  const p1Done = completedProfileState("41XPPYoeuqQyDtXDLltg7aBWchubmMBfEErR88VDm99210SJeDG1Qp1YattZ7Qnv", 140);
  assert.equal(detectProfileContextMismatch({ ...p1Done, profile_url: profileP1 }, profileP2), true);
  assert.equal(resolveScanProfileResetMode({ ...p1Done, profile_url: profileP1 }, profileP2), "new_profile");
  const blockedVm = getScannerControlPanelViewModel({
    ...p1Done,
    profile_url: profileP2,
    harvest: { ...p1Done.harvest, queue: [], pending: 0 },
    scan_job: {
      ...p1Done.scan_job,
      profile_identifier: profileIdentifierFromUrl(profileP2),
      total_persisted: 0,
      status: "completed"
    },
    layer: { ...p1Done.layer, profile_scan_ready: false },
    profile_scan: { ...createWholeProfileHarvestIdleState("2026-07-06T12:00:00.000Z").profile_scan, status: "idle" },
    classification: createWholeProfileHarvestIdleState("2026-07-06T12:00:00.000Z").classification,
    debug: {
      ...p1Done.debug,
      last_action_clicked: "start_collecting",
      last_action_result: "blocked",
      last_response_summary: {
        start_collecting_blocked_reason: "No pending video is available for collection."
      }
    }
  }, { active_tab_url: profileP2, app_backend_logged_in: true });
  assert.equal(blockedVm.primaryAction.key, "scan_profile", "P2 session with empty queue must route to Scan Profile");
  assert.notEqual(blockedVm.emptyState, "No pending video is available for collection.", "stale No pending video copy must not paint after profile switch");
  assert.notEqual(blockedVm.primaryAction.title, "Start Collecting", "blocked empty queue must not keep Start Collecting as primary title");
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-11T04:00:00.000Z");
  assert.equal(shouldHoldScanPresentationForRescan(idle), false, "first scan must not hold stale presentation");

  const rescanReady: WholeProfileHarvestState = {
    ...idle,
    profile_url: "https://www.douyin.com/user/MS4wLjABRESCAN",
    profile_scan: { ...idle.profile_scan, status: "success" },
    scan_job: { ...idle.scan_job, status: "completed", total_persisted: 354, expected_count: 354 },
    post_scan_counter_snapshot: {
      status: "applied",
      scanned_total: 354,
      new: 354,
      queue: 354,
      already_collected: 0,
      applied_at: "2026-07-11T03:00:00.000Z"
    }
  };
  assert.equal(shouldHoldScanPresentationForRescan(rescanReady), true, "same-profile rescan must hold presentation anchors");
}

{
  const profileQueue = "https://www.douyin.com/user/MS4wLjABQUEUE";
  const idle = createWholeProfileHarvestIdleState("2026-07-11T05:00:00.000Z");
  assert.equal(
    scanQueueProvesSessionCompleteForPresentation({
      ...idle,
      profile_url: profileQueue,
      classification: { ...idle.classification, status: "success" },
      workflow: { ...idle.workflow, classification: { ...idle.workflow.classification, status: "success" } },
      scan_job: { ...idle.scan_job, total_persisted: 366, profile_identifier: profileIdentifierFromUrl(profileQueue) },
      harvest: {
        ...idle.harvest,
        queue: [{
          index: 0,
          aweme_id: "aweme_1",
          capture_status: "pending",
          status: "new",
          attempts: 0,
          checkpoint_sequence: null,
          extraction_result: null,
          last_error: null,
          capture_inbox_item_id: null,
          source_url: profileQueue,
          profile_card_evidence: {}
        }]
      }
    }, profileQueue),
    true
  );
}

console.log("wholeProfileHarvest profile context tests passed");
