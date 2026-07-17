import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { deriveAuthoritativeRunnerLock } from "./wholeProfileHarvest/authoritativePopupState.js";
import { clearProfileScanState } from "./wholeProfileHarvest/controller.js";
import { applyHybridNetworkCacheModeFlagToState, getCanonicalCalibrationReady, getCanonicalScannerPrimaryAction, getDouyinScannerBusyState, getDouyinScannerWorkflowReadiness, getWholeProfileHarvestActionState, getWholeProfileHarvestReadiness, isCollectCalibrationSatisfied, isCollectionRunnerActive, isDouyinCalibrationReady, isHybridNetworkCacheModeEnabledForCollect, preserveOperatorCollectPrerequisitesInDiagnostics } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

const readinessSource = readFileSync(new URL("./wholeProfileHarvest/readiness.ts", import.meta.url), "utf8");

function baseState(): WholeProfileHarvestState {
  return createWholeProfileHarvestIdleState("2026-05-06T10:00:00.000Z");
}

function withVerified(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    status: "verified",
    profile_scan: {
      ...state.profile_scan,
      status: "success",
      accepted_target_count: 55
    },
    verify: {
      ...state.verify,
      status: "success",
      accepted_target_count: 55,
      verified_target_count: 55
    },
    workflow: {
      ...state.workflow,
      scan: {
        ...state.workflow.scan,
        status: "success",
        started_at: "2026-05-06T10:00:00.000Z",
        updated_at: "2026-05-06T10:00:10.000Z",
        completed_at: "2026-05-06T10:00:10.000Z",
        last_error: null
      }
    }
  };
}

function canonicalCalibrationPoints(): Record<string, unknown> {
  return {
    like: { x: 100, y: 200 },
    comment: { x: 100, y: 260 },
    favorite: { x: 100, y: 320 },
    share: { x: 100, y: 380 }
  };
}

function withCalibration(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      source_url: "https://www.douyin.com/user/MS4wLjABAAAA_fixture",
      profile_url: "https://www.douyin.com/user/MS4wLjABAAAA_fixture",
      points: canonicalCalibrationPoints(),
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null
    }
  };
}

function withDryRunSuccess(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    dry_run: {
      ...state.dry_run,
      status: "success",
      pass: 3,
      fail: 0
    }
  };
}

function hybridFixtureQueueEvidence(): Record<string, unknown> {
  return {
    duration_seconds: 12,
    like_count: 1,
    comment_count: 0,
    favorite_count: 0,
    share_count: 0
  };
}

function withClassificationReady(state: WholeProfileHarvestState, collect = 10): WholeProfileHarvestState {
  return {
    ...state,
    classification: {
      ...state.classification,
      status: "success",
      started_at: "2026-05-06T10:00:10.000Z",
      completed_at: "2026-05-06T10:00:20.000Z",
      schema_version: "douyin_profile_video_classification_result.v1",
      collection_mode: "new_incomplete_failed",
      database_lookup_status: "ok",
      total_candidates: 55,
      counts: { new: 8, incomplete: 1, complete: 44, failed: 1, skipped: 1, unknown: 0, collect, skip: 45 },
      targets: [],
      collect_aweme_ids: Array.from({ length: collect }, (_, index) => `76341927335145010${String(index).padStart(2, "0")}`),
      skip_aweme_ids: [],
      diagnostics: { fixture: true }
    },
    workflow: {
      ...state.workflow,
      scan: {
        ...state.workflow.scan,
        status: "success",
        started_at: "2026-05-06T10:00:00.000Z",
        updated_at: "2026-05-06T10:00:10.000Z",
        completed_at: "2026-05-06T10:00:10.000Z",
        last_error: null
      },
      classification: {
        ...state.workflow.classification,
        status: "success",
        started_at: "2026-05-06T10:00:10.000Z",
        updated_at: "2026-05-06T10:00:20.000Z",
        completed_at: "2026-05-06T10:00:20.000Z",
        last_error: null
      }
    },
    harvest: {
      ...state.harvest,
      queue: Array.from({ length: collect }, (_, index) => ({
        index: index + 1,
        aweme_id: `76341927335145010${String(index).padStart(2, "0")}`,
        capture_status: index === collect - 1 ? "failed" as const : "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/76341927335145010${String(index).padStart(2, "0")}`,
        profile_card_evidence: hybridFixtureQueueEvidence()
      }))
    }
  };
}

function withExtractedResult(state: WholeProfileHarvestState, awemeId = "7634192733514501001"): WholeProfileHarvestState {
  return {
    ...state,
    harvest: {
      ...state.harvest,
      results: [
        {
          index: 1,
          aweme_id: awemeId,
          status: "extracted",
          stage: "build_payload",
          attempts: 1,
          checkpoint_sequence: 1,
          error: null,
          error_code: null,
          error_message: null,
          modal_opened: true,
          modal_id_matched: true,
          metrics_extracted: true,
          payload_built: true,
          backend_called: false,
          backend_status: null,
          backend_error_code: null,
          capture_inbox_item_id: null,
          target_url: `https://www.douyin.com/video/${awemeId}`,
          data_integrity_status: "passed",
          profile_card_evidence: {},
          started_at: "2026-05-06T10:00:00.000Z",
          completed_at: "2026-05-06T10:01:00.000Z",
          duration_seconds: 20,
          duration_text: "00:20",
          like_count: 10,
          comment_count: 2,
          favorite_count: 1,
          share_count: 1,
          current_modal_id_before: awemeId,
          current_modal_id_after: awemeId,
          extracted_aweme_id: awemeId,
          source_used: "calibrated_point_dom"
        }
      ]
    }
  };
}

function withBackendReady(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    capture_session_id: "session_1",
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        capture_session: {
          ...state.harvest.backend.capture_session,
          status: "ready",
          session_id: "session_1"
        }
      }
    }
  };
}

function withPayloadPreview(state: WholeProfileHarvestState, guardOk: boolean): WholeProfileHarvestState {
  return {
    ...state,
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        payload_preview: {
          ...state.harvest.backend.payload_preview,
          status: guardOk ? "ready" : "guard_failed",
          target_aweme_id: "7634192733514501001",
          removed_fields: [],
          guard: { ok: guardOk, offending_paths: [] },
          payload: { aweme_id: "7634192733514501001" },
          summary: { aweme_id: "7634192733514501001" }
        }
      }
    }
  };
}

{
  const readiness = getWholeProfileHarvestReadiness(withDryRunSuccess(withVerified(baseState())));
  assert.equal(readiness.dry_run_ready, true);
}

{
  const actions = getWholeProfileHarvestActionState(baseState());
  assert.equal(actions.verifyProfile.enabled, true, "Scan Profile must be enabled when no canonical scanner task is running");
  assert.equal(actions.verifyProfile.disabledReason, null);
}

{
  const state: WholeProfileHarvestState = {
    ...baseState(),
    profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    debug: {
      ...baseState().debug,
      last_response_summary: {
        profile_queue_total_count: 25,
        lastScannerResult: "incomplete",
        scan_finalization_result: "incomplete"
      }
    }
  };
  const readiness = getWholeProfileHarvestReadiness(state);
  assert.equal(readiness.profile_scan_ready, false, "incomplete finalization must override collected>=20 heuristic");
}


{
  const nearCompleteState: WholeProfileHarvestState = {
    ...baseState(),
    profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    status: "failed",
    phase: "scan_finished",
    scan_job: {
      ...baseState().scan_job,
      status: "failed",
      has_more_state: true,
      total_persisted: 991,
      total_discovered: 991,
      expected_count: 996,
      remaining_estimate: 5,
      last_status_code: 0,
      last_error: "expected_gap_unresolved_strict_completeness_gate"
    },
    workflow: {
      ...baseState().workflow,
      scan: { ...baseState().workflow.scan, status: "failed", completed_at: "2026-05-06T10:00:10.000Z", last_error: "expected_gap_unresolved_strict_completeness_gate" }
    },
    classification: {
      ...baseState().classification,
      status: "success",
      total_candidates: 991,
      counts: { ...baseState().classification.counts, new: 991, collect: 991 },
      collect_aweme_ids: ["7634192733514501001"]
    },
    harvest: {
      ...baseState().harvest,
      queue: [{ index: 1, aweme_id: "7634192733514501001", capture_status: "new", status: "pending", attempts: 0, checkpoint_sequence: null, extraction_result: null, last_error: null, capture_inbox_item_id: null, source_url: "https://www.douyin.com/video/7634192733514501001", profile_card_evidence: {} }]
    },
    profile_scan: {
      ...baseState().profile_scan,
      status: "failed",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 996,
        scan_job_total_persisted: 991,
        scan_completeness_missing_count: 5,
        scan_finalization_result: "incomplete",
        lastScannerResult: "incomplete",
        active_profile_post_fetch_response_status_code: 0,
        large_profile_mode: "yes",
        queue_total_persisted: 991,
        profile_url: "https://www.douyin.com/user/MS4wLjABCD"
      }
    },
    verify: {
      ...baseState().verify,
      status: "failed",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 996,
        scan_job_total_persisted: 991,
        scan_completeness_missing_count: 5,
        scan_finalization_result: "incomplete",
        lastScannerResult: "incomplete",
        active_profile_post_fetch_response_status_code: 0,
        large_profile_mode: "yes",
        queue_total_persisted: 991,
        profile_url: "https://www.douyin.com/user/MS4wLjABCD"
      }
    }
  };
  const readiness = getDouyinScannerWorkflowReadiness(nearCompleteState);
  const primary = getCanonicalScannerPrimaryAction(nearCompleteState);
  assert.equal(readiness.profileScanReady, true, "near-complete small-gap scan must be usable even if terminal status was failed with has_more=true");
  assert.equal(readiness.classificationReady, true);
  assert.equal(readiness.collectQueueReady, true);
  assert.equal(primary.key, "calibrate", "near-complete scan without calibration should advance to Calibrate, not Scan Profile");
}

