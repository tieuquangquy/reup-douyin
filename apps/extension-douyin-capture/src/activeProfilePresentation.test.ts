import assert from "node:assert/strict";

import {
  activeProfileRevisitHasEvidence,
  activeProfileRevisitPresentationActive,
  buildActiveProfileRepositorySnapshot,
  resolveActiveProfilePresentation
} from "./wholeProfileHarvest/activeProfilePresentation.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import { profileIdentifierFromUrl } from "./wholeProfileHarvest/profileTargetRepository.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

const profileP1 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p1";
const profileP2 = "https://www.douyin.com/user/MS4wLjABAAAA-profile-p2";

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
      profile_identifier: profileIdentifierFromUrl(profileUrl),
      has_more_state: false
    },
    layer: { ...idle.layer, profile_scan_ready: true }
  };
}

{
  const repo = buildActiveProfileRepositorySnapshot("profile-p1", {
    total: 739,
    counts: [
      { status: "new", count: 120 },
      { status: "pending", count: 80 },
      { status: "already_collected", count: 500 }
    ],
    degraded: false,
    degraded_reason: null
  });
  assert.equal(repo.scanned_total, 739);
  assert.equal(activeProfileRevisitHasEvidence({ inbox: null, repository: repo, sessionEntry: null }), true);
}

{
  const p1Id = profileIdentifierFromUrl(profileP1);
  const p2Stored = {
    ...completedProfileState("profile-p2", 200),
    profile_url: profileP2
  };
  const presentation = resolveActiveProfilePresentation({
    state: p2Stored,
    activeTabUrl: profileP1,
    inbox: {
      total_count: 739,
      already_collected: 736,
      new_count: 3,
      queue_count: 3,
      incomplete_count: 0,
      inbox_needs_review_count: 0,
      need_retry_count: 0,
      captured_total: 736,
      trusted: true
    },
    repository: buildActiveProfileRepositorySnapshot(p1Id, {
      total: 739,
      counts: [{ status: "pending", count: 739 }],
      degraded: false,
      degraded_reason: null
    }),
    sessionEntry: null
  });
  assert.ok(presentation);
  assert.equal(presentation?.mode, "revisit_mismatch");
  assert.equal(presentation?.has_prior_scan, true);
  assert.equal(presentation?.already_collected, 736);
  assert.match(presentation?.primary_label ?? "", /Rescan profile/i);
  assert.notEqual(presentation?.new_count, 0);
  assert.notEqual(presentation?.already_collected, 0);
}

{
  const p1Id = profileIdentifierFromUrl(profileP1);
  const p2Stored = {
    ...completedProfileState("profile-p2", 200),
    profile_url: profileP2
  };
  const vm = getScannerControlPanelViewModel(p2Stored, {
    active_tab_url: profileP1,
    app_backend_logged_in: true,
    active_profile_presentation: resolveActiveProfilePresentation({
      state: p2Stored,
      activeTabUrl: profileP1,
      inbox: {
        total_count: 739,
        already_collected: 736,
        new_count: 3,
        queue_count: 3,
        incomplete_count: 0,
        inbox_needs_review_count: 0,
        need_retry_count: 0,
        captured_total: 736,
        trusted: true
      },
      repository: buildActiveProfileRepositorySnapshot(p1Id, {
        total: 739,
        counts: [{ status: "pending", count: 739 }],
        degraded: false,
        degraded_reason: null
      }),
      sessionEntry: null
    })
  });
  assert.equal(vm.primaryAction.key, "scan_profile");
  assert.match(vm.primaryAction.label, /Rescan profile/i);
  assert.equal(vm.counts.alreadyCollectedCount, 736);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true);
  assert.notEqual(vm.headerStatus, "Scan required");
}

{
  const p1Id = profileIdentifierFromUrl(profileP1);
  const p2Stored = {
    ...completedProfileState("profile-p2", 200),
    profile_url: profileP2
  };
  const repository = buildActiveProfileRepositorySnapshot(p1Id, {
    total: 739,
    counts: [{ status: "pending", count: 739 }],
    degraded: false,
    degraded_reason: null
  });
  const presentation = resolveActiveProfilePresentation({
    state: p2Stored,
    activeTabUrl: profileP1,
    inbox: null,
    repository,
    sessionEntry: null
  });
  assert.equal(activeProfileRevisitPresentationActive(presentation), true, "repository scanned_total must activate revisit presentation");
  const vm = getScannerControlPanelViewModel(p2Stored, {
    active_tab_url: profileP1,
    app_backend_logged_in: true,
    active_profile_presentation: presentation,
    active_profile_repository_snapshot: repository
  });
  assert.equal(vm.scanDataVisible, true);
  assert.notEqual(vm.counts.newCount + vm.counts.queueCount, 0);
  assert.notEqual(vm.headerStatus, "Scan required");
}

