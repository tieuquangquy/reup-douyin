import assert from "node:assert/strict";

import { profileIdentifierFromUrl } from "./wholeProfileHarvest/profileTargetRepository.js";
import {
  normalizeScanProgressPhaseLabel,
  resolveScanPresentationPhase,
  scanFinalizingTimedOut,
  scanIncompleteUnderExpectedForPresentation,
  scanJobVisiblyActive,
  scanPaginationExhaustedWithPersisted,
  scanSessionCompleteForPresentation
} from "./wholeProfileHarvest/scanPresentationPhase.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

const profileFull = "https://www.douyin.com/user/MS4wLjABAAAA-profile-full";
const profilePartial = "https://www.douyin.com/user/MS4wLjABAAAA-profile-partial";

function failedFullCountState(): WholeProfileHarvestState {
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  return {
    ...idle,
    status: "failed",
    phase: "scan_finished",
    profile_url: profileFull,
    layer: { ...idle.layer, profile_scan_ready: false },
    workflow: {
      ...idle.workflow,
      scan: { status: "failed", started_at: "t", updated_at: "t", completed_at: "t", last_error: "x" }
    },
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profileFull),
      total_persisted: 1007,
      expected_count: 1007,
      has_more_state: true,
      completed_at: "2026-07-10T14:05:00.000Z"
    },
    profile_scan: { ...idle.profile_scan, status: "failed", accepted_target_count: 1007 },
    verify: { ...idle.verify, status: "failed", verified_target_count: 1007, accepted_target_count: 1007 },
    harvest: { ...idle.harvest, queue: [], planned_total: 1007, pending: 1007 }
  };
}

{
  assert.equal(normalizeScanProgressPhaseLabel("Finalizing scan"), "Finalizing");
  assert.equal(normalizeScanProgressPhaseLabel(null, { scanActive: true, atFullProgress: true }), "Finalizing");
  assert.equal(
    normalizeScanProgressPhaseLabel("Scanning profile", { scanActive: true, atFullProgress: true }),
    "Scanning profile",
    "explicit scanning phase label must stay until backend reports finalizing"
  );
}

{
  const state = failedFullCountState();
  assert.equal(scanSessionCompleteForPresentation(state, profileFull), true);
  const resolution = resolveScanPresentationPhase(state, { active_tab_url: profileFull });
  assert.equal(resolution.phase, "calibrate_required");
  assert.equal(resolution.suppressPartialRescanOverlay, true);
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  const partial: WholeProfileHarvestState = {
    ...idle,
    status: "failed",
    phase: "scan_finished",
    profile_url: profilePartial,
    workflow: { ...idle.workflow, scan: { status: "failed", started_at: "t", updated_at: "t", completed_at: "t", last_error: "x" } },
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profilePartial),
      total_persisted: 143,
      expected_count: 200,
      has_more_state: true,
      completed_at: "2026-07-10T14:05:00.000Z"
    },
    profile_scan: { ...idle.profile_scan, status: "failed", accepted_target_count: 143 },
    harvest: { ...idle.harvest, queue: [], planned_total: 143, pending: 143 }
  };
  const resolution = resolveScanPresentationPhase(partial, { active_tab_url: profilePartial });
  assert.equal(resolution.phase, "scan_partial_failed");
  assert.equal(resolution.suppressPartialRescanOverlay, false);
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  const exhausted: WholeProfileHarvestState = {
    ...idle,
    phase: "scan_finished",
    profile_url: profileFull,
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profileFull),
      total_persisted: 1007,
      expected_count: null,
      has_more_state: false,
      completed_at: "2026-07-10T14:05:00.000Z"
    },
    profile_scan: { ...idle.profile_scan, accepted_target_count: 1007 },
    harvest: { ...idle.harvest, planned_total: 1007, pending: 1007 }
  };
  assert.equal(scanPaginationExhaustedWithPersisted(exhausted, profileFull), true);
  assert.equal(resolveScanPresentationPhase(exhausted, { active_tab_url: profileFull }).phase, "calibrate_required");
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  const nearIncomplete: WholeProfileHarvestState = {
    ...idle,
    status: "verified",
    phase: "scan_finished",
    profile_url: profilePartial,
    profile_scan: {
      ...idle.profile_scan,
      status: "success",
      accepted_target_count: 199,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 203,
        profile_queue_total_count: 199,
        missing_profile_video_count: 4,
        scan_finalization_result: "incomplete"
      }
    },
    verify: {
      ...idle.verify,
      status: "success",
      verified_target_count: 199,
      accepted_target_count: 199
    },
    workflow: {
      ...idle.workflow,
      scan: { status: "success", started_at: "t", updated_at: "t", completed_at: "t", last_error: null }
    },
    scan_job: {
      ...idle.scan_job,
      status: "completed",
      profile_identifier: profileIdentifierFromUrl(profilePartial),
      total_persisted: 199,
      expected_count: 203
    }
  };
  assert.equal(scanIncompleteUnderExpectedForPresentation(nearIncomplete, profilePartial), true);
  assert.equal(scanSessionCompleteForPresentation(nearIncomplete, profilePartial), false);
  assert.equal(resolveScanPresentationPhase(nearIncomplete, { active_tab_url: profilePartial }).phase, "scan_partial_failed");
}