{
  const warningState: WholeProfileHarvestState = {
    ...baseState(),
    profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    status: "verified",
    phase: "scan_finished",
    scan_job: {
      ...baseState().scan_job,
      status: "completed",
      total_persisted: 991,
      total_discovered: 991,
      expected_count: 996,
      remaining_estimate: 5,
      last_status_code: 0,
      last_error: null
    },
    workflow: {
      ...baseState().workflow,
      scan: { ...baseState().workflow.scan, status: "success", completed_at: "2026-05-06T10:00:10.000Z", last_error: null }
    },
    classification: {
      ...baseState().classification,
      status: "success",
      total_candidates: 991,
      counts: { ...baseState().classification.counts, new: 991, collect: 991 },
      collect_aweme_ids: ["7634192733514501001"]
    },
    harvest: {
      ...baseState().harvest,
      queue: [{ index: 1, aweme_id: "7634192733514501001", capture_status: "new", status: "pending", attempts: 0, checkpoint_sequence: null, extraction_result: null, last_error: null, capture_inbox_item_id: null, source_url: "https://www.douyin.com/video/7634192733514501001", profile_card_evidence: {} }]
    },
    profile_scan: {
      ...baseState().profile_scan,
      status: "success",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 996,
        scan_job_total_persisted: 991,
        scan_completeness_missing_count: 5,
        scan_finalization_result: "completed_with_warning",
        lastScannerResult: "completed_with_warning",
        active_profile_post_fetch_response_status_code: 0,
        queue_total_persisted: 991,
        queue_total_visible: 1,
        profile_url: "https://www.douyin.com/user/MS4wLjABCD"
      }
    },
    verify: { ...baseState().verify, status: "success", verified_target_count: 991, accepted_target_count: 991 }
  };
  const readiness = getDouyinScannerWorkflowReadiness(warningState);
  const primary = getCanonicalScannerPrimaryAction(warningState);
  assert.equal(readiness.profileScanReady, true, "completed_with_warning near-complete scan must be usable");
  assert.equal(readiness.classificationReady, true, "completed_with_warning near-complete scan must not route back through classification-required Scan Profile");
  assert.equal(readiness.collectQueueReady, true);
  assert.equal(primary.key, "calibrate", "completed_with_warning near-complete scan without calibration should advance to Calibrate");
}

{
  const staleScanState: WholeProfileHarvestState = {
    ...baseState(),
    workflow: {
      ...baseState().workflow,
      scan: {
        ...baseState().workflow.scan,
        status: "running",
        started_at: "2026-05-06T09:55:00.000Z",
        updated_at: "2026-05-06T09:55:00.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    updated_at: "2026-05-06T09:55:00.000Z"
  };
  const busy = getDouyinScannerBusyState(staleScanState, Date.parse("2026-05-06T10:00:00.000Z"));
  const actions = getWholeProfileHarvestActionState(staleScanState);
  assert.equal(busy.isStale, true);
  assert.equal(busy.isBusy, false);
  assert.equal(busy.busyReason, "Previous scan was interrupted. Please scan again.");
  assert.equal(actions.verifyProfile.enabled, true, "stale scan locks must not block Scan Profile");
  assert.notEqual(actions.verifyProfile.disabledReason, "Wait for the current step to finish.");
}

{
  const activeScanState: WholeProfileHarvestState = {
    ...baseState(),
    workflow: {
      ...baseState().workflow,
      scan: {
        ...baseState().workflow.scan,
        status: "running",
        started_at: "2030-05-07T11:43:00.000Z",
        updated_at: "2030-05-07T11:43:00.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    updated_at: "2030-05-07T11:43:00.000Z"
  };
  const busy = getDouyinScannerBusyState(activeScanState, Date.parse("2030-05-07T11:43:30.000Z"));
  assert.equal(busy.isBusy, true);
  assert.equal(busy.busySource, "scan.status");
  assert.equal(busy.busyReason, "Wait for the current step to finish.");
  assert.equal(busy.disabledLabel, "Scanning...");
  const actions = getWholeProfileHarvestActionState(activeScanState);
  assert.equal(actions.verifyProfile.enabled, false);
  assert.equal(actions.verifyProfile.disabledReason, null);
  assert.equal(actions.verifyProfile.label, "Scanning...");
}

{
  const staleLegacyHarvest: WholeProfileHarvestState = {
    ...baseState(),
    harvest: { ...baseState().harvest, status: "running", started_at: null, updated_at: null }
  };
  const busy = getDouyinScannerBusyState(staleLegacyHarvest, Date.parse("2026-05-06T10:00:00.000Z"));
  const actions = getWholeProfileHarvestActionState(staleLegacyHarvest);
  assert.equal(busy.isStale, false);
  assert.equal(busy.isBusy, false);
  assert.equal(actions.verifyProfile.enabled, true, "legacy running harvest without active timestamps must not block new scanner UI");
}

{
  const stalePausedState: WholeProfileHarvestState = {
    ...withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3),
    status: "paused",
    workflow: {
      ...withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3).workflow,
      collection: {
        ...withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3).workflow.collection,
        status: "paused",
        started_at: "2026-05-06T10:00:00.000Z",
        updated_at: "2026-05-06T10:01:00.000Z",
        completed_at: null,
        last_error: null
      }
    },
    harvest: {
      ...withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3).harvest,
      status: "paused",
      resume_available: false
    }
  };
  const primary = getCanonicalScannerPrimaryAction(stalePausedState);
  assert.equal(primary.key, "start_collecting", "stale non-resumable paused state must recover to Start/Continue Collecting instead of disabled Resume");
  assert.notEqual(primary.disabledReason, "No paused run to resume.");
}

{
  const pausedState: WholeProfileHarvestState = {
    ...withDryRunSuccess(withCalibration(withVerified(baseState()))),
    status: "paused",
    workflow: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow,
      collection: {
        ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow.collection,
        status: "paused",
        started_at: "2026-05-06T10:00:00.000Z",
        updated_at: "2026-05-06T10:01:00.000Z",
        completed_at: null,
        last_error: null
      }
    },
    harvest: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).harvest,
      status: "paused",
      resume_available: true
    }
  };
  const busy = getDouyinScannerBusyState(pausedState, Date.parse("2026-05-06T10:00:00.000Z"));
  const actions = getWholeProfileHarvestActionState(pausedState);
  assert.equal(busy.isBusy, false, "paused state must not count as busy");
  assert.equal(actions.resume.visible, true);
  assert.equal(actions.resume.enabled, true);
}

{
  const readiness = getWholeProfileHarvestReadiness(withCalibration(withVerified(baseState())));
  assert.equal(readiness.calibration_ready, true);
  assert.notEqual(readiness.next_recommended_action.code, "calibrate_4_points");
}

{
  assert.equal(isDouyinCalibrationReady({ status: "calibrated", point_count: 0, source_key: null, viewport_warning: null }), false, "calibrated status alone must not fake readiness without four points");
  assert.equal(isDouyinCalibrationReady({ calibrationStatus: "calibrated" }), false, "legacy calibrated status alone must not fake readiness without four points");
  assert.equal(isDouyinCalibrationReady({ ready: true }), false, "ready flag alone must not fake canonical readiness");
  assert.equal(isDouyinCalibrationReady({ pointCount: 4 }), false, "legacy point count alone must not fake canonical readiness");
  assert.equal(isDouyinCalibrationReady({ status: "calibrated", point_count: 4, source_key: null, viewport_warning: null }), false, "point count without canonical points must not fake readiness");
  assert.equal(isDouyinCalibrationReady({ calibrationStatus: "calibrated", point_count: 4 }), false, "legacy status and count still require persisted points");
  assert.equal(isDouyinCalibrationReady({ status: "calibrated", ready: true, point_count: 4, source_key: null, viewport_warning: null, points: canonicalCalibrationPoints() }), true);
  assert.equal(isDouyinCalibrationReady({ calibrationStatus: "calibrated", point_count: 4, points: { like_count: {}, comment_count: {}, favorite_count: {}, share_count: {} } }), true, "legacy calibrated records are accepted only when all points are present");
  assert.equal(isDouyinCalibrationReady({ status: "unknown", point_count: 0, source_key: null, viewport_warning: null, points: { like_count: {}, comment_count: {}, favorite_count: {}, share_count: {} } }), false, "points without calibrated status must not fake readiness");
  assert.equal(isDouyinCalibrationReady({ status: "unknown", point_count: 0, source_key: null, viewport_warning: null, points: canonicalCalibrationPoints() }), false, "canonical points still require canonical calibrated status");
  assert.equal(isDouyinCalibrationReady({ status: "missing", point_count: 0, source_key: null, viewport_warning: null, points: { like_count: {}, comment_count: {}, favorite_count: {}, share_count: {} } }), false, "stale missing status must not override canonical readiness");
  assert.equal(isDouyinCalibrationReady({ status: "unknown", point_count: 3, source_key: null, viewport_warning: null, points: { like_count: {}, comment_count: {}, favorite_count: {} } }), false);
}

{
  const actions = getWholeProfileHarvestActionState(withCalibration(withVerified(baseState())));
  assert.equal(actions.dryRunRandom.enabled, true);
  assert.notEqual(actions.dryRunRandom.disabledReason, "Calibrate 4 Points first.");
}

{
  const state = withVerified(baseState());
  const readiness = getWholeProfileHarvestReadiness(state);
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(readiness.dry_run_ready, false);
  assert.equal(actions.flushOneItem.enabled, false);
  assert.equal(actions.flushOneItem.disabledReason, "Create a scan session first.");
}

{
  const state = withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState())))));
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.flushOneItem.enabled, false);
  assert.equal(actions.flushOneItem.disabledReason, "Run a data check first.");
}

{
  const state = withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), false);
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.flushOneItem.enabled, false);
  assert.equal(actions.flushOneItem.disabledReason, "Data check failed. Fix save data before saving.");
}

{
  const state = withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), true);
  const readiness = getWholeProfileHarvestReadiness(state);
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(readiness.one_item_flush_ready, true);
  assert.equal(actions.flushOneItem.enabled, true);
}

{
  const state = withBackendReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.flushBatch.enabled, false);
  assert.equal(actions.flushBatch.disabledReason, "No extracted videos are ready to save.");
}

{
  const state = withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState())))));
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.flushBatch.enabled, false);
  assert.equal(actions.flushBatch.disabledReason, "Save 1 Video first to verify Capture Inbox write.");
}