{
  const profileA = "https://www.douyin.com/user/MS4wLjABAAAA-profile-a";
  const idle = createWholeProfileHarvestIdleState("2026-07-10T12:00:00.000Z");
  const incompleteRescan: WholeProfileHarvestState = {
    ...idle,
    status: "failed",
    phase: "scan_finished",
    profile_url: profileA,
    layer: { ...idle.layer, profile_scan_ready: false },
    workflow: {
      ...idle.workflow,
      scan: { status: "failed", started_at: "2026-07-10T12:00:00.000Z", updated_at: "2026-07-10T12:05:00.000Z", completed_at: "2026-07-10T12:05:00.000Z", last_error: "paginated_scan_incomplete" }
    },
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profileA),
      total_persisted: 143,
      expected_count: 200,
      has_more_state: true,
      completed_at: "2026-07-10T12:05:00.000Z"
    },
    profile_scan: {
      ...idle.profile_scan,
      status: "failed",
      accepted_target_count: 143
    },
    verify: {
      ...idle.verify,
      status: "failed",
      verified_target_count: 143,
      accepted_target_count: 143
    },
    harvest: { ...idle.harvest, queue: [], queue_preview: [], planned_total: 143, pending: 143 },
    debug: {
      ...idle.debug,
      last_response_summary: {
        scan_completeness_ready_blocked: "yes",
        lastScannerResult: "incomplete",
        profile_queue_total_count: 143
      }
    }
  };
  const vm = getScannerControlPanelViewModel(incompleteRescan, { active_tab_url: profileA, app_backend_logged_in: true });
  assert.equal(vm.scanDataVisible, true);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true);
  assert.notEqual(vm.headerStatus, "Scan required");
  assert.match(vm.primaryAction.label, /Rescan profile/i);
}

{
  const profileFull = "https://www.douyin.com/user/MS4wLjABAAAA-profile-full";
  const idle = createWholeProfileHarvestIdleState("2026-07-10T13:00:00.000Z");
  const fullCountFailedFinalize: WholeProfileHarvestState = {
    ...idle,
    status: "failed",
    phase: "scan_finished",
    profile_url: profileFull,
    layer: { ...idle.layer, profile_scan_ready: false },
    workflow: {
      ...idle.workflow,
      scan: { status: "failed", started_at: "2026-07-10T13:00:00.000Z", updated_at: "2026-07-10T13:05:00.000Z", completed_at: "2026-07-10T13:05:00.000Z", last_error: "paginated_scan_incomplete" }
    },
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profileFull),
      total_persisted: 1007,
      expected_count: 1007,
      has_more_state: true,
      completed_at: "2026-07-10T13:05:00.000Z"
    },
    profile_scan: {
      ...idle.profile_scan,
      status: "failed",
      accepted_target_count: 1007
    },
    verify: {
      ...idle.verify,
      status: "failed",
      verified_target_count: 1007,
      accepted_target_count: 1007
    },
    harvest: { ...idle.harvest, queue: [], queue_preview: [], planned_total: 1007, pending: 1007 },
    debug: {
      ...idle.debug,
      last_response_summary: {
        scan_completeness_ready_blocked: "yes",
        lastScannerResult: "failed",
        profile_queue_total_count: 1007,
        expected_profile_video_count: 1007
      }
    }
  };
  const vm = getScannerControlPanelViewModel(fullCountFailedFinalize, { active_tab_url: profileFull, app_backend_logged_in: true });
  assert.equal(vm.scanDataVisible, true);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true);
  assert.doesNotMatch(vm.primaryAction.label, /Rescan profile/i);
  assert.match(vm.primaryAction.label, /Calibrate/i);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true);
}