{
  const profileQueueReady = "https://www.douyin.com/user/MS4wLjABAAAA-profile-queue-ready";
  const idle = createWholeProfileHarvestIdleState("2026-07-11T05:00:00.000Z");
  const queueReadyFailedFinalize: WholeProfileHarvestState = {
    ...idle,
    status: "failed",
    phase: "scan_finished",
    profile_url: profileQueueReady,
    workflow: {
      ...idle.workflow,
      scan: { status: "failed", started_at: "t", updated_at: "t", completed_at: "t", last_error: "paginated_scan_incomplete" },
      classification: { ...idle.workflow.classification, status: "success", completed_at: "t" }
    },
    classification: { ...idle.classification, status: "success", total_candidates: 366 },
    scan_job: {
      ...idle.scan_job,
      status: "failed",
      profile_identifier: profileIdentifierFromUrl(profileQueueReady),
      total_persisted: 366,
      expected_count: 400,
      has_more_state: true
    },
    profile_scan: { ...idle.profile_scan, status: "failed", accepted_target_count: 366 },
    harvest: {
      ...idle.harvest,
      queue: [{
        index: 0,
        aweme_id: "aweme_queue_ready_1",
        capture_status: "pending",
        status: "new",
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: profileQueueReady,
        profile_card_evidence: { profile_url: profileQueueReady }
      }],
      planned_total: 366,
      pending: 366
    }
  };
  assert.equal(scanSessionCompleteForPresentation(queueReadyFailedFinalize, profileQueueReady), true, "actionable queue + classification must not trap rescan when finalize failed");
  assert.notEqual(
    resolveScanPresentationPhase(queueReadyFailedFinalize, { active_tab_url: profileQueueReady }).phase,
    "scan_partial_failed",
    "failed finalize with collectable queue must route to calibrate/collect not rescan loop"
  );
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  const running = {
    ...idle,
    phase: "canonical_scan_starting",
    scan_job: { ...idle.scan_job, status: "running" as const }
  };
  assert.equal(scanJobVisiblyActive(running), true);
  const resolution = resolveScanPresentationPhase(running, { active_tab_url: profileFull }, {
    scanProgressActive: true,
    scanProgressPhaseLabel: "Finalizing scan",
    scanProgressAtFull: true
  });
  assert.equal(resolution.phase, "scan_finalizing");
}

{
  const idle = createWholeProfileHarvestIdleState("2026-07-10T14:00:00.000Z");
  const stuckFinalizing = {
    ...idle,
    updated_at: "2026-07-10T12:00:00.000Z",
    phase: "canonical_scan_starting",
    scan_job: { ...idle.scan_job, status: "running" as const },
    profile_scan: {
      ...idle.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_progress_updated_at: "2026-07-10T12:00:00.000Z"
      }
    }
  };
  assert.equal(scanFinalizingTimedOut(stuckFinalizing, {
    scanProgressActive: true,
    scanProgressPhaseLabel: "Finalizing scan",
    scanProgressAtFull: true,
    nowMs: Date.parse("2026-07-10T14:05:00.000Z")
  }), true, "finalizing must time out when profile_scan_ready never arrives");
  assert.equal(scanFinalizingTimedOut({
    ...stuckFinalizing,
    layer: { ...stuckFinalizing.layer, profile_scan_ready: true }
  }, {
    scanProgressActive: true,
    scanProgressPhaseLabel: "Finalizing scan",
    scanProgressAtFull: true,
    nowMs: Date.parse("2026-07-10T14:05:00.000Z")
  }), false, "completed scan must not report finalizing timeout");
  const runningWithoutFinalizeClock = {
    ...idle,
    updated_at: "2026-05-06T12:00:00.000Z",
    phase: "scan_running",
    scan_job: { ...idle.scan_job, status: "running" as const, total_persisted: 996, expected_count: 996 },
    debug: {
      ...idle.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_progress_discovered: 996,
        scan_progress_expected: 996,
        scan_progress_phase_label: "Scanning profile"
      }
    }
  };
  assert.equal(scanFinalizingTimedOut(runningWithoutFinalizeClock, {
    scanProgressActive: true,
    scanProgressAtFull: true,
    nowMs: Date.parse("2026-07-11T02:00:00.000Z")
  }), false, "active running scan without finalize clock must not time out from stale state.updated_at");
}

console.info("scanPresentationPhase.test.ts: all assertions passed");