{
  const state = {
    ...withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), true),
    harvest: {
      ...withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), true).harvest,
      backend: {
        ...withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), true).harvest.backend,
        one_item_flush: {
          ...withPayloadPreview(withBackendReady(withExtractedResult(withDryRunSuccess(withCalibration(withVerified(baseState()))))), true).harvest.backend.one_item_flush,
          status: "succeeded" as const,
          capture_inbox_item_id: "inbox_1",
          item_created_or_updated: true
        }
      }
    }
  };
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.flushBatch.enabled, true);
}

{
  const actions = getWholeProfileHarvestActionState(baseState());
  assert.equal(actions.resume.visible, false);
  assert.equal(actions.resume.enabled, false);
}

{
  const state: WholeProfileHarvestState = {
    ...withDryRunSuccess(withCalibration(withVerified(baseState()))),
    status: "paused",
    workflow: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow,
      collection: {
        ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow.collection,
        status: "paused"
      }
    },
    harvest: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).harvest,
      status: "paused",
      resume_available: true
    }
  };
  const actions = getWholeProfileHarvestActionState(state);
  assert.equal(actions.resume.visible, true);
  assert.equal(actions.resume.enabled, true);
}

{
  const idle = getWholeProfileHarvestActionState(baseState());
  const running = getWholeProfileHarvestActionState({
    ...withDryRunSuccess(withCalibration(withVerified(baseState()))),
    status: "harvesting",
    workflow: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow,
      collection: {
        ...withDryRunSuccess(withCalibration(withVerified(baseState()))).workflow.collection,
        status: "running",
        started_at: "2030-05-07T11:43:00.000Z",
        updated_at: "2030-05-07T11:43:00.000Z"
      }
    },
    harvest: {
      ...withDryRunSuccess(withCalibration(withVerified(baseState()))).harvest,
      status: "running",
      started_at: "2030-05-07T11:43:00.000Z",
      updated_at: "2030-05-07T11:43:00.000Z"
    },
    updated_at: "2030-05-07T11:43:00.000Z"
  });
  assert.equal(idle.stop.enabled, false);
  assert.equal(running.stop.enabled, true);
}

{
  const beforeClassification = getWholeProfileHarvestActionState(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const afterClassification = getWholeProfileHarvestActionState(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState())))));
  const emptyClassification = getWholeProfileHarvestActionState(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 0));
  assert.equal(beforeClassification.runHarvest.enabled, false);
  assert.equal(beforeClassification.runHarvest.disabledReason, "Scan Profile first.");
  assert.equal(afterClassification.runHarvest.enabled, true);
  assert.equal(emptyClassification.runHarvest.enabled, false);
  assert.equal(emptyClassification.runHarvest.disabledReason, "No videos are queued for collection.");
}

{
  const noScan = getWholeProfileHarvestReadiness(baseState());
  assert.equal(noScan.next_recommended_action.code, "verify_profile");

  const calibratedNoScan = getWholeProfileHarvestReadiness(withCalibration(baseState()));
  assert.equal(calibratedNoScan.next_recommended_action.code, "verify_profile");

  const afterScan = getWholeProfileHarvestReadiness(withCalibration(withVerified(baseState())));
  assert.equal(afterScan.next_recommended_action.code, "verify_profile");
  assert.equal(afterScan.next_recommended_action.label, "Scan Profile");

  const afterDryRun = getWholeProfileHarvestReadiness(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  assert.equal(afterDryRun.next_recommended_action.code, "verify_profile");

  const afterClassification = getWholeProfileHarvestReadiness(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState())))));
  assert.equal(afterClassification.next_recommended_action.code, "run_extraction");

  const afterExtraction = getWholeProfileHarvestReadiness(withExtractedResult(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))))));
  assert.equal(afterExtraction.next_recommended_action.code, "prepare_backend_session");

  const afterGuard = getWholeProfileHarvestReadiness(withPayloadPreview(withBackendReady(withExtractedResult(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState())))))), true));
  assert.equal(afterGuard.next_recommended_action.code, "flush_one_item");
}

{
  const actions = getWholeProfileHarvestActionState(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState())))));
  assert.equal(actions.runHarvest.label, "Extract Next 10");
}

{
  const canonicalWins = getCanonicalCalibrationReady({
    calibration: {
      status: "calibrated",
      ready: true,
      point_count: 4,
      source_key: null,
      viewport_warning: null,
      points: canonicalCalibrationPoints(),
      calibrationStatus: "missing_points"
    }
  });
  assert.deepEqual(canonicalWins, {
    ready: true,
    source: "canonical",
    canonicalReady: true,
    legacyReady: false,
    conflict: true
  }, "canonical calibration helper must prefer full canonical readiness even when legacy flags disagree");
}

{
  const uncalibratedNoScan = getCanonicalScannerPrimaryAction(baseState());
  assert.equal(uncalibratedNoScan.key, "scan_profile", "missing calibration must not outrank missing profile scan");
  assert.equal(uncalibratedNoScan.enabled, true, "Scan Profile must be enabled before calibration");
  assert.equal(uncalibratedNoScan.decisionTrace.reason, "profile_scan_required_before_calibration");
  assert.equal(uncalibratedNoScan.decisionTrace.selector_version, "22C-11B");
  assert.equal(uncalibratedNoScan.decisionTrace.selected_action, "scan_profile");
  assert.equal(uncalibratedNoScan.decisionTrace.canonicalCalibrationReady, false);
}

{
  const calibratedNoScan = getCanonicalScannerPrimaryAction(withCalibration(baseState()));
  assert.equal(calibratedNoScan.key, "scan_profile", "calibrated fresh profile still scans before collecting");
  assert.equal(calibratedNoScan.decisionTrace.profileScanReady, false);
}

{
  const blockedPartialScan: WholeProfileHarvestState = {
    ...withCalibration(baseState()),
    profile_url: "https://www.douyin.com/user/MS4wLjABBLOCKED",
    harvest: {
      ...baseState().harvest,
      queue: Array.from({ length: 25 }, (_, index) => ({
        index: index + 1,
        aweme_id: `763419273351452${String(index).padStart(3, "0")}`,
        capture_status: "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/763419273351452${String(index).padStart(3, "0")}`,
        profile_card_evidence: {}
      }))
    },
    profile_scan: {
      ...baseState().profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        profile_queue_total_count: 25,
        expected_profile_video_count: 200,
        missing_profile_video_count: 175,
        scan_completeness_gate_result: "blocked",
        scan_completeness_ready_blocked: "yes",
        scan_completeness_dom_only_fallback: "yes",
        scan_completeness_active_fetch_meaningful: "no",
        lastScannerResult: "incomplete",
        scan_finalization_result: "incomplete"
      }
    }
  };
  const readiness = getWholeProfileHarvestReadiness(blockedPartialScan);
  const primary = getCanonicalScannerPrimaryAction(blockedPartialScan);
  assert.equal(readiness.profile_scan_ready, false, "blocked severe DOM-only fallback must not become scan-ready through collected>=20");
  assert.equal(primary.key, "scan_profile", "blocked severe DOM-only fallback must retry Scan Profile instead of routing to calibration/collection");
  assert.notEqual(primary.label, "Calibrate 4 Points");
}

{
  const endpointSeenWithoutSource: WholeProfileHarvestState = {
    ...withCalibration(baseState()),
    profile_url: "https://www.douyin.com/user/MS4wLjAB_ENDPOINT_MISSING",
    profile_scan: {
      ...baseState().profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 200,
        profile_queue_total_count: 44,
        missing_profile_video_count: 156,
        network_profile_post_batch_count: 3,
        network_profile_post_unique_count: 36,
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        active_profile_post_template_warmup_stop_reason: "profile_post_endpoint_seen_but_source_url_missing",
        active_profile_post_fetch_not_attempted_reason: "profile_post_endpoint_seen_but_source_url_missing",
        active_profile_post_fetch_request_count: 0,
        active_profile_post_fetch_page_count: 0,
        active_profile_post_fetch_endpoint_variant_attempt_count: 0,
        scan_completeness_gate_result: "blocked",
        scan_completeness_ready_blocked: "yes",
        scan_completeness_dom_only_fallback: "yes",
        scan_completeness_active_fetch_meaningful: "no",
        scan_completeness_gate_reason: "profile_post_endpoint_seen_but_source_url_missing",
        lastScannerResult: "incomplete",
        scan_finalization_result: "incomplete"
      }
    }
  };
  const readiness = getWholeProfileHarvestReadiness(endpointSeenWithoutSource);
  const primary = getCanonicalScannerPrimaryAction(endpointSeenWithoutSource);
  assert.equal(readiness.profile_scan_ready, false, "profile-post endpoint evidence without source URL must not silently become scan-ready");
  assert.equal(primary.key, "scan_profile", "missing source URL keeps Scan Profile as the primary action");
  assert.match(primary.disabledReason ?? "profile_post_endpoint_seen_but_source_url_missing", /profile-post source failed|profile_post_endpoint_seen_but_source_url_missing|Scan Profile/, "primary action must expose an active source problem instead of DOM-only success");
}

{
  const legacyOverrideAttempt = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 44);
  const guardedLegacyOverride: WholeProfileHarvestState = {
    ...legacyOverrideAttempt,
    profile_url: "https://www.douyin.com/user/MS4wLjAB_LEGACY_OVERRIDE",
    profile_scan: {
      ...legacyOverrideAttempt.profile_scan,
      status: "success",
      accepted_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 995,
        profile_queue_total_count: 44,
        missing_profile_video_count: 951,
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        active_profile_post_fetch_not_attempted_reason: "profile_post_endpoint_seen_but_source_url_missing",
        scan_queue_builder_used: "dom_probe_known_good_fallback_22C9K",
        scan_fallback_used: "yes",
        scan_completeness_active_fetch_meaningful: "no",
        scan_completeness_dom_only_fallback: "yes",
        scan_completeness_ready_blocked: "yes",
        scan_completeness_gate_result: "blocked",
        scan_completeness_gate_reason: "active_profile_post_incomplete_dom_only_undercollection",
        lastScannerResult: "incomplete",
        scan_finalization_result: "incomplete"
      }
    },
    verify: {
      ...legacyOverrideAttempt.verify,
      status: "success",
      accepted_target_count: 44,
      verified_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 995,
        profile_queue_total_count: 44,
        missing_profile_video_count: 951,
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        scan_queue_builder_used: "dom_probe_known_good_fallback_22C9K",
        scan_fallback_used: "yes",
        scan_completeness_active_fetch_meaningful: "no",
        scan_completeness_dom_only_fallback: "yes",
        scan_completeness_ready_blocked: "yes",
        scan_completeness_gate_result: "blocked",
        lastScannerResult: "incomplete",
        scan_finalization_result: "incomplete"
      }
    }
  };
  const readiness = getWholeProfileHarvestReadiness(guardedLegacyOverride);
  const primary = getCanonicalScannerPrimaryAction(guardedLegacyOverride);
  assert.equal(readiness.profile_scan_ready, false, "legacy DOM queue success fields cannot override canonical active incomplete diagnostics");
  assert.equal(primary.key, "scan_profile", "legacy queue builder must not route canonical incomplete scans to calibration or collection");
}