{
  const profileRescan = "https://www.douyin.com/user/MS4wLjABAAAA-profile-rescan";
  const idle = createWholeProfileHarvestIdleState("2026-07-10T15:00:00.000Z");
  const rescanCompleteEmptyQueue: WholeProfileHarvestState = {
    ...idle,
    status: "verified",
    phase: "scan_finished",
    profile_url: profileRescan,
    layer: { ...idle.layer, profile_scan_ready: true },
    workflow: {
      ...idle.workflow,
      scan: { status: "success", started_at: "t", updated_at: "t", completed_at: "t", last_error: null }
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed",
      profile_identifier: profileIdentifierFromUrl(profileRescan),
      total_persisted: 1007,
      expected_count: 1007,
      has_more_state: false,
      completed_at: "2026-07-10T15:05:00.000Z"
    },
    profile_scan: {
      ...idle.profile_scan,
      status: "success",
      accepted_target_count: 1007,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        profile_queue_total_count: 1007,
        expected_profile_video_count: 1007,
        scan_finalization_result: "success"
      }
    },
    verify: {
      ...idle.verify,
      status: "success",
      verified_target_count: 1007,
      accepted_target_count: 1007
    },
    harvest: { ...idle.harvest, queue: [], queue_preview: [], planned_total: 1007, pending: 1007 },
    post_scan_counter_snapshot: {
      status: "applied",
      already_collected: 0,
      new: 0,
      queue: 0,
      backend_captured: 0,
      source: "scan_finalize",
      applied_at: "2026-07-10T15:05:00.000Z"
    },
    debug: {
      ...idle.debug,
      last_response_summary: {
        profile_queue_total_count: 1007,
        expected_profile_video_count: 1007,
        scan_finalization_result: "success"
      }
    }
  };
  const vm = getScannerControlPanelViewModel(rescanCompleteEmptyQueue, {
    active_tab_url: profileRescan,
    app_backend_logged_in: true
  });
  assert.match(vm.primaryAction.label, /Calibrate/i);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true, "persisted scan totals must restore tiles after rescan");
  assert.doesNotMatch(vm.headerStatus, /^Scan required$/);
}

{
  const profileCal = "https://www.douyin.com/user/MS4wLjABAAAA-profile-cal";
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:10:00.000Z");
  const calibrateReady: WholeProfileHarvestState = {
    ...idle,
    status: "verified",
    phase: "scan_finished",
    profile_url: profileCal,
    layer: { ...idle.layer, profile_scan_ready: true },
    workflow: {
      ...idle.workflow,
      scan: { status: "success", started_at: "t", updated_at: "t", completed_at: "t", last_error: null }
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed",
      profile_identifier: profileIdentifierFromUrl(profileCal),
      total_persisted: 354,
      expected_count: 354,
      has_more_state: false,
      completed_at: "2026-07-10T14:05:00.000Z"
    },
    profile_scan: { ...idle.profile_scan, status: "success", accepted_target_count: 354 },
    harvest: { ...idle.harvest, queue: [], planned_total: 354, pending: 354 }
  };
  const vm = getScannerControlPanelViewModel(calibrateReady, { active_tab_url: profileCal, app_backend_logged_in: true });
  assert.match(vm.primaryAction.label, /Calibrate/i);
  assert.equal(vm.counts.newCount > 0 || vm.counts.queueCount > 0, true);
  assert.doesNotMatch(vm.primaryAction.label, /Rescan profile/i);

  const calibratedReady: WholeProfileHarvestState = {
    ...calibrateReady,
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      source_url: profileCal,
      profile_url: profileCal,
      aweme_id: "1234567890123456",
      points: {
        like: { x: 1, y: 1 },
        comment: { x: 2, y: 2 },
        favorite: { x: 3, y: 3 },
        share: { x: 4, y: 4 }
      },
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null,
      updated_at: "2026-07-10T14:10:00.000Z"
    },
    classification: {
      ...idle.classification,
      status: "success",
      profile_url: profileCal,
      sec_uid: "MS4wLjABAAAA-profile-cal",
      collect_aweme_ids: Array.from({ length: 354 }, (_, index) => `aweme-${index}`)
    },
    verify: { ...idle.verify, status: "success", verified_target_count: 354, accepted_target_count: 354 },
    layer: { ...idle.layer, profile_scan_ready: true }
  };
  const collectVm = getScannerControlPanelViewModel(calibratedReady, { active_tab_url: profileCal, app_backend_logged_in: true });
  assert.equal(collectVm.primaryAction.key, "start_collecting", "after calibration empty queue must offer Start Collecting, not Scan Profile");
  assert.match(collectVm.primaryAction.label, /Collect|Start Collecting/i);
  assert.notEqual(collectVm.primaryAction.label, "Scan Profile");
  assert.equal(collectVm.counts.newCount, 354);
  assert.equal(collectVm.counts.queueCount, 354);
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T12:00:00.000Z");
  const p1Id = profileIdentifierFromUrl(profileP1);
  const p2Stored = {
    ...completedProfileState("profile-p2", 200),
    profile_url: profileP2
  };
  const repository = buildActiveProfileRepositorySnapshot(p1Id, {
    total: 739,
    counts: [{ status: "pending", count: 739 }],
    degraded: false,
    degraded_reason: null
  });
  const presentation = resolveActiveProfilePresentation({
    state: p2Stored,
    activeTabUrl: profileP1,
    inbox: null,
    repository,
    sessionEntry: null
  });
  assert.equal(activeProfileRevisitPresentationActive(presentation), true, "repository scanned_total must activate revisit presentation");
  const vm = getScannerControlPanelViewModel(p2Stored, {
    active_tab_url: profileP1,
    app_backend_logged_in: true,
    active_profile_presentation: presentation,
    active_profile_repository_snapshot: repository
  });
  assert.equal(vm.scanDataVisible, true);
  assert.notEqual(vm.counts.newCount + vm.counts.queueCount, 0);
  assert.notEqual(vm.headerStatus, "Scan required");
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T12:00:00.000Z");
  assert.equal(
    activeProfileRevisitPresentationActive(resolveActiveProfilePresentation({
      state: idle,
      activeTabUrl: profileP1,
      inbox: null,
      repository: null,
      sessionEntry: null
    })),
    false
  );
}