{
  const successfulActiveScan = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 55);
  const readiness = getWholeProfileHarvestReadiness({
    ...successfulActiveScan,
    profile_url: "https://www.douyin.com/user/MS4wLjAB_ACTIVE_SUCCESS",
    profile_scan: {
      ...successfulActiveScan.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 55,
        profile_queue_total_count: 55,
        missing_profile_video_count: 0,
        active_profile_post_template_found: "yes",
        active_profile_post_template_required_query_keys_available: "yes",
        active_profile_post_fetch_request_count: 3,
        active_profile_post_fetch_page_count: 3,
        active_profile_post_fetch_endpoint_variant_attempt_count: 1,
        scan_completeness_active_fetch_meaningful: "yes",
        scan_completeness_dom_only_fallback: "no",
        scan_completeness_ready_blocked: "no",
        scan_finalization_result: "success"
      }
    }
  });
  assert.equal(readiness.profile_scan_ready, true, "successful active profile-post scan must still become scan-ready");
}

{
  const smallGapActiveScan = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 49);
  const readiness = getWholeProfileHarvestReadiness({
    ...smallGapActiveScan,
    profile_url: "https://www.douyin.com/user/MS4wLjAB_ACTIVE_SMALL_GAP",
    profile_scan: {
      ...smallGapActiveScan.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 50,
        profile_queue_total_count: 49,
        missing_profile_video_count: 1,
        active_profile_post_template_found: "yes",
        active_profile_post_template_required_query_keys_available: "yes",
        active_profile_post_fetch_request_count: 3,
        active_profile_post_fetch_page_count: 3,
        active_profile_post_fetch_endpoint_variant_attempt_count: 1,
        scan_completeness_active_fetch_meaningful: "yes",
        scan_completeness_dom_only_fallback: "no",
        scan_completeness_ready_blocked: "no",
        scan_finalization_result: "success"
      }
    }
  });
  assert.equal(readiness.profile_scan_ready, true, "small-gap active profile-post scan must remain accepted when the active source was meaningful");
}

{
  const queuedMissingCalibration = getCanonicalScannerPrimaryAction(withClassificationReady(withDryRunSuccess(withVerified(baseState()))));
  assert.equal(queuedMissingCalibration.key, "calibrate", "after scan queue exists, missing calibration asks for 4-point calibration");
  assert.equal(queuedMissingCalibration.decisionTrace.reason, "validated_same_profile_api_overdisplay_warning_continue_to_calibration");
}

{
  // Hybrid network-cache collect does not use modal DOM points — skip Calibrate
  // and route Scan Profile → Start Collecting when the operator flag is on.
  const scannedNoCalibration = withClassificationReady(withDryRunSuccess(withVerified(baseState())));
  assert.equal(isHybridNetworkCacheModeEnabledForCollect(scannedNoCalibration), false);
  assert.equal(isCollectCalibrationSatisfied(scannedNoCalibration), false);

  const hybridEnabled = applyHybridNetworkCacheModeFlagToState(scannedNoCalibration, true);
  assert.equal(isHybridNetworkCacheModeEnabledForCollect(hybridEnabled), true);
  assert.equal(isCollectCalibrationSatisfied(hybridEnabled), true);
  assert.equal(isDouyinCalibrationReady(hybridEnabled.calibration), false, "actual 4-point calibration remains incomplete");

  const workflow = getDouyinScannerWorkflowReadiness(hybridEnabled);
  assert.equal(workflow.calibrationReady, true, "hybrid mode satisfies collect calibration gate");
  assert.equal(workflow.nextActionKey, "start_collecting");
  assert.equal(workflow.canStartCollecting, true);

  const primary = getCanonicalScannerPrimaryAction(hybridEnabled);
  assert.equal(primary.key, "start_collecting", "hybrid mode must skip Calibrate 4 Points primary action");
  assert.notEqual(primary.title, "Calibrate 4 Points");

  const readiness = getWholeProfileHarvestReadiness(hybridEnabled);
  assert.equal(readiness.calibration_ready, true);

  const hybridDisabled = applyHybridNetworkCacheModeFlagToState(hybridEnabled, false);
  assert.equal(getCanonicalScannerPrimaryAction(hybridDisabled).key, "calibrate", "turning hybrid off restores calibration gate");
}

{
  // Rescan reset must not wipe operator collect prerequisites (hybrid flag, dry-run, calibration).
  const hybridScanned = applyHybridNetworkCacheModeFlagToState(
    withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 383),
    true
  );
  const clearedHybrid = clearProfileScanState(hybridScanned, "reset:current_profile_rescan");
  assert.equal(isHybridNetworkCacheModeEnabledForCollect(clearedHybrid), true, "rescan clear must preserve hybrid_network_cache_mode_flag");
  assert.equal(isCollectCalibrationSatisfied(clearedHybrid), true);
  assert.equal(getCanonicalCalibrationReady(clearedHybrid).ready, true, "calibration must survive profile scan reset");

  const postRescanHybridComplete: WholeProfileHarvestState = {
    ...clearedHybrid,
    layer: { ...clearedHybrid.layer, profile_scan_ready: true },
    profile_scan: {
      ...hybridScanned.profile_scan,
      status: "success",
      diagnostics: {
        ...hybridScanned.profile_scan.diagnostics,
        scan_finalization_result: "success",
        profile_queue_total_count: 383,
        expected_profile_video_count: 383
      }
    },
    classification: hybridScanned.classification,
    harvest: hybridScanned.harvest,
    workflow: {
      ...hybridScanned.workflow,
      scan: hybridScanned.workflow.scan,
      classification: hybridScanned.workflow.classification
    },
    scan_job: {
      ...clearedHybrid.scan_job,
      status: "completed",
      total_persisted: 383,
      expected_count: 383,
      has_more_state: false
    }
  };
  assert.equal(getDouyinScannerWorkflowReadiness(postRescanHybridComplete).calibrationReady, true);
  assert.equal(getCanonicalScannerPrimaryAction(postRescanHybridComplete).key, "start_collecting", "post-rescan must match first-scan Start Collecting when hybrid was already on");

  const postScanRuntimeDiagnostics = {
    diagnostics_channel: "runtime_debug_diagnostics",
    scan_run_id: "scan_profile_rescan_2",
    scan_finalization_result: "success",
    scan_finalized_at: "2026-05-06T10:05:00.000Z",
    profile_queue_total_count: 354
  };
  const preservedDiagnostics = preserveOperatorCollectPrerequisitesInDiagnostics(hybridScanned, postScanRuntimeDiagnostics);
  assert.equal(preservedDiagnostics.hybrid_network_cache_mode_flag, "enabled", "scan finalize must preserve hybrid flag from pre-scan state");

  const wipedWithoutStateMirror = preserveOperatorCollectPrerequisitesInDiagnostics(
    withClassificationReady(withDryRunSuccess(withVerified(baseState())), 354),
    postScanRuntimeDiagnostics,
    { hybridNetworkCacheModeEnabled: true }
  );
  assert.equal(wipedWithoutStateMirror.hybrid_network_cache_mode_flag, "enabled", "scan finalize must fall back to chrome.storage hybrid toggle when diagnostics mirrors were wiped");

  const postScanWipedSummaries: WholeProfileHarvestState = {
    ...postRescanHybridComplete,
    debug: {
      ...postRescanHybridComplete.debug,
      last_response_summary: preservedDiagnostics,
      last_request_summary: preservedDiagnostics
    }
  };
  assert.equal(isHybridNetworkCacheModeEnabledForCollect(postScanWipedSummaries), true);
  assert.equal(getCanonicalScannerPrimaryAction(postScanWipedSummaries).key, "start_collecting", "post-rescan scan finalize must not trap hybrid operators on Calibrate");

  const dryRunOnly = withClassificationReady(withDryRunSuccess(withVerified(baseState())), 100);
  const clearedDryRun = clearProfileScanState(dryRunOnly, "reset:current_profile_rescan");
  assert.equal(clearedDryRun.dry_run.status, "success");
  assert.equal(clearedDryRun.layer.dry_run_ready, true);
  assert.equal(isCollectCalibrationSatisfied(clearedDryRun), true, "successful dry-run must survive rescan reset");
}

{
  // Stale overcollection diagnostics without a finished scan must not trap the operator on Review.
  const staleReviewTrap = applyHybridNetworkCacheModeFlagToState(baseState(), true);
  const staleState: WholeProfileHarvestState = {
    ...staleReviewTrap,
    profile_url: "https://www.douyin.com/user/MS4wLjABSTALE",
    page_context: {
      ...staleReviewTrap.page_context,
      current_url: "https://www.douyin.com/user/MS4wLjABSTALE"
    },
    debug: {
      ...staleReviewTrap.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        hybrid_network_cache_mode_flag: "enabled",
        over_displayed_count: 1,
        count_semantics_status: "overcollected_needs_validation",
        over_displayed_validation_status: "needs_validation"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(staleState);
  const primary = getCanonicalScannerPrimaryAction(staleState);
  assert.equal(workflow.nextActionKey, "scan_profile", "stale +1 overcollection without queue must route to Scan Profile");
  assert.equal(primary.key, "scan_profile", "stale overcollection must not block scan with Review primary action");
}

{
  // Benign single same-profile overdisplay should auto-validate and unlock collect.
  const benignSingle = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 143);
  const benignState: WholeProfileHarvestState = {
    ...benignSingle,
    run_id: "run_benign_single_overdisplay",
    scan_job: {
      ...benignSingle.scan_job,
      scan_job_id: "run_benign_single_overdisplay",
      total_persisted: 143,
      expected_count: 142,
      status: "completed",
      has_more_state: false
    },
    profile_scan: {
      ...benignSingle.profile_scan,
      status: "success",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_benign_single_overdisplay",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 1,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_source: "accepted_target_ledger_boundary_tail",
        over_displayed_extra_ids_exact: ["763419273351450199"],
        over_displayed_extra_items_exact: [{ aweme_id: "763419273351450199", same_profile_validated: "yes" }],
        count_semantics_status: "overcollected_needs_validation",
        scan_finalization_result: "completed_with_warning"
      }
    },
    verify: {
      ...benignSingle.verify,
      status: "success",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_benign_single_overdisplay",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 1,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_source: "accepted_target_ledger_boundary_tail",
        scan_finalization_result: "completed_with_warning"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(benignState);
  assert.equal(workflow.nextActionKey, "start_collecting", "benign +1 same-profile overdisplay must not require manual review");
}

{
  // All remaining complete: large profile persisted total exists but tiles show
  // New=0 Queue=0 — primary must be Open Capture Inbox, not Start Collecting.
  const hybridScanned = applyHybridNetworkCacheModeFlagToState(
    withClassificationReady(withDryRunSuccess(withVerified(baseState())), 0),
    true
  );
  const allRemainingCompleteState: WholeProfileHarvestState = {
    ...hybridScanned,
    harvest_options: { ...hybridScanned.harvest_options, batch: "all_remaining", batch_limit: "all" },
    scan_job: {
      ...hybridScanned.scan_job,
      status: "completed",
      total_persisted: 365,
      expected_count: 365,
      has_more_state: false
    },
    harvest: {
      ...hybridScanned.harvest,
      pending: 0,
      queue: [],
      queue_preview: []
    },
    classification: {
      ...hybridScanned.classification,
      status: "success",
      collect_aweme_ids: []
    },
    profile_scan: {
      ...hybridScanned.profile_scan,
      diagnostics: {
        ...(hybridScanned.profile_scan.diagnostics && typeof hybridScanned.profile_scan.diagnostics === "object"
          ? hybridScanned.profile_scan.diagnostics as Record<string, unknown>
          : {}),
        large_profile_mode: "yes",
        queue_total_persisted: 365,
        scan_job_total_persisted: 365,
        profile_queue_total_count: 365,
        scan_finalization_result: "success"
      }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA_fixture",
      scanned_total: 365,
      backend_captured: 365,
      backend_ready: 365,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 365,
      incomplete: 0,
      need_retry: 0,
      new: 0,
      queue: 0,
      applied_at: "2026-05-06T12:00:00.000Z"
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(allRemainingCompleteState);
  const primary = getCanonicalScannerPrimaryAction(allRemainingCompleteState);
  assert.equal(workflow.nextActionKey, "open_capture_inbox", "empty actionable queue after all-remaining collect must route to Capture Inbox");
  assert.equal(primary.key, "open_capture_inbox");
  assert.equal(primary.label, "Open Capture Inbox");
  assert.equal(primary.enabled, true);
  assert.equal(workflow.canStartCollecting, false, "Start Collecting must be disabled when nothing remains");
}

{
  const validatedSameProfileState = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 44);
  const state: WholeProfileHarvestState = {
    ...validatedSameProfileState,
    run_id: "run_validated_same_profile_ready",
    scan_job: {
      ...validatedSameProfileState.scan_job,
      scan_job_id: "run_validated_same_profile_ready",
      total_persisted: 44,
      expected_count: 41,
      status: "completed",
      has_more_state: false
    },
    harvest: {
      ...validatedSameProfileState.harvest,
      queue: validatedSameProfileState.harvest.queue.map((item, index) => ({
        ...item,
        aweme_id: `763419273351459${String(index).padStart(3, "0")}`,
        source_url: `https://www.douyin.com/video/763419273351459${String(index).padStart(3, "0")}`
      }))
    },
    profile_scan: {
      ...validatedSameProfileState.profile_scan,
      status: "success",
      accepted_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_validated_same_profile_ready",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_validated_same_profile_ready",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["763419273351459041", "763419273351459042", "763419273351459043"],
        over_displayed_extra_items_exact: [
          { aweme_id: "763419273351459041", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" },
          { aweme_id: "763419273351459042", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" },
          { aweme_id: "763419273351459043", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" }
        ],
        count_semantics_status: "completed_with_api_over_displayed_count",
        count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_verdict_reason: "validated_same_profile_api_over_display",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "validated_same_profile"
      }
    },
    verify: {
      ...validatedSameProfileState.verify,
      status: "success",
      accepted_target_count: 44,
      verified_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_validated_same_profile_ready",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_validated_same_profile_ready",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["763419273351459041", "763419273351459042", "763419273351459043"],
        over_displayed_extra_items_exact: [
          { aweme_id: "763419273351459041", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" },
          { aweme_id: "763419273351459042", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" },
          { aweme_id: "763419273351459043", profile_url: "https://www.douyin.com/user/MS4wLjABVALIDATED", same_profile_validation_status: "same_profile", same_profile_validated: "yes" }
        ],
        count_semantics_status: "completed_with_api_over_displayed_count",
        count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_verdict_reason: "validated_same_profile_api_over_display",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "validated_same_profile"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(state);
  const primary = getCanonicalScannerPrimaryAction(state);
  assert.equal(workflow.profileScanReady, true, "same-run validated same-profile proof must force scanner readiness true before fallback review routing");
  assert.equal(workflow.nextActionKey, "start_collecting", "validated same-profile proof must outrank review fallback when calibration and queue are ready");
  assert.equal(primary.key, "start_collecting", "canonical primary action must not stay stuck on review_overcollection once same-run proof is validated");
  assert.equal(primary.decisionTrace.reason, "validated_same_profile_api_overdisplay_warning_continue_to_collect");
}

{
  const forensicShapedExtraItems = [
    {
      aweme_id: "6687830664089177351",
      page_index: 9,
      raw_index_in_page: 8,
      accepted_index: 188,
      endpoint_path: "/aweme/v1/web/aweme/post/",
      request_cursor: 1589283983000,
      author_sec_uid: "MS4wLjABAAAAW2Q2sGP5ebyRK45zsb2ccvTZ98rpIUqLvtycKNJu6Gw",
      same_profile_validation_status: "same_profile",
      desc_sample: "巴拉格宗5.1音乐节，这首歌曲完整版来啦"
    },
    {
      aweme_id: "6686007222931066123",
      page_index: 9,
      raw_index_in_page: 9,
      accepted_index: 189,
      endpoint_path: "/aweme/v1/web/aweme/post/",
      request_cursor: 1589283983000,
      author_sec_uid: "MS4wLjABAAAAW2Q2sGP5ebyRK45zsb2ccvTZ98rpIUqLvtycKNJu6Gw",
      same_profile_validation_status: "same_profile",
      desc_sample: "巴拉格宗音乐节-藏地传奇"
    },
    {
      aweme_id: "6632051963091488007",
      page_index: 9,
      raw_index_in_page: 10,
      accepted_index: 190,
      endpoint_path: "/aweme/v1/web/aweme/post/",
      request_cursor: 1589283983000,
      author_sec_uid: "MS4wLjABAAAAW2Q2sGP5ebyRK45zsb2ccvTZ98rpIUqLvtycKNJu6Gw",
      same_profile_validation_status: "same_profile",
      desc_sample: "这首歌叫《向往神鹰》，完整版可以去原创音乐基地搜到🦅"
    }
  ];
  const forensicShapeState = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 191);
  const state: WholeProfileHarvestState = {
    ...forensicShapeState,
    run_id: "scan_profile_22C11B_1783279954835",
    scan_job: {
      ...forensicShapeState.scan_job,
      scan_job_id: "scan_profile_22C11B_1783279954835",
      total_persisted: 191,
      expected_count: 188,
      status: "completed",
      has_more_state: false
    },
    harvest: {
      ...forensicShapeState.harvest,
      queue: forensicShapeState.harvest.queue.map((item, index) => ({
        ...item,
        aweme_id: `763419273351459${String(index).padStart(3, "0")}`,
        source_url: `https://www.douyin.com/video/763419273351459${String(index).padStart(3, "0")}`
      }))
    },
    profile_scan: {
      ...forensicShapeState.profile_scan,
      status: "success",
      accepted_target_count: 191,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "scan_profile_22C11B_1783279954835",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "scan_profile_22C11B_1783279954835",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["6687830664089177351", "6686007222931066123", "6632051963091488007"],
        over_displayed_extra_items_exact: forensicShapedExtraItems,
        count_semantics_status: "completed_with_api_over_displayed_count",
        count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_verdict_reason: "validated_same_profile_api_over_display",
        expected_profile_video_count: 188,
        profile_queue_total_count: 191,
        collectable_count: 191,
        displayed_profile_count: 188,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "validated_same_profile"
      }
    },
    verify: {
      ...forensicShapeState.verify,
      status: "success",
      accepted_target_count: 191,
      verified_target_count: 191,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "scan_profile_22C11B_1783279954835",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "scan_profile_22C11B_1783279954835",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["6687830664089177351", "6686007222931066123", "6632051963091488007"],
        over_displayed_extra_items_exact: forensicShapedExtraItems,
        count_semantics_status: "completed_with_api_over_displayed_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        expected_profile_video_count: 188,
        profile_queue_total_count: 191,
        collectable_count: 191,
        displayed_profile_count: 188,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "validated_same_profile"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(state);
  const primary = getCanonicalScannerPrimaryAction(state);
  assert.equal(workflow.profileScanReady, true, "forensic-export item field names must satisfy itemized same-profile proof");
  assert.equal(workflow.nextActionKey, "start_collecting", "forensic-shaped validated proof must unlock Start Collecting");
  assert.equal(primary.key, "start_collecting");
}

{
  const unresolvedOvercollectionState = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 44);
  const state: WholeProfileHarvestState = {
    ...unresolvedOvercollectionState,
    run_id: "run_overcollection_needs_validation",
    scan_job: {
      ...unresolvedOvercollectionState.scan_job,
      scan_job_id: "run_overcollection_needs_validation",
      total_persisted: 44,
      expected_count: 41,
      status: "completed",
      has_more_state: false
    },
    profile_scan: {
      ...unresolvedOvercollectionState.profile_scan,
      status: "success",
      accepted_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_overcollection_needs_validation",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_overcollection_needs_validation",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "overcollected_needs_validation",
        scan_health_verdict: "failed_or_warning_overcollection_validation_needed",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "needs_validation"
      }
    },
    verify: {
      ...unresolvedOvercollectionState.verify,
      status: "success",
      accepted_target_count: 44,
      verified_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_overcollection_needs_validation",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_overcollection_needs_validation",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "overcollected_needs_validation",
        scan_health_verdict: "failed_or_warning_overcollection_validation_needed",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "needs_validation"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(state);
  const primary = getCanonicalScannerPrimaryAction(state);
  assert.equal(workflow.profileScanReady, false, "needs_validation must keep scanner readiness blocked");
  assert.equal(workflow.nextActionKey, "review_overcollection", "needs_validation must continue routing to review");
  assert.equal(primary.key, "review_overcollection", "canonical primary action must preserve review routing for unresolved overcollection");
}

{
  const outsideProfileState = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 44);
  const state: WholeProfileHarvestState = {
    ...outsideProfileState,
    run_id: "run_outside_profile_detected",
    scan_job: {
      ...outsideProfileState.scan_job,
      scan_job_id: "run_outside_profile_detected",
      total_persisted: 44,
      expected_count: 41,
      status: "completed",
      has_more_state: false
    },
    profile_scan: {
      ...outsideProfileState.profile_scan,
      status: "success",
      accepted_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_outside_profile_detected",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_outside_profile_detected",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "outside_profile_detected",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "failed_overcollection_outside_profile",
        scan_health_verdict: "failed_overcollection_outside_profile",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "outside_profile_detected"
      }
    },
    verify: {
      ...outsideProfileState.verify,
      status: "success",
      accepted_target_count: 44,
      verified_target_count: 44,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "run_outside_profile_detected",
        forensic_export_available: "yes",
        forensic_export_scan_run_id: "run_outside_profile_detected",
        accepted_target_ledger_present: "yes",
        over_displayed_count: 3,
        over_displayed_validation_status: "outside_profile_detected",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "failed_overcollection_outside_profile",
        scan_health_verdict: "failed_overcollection_outside_profile",
        expected_profile_video_count: 41,
        profile_queue_total_count: 44,
        collectable_count: 44,
        scan_finalization_result: "completed_with_warning",
        final_verdict: "outside_profile_detected"
      }
    }
  };
  const workflow = getDouyinScannerWorkflowReadiness(state);
  const primary = getCanonicalScannerPrimaryAction(state);
  assert.equal(workflow.profileScanReady, false, "outside-profile exact proof must stay blocking");
  assert.equal(workflow.nextActionKey, "review_overcollection", "outside-profile proof must route to review");
  assert.equal(primary.key, "review_overcollection", "canonical primary action must preserve review routing for outside-profile proof");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const primaryAction = getCanonicalScannerPrimaryAction(state);
  assert.equal(primaryAction.key, "start_collecting");
  assert.equal(primaryAction.label, "Start Collecting");
  assert.equal(primaryAction.source, "getCanonicalScannerPrimaryAction");
  assert.equal(primaryAction.selectorVersion, "22C-11B");
  assert.equal(primaryAction.calibration.ready, true);
  assert.equal(primaryAction.decisionTrace.selectedAction, "start_collecting");
  assert.equal(primaryAction.decisionTrace.extractionReady, true);
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const runningState: WholeProfileHarvestState = {
    ...state,
    status: "harvesting",
    workflow: {
      ...state.workflow,
      collection: {
        ...state.workflow.collection,
        status: "running",
        started_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        completed_at: null,
        last_error: null
      },
      active_task: "collect_videos",
      action_lock: "start_collecting"
    },
    harvest: {
      ...state.harvest,
      status: "running"
    }
  };
  const primaryAction = getCanonicalScannerPrimaryAction(runningState);
  assert.equal(isCollectionRunnerActive(runningState), true, "fresh running collection must be reported as an active runner");
  assert.equal(primaryAction.key, "pause", "running collection keeps the primary action in the collection state");
  assert.equal(primaryAction.title, "Collecting videos");
  assert.equal(primaryAction.label, "Collecting videos...");
  assert.equal(primaryAction.enabled, false, "running collection primary action must be non-reentrant");
  assert.equal(primaryAction.disabledReason, null, "normal duplicate active collection clicks must not show user-facing Action blocked text");
  assert.equal(primaryAction.decisionTrace.collection_runner_active, true);
  assert.equal(primaryAction.decisionTrace.primary_action_locked_reason, "collection_running");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const nowMs = Date.parse("2026-05-06T12:01:30.000Z");
  const delayedHybridCompletedState: WholeProfileHarvestState = {
    ...state,
    status: "harvesting",
    workflow: {
      ...state.workflow,
      collection: {
        ...state.workflow.collection,
        status: "running",
        started_at: "2026-05-06T12:00:00.000Z",
        updated_at: "2026-05-06T12:01:29.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "collect_videos",
      action_lock: "start_collecting"
    },
    harvest: {
      ...state.harvest,
      status: "running"
    },
    collect_job: {
      ...state.collect_job,
      job_id: "collect_job_hybrid_completed_delayed_running",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:29.000Z",
      heartbeat_at: "2026-05-06T12:01:29.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "after_backend_write",
      current_aweme_id: "7634192733514501001",
      current_item_index: 1,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 10,
      succeeded_count: 10,
      failed_count: 0,
      skipped_count: 0,
      lock_owner: "collect_job_hybrid_completed_delayed_running",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:02:30.000Z",
      recoverable: false,
      stale_reason: null,
      lock_released: false
    },
    active_collect_runtime: {
      ...state.active_collect_runtime,
      job_id: "collect_job_hybrid_completed_delayed_running",
      canonical_state: "running",
      canonical_phase: "collecting",
      current_step: "after_backend_write",
      current_aweme_id: "7634192733514501001",
      current_item_index: 1,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 10,
      succeeded_count: 10,
      failed_count: 0,
      skipped_count: 0,
      heartbeat_at: "2026-05-06T12:01:29.000Z",
      lock_owner: "collect_job_hybrid_completed_delayed_running",
      lock_expires_at: "2026-05-06T12:02:30.000Z",
      last_update_source: "hybrid_readback.delayed_1500ms",
      updated_at: "2026-05-06T12:01:29.000Z"
    },
    debug: {
      ...state.debug,
      last_response_summary: {
        ...(state.debug.last_response_summary && typeof state.debug.last_response_summary === "object" ? state.debug.last_response_summary as Record<string, unknown> : {}),
        hybrid_collector_completed: "yes",
        hybrid_runner_backend_write_status: 200,
        hybrid_runner_write_ok_count: 10,
        hybrid_readback_delayed_1500ms_collection_status: "idle",
        hybrid_readback_delayed_1500ms_collect_job_state: "running",
        hybrid_readback_delayed_1500ms_runtime_canonical_state: "running"
      }
    }
  };
  const busyState = getDouyinScannerBusyState(delayedHybridCompletedState, nowMs);
  const runnerLock = deriveAuthoritativeRunnerLock(delayedHybridCompletedState, nowMs);
  const primaryAction = getCanonicalScannerPrimaryAction(delayedHybridCompletedState);

  assert.equal(busyState.isBusy, false, "hybrid completion must override stale workflow.collection running busy state");
  assert.equal(runnerLock.active, false, "hybrid completion must release stale delayed collect_job/runtime lock");
  assert.equal(runnerLock.source, "hybrid_collector_completed_override", "runner lock must report hybrid completion as authoritative source");
  assert.equal(isCollectionRunnerActive(delayedHybridCompletedState, nowMs), false, "hybrid completion must make stale delayed runtime non-active");
  assert.equal(primaryAction.key, "start_collecting", "eligible remaining queue must show Start Collecting after hybrid completion");
  assert.equal(primaryAction.enabled, true, "Start Collecting must be enabled after hybrid completion releases stale lock");
  assert.notEqual(primaryAction.disabledReason, "Wait for the current step to finish.", "hybrid completion must not show generic wait disabled reason");
  assert.equal(primaryAction.decisionTrace.collection_runner_active, false, "primary action trace must show runner inactive after hybrid completion");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const diagnosticRunnerState: WholeProfileHarvestState = {
    ...state,
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_run_id: "scan_profile_fixture_next_10_safe",
        batch_heartbeat_at: "2030-05-07T11:43:30.000Z",
        batch_heartbeat_stage: "after_checkpoint"
      }
    }
  };
  const primaryAction = getCanonicalScannerPrimaryAction(diagnosticRunnerState);
  const runnerLock = deriveAuthoritativeRunnerLock(diagnosticRunnerState, Date.parse("2030-05-07T11:43:40.000Z"));
  assert.equal(isCollectionRunnerActive(diagnosticRunnerState, Date.parse("2030-05-07T11:43:40.000Z")), true, "recent safe-batch heartbeat diagnostics must lock collection as active");
  assert.equal(runnerLock.active, true, "authoritative runner lock must activate from safe batch diagnostics");
  assert.equal(runnerLock.source, "debug.batch_collection_ui_state", "authoritative runner lock must report exact field source");
  assert.equal(runnerLock.diagnostics.primary_action_locked_reason, "collection_running", "authoritative runner lock must expose locked reason diagnostics");
  assert.equal(primaryAction.key, "pause");
  assert.equal(primaryAction.label, "Collecting videos...");
  assert.equal(primaryAction.enabled, false);
  assert.equal(primaryAction.decisionTrace.primary_action_locked_reason, "collection_running");
  assert.notEqual(primaryAction.label, "Start Collecting");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const waitingForTabState: WholeProfileHarvestState = {
    ...state,
    harvest: {
      ...state.harvest,
      pause_message: "Return to the Douyin tab to continue collecting."
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_tab_inactive_evidence: "target_tab_inactive",
        trace_collect_tab_inactive_state: "inactive"
      }
    },
    collect_job: {
      ...state.collect_job,
      state: "waiting_for_active_tab",
      job_id: "collect_job_waiting_1",
      started_at: "2030-05-07T11:43:20.000Z",
      updated_at: "2030-05-07T11:43:40.000Z",
      heartbeat_at: "2030-05-07T11:43:40.000Z",
      runner_ack_at: "2030-05-07T11:43:25.000Z",
      selected_count: 10,
      current_step: "wait_for_active_tab"
    }
  };
  const primaryAction = getCanonicalScannerPrimaryAction(waitingForTabState);
  const runnerLock = deriveAuthoritativeRunnerLock(waitingForTabState, Date.parse("2030-05-07T11:43:40.000Z"));
  assert.equal(runnerLock.active, true, "waiting-for-active-tab collect runtime must remain authoritative");
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "waiting_for_active_tab", "runner diagnostics must surface waiting-for-active-tab UI state");
  assert.equal(primaryAction.key, "pause", "waiting-for-active-tab runtime must keep the primary route on the active collect action");
  assert.equal(primaryAction.title, "Collecting videos", "sanitized active collect action must keep the canonical collecting title while tab-return guidance is rendered elsewhere");
  assert.equal(primaryAction.label, "Paused: return to the Douyin tab to continue.", "waiting-for-active-tab runtime must expose paused tab-return guidance through the sanitized label");
  assert.equal(primaryAction.enabled, false, "waiting-for-active-tab runtime must stay non-reentrant");
  assert.equal(primaryAction.disabledReason, null, "sanitized active collect action must suppress duplicate-click disabled text while runner lock is active");

  const runtimeWaitingForTabState: WholeProfileHarvestState = {
    ...waitingForTabState,
    active_collect_runtime: {
      ...waitingForTabState.active_collect_runtime,
      job_id: "collect_job_waiting_1",
      canonical_state: "waiting_for_active_tab",
      canonical_phase: "collecting",
      current_step: "wait_for_active_tab",
      selected_count: 10,
      heartbeat_at: "2030-05-07T11:43:40.000Z",
      lock_owner: "collect_job_waiting_1",
      lock_expires_at: "2030-05-07T11:44:10.000Z",
      updated_at: "2030-05-07T11:43:40.000Z"
    }
  };
  const runtimePrimaryAction = getCanonicalScannerPrimaryAction(runtimeWaitingForTabState);
  const runtimeRunnerLock = deriveAuthoritativeRunnerLock(runtimeWaitingForTabState, Date.parse("2030-05-07T11:43:40.000Z"));
  assert.equal(runtimeRunnerLock.active, true, "matching active runtime waiting-for-tab state must keep the runner lock active");
  assert.equal(runtimeRunnerLock.source, "active_collect_runtime", "matching active runtime waiting-for-tab state must become the authoritative lock source");
  assert.equal(runtimeRunnerLock.diagnostics.trace_collect_runtime_authoritative, "yes", "runtime-authoritative waiting-for-tab state must publish runtime authority diagnostics");
  assert.equal(runtimeRunnerLock.diagnostics.trace_collect_runtime_authoritative_state, "waiting_for_active_tab", "runtime-authoritative waiting-for-tab state must publish the runtime canonical state");
  assert.equal(runtimePrimaryAction.key, "pause", "runtime-authoritative waiting-for-tab state must keep the primary route on the active collect action");
  assert.equal(runtimePrimaryAction.label, "Paused: return to the Douyin tab to continue.", "runtime-authoritative waiting-for-tab state must preserve the paused tab-return guidance label");
  assert.equal(runtimePrimaryAction.enabled, false, "runtime-authoritative waiting-for-tab state must stay non-reentrant");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const mismatchedRuntimeState: WholeProfileHarvestState = {
    ...state,
    collect_job: {
      ...state.collect_job,
      state: "running",
      job_id: "collect_job_expected_1",
      started_at: "2030-05-07T11:43:00.000Z",
      updated_at: "2030-05-07T11:43:10.000Z",
      heartbeat_at: "2030-05-07T11:43:10.000Z",
      runner_ack_at: "2030-05-07T11:43:05.000Z",
      current_step: "safe_delay_waiting",
      selected_count: 10,
      attempted_count: 1,
      succeeded_count: 1
    },
    active_collect_runtime: {
      ...state.active_collect_runtime,
      job_id: "collect_job_other_2",
      canonical_state: "running",
      canonical_phase: "collecting",
      current_step: "after_backend_write",
      selected_count: 10,
      attempted_count: 3,
      succeeded_count: 2,
      failed_count: 0,
      skipped_count: 0,
      heartbeat_at: "2030-05-07T11:43:38.000Z",
      lock_owner: "collect_job_other_2",
      lock_expires_at: "2030-05-07T11:44:08.000Z",
      updated_at: "2030-05-07T11:43:38.000Z"
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(mismatchedRuntimeState, Date.parse("2030-05-07T11:43:40.000Z"));
  assert.equal(runnerLock.active, true, "collect job fallback should keep active lock despite runtime job mismatch");
  assert.equal(runnerLock.source, "collect_job", "runtime job mismatch must not become runtime authoritative source");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_warning, "yes", "fresh runtime mismatch must surface non-blocking coherence warning");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_warning_reason, "runtime_job_mismatch_with_fresh_heartbeat");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_expected_job_id, "collect_job_expected_1");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_runtime_job_id, "collect_job_other_2");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_runtime_ui_authoritative, "no", "mismatched runtime must not claim popup authority");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const staleDiagnosticRunnerState: WholeProfileHarvestState = {
    ...state,
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_run_id: "scan_profile_fixture_next_10_safe",
        batch_heartbeat_at: "2030-05-07T11:40:00.000Z"
      }
    }
  };
  assert.equal(isCollectionRunnerActive(staleDiagnosticRunnerState, Date.parse("2030-05-07T11:43:30.000Z")), false, "stale safe-batch diagnostics must not permanently lock Start Collecting");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const startupRecoverableState: WholeProfileHarvestState = {
    ...state,
    harvest: {
      ...state.harvest,
      resume_available: false,
      pause_message: "Collect runner did not acknowledge startup. Start Collecting can safely retry."
    },
    collect_job: {
      ...state.collect_job,
      state: "start_failed_recoverable",
      job_id: "collect_job_start_failed_recoverable_1",
      started_at: "2030-05-07T11:42:20.000Z",
      updated_at: "2030-05-07T11:42:40.000Z",
      heartbeat_at: "2030-05-07T11:42:40.000Z",
      runner_ack_at: null,
      startup_deadline_at: "2030-05-07T11:42:30.000Z",
      startup_timeout_ms: 10_000,
      current_step: "startup_failed",
      failure_reason: "collect_runner_not_started",
      lock_owner: null,
      lock_expires_at: null,
      lock_released: true,
      recoverable: true
    }
  };
  const primaryAction = getCanonicalScannerPrimaryAction(startupRecoverableState);
  assert.equal(primaryAction.key, "resume", "startup no-ack recoverable state must keep canonical resume route while forcing Start Collecting semantics");
  assert.equal(primaryAction.label, "Start Collecting", "startup no-ack recoverable state must show Start Collecting label");
  assert.equal(primaryAction.enabled, true, "startup no-ack recoverable state must force Start Collecting enabled even if resume_available is false");
  assert.equal(primaryAction.disabledReason, null, "startup no-ack recoverable state must clear disabled reason for immediate retry");
  assert.equal(primaryAction.decisionTrace.selectedAction, "resume", "startup no-ack recoverable state must keep effective action selection as resume");
  assert.equal(primaryAction.decisionTrace.reason, "startup_ack_missing_recoverable", "startup no-ack recoverable state must expose explicit decision reason");
}