{
  const profileA = "https://www.douyin.com/user/MS4wLjABAAAA-profile-a-1007";
  const profileB = "https://www.douyin.com/user/MS4wLjABAAAA-profile-b-1127";
  const aId = profileIdentifierFromUrl(profileA);
  const bId = profileIdentifierFromUrl(profileB);
  const staleSession = {
    ...completedProfileState("profile-b-1127", 1127),
    profile_url: profileA,
    classification: {
      ...createWholeProfileHarvestIdleState("2026-07-10T12:00:00.000Z").classification,
      status: "success",
      sec_uid: "MS4wLjABAAAA-profile-a-1007"
    },
    scan_job: {
      ...completedProfileState("profile-b-1127", 1127).scan_job,
      profile_identifier: bId,
      total_persisted: 1127,
      expected_count: 1127
    },
    layer: { ...completedProfileState("profile-b-1127", 1127).layer, profile_scan_ready: true }
  };
  const repository = buildActiveProfileRepositorySnapshot(aId, {
    total: 1007,
    counts: [{ status: "new", count: 1007 }],
    degraded: false,
    degraded_reason: null
  });
  const presentation = resolveActiveProfilePresentation({
    state: staleSession,
    activeTabUrl: profileA,
    inbox: {
      total_count: 1127,
      already_collected: 0,
      new_count: 1127,
      queue_count: 1127,
      incomplete_count: 0,
      inbox_needs_review_count: 0,
      need_retry_count: 0,
      captured_total: 0,
      trusted: true
    },
    repository,
    sessionEntry: null
  });
  assert.ok(presentation, "stale scan_job profile_identifier must force revisit presentation");
  assert.equal(presentation?.scanned_total, 1007, "repository must win over stale inbox totals");
  assert.equal(presentation?.new_count, 1007);
  assert.equal(presentation?.queue_count, 1007);
  assert.match(presentation?.primary_label ?? "", /Rescan profile/i);

  const vm = getScannerControlPanelViewModel(staleSession, {
    active_tab_url: profileA,
    app_backend_logged_in: true,
    active_profile_presentation: presentation,
    active_profile_repository_snapshot: repository
  });
  assert.notEqual(vm.counts.newCount, 1127, "must not show another profile persisted total");
  assert.equal(vm.counts.newCount, 1007);
  assert.equal(vm.counts.queueCount, 1007);
  assert.match(vm.primaryAction.label ?? "", /Rescan profile/i);
}