{
  const state = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))));
  const terminalContinuationState: WholeProfileHarvestState = {
    ...state,
    phase: "batch_safe_mode_completed",
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "batch_safe_mode_completed",
        pending_count: 4,
        profile_eligible_count: 4,
        profile_queue_total_count: 10
      }
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(terminalContinuationState, Date.parse("2030-05-07T11:43:30.000Z"));
  const primaryAction = getCanonicalScannerPrimaryAction(terminalContinuationState);
  assert.equal(runnerLock.active, false, "terminal batch_safe_mode_completed must release authoritative runner lock");
  assert.equal(primaryAction.label, "Continue Next 10", "terminal safe batch with pending queue must show continuation label");
  assert.equal(primaryAction.key, "start_collecting", "terminal safe batch continuation may keep canonical start collecting route");
}

{
  const readyState = withBackendReady(withPayloadPreview(withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3), true));
  const withPopupDiagnostics: WholeProfileHarvestState = {
    ...readyState,
    debug: {
      ...readyState.debug,
      last_response_summary: {
        popup_counter_authority_selected: "scan_job_total_persisted",
        popup_counter_authority_total: 3,
        popup_active_scan_run_id: "scan_run_readiness_regression"
      }
    }
  };
  assert.deepEqual(getWholeProfileHarvestReadiness(withPopupDiagnostics), getWholeProfileHarvestReadiness(readyState), "popup-only authority diagnostics must not change readiness gating");
  assert.deepEqual(getCanonicalScannerPrimaryAction(withPopupDiagnostics), getCanonicalScannerPrimaryAction(readyState), "popup-only authority diagnostics must not change canonical primary action");
}