{
  const profileA = "https://www.douyin.com/user/MS4wLjABAAAA-profile-a-143";
  const idle = createWholeProfileHarvestIdleState("2026-07-11T02:00:00.000Z");
  const revisitAfterCompleteScan: WholeProfileHarvestState = {
    ...completedProfileState("profile-a-143", 143),
    profile_url: profileA,
    phase: "scan_finished",
    workflow: {
      ...idle.workflow,
      scan: {
        status: "running",
        started_at: "2026-07-11T01:00:00.000Z",
        updated_at: "2026-07-11T01:05:00.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...completedProfileState("profile-a-143", 143).scan_job,
      status: "completed",
      profile_identifier: profileIdentifierFromUrl(profileA),
      total_persisted: 143,
      expected_count: 143,
      has_more_state: false,
      page_count: 12,
      total_discovered: 143
    },
    harvest: {
      ...idle.harvest,
      queue: [],
      queue_preview: [],
      planned_total: 143,
      pending: 143
    },
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      source_url: profileA,
      profile_url: profileA,
      aweme_id: "1234567890123456",
      points: {
        like: { x: 1, y: 1 },
        comment: { x: 2, y: 2 },
        favorite: { x: 3, y: 3 },
        share: { x: 4, y: 4 }
      },
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null,
      updated_at: "2026-07-11T02:00:00.000Z"
    },
    classification: {
      ...idle.classification,
      status: "success",
      profile_url: profileA,
      sec_uid: "MS4wLjABAAAA-profile-a-143",
      collect_aweme_ids: Array.from({ length: 143 }, (_, index) => `aweme-${index}`)
    },
    verify: {
      ...idle.verify,
      status: "success",
      verified_target_count: 143,
      accepted_target_count: 143
    }
  };
  const vm = getScannerControlPanelViewModel(revisitAfterCompleteScan, {
    active_tab_url: profileA,
    app_backend_logged_in: true
  });
  assert.equal(vm.primaryAction.key, "start_collecting", "completed profile revisit must offer Start Collecting, not a fresh Scan Profile");
  assert.notEqual(vm.primaryAction.label, "Scan Profile", "stale workflow.scan running must not block collect after a completed scan");
  assert.equal(vm.counts.newCount, 143, "persisted scan totals must restore revisit tiles when harvest queue is empty");
  assert.equal(vm.counts.queueCount, 143);
  assert.notEqual(vm.emptyState, "Scan a profile to build the collection plan.");
}

{
  const p1Id = profileIdentifierFromUrl(profileP1);
  const p2Stored = {
    ...completedProfileState("profile-p2", 102),
    profile_url: profileP2
  };
  const completeInbox = {
    total_count: 143,
    already_collected: 143,
    new_count: 0,
    queue_count: 0,
    incomplete_count: 0,
    inbox_needs_review_count: 0,
    need_retry_count: 0,
    captured_total: 143,
    trusted: true as const
  };
  const presentation = resolveActiveProfilePresentation({
    state: p2Stored,
    activeTabUrl: profileP1,
    inbox: completeInbox,
    repository: null,
    sessionEntry: null
  });
  assert.ok(presentation);
  assert.equal(presentation?.mode, "revisit_mismatch");
  assert.equal(presentation?.already_collected, 143);
  assert.equal(presentation?.new_count, 0);
  assert.equal(presentation?.queue_count, 0);
  assert.equal(presentation?.primary_label, "Open Capture Inbox");
  assert.match(presentation?.primary_description ?? "", /143 videos are ready/i);

  const vm = getScannerControlPanelViewModel(p2Stored, {
    active_tab_url: profileP1,
    app_backend_logged_in: true,
    active_profile_inbox_summary: completeInbox,
    active_profile_presentation: presentation
  });
  assert.equal(vm.primaryAction.key, "open_capture_inbox");
  assert.equal(vm.primaryAction.label, "Open Capture Inbox");
  assert.equal(vm.counts.alreadyCollectedCount, 143);
  assert.equal(vm.counts.newCount, 0);
  assert.equal(vm.counts.queueCount, 0);
  assert.equal(vm.health.calibration, "Cal ready");
  assert.match(vm.profileContext?.banner_message ?? "", /143 videos collected in Capture Inbox/i);
}

console.info("activeProfilePresentation.test.ts: all assertions passed");