{
  const base = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3);
  const unresolvedState: WholeProfileHarvestState = {
    ...base,
    scan_job: {
      ...base.scan_job,
      status: "retry_wait",
      has_more_state: true,
      last_status_code: 5,
      last_error: "active_profile_post_response_status_non_zero_retryable",
      retry_count: 2,
      next_retry_at: "2026-05-06T10:00:05.000Z",
      expected_count: 1000,
      total_persisted: 953
    },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 1000,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_fetch_stop_reason: "active_profile_post_response_status_non_zero",
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        expected_count_gate_meaningful_active_fetch: "no",
        expected_count_gate_dom_only_convergence_allowed: "no"
      }
    }
  };
  const readiness = getWholeProfileHarvestReadiness(unresolvedState);
  const workflow = getCanonicalScannerPrimaryAction(unresolvedState);
  const actionState = getWholeProfileHarvestActionState(unresolvedState);
  assert.equal(readiness.profile_scan_ready, false, "retry_wait active-source unresolved state must keep profile scan not ready");
  assert.equal(readiness.extraction_ready, false, "expected-known active-source unresolved state must not escalate to extraction readiness");
  assert.equal(workflow.key, "scan_profile", "retry_wait active-source unresolved state must keep Scan Profile primary action");
  assert.match(workflow.disabledReason ?? actionState.runHarvest.disabledReason ?? "", /Active profile-post source is retrying|Scan Profile first/, "blocked reason must reference active-source retry or scan requirement");
}

{
  const base = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3);
  const staleResumeRecoveryState: WholeProfileHarvestState = {
    ...base,
    phase: "scan_running",
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "running", updated_at: "2026-05-06T10:00:30.000Z", completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_stale_resume_readiness",
      status: "running",
      expected_count: 1000,
      total_discovered: 953,
      total_persisted: 953,
      page_count: 3,
      request_count: 3,
      has_more_state: true,
      last_status_code: 0,
      last_error: null
    },
    profile_scan: {
      ...base.profile_scan,
      status: "running",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 1000,
        stale_resume_detected: "yes",
        stale_resume_recovery_attempted: "yes",
        stale_resume_recovery_result: "restarted_from_fresh_cursor",
        fresh_cursor_restart_attempted: "yes",
        fresh_cursor_restart_result: "restarted",
        current_run_found_count: 0,
        current_run_new_inserted_total: 0,
        persisted_total_count: 953,
        scan_progress_discovered: 0,
        scan_progress_pages: 3,
        scan_progress_requests: 3,
        scan_progress_phase_label: "Refreshing scan cursor"
      }
    }
  };
  const staleResumeReadiness = getWholeProfileHarvestReadiness(staleResumeRecoveryState);
  const staleResumeWorkflow = getCanonicalScannerPrimaryAction(staleResumeRecoveryState);
  assert.equal(staleResumeReadiness.profile_scan_ready, false, "fresh-cursor restart should not finalize scan readiness early");
  assert.equal(staleResumeReadiness.extraction_ready, false, "fresh-cursor restart should not unlock downstream collection flow while scan is still active");
  assert.equal(staleResumeWorkflow.key, "scan_profile", "fresh-cursor restart remains the active Scan Profile action");
  assert.equal(staleResumeWorkflow.label, "Scanning...", "fresh-cursor restart should present active scanning state rather than blocked failure");
  assert.equal(staleResumeWorkflow.disabledReason, null, "fresh-cursor restart must suppress stale blocked failure messaging");
}

{
  const base = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3);
  const activeWithStaleSourceFailure: WholeProfileHarvestState = {
    ...base,
    phase: "scan_running",
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "running", updated_at: "2026-05-06T10:00:30.000Z", completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_active_progress_22C14R",
      status: "running",
      expected_count: 118,
      total_discovered: 21,
      total_persisted: 21,
      page_count: 1,
      request_count: 1,
      has_more_state: true,
      last_status_code: 0
    },
    profile_scan: {
      ...base.profile_scan,
      status: "running",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "older_scan_run_22C14R",
        expected_profile_video_count: 118,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_fetch_stop_reason: "active_profile_post_response_status_non_zero",
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        scan_progress_discovered: 21,
        scan_progress_pages: 1,
        scan_progress_requests: 1,
        scan_progress_update_seq: 1,
        scan_progress_updated_at: "2026-05-06T10:00:30.000Z"
      }
    }
  };
  const workflow = getCanonicalScannerPrimaryAction(activeWithStaleSourceFailure);
  const readiness = getDouyinScannerWorkflowReadiness(activeWithStaleSourceFailure);
  assert.equal(workflow.key, "scan_profile", "active scan keeps Scan Profile as the non-reentrant busy action");
  assert.equal(workflow.label, "Scanning...", "active scan must render the busy scanning label");
  assert.equal(workflow.enabled, false, "active scan action must be disabled without a blocked warning");
  assert.equal(workflow.disabledReason, null, "active scan progress must suppress stale active-source failed diagnostics");
  assert.equal(readiness.disabledReason, null, "active scan readiness must not expose Action blocked text");
}

{
  const base = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3);
  const terminalFailedSource: WholeProfileHarvestState = {
    ...base,
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "failed", updated_at: "2026-05-06T10:00:30.000Z", completed_at: "2026-05-06T10:00:30.000Z", last_error: "active_profile_post_response_status_non_zero_terminal" },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...base.scan_job,
      status: "failed",
      expected_count: 118,
      total_persisted: 21,
      has_more_state: true,
      last_status_code: 5,
      last_error: "active_profile_post_response_status_non_zero_terminal"
    },
    profile_scan: {
      ...base.profile_scan,
      status: "failed",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 118,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_fetch_stop_reason: "active_profile_post_response_status_non_zero_terminal",
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        scan_finalization_result: "failed"
      }
    }
  };
  const workflow = getCanonicalScannerPrimaryAction(terminalFailedSource);
  assert.equal(workflow.key, "scan_profile", "terminal active-source failure should still route to Scan Profile");
  assert.match(workflow.disabledReason ?? "", /Active profile-post source failed/, "terminal source failure must still show the actionable blocked reason");
}

{
  const base = withClassificationReady(withDryRunSuccess(withCalibration(withVerified(baseState()))), 3);
  const resumableBudgetState: WholeProfileHarvestState = {
    ...base,
    workflow: {
      ...base.workflow,
      scan: { ...base.workflow.scan, status: "idle", updated_at: "2026-05-06T10:05:00.000Z", completed_at: "2026-05-06T10:05:00.000Z", last_error: "incomplete_api_budget_exhausted" },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_budget_resume_22C14B",
      status: "completed",
      expected_count: 996,
      total_discovered: 991,
      total_persisted: 991,
      page_count: 128,
      request_count: 128,
      has_more_state: true,
      last_status_code: 0,
      last_error: "incomplete_api_budget_exhausted"
    },
    profile_scan: {
      ...base.profile_scan,
      status: "success",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 996,
        scan_finalization_result: "incomplete",
        scan_stop_authoritative: "incomplete_api_budget_exhausted",
        final_gap_reason: "api_budget_exhausted_before_has_more_false",
        final_gap_classification: "resumable_api_budget_exhausted",
        page_budget_exhausted: "yes",
        page_budget_limit: 128,
        continuation_available: "yes",
        continuation_reason: "page_budget_exhausted",
        continuation_cursor: 128,
        partial_scan_resumable: "yes",
        source_failure: "no",
        active_profile_post_source_healthy: "yes",
        scan_progress_discovered: 991,
        scan_progress_pages: 128,
        scan_progress_requests: 128
      }
    }
  };
  const workflow = getCanonicalScannerPrimaryAction(resumableBudgetState);
  const readiness = getDouyinScannerWorkflowReadiness(resumableBudgetState);
  assert.equal(readiness.profileScanReady, true, "page-budget resumable scan must remain usable for continuation");
  assert.equal(readiness.canScanProfile, true, "page-budget resumable scan must allow Scan Profile continuation");
  assert.equal(readiness.disabledReason, null, "page-budget resumable scan must not expose Action blocked text");
  assert.equal(workflow.key, "scan_profile", "page-budget resumable scan must keep Scan Profile as the primary action");
  assert.equal(workflow.label, "Continue Scan", "page-budget resumable scan must present Continue Scan copy");
  assert.equal(workflow.enabled, true, "page-budget resumable scan must keep continuation action enabled");
  assert.match(workflow.description, /saved continuation cursor|healthy pagination batch/, "page-budget resumable scan must explain that continuation resumes from the saved cursor");
  assert.match(workflow.description, /remaining unseen pages|resume from the saved continuation cursor/, "page-budget resumable scan must explain that continuation fetches the unseen tail");
  assert.equal(workflow.disabledReason, null, "page-budget resumable scan must not surface source-failure disabled reason");
}

assert.match(readinessSource, /export type CanonicalCalibrationReady = \{[\s\S]*source: "canonical" \| "legacy" \| "missing";[\s\S]*conflict: boolean;[\s\S]*\}/s, "Phase 22C-9 readiness must expose canonical calibration metadata");
assert.match(readinessSource, /export type CanonicalScannerPrimaryAction = \{[\s\S]*source: "getCanonicalScannerPrimaryAction";[\s\S]*selectorVersion: "22C-11B";[\s\S]*decisionTrace: CanonicalScannerPrimaryActionDecisionTrace;[\s\S]*\}/s, "Phase 22C-9 readiness must expose canonical primary action decision trace metadata");
assert.match(readinessSource, /export function getCanonicalCalibrationReady\(state: CalibrationReadyInput\): CanonicalCalibrationReady/, "Phase 22C-9 readiness must route canonical calibration through the loose nullable calibration input helper");
assert.match(readinessSource, /export function isDouyinCalibrationReady\(calibration:[\s\S]*return getCanonicalCalibrationReady\(\{ calibration \}\)\.ready;/s, "legacy calibration readiness must delegate to canonical calibration readiness");
assert.match(readinessSource, /export function getCanonicalScannerPrimaryAction\(state: WholeProfileHarvestState\): CanonicalScannerPrimaryAction/, "Phase 22C-9 readiness must expose a canonical scanner primary action selector");
assert.match(readinessSource, /else if \(!scanReady\)[\s\S]*nextActionKey = "scan_profile";[\s\S]*else if \((?:queueReady|effectiveQueueReady) && !calibrationReady\)[\s\S]*nextActionKey = "calibrate";/s, "Scan Profile readiness must be checked before calibration readiness");
assert.doesNotMatch(readinessSource, /douyinHarvestRuntimeV2|douyinSafeHarvestRun|harvestProgress|smartHarvestState|fullModalHarvestState/, "whole-profile readiness must not read V2 or legacy runtime keys");

console.log("wholeProfileHarvest readiness/action gating tests passed");
