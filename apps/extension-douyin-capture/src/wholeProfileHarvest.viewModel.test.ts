import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { EXTENSION_BUILD_TIMESTAMP, EXTENSION_RUNTIME_BUILD_ID } from "./generated/buildIdentity.js";

import { deriveAuthoritativeProfileCounters, deriveAuthoritativeRunnerLock, deriveReconciledPopupMetrics, isTerminalBatchContinuation, sanitizePopupViewState } from "./wholeProfileHarvest/authoritativePopupState.js";
import { getCanonicalScannerPrimaryAction, getWholeProfileHarvestActionState, getWholeProfileHarvestReadiness, applyHybridNetworkCacheModeFlagToState } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { wholeProfileProgressSummary } from "./wholeProfileHarvest/progress.js";
import { getActionDeckViewModel, getActionHelpText, getDouyinScannerMainViewModel, getRunTabViewModel, getScannerControlPanelViewModel, getWholeProfileHarvestProgressViewModel } from "./wholeProfileHarvest/viewModel.js";

const viewModelSource = readFileSync(new URL("./wholeProfileHarvest/viewModel.ts", import.meta.url), "utf8");
const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf8");
const backgroundSource = readFileSync(new URL("./background.ts", import.meta.url), "utf8");

assert.ok(EXTENSION_RUNTIME_BUILD_ID.startsWith("reup-douyin-extension-"), "build identity must use a recognizable extension prefix");
assert.ok(EXTENSION_BUILD_TIMESTAMP.length > 0, "build timestamp must be present for runtime diagnostics");
assert.match(backgroundSource, /background_runtime_build_id/, "background diagnostics must expose its runtime build id");
assert.match(popupSource, /popup_runtime_build_id/, "popup diagnostics must expose its runtime build id");
assert.match(contentScriptSource, /content_script_runtime_build_id/, "content script diagnostics must expose its runtime build id");
assert.match(viewModelSource, /Runtime build id consistent/, "view model must display runtime build identity consistency");

{
  const runtimeState: WholeProfileHarvestState = {
    ...createWholeProfileHarvestIdleState("2026-05-06T12:00:00.000Z"),
    debug: {
      ...createWholeProfileHarvestIdleState("2026-05-06T12:00:00.000Z").debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        extension_runtime_build_id: "reup-douyin-extension-test-build",
        background_runtime_build_id: "reup-douyin-extension-test-build",
        popup_runtime_build_id: "reup-douyin-extension-test-build",
        content_script_runtime_build_id: "reup-douyin-extension-test-build"
      }
    }
  };
  const runtimeVm = getWholeProfileHarvestProgressViewModel(runtimeState);
  const runtimeValue = (label: string): string | undefined => runtimeVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(runtimeValue("Popup runtime build id"), "reup-douyin-extension-test-build", "popup runtime build ID must render from runtime debug diagnostics instead of none");
  assert.equal(runtimeValue("Content script runtime build id"), "reup-douyin-extension-test-build", "content script runtime build ID must render from runtime debug diagnostics instead of none");
  assert.equal(runtimeValue("Runtime build id consistent"), "yes", "all required runtime build IDs matching must render consistent=yes");

  const missingRuntimeVm = getWholeProfileHarvestProgressViewModel({
    ...runtimeState,
    debug: {
      ...runtimeState.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        extension_runtime_build_id: "reup-douyin-extension-test-build",
        background_runtime_build_id: "reup-douyin-extension-test-build"
      }
    }
  });
  const missingRuntimeValue = (label: string): string | undefined => missingRuntimeVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(missingRuntimeValue("Popup runtime build id"), "none", "missing popup runtime ID must be visible as none");
  assert.equal(missingRuntimeValue("Runtime build id consistent"), "no + missing_runtime_id", "missing content runtime ID must make consistency diagnostic false");

  const popupMissingOnlyVm = getWholeProfileHarvestProgressViewModel({
    ...runtimeState,
    debug: {
      ...runtimeState.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        extension_runtime_build_id: "reup-douyin-extension-test-build",
        background_runtime_build_id: "reup-douyin-extension-test-build",
        content_script_runtime_build_id: "reup-douyin-extension-test-build"
      }
    }
  });
  const popupMissingOnlyValue = (label: string): string | undefined => popupMissingOnlyVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(popupMissingOnlyValue("Popup runtime build id"), "none", "missing popup runtime ID must still render as none for diagnostics");
  assert.equal(popupMissingOnlyValue("Runtime build id consistent"), "yes", "runtime consistency must not fail only because popup ID is absent from a non-popup diagnostic source");
}

function baseState(): WholeProfileHarvestState {
  return createWholeProfileHarvestIdleState("2026-05-06T12:00:00.000Z");
}

{
  const state: WholeProfileHarvestState = {
    ...baseState(),
    status: "failed",
    phase: "failed",
    workflow: {
      ...baseState().workflow,
      scan: { status: "failed", started_at: "2026-05-06T12:00:00.000Z", updated_at: "2026-05-06T12:00:10.000Z", completed_at: "2026-05-06T12:00:10.000Z", last_error: "transient_scan_failure" },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...baseState().scan_job,
      scan_job_id: "scan-progress-test",
      status: "running",
      profile_identifier: "profile-progress-test",
      page_count: 12,
      request_count: 12,
      total_discovered: 240,
      total_persisted: 240,
      expected_count: 996,
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:00:12.000Z"
    },
    profile_scan: {
      ...baseState().profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "scan-progress-test",
        scan_progress_pages: 12,
        scan_progress_requests: 12
      }
    },
    debug: {
      ...baseState().debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_run_id: "scan-progress-test",
        scan_progress_discovered: 0
      }
    }
  };
  const vm = getScannerControlPanelViewModel(state);
  assert.equal(vm.scanProgress.active, true, "running scan_job must keep progress visible even if workflow/status briefly failed");
  assert.equal(vm.headerStatus, "Scanning 0 / 996");
  assert.equal(vm.scanProgress.pagesFetched, 12);
  assert.equal(vm.scanProgress.requestCount, 12);
}

{
  const misalignedState: WholeProfileHarvestState = {
    ...baseState(),
    status: "verifying",
    phase: "scanning",
    run_id: "scan-profile-p2-new",
    workflow: {
      ...baseState().workflow,
      scan: { status: "running", started_at: "2026-05-06T12:00:00.000Z", updated_at: "2026-05-06T12:00:12.000Z", completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...baseState().scan_job,
      scan_job_id: "scan-profile-p2-new",
      status: "running",
      page_count: 3,
      request_count: 4,
      total_persisted: 0,
      expected_count: 140
    },
    profile_scan: {
      ...baseState().profile_scan,
      status: "running",
      accepted_target_count: 0,
      diagnostics: {
        scan_run_id: "scan-profile-p1-old",
        scan_progress_pages: 3,
        scan_progress_requests: 4,
        current_run_found_count: 140
      }
    }
  };
  const misalignedVm = getScannerControlPanelViewModel(misalignedState);
  assert.equal(misalignedVm.scanProgress.active, true);
  assert.equal(misalignedVm.scanProgress.discovered, 0, "stale prior-run discovered count must not bleed into a new scan");
  assert.equal(misalignedVm.scanProgress.pagesFetched, 0, "stale prior-run page count must not show before diagnostics align");
  assert.equal(misalignedVm.scanProgress.requestCount, 0, "stale prior-run request count must not show before diagnostics align");
}

{
  const scanningWithStaleCollectBlock: WholeProfileHarvestState = {
    ...baseState(),
    status: "verifying",
    phase: "scanning",
    run_id: "scan-profile-p2-new",
    workflow: {
      ...baseState().workflow,
      scan: { status: "running", started_at: "2026-05-06T12:00:00.000Z", updated_at: "2026-05-06T12:00:12.000Z", completed_at: null, last_error: null },
      active_task: "scan_profile",
      action_lock: "scan_profile"
    },
    scan_job: {
      ...baseState().scan_job,
      scan_job_id: "scan-profile-p2-new",
      status: "running",
      page_count: 1,
      request_count: 1,
      total_persisted: 0,
      expected_count: null
    },
    profile_scan: {
      ...baseState().profile_scan,
      status: "running",
      accepted_target_count: 0,
      diagnostics: { scan_run_id: "scan-profile-p2-new", scan_progress_discovered: 12 }
    },
    debug: {
      ...baseState().debug,
      last_action_clicked: "start_collecting",
      last_action_result: "blocked",
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        start_collecting_blocked_reason: "No pending video is available for collection."
      }
    }
  };
  const blockedDuringScanVm = getScannerControlPanelViewModel(scanningWithStaleCollectBlock);
  assert.equal(blockedDuringScanVm.scanProgress.active, true, "active scan must keep scan progress visible");
  assert.notEqual(
    blockedDuringScanVm.emptyState,
    "No pending video is available for collection.",
    "stale Start Collecting block copy must not paint while scan is running"
  );
  assert.equal(blockedDuringScanVm.primaryAction.key, "scan_profile", "primary action must stay on scan while scan is running");
  assert.equal(blockedDuringScanVm.primaryAction.disabledReason, null, "scan primary action must not inherit collect block reason");
}

function authoritativeReconciliationFixtureState(): WholeProfileHarvestState {
  const state = withClassification(withDryRun(withVerify(baseState())), 111);
  const queue = Array.from({ length: 111 }, (_, index) => {
    const awemeId = `76341927335145${String(index).padStart(5, "0")}`;
    return {
      index: index + 1,
      aweme_id: awemeId,
      capture_status: "new" as const,
      status: "pending" as const,
      attempts: 0,
      checkpoint_sequence: null,
      extraction_result: null,
      last_error: null,
      capture_inbox_item_id: null,
      source_url: `https://www.douyin.com/video/${awemeId}`,
      profile_card_evidence: {}
    };
  });
  return {
    ...state,
    target_status: { ...state.target_status, new: 108, incomplete: 0, complete: 3, unknown: 0 },
    harvest: { ...state.harvest, queue, pending: 109, planned_total: 111, queue_preview: queue.slice(0, 81).map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })) },
    debug: {
      ...state.debug,
      last_response_summary: {
        saved_count_after_batch: 10,
        batch_runner_called: true,
        start_collecting_popup_route_hit: true,
        start_collecting_popup_dispatch_target: "runStartCollectingWorkflow",
        start_collecting_controller_entry_hit: true,
        collect_batch_runner_entry_hit: true,
        collect_batch_runner_entered_at: "2026-05-06T12:10:01.000Z",
        start_collecting_clicked_at: "2026-05-06T12:10:00.000Z",
        batch_selected_count: 2,
        effective_batch_limit: 10,
        batch_target_queue_index: 30,
        batch_selected_aweme_ids: ["700000000000000030", "700000000000000031"],
        backend_captured_aweme_id_count: 30,
        trace_collect_pre_batch_backend_captured: 30,
        trace_collect_pre_batch_backend_ready: 19,
        trace_collect_pre_batch_backend_dup: 0,
        trace_collect_pre_batch_backend_fail: 0,
        trace_collect_pre_batch_new: 81,
        trace_collect_pre_batch_queue: 81,
        trace_collect_post_batch_backend_captured: 32,
        trace_collect_post_batch_backend_ready: 21,
        trace_collect_post_batch_backend_dup: 0,
        trace_collect_post_batch_backend_fail: 0,
        trace_collect_post_batch_new: 79,
        trace_collect_post_batch_queue: 79,
        trace_collect_batch_delta_captured: 2,
        trace_collect_batch_delta_queue: -2,
        queue_filtering_backend_captured_aweme_id_count_expected: 30,
        queue_filtering_backend_captured_aweme_id_count_actual: 30,
        trace_collect_backend_captured_count_source: "backend_profile_items_response.counts.captured",
        trace_collect_backend_captured_id_set_source: "backend_profile_items_response.items.aweme_ids",
        trace_collect_backend_counts_and_ids_same_response: true,
        trace_collect_backend_captured_aweme_id_count_expected: 30,
        trace_collect_backend_captured_aweme_id_count_actual: 30,
        trace_collect_backend_captured_id_set_stale: false,
        trace_collect_backend_captured_id_set_stale_reason: null,
        trace_collect_selection_blocked: false,
        trace_collect_selection_block_reason: null,
        filtered_collectable_count: 81,
        skipped_already_captured_count: 30,
        selected_ids_already_captured_count: 0,
        selected_ids_already_captured_first_10: [],
        was_in_backend_captured_set_before_collect: false,
        backend_captured_id_set_available: true,
        backend_captured_id_set_incomplete: false,
        backend_captured_id_set_selection_blocked: false,
        backend_captured_id_set_selection_block_reason: null,
        queue_filtering: {
          queue_filtering_endpoint: "/douyin-extension/capture-inbox/profile-items",
          queue_filtering_backend_summary_status: "success",
          queue_filtering_backend_captured_count: 30,
          queue_filtering_backend_captured_aweme_id_count: 30,
          queue_filtering_raw_queue_count: 111,
          queue_filtering_filtered_collectable_count: 81,
          queue_filtering_skipped_already_captured_count: 30,
          queue_filtering_selected_ids_already_captured_count: 0,
          queue_filtering_selected_ids_already_captured_first_10: [],
          queue_filtering_was_in_backend_captured_set_before_collect: false,
          queue_filtering_backend_captured_id_set_available: true,
          queue_filtering_backend_captured_id_set_incomplete: false,
          queue_filtering_selection_blocked: false,
          queue_filtering_selection_block_reason: null,
          queue_filtering_used_for_selection: true,
          queue_filtering_source: "backend_profile_items_aweme_ids"
        },
        recent_batch_item_results: [
          {
            index: 30,
            aweme_id: "700000000000000030",
            selected_from_queue: true,
            was_in_backend_captured_set_before_collect: false,
            expected_backend_operation: "create",
            backend_operation_result: "created",
            backend_profile_capture_delta_effect: "newly_captured_for_profile",
            backend_summary_missing_this_id_before_collect: true,
            backend_match_diagnostics: null,
            skipped_reason: null,
            modal_open_result: "success",
            extraction_result: "success",
            backend_write_attempted: true,
            backend_http_status: 200,
            backend_success: true,
            backend_item_created_or_updated: true,
            backend_duplicate: false,
            backend_capture_inbox_item_id: "capture_item_30",
            backend_error_code: null,
            final_status: "saved_verified"
          }
        ],
        verify_response: {
          counts: { captured: 30, ready: 19, needs_action: 11, dup: 0, fail: 0 },
          items_count: 30,
          items: queue.slice(0, 30).map((item, index) => ({
            id: `backend_${index}`,
            aweme_id: index < 10 ? item.aweme_id : undefined,
            source_video_external_id: index >= 10 && index < 15 ? item.aweme_id : undefined,
            video_external_id: index >= 15 && index < 20 ? item.aweme_id : undefined,
            external_id: index >= 20 && index < 23 ? item.aweme_id : undefined,
            metadata_json: index >= 23 && index < 28 ? { extracted_aweme_id: item.aweme_id, profile_card_evidence: { aweme_id: item.aweme_id } } : undefined,
            raw_payload_json: index >= 28 ? { profile_card_evidence: { aweme_id: item.aweme_id } } : undefined
          }))
        }
      }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAAfixture",
      scanned_total: 111,
      backend_captured: 30,
      backend_ready: 19,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 30,
      incomplete: 11,
      need_retry: 0,
      new: 81,
      queue: 81,
      applied_at: "2026-05-06T12:00:00.000Z"
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        profile_already_collected_count: 0,
        profile_eligible_count: 101,
        pending_count: 109,
        profile_batch_pending_count: 111,
        profile_queue_total_count: 111,
        verify_response: {
          counts: { captured: 30, ready: 19, needs_action: 11, dup: 0, fail: 0 },
          items_count: 30,
          items: queue.slice(0, 30).map((item, index) => ({
            id: `backend_${index}`,
            aweme_id: index < 10 ? item.aweme_id : undefined,
            source_video_external_id: index >= 10 && index < 15 ? item.aweme_id : undefined,
            video_external_id: index >= 15 && index < 20 ? item.aweme_id : undefined,
            external_id: index >= 20 && index < 23 ? item.aweme_id : undefined,
            metadata_json: index >= 23 && index < 28 ? { extracted_aweme_id: item.aweme_id, profile_card_evidence: { aweme_id: item.aweme_id } } : undefined,
            raw_payload_json: index >= 28 ? { profile_card_evidence: { aweme_id: item.aweme_id } } : undefined
          }))
        }
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

function requestOnlyStartCollectingTraceFixtureState(): WholeProfileHarvestState {
  const state = authoritativeReconciliationFixtureState();
  return {
    ...state,
    debug: {
      ...state.debug,
      last_request_summary: {
        last_primary_action_key_clicked: "start_collecting",
        last_primary_action_dispatch_target: "runStartCollectingWorkflow",
        start_collecting_popup_route_hit: true,
        start_collecting_popup_dispatch_target: "runStartCollectingWorkflow",
        start_collecting_clicked_at: "2026-05-06T12:11:00.000Z"
      },
      last_response_summary: {}
    }
  };
}

function controllerExitBeforeBatchTraceFixtureState(): WholeProfileHarvestState {
  const state = authoritativeReconciliationFixtureState();
  return {
    ...state,
    debug: {
      ...state.debug,
      last_request_summary: {
        last_primary_action_key_clicked: "start_collecting",
        last_primary_action_dispatch_target: "runStartCollectingWorkflow",
        start_collecting_popup_route_hit: true,
        start_collecting_popup_dispatch_target: "runStartCollectingWorkflow",
        start_collecting_controller_entry_hit: true,
        start_collecting_controller_entered_at: "2026-05-06T12:12:00.000Z",
        start_collecting_clicked_at: "2026-05-06T12:12:00.000Z"
      },
      last_response_summary: {
        start_collecting_controller_entry_hit: true,
        start_collecting_controller_exit_before_batch_runner: true,
        start_collecting_controller_exit_stage: "calibration_ready",
        start_collecting_controller_exit_reason: "Calibrate 4 Points first.",
        start_collecting_stage: "calibration_ready",
        start_collecting_preflight_result: "blocked",
        start_collecting_blocked_reason: "Calibrate 4 Points first.",
        collect_batch_runner_entry_hit: false,
        batch_runner_called: false,
        runtime_open_direct_modal_present: true,
        runtime_extract_modal_metrics_present: true
      }
    }
  };
}

function withVerify(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture?foo=bar&very_long=true&another=parameter",
    status: "verified",
    profile_scan: {
      ...state.profile_scan,
      status: "success",
      accepted_target_count: 55,
      rejected_target_count: 619,
      scan_rounds: 5,
      stop_reason: "reached_bottom"
    },
    verify: {
      ...state.verify,
      status: "success",
      accepted_target_count: 55,
      rejected_target_count: 619,
      verified_target_count: 55,
      scan_rounds: 5,
      stop_reason: "reached_bottom"
    },
    workflow: {
      ...state.workflow,
      scan: {
        ...state.workflow.scan,
        status: "success",
        started_at: "2026-05-06T12:01:00.000Z",
        updated_at: "2026-05-06T12:01:10.000Z",
        completed_at: "2026-05-06T12:01:10.000Z",
        last_error: null
      }
    },
    target_status: {
      new: 21,
      incomplete: 14,
      complete: 18,
      failed: 0,
      skipped: 0,
      unknown: 2
    }
  };
}

function withDryRun(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      source_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      points: canonicalCalibrationPoints(),
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null
    },
    dry_run: {
      ...state.dry_run,
      status: "success",
      mode: "random",
      pass: 3,
      fail: 0,
      sample_size: 3,
      completed_at: "2026-05-06T12:03:00.000Z"
    }
  };
}

function withClassification(state: WholeProfileHarvestState, collect = 10): WholeProfileHarvestState {
  return {
    ...state,
    classification: {
      ...state.classification,
      status: "success",
      started_at: "2026-05-06T12:02:00.000Z",
      completed_at: "2026-05-06T12:02:10.000Z",
      profile_url: state.profile_url,
      sec_uid: null,
      schema_version: "douyin_profile_video_classification_result.v1",
      collection_mode: "new_incomplete_failed",
      database_lookup_status: "ok",
      total_candidates: 56,
      counts: {
        new: 22,
        incomplete: 15,
        complete: 17,
        failed: 1,
        skipped: 1,
        unknown: 0,
        collect,
        skip: 18
      },
      targets: [],
      collect_aweme_ids: Array.from({ length: collect }, (_, index) => `76352942674133681${String(index).padStart(2, "0")}`),
      skip_aweme_ids: [],
      diagnostics: { fixture: true }
    },
    workflow: {
      ...state.workflow,
      scan: {
        ...state.workflow.scan,
        status: "success",
        started_at: "2026-05-06T12:01:00.000Z",
        updated_at: "2026-05-06T12:01:10.000Z",
        completed_at: "2026-05-06T12:01:10.000Z",
        last_error: null
      },
      classification: {
        ...state.workflow.classification,
        status: "success",
        started_at: "2026-05-06T12:02:00.000Z",
        updated_at: "2026-05-06T12:02:10.000Z",
        completed_at: "2026-05-06T12:02:10.000Z",
        last_error: null
      }
    },
    harvest: {
      ...state.harvest,
      queue: Array.from({ length: collect }, (_, index) => ({
        index,
        aweme_id: `76352942674133681${String(index).padStart(2, "0")}`,
        capture_status: index === collect - 1 ? "failed" as const : "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/76352942674133681${String(index).padStart(2, "0")}`,
        profile_card_evidence: {}
      }))
    }
  };
}

function withExtracted(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    harvest_options: {
      ...state.harvest_options,
      mode: "new_and_incomplete",
      batch: "next_10",
      speed: "safe"
    },
    harvest: {
      ...state.harvest,
      planned_total: 10,
      pending: 5,
      updated: 5,
      failed: 1,
      current_aweme_id: "7629392343484894491",
      last_checkpoint_at: "2026-05-06T12:08:00.000Z",
      queue_preview: Array.from({ length: 10 }, (_, index) => ({
        index,
        aweme_id: `76352942674133681${String(index).padStart(2, "0")}`,
        capture_status: "new" as const,
        source_url: null,
        title: null,
        thumbnail_url: null
      })),
      results: [
        {
          index: 1,
          aweme_id: "a1",
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
          target_url: null,
          data_integrity_status: "passed",
          profile_card_evidence: {},
          started_at: "2026-05-06T12:05:00.000Z",
          completed_at: "2026-05-06T12:06:00.000Z",
          duration_seconds: 803,
          duration_text: "13:23",
          like_count: 409,
          comment_count: 12,
          favorite_count: 33,
          share_count: 7,
          current_modal_id_before: "a1",
          current_modal_id_after: "a1",
          extracted_aweme_id: "a1",
          source_used: "calibrated_point_dom"
        },
        {
          index: 2,
          aweme_id: "a2",
          status: "failed",
          stage: "open_modal",
          attempts: 1,
          checkpoint_sequence: 2,
          error: "modal_navigation_timeout",
          error_code: "modal_navigation_timeout",
          error_message: "modal_navigation_timeout",
          modal_opened: false,
          modal_id_matched: false,
          metrics_extracted: false,
          payload_built: false,
          backend_called: false,
          backend_status: null,
          backend_error_code: null,
          capture_inbox_item_id: null,
          target_url: null,
          data_integrity_status: "not_checked",
          profile_card_evidence: {},
          started_at: "2026-05-06T12:06:00.000Z",
          completed_at: "2026-05-06T12:07:00.000Z",
          duration_seconds: null,
          duration_text: null,
          like_count: null,
          comment_count: null,
          favorite_count: null,
          share_count: null,
          current_modal_id_before: null,
          current_modal_id_after: null,
          extracted_aweme_id: null,
          source_used: null
        }
      ],
      backend: {
        ...state.harvest.backend,
        capture_session: {
          ...state.harvest.backend.capture_session,
          status: "ready",
          session_id: "session_123"
        },
        payload_preview: {
          ...state.harvest.backend.payload_preview,
          status: "ready",
          target_aweme_id: "a1",
          guard: { ok: true, offending_paths: [] },
          payload: { aweme_id: "a1" },
          summary: { aweme_id: "a1" }
        },
        one_item_flush: {
          ...state.harvest.backend.one_item_flush,
          status: "idle"
        },
        batch_flush: {
          ...state.harvest.backend.batch_flush,
          status: "idle",
          failed: 0
        }
      }
    },
    capture_session_id: "session_123"
  };
}

function withSafeBatchContinuation(state: WholeProfileHarvestState): WholeProfileHarvestState {
  const savedQueue = state.harvest.queue.map((item, index) => index < 10
    ? {
      ...item,
      status: "extracted" as const,
      capture_inbox_item_id: `capture_inbox_item_${index}`,
      extraction_result: "extracted" as const
    }
    : item);
  const pending = savedQueue.filter((item) => ["new", "pending", "processing", "retry", "incomplete", "needs_metadata"].includes(String(item.status))).length;

  return {
    ...state,
    status: "idle",
    phase: "batch_safe_mode_completed",
    workflow: {
      ...state.workflow,
      collection: {
        ...state.workflow.collection,
        status: "idle",
        completed_at: "2026-05-06T12:10:00.000Z",
        last_error: null
      },
      active_task: null,
      action_lock: null
    },
    harvest: {
      ...state.harvest,
      status: "idle",
      queue: savedQueue,
      planned_total: state.harvest.queue.length,
      pending,
      updated: 10,
      failed: 0,
      current_index: 9,
      current_aweme_id: state.harvest.queue[9]?.aweme_id ?? null
    },
    debug: {
      ...state.debug,
      last_response_summary: {
        batch_stop_reason: "limit_reached",
        saved_count_after_batch: 10,
        pending_count_after_batch: pending,
        top_failure: "none",
        failed_count: 0
      }
    }
  };
}

{
  const reconciledQueue = Array.from({ length: 111 }, (_, index) => ({
    index: index + 1,
    aweme_id: `76341927335145${String(index).padStart(5, "0")}`,
    capture_status: index < 30 ? "complete" as const : "new" as const,
    status: index < 30 ? "already_collected" as const : "pending" as const,
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: index < 30 ? "skipped" as const : null,
    last_error: null,
    capture_inbox_item_id: index < 30 ? `inbox_${index + 1}` : null,
    source_url: `https://www.douyin.com/video/76341927335145${String(index).padStart(5, "0")}`,
    profile_card_evidence: {}
  }));
  const reconciledState: WholeProfileHarvestState = {
    ...withClassification(withDryRun(withVerify(baseState())), 111),
    harvest: {
      ...withClassification(withDryRun(withVerify(baseState())), 111).harvest,
      queue: reconciledQueue
    },
    profile_scan: {
      ...withClassification(withDryRun(withVerify(baseState())), 111).profile_scan,
      diagnostics: {
        profile_already_collected_count_before_apply: 0,
        profile_already_collected_count_after_apply: 30,
        profile_already_collected_count: 30,
        profile_eligible_count: 81,
        pending_count: 81,
        profile_queue_total_count: 111,
        backend_reconciliation_counter_source: "backend_profile_matched_items",
        backend_reconciliation_applied_to_profile_counters: "yes",
        backend_reconciliation_backend_profile_captured_count: 30,
        backend_reconciliation_backend_item_count: 30,
        backend_reconciliation_matched_count: 30,
        backend_reconciliation_unmatched_backend_count: 0,
        backend_reconciliation_unmatched_scan_count: 81
      }
    }
  };
  const vm = getWholeProfileHarvestProgressViewModel(reconciledState);
  const row = (label: string): string | undefined => vm.details.technical_rows.find((item) => item.label === label)?.value;
  assert.equal(row("Profile already collected count"), "30", "Advanced diagnostics must render reconciled backend already-collected count instead of stale zero");
  assert.equal(row("Profile eligible count"), "81");
  assert.equal(row("Profile queue total count"), "111");
}

{
  const vm = getWholeProfileHarvestProgressViewModel(baseState());
  assert.equal(vm.stepper.length, 4);
  assert.equal(vm.stepper[0]?.key, "verify");
  assert.equal(vm.stepper[1]?.key, "dry_run");
  assert.equal(vm.stepper[2]?.key, "extract");
  assert.equal(vm.stepper[3]?.key, "flush");
}

{
  const verified = withVerify(baseState());
  const vm = getWholeProfileHarvestProgressViewModel(verified);
  assert.equal(vm.stepper[0]?.status, "done");
  assert.equal(vm.stepper[1]?.status, "locked");
  assert.equal(vm.stepper[2]?.status, "locked");
  assert.equal(vm.stepper[3]?.status, "locked");
}

{
  const dryRun = withClassification(withDryRun(withVerify(baseState())));
  const readiness = getWholeProfileHarvestReadiness(dryRun);
  const vm = getWholeProfileHarvestProgressViewModel(dryRun);
  const runVm = getRunTabViewModel(dryRun, readiness, getWholeProfileHarvestActionState(dryRun));
  assert.equal(readiness.dry_run_ready, true);
  assert.equal(vm.stepper[1]?.status, "done");
  assert.equal(vm.stepper[2]?.status, "next");
  assert.equal(vm.next_action.label, "Start Collecting");
  assert.equal(runVm.primary_action?.label, "Extract Next 10");
}

{
  const extracted = withExtracted(withClassification(withDryRun(withVerify(baseState()))));
  const vm = getWholeProfileHarvestProgressViewModel(extracted);
  assert.equal(vm.cards.profile.title, "Profile");
  assert.equal(vm.cards.profile.metrics[0]?.value, "55");
  assert.equal(vm.cards.profile.metrics[1]?.value, "37");
  assert.equal(vm.cards.profile.metrics.length, 3);
  assert.equal(vm.cards.dry_run.metrics[1]?.value, "3 passed, 0 failed");
  assert.equal(vm.cards.extraction.metrics[0]?.value, "Next 10");
  assert.equal(vm.cards.extraction.metrics[1]?.value, "5");
  assert.match(vm.cards.backend.metrics[0]?.value ?? "", /^Ready: /);
  assert.equal(vm.cards.backend.metrics[1]?.value, "Passed");
  assert.equal(vm.cards.safety.metrics[0]?.value, "None");
  assert.equal(vm.lists.queue_preview.rows.length, 5);
  assert.equal(vm.lists.queue_preview.remaining_count, 5);
  assert.equal(vm.lists.queue_preview.rows[0]?.badge, "NEW");
  assert.match(vm.lists.queue_preview.rows[0]?.aweme_short ?? "", /\.\.\./);
  assert.match(vm.details.profile_url_short, /\.\.\.$|douyin/, "long profile URL should be shortened for main UI");
  assert.equal(vm.details.technical_rows.some((row) => row.label === "Scanner busy"), true, "Advanced details should expose scanner busy diagnostics");
  assert.equal(vm.details.technical_rows.some((row) => row.label === "Scanner next action"), true, "Advanced details should expose scanner next action diagnostics");
  assert.equal(vm.details.technical_rows.some((row) => row.label === "Last scanner result"), true, "Advanced details should expose last scanner action diagnostics");
  assert.equal(vm.lists.extraction_results.rows.length, 2);
  assert.equal(vm.lists.extraction_results.rows[0]?.status, "extracted");
  assert.equal(vm.lists.extraction_results.rows[1]?.status, "failed");
  assert.equal(vm.lists.backend_results.total, 0);
}

{
  const idle = baseState();
  const readiness = getWholeProfileHarvestReadiness(idle);
  const actions = getWholeProfileHarvestActionState(idle);
  const vm = getWholeProfileHarvestProgressViewModel(idle);
  const runVm = getRunTabViewModel(idle, readiness, actions);
  assert.deepEqual(vm.operator_help.quick_start, [
    "Scan Profile to build a clean queue from the current Douyin profile.",
    "Test 3 Videos before a larger extraction run.",
    "Extract Next 10 to read metrics without saving yet.",
    "Create a scan session, run a data check, then start with Save 1 Video."
  ]);
  assert.equal(runVm.workflow_hint, "Workflow: Scan -> Test -> Extract -> Save");
  assert.equal(runVm.secondary_actions[0]?.label, "Scan Profile");
  assert.equal(runVm.compact_metrics.videos_found, 0);
  assert.equal(vm.operator_help.action_help.run_harvest, "Scan Profile first.");
  assert.equal(vm.operator_help.capture_inbox_cta, null);
  assert.equal(getActionHelpText("mode", actions, readiness, idle), "New + incomplete controls which queued videos will be extracted next.");
  assert.equal(getActionHelpText("batch", actions, readiness, idle), "Next 10 controls how many videos the next extraction or save run will process.");
  assert.equal(getActionHelpText("speed", actions, readiness, idle), "Safe controls pacing. Safe is best when you want fewer security checks.");
}

{
  const verified = {
    ...withVerify(baseState()),
    calibration: {
      status: "calibrated" as const,
      ready: true,
      layout: "profile_modal" as const,
      source_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      points: canonicalCalibrationPoints(),
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null
    }
  };
  const readiness = getWholeProfileHarvestReadiness(verified);
  const actions = getWholeProfileHarvestActionState(verified);
  const runVm = getRunTabViewModel(verified, readiness, actions);
  assert.equal(runVm.workflow_hint, null);
  assert.equal(runVm.primary_action?.label, "Scan Profile");
  assert.equal(runVm.primary_action?.enabled, true);
  assert.equal(runVm.secondary_actions[0]?.label, "Rescan");
  assert.equal(runVm.mini_stepper[0]?.status, "done");
  assert.equal(runVm.mini_stepper[1]?.status, "next");
  assert.equal(runVm.mini_stepper[2]?.status, "locked");
  assert.equal(runVm.mini_stepper[3]?.status, "locked");
}

{
  const extracted = withExtracted(withClassification(withDryRun(withVerify(baseState()))));
  const readiness = getWholeProfileHarvestReadiness(extracted);
  const actions = getWholeProfileHarvestActionState(extracted);
  const runVm = getRunTabViewModel(extracted, readiness, actions);
  assert.equal(runVm.compact_metrics.videos_found, 55);
  assert.equal(runVm.compact_metrics.extracted, 1);
  assert.equal(runVm.save_next.visible, true);
  assert.equal(runVm.shortcuts.results_visible, true);
}

{
  const scannerVm = getDouyinScannerMainViewModel(baseState());
  assert.equal(scannerVm.header_status, "Ready");
  assert.equal(scannerVm.status_chips[0]?.label, "Tab");
  assert.equal(scannerVm.primary_action?.label, "Scan Profile");
  assert.equal(scannerVm.primary_action?.enabled, true);
  assert.equal(scannerVm.stats_summary.metrics[0]?.value, "0");
  assert.equal(scannerVm.stats_summary.metrics[3]?.value, "0");
  assert.equal(scannerVm.footer_actions.advanced.visible, true);
  assert.equal(scannerVm.footer_actions.open_capture_inbox.visible, false);
  assert.equal(scannerVm.progress.label, "Idle");

  const scpVm = getScannerControlPanelViewModel(baseState());
  assert.equal(scpVm.headerStatus, "Ready");
  assert.equal(scpVm.profileScanned, false);
  assert.equal(scpVm.scanDataVisible, false);
  assert.equal(scpVm.emptyState, "Scan a profile to build the collection plan.");
  assert.equal(scpVm.action.key, "scan_profile");
  assert.equal(scpVm.action.title, "Scan Profile");
  assert.equal(scpVm.action.description, "Scan this Douyin profile and build a collection plan.");
  assert.equal(scpVm.health.api, "API not checked");
  assert.equal(scpVm.health.calibration, "Cal needed");
  assert.equal(scpVm.counts.queueCount, 0);
}

{
  const scannerVm = getDouyinScannerMainViewModel(withClassification(withExtracted(withDryRun(withVerify(baseState())))));
  const metricValue = (label: string): string | undefined => scannerVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;
  assert.equal(scannerVm.header_status, "56 videos");
  assert.equal(metricValue("Found this run"), "55");
  assert.equal(metricValue("Videos found"), "56");
  assert.equal(metricValue("New"), "21");
  assert.equal(metricValue("Queued"), "10");
  assert.equal(metricValue("Collected"), "1");
  assert.equal(metricValue("Saved"), "0");
  assert.equal(scannerVm.primary_action?.label, "Start Collecting");
  assert.equal(scannerVm.footer_actions.open_capture_inbox.visible, false);
  assert.equal(scannerVm.footer_actions.pause_or_resume.visible, true);
  assert.equal(scannerVm.alert?.title, undefined);
  assert.equal(scannerVm.progress.label, "Collected");
}

{
  const calibrated = withDryRun(baseState());
  const scanVm = getScannerControlPanelViewModel(calibrated);
  assert.equal(scanVm.action.key, "scan_profile");
  assert.notEqual(scanVm.action.title, "Calibrate 4 Points");
  assert.equal(scanVm.health.calibration, "Cal ready");

  const detectedProfile = getScannerControlPanelViewModel({
    ...calibrated,
    page_context: { ...calibrated.page_context, page_type: "profile", current_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture" }
  });
  assert.equal(detectedProfile.health.profile, "Profile");

  const unclassifiedQueued = withExtracted(withDryRun(withVerify(baseState())));
  const blockedVm = getScannerControlPanelViewModel(unclassifiedQueued);
  assert.equal(blockedVm.action.key, "scan_profile");
  assert.equal(blockedVm.counts.queueCount, 10);

  const uncalibratedQueued = withClassification(withVerify(baseState()));
  const calibrateVm = getScannerControlPanelViewModel(uncalibratedQueued);
  assert.equal(calibrateVm.action.key, "calibrate");
  assert.equal(calibrateVm.action.title, "Calibrate 4 Points");

  const queued = withClassification(unclassifiedQueued);
  const startVm = getScannerControlPanelViewModel(queued);
  assert.equal(startVm.headerStatus, "56 videos");
  assert.equal(startVm.profileScanned, true);
  assert.equal(startVm.scanDataVisible, true);
  assert.equal(startVm.emptyState, null);
  assert.equal(startVm.action.key, "start_collecting");
  assert.equal(startVm.counts.newCount, 9);
  assert.equal(startVm.counts.incompleteCount, 0);
  assert.equal(startVm.counts.failedCount, 1);
  assert.equal(startVm.counts.alreadyCollectedCount, 0);
  assert.equal(startVm.counts.queueCount, 10);

  const savedQueueState = {
    ...queued,
    harvest: {
      ...queued.harvest,
      queue: queued.harvest.queue.map((item, index) => {
        if (index === 0) {
          return {
            ...item,
            status: "extracted" as const,
            capture_inbox_item_id: "capture_inbox_item_1",
            extraction_result: "extracted" as const
          };
        }
        if (index === 1) {
          return {
            ...item,
            status: "processing" as const,
            capture_status: "incomplete" as const
          };
        }
        return item;
      })
    }
  };
  const savedVm = getScannerControlPanelViewModel(savedQueueState);
  assert.equal(savedVm.counts.newCount, 7, "queue-derived counters must shrink new items after one save and one in-progress item");
  assert.equal(savedVm.counts.incompleteCount, 1, "queue-derived counters must classify in-progress incomplete items correctly");
  assert.equal(savedVm.counts.alreadyCollectedCount, 1, "queue-derived counters must immediately reflect saved queue items");
  assert.equal(savedVm.counts.queueCount, 9, "queue-derived counters must only count pending or processing items still in queue");

  const runningState = { ...queued, status: "harvesting" as const, workflow: { ...queued.workflow, collection: { ...queued.workflow.collection, status: "running" as const, started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:43:00.000Z", completed_at: null, last_error: null }, active_task: "collect_videos" as const, action_lock: "collect_videos" as const }, harvest: { ...queued.harvest, status: "running" as const, started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:43:00.000Z" }, debug: { ...queued.debug, last_response_summary: { batch_processed_count: 3, batch_selected_count: 10, batch_success_count: 2 } }, updated_at: "2030-05-07T11:43:00.000Z" };
  const runningVm = getScannerControlPanelViewModel(runningState);
  const runningMainVm = getDouyinScannerMainViewModel(runningState);
  assert.equal(runningVm.action.key, "pause");
  assert.equal(runningVm.action.buttonLabel, "Collecting videos...");
  assert.equal(runningMainVm.primary_action?.label, "Collecting videos...");
  assert.equal(runningMainVm.primary_action?.enabled, false);
  assert.equal(runningMainVm.progress.detail, "Collecting batch: 3/10 processed, 2 saved.");
  assert.notEqual(runningMainVm.primary_action?.label, "Start Collecting");
  assert.notEqual(runningMainVm.primary_action?.label, "Continue Next 10");

  const diagnosticLockedState = {
    ...queued,
    profile_scan: {
      ...queued.profile_scan,
      diagnostics: {
        ...(queued.profile_scan.diagnostics && typeof queued.profile_scan.diagnostics === "object" ? queued.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_run_id: "scan_profile_22C11B_1778899282538_next_10_safe",
        batch_heartbeat_at: "2030-05-07T11:43:30.000Z",
        batch_heartbeat_stage: "after_checkpoint"
      }
    }
  };
  const diagnosticLockedPanelVm = getScannerControlPanelViewModel(diagnosticLockedState);
  const diagnosticLockedMainVm = getDouyinScannerMainViewModel(diagnosticLockedState);
  assert.equal(diagnosticLockedPanelVm.action.key, "pause", "recent safe-batch runner diagnostics must keep the primary action locked");
  assert.equal(diagnosticLockedPanelVm.action.buttonLabel, "Collecting videos...");
  assert.equal(diagnosticLockedMainVm.primary_action?.label, "Collecting videos...");
  assert.equal(diagnosticLockedMainVm.primary_action?.enabled, false);
  assert.notEqual(diagnosticLockedMainVm.primary_action?.label, "Start Collecting");

  const pausingState = { ...queued, status: "harvesting" as const, workflow: { ...queued.workflow, collection: { ...queued.workflow.collection, status: "pausing" as const, started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:43:10.000Z", completed_at: null, last_error: null }, active_task: "collect_videos" as const, action_lock: "collect_videos" as const }, harvest: { ...queued.harvest, status: "running" as const, pause_requested: true, pause_requested_at: "2030-05-07T11:43:10.000Z", pause_message: "Pause requested. Stopping after the current video.", started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:43:10.000Z" }, updated_at: "2030-05-07T11:43:10.000Z" };
  const pausingVm = getScannerControlPanelViewModel(pausingState);
  const pausingMainVm = getDouyinScannerMainViewModel(pausingState);
  assert.equal(pausingVm.headerStatus, "Pausing...");
  assert.equal(pausingVm.action.key, "pause");
  assert.equal(pausingVm.action.buttonLabel, "Pausing...");
  assert.equal(pausingVm.action.enabled, false);
  assert.equal(pausingMainVm.footer_actions.pause_or_resume.label, "Pausing...");
  assert.equal(pausingMainVm.footer_actions.pause_or_resume.enabled, false);
  assert.equal(pausingMainVm.primary_action?.label, "Pausing...");

  const staleRunningVm = getScannerControlPanelViewModel({ ...queued, status: "harvesting", harvest: { ...queued.harvest, status: "running", started_at: null, updated_at: null } });
  assert.equal(staleRunningVm.action.key, "start_collecting", "stale legacy running lock must not force scanner into pause state");
  assert.notEqual(staleRunningVm.action.description, "Wait for the current step to finish.");

  const staleWorkflowRunning = { ...queued, status: "harvesting" as const, workflow: { ...queued.workflow, collection: { ...queued.workflow.collection, status: "running" as const, started_at: "2026-05-06T12:03:00.000Z", updated_at: "2026-05-06T12:03:00.000Z", completed_at: null, last_error: null }, active_task: "collect_videos" as const, action_lock: "collect_videos" as const }, harvest: { ...queued.harvest, status: "running" as const, started_at: "2026-05-06T12:03:00.000Z", updated_at: "2026-05-06T12:03:00.000Z" } };
  const staleWorkflowPanelVm = getScannerControlPanelViewModel(staleWorkflowRunning);
  const staleWorkflowMainVm = getDouyinScannerMainViewModel(staleWorkflowRunning);
  assert.equal(staleWorkflowPanelVm.action.key, "start_collecting", "stale workflow collection must not expose Pause as the primary action");
  assert.equal(staleWorkflowPanelVm.headerStatus, "56 videos", "stale workflow collection must not show contradictory Collecting header");
  assert.equal(staleWorkflowMainVm.primary_action?.label, "Start Collecting", "stale workflow collection must keep Start Collecting as the primary label");
  assert.equal(staleWorkflowMainVm.header_status, "56 videos", "stale workflow collection must not show Collecting in the compact header");
  assert.equal(staleWorkflowMainVm.progress.label, "Collected", "stale workflow collection must not show Collecting progress");

  const pausedState = { ...queued, status: "paused" as const, workflow: { ...queued.workflow, collection: { ...queued.workflow.collection, status: "paused" as const, started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:44:00.000Z", completed_at: null, last_error: null } }, harvest: { ...queued.harvest, status: "paused" as const, pause_message: "Resume when the Douyin tab is ready again." } };
  const pausedVm = getScannerControlPanelViewModel(pausedState);
  assert.equal(pausedVm.action.key, "resume");
  const pausedDeckVm = getActionDeckViewModel(pausedState);
  assert.equal(pausedDeckVm.health.safety.value, "Paused");
  assert.equal(pausedDeckVm.alert?.title, "Collecting paused");
  assert.equal(pausedDeckVm.alert?.message, "Resume when the Douyin tab is ready again.");

  const waitingForTabDeckState = {
    ...queued,
    harvest: {
      ...queued.harvest,
      pause_message: "Return to the Douyin tab to continue collecting."
    },
    profile_scan: {
      ...queued.profile_scan,
      diagnostics: {
        ...(queued.profile_scan.diagnostics && typeof queued.profile_scan.diagnostics === "object" ? queued.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_tab_inactive_evidence: "target_tab_inactive",
        trace_collect_tab_inactive_state: "inactive"
      }
    },
    collect_job: {
      ...queued.collect_job,
      state: "waiting_for_active_tab" as const,
      job_id: "collect_job_waiting_1",
      started_at: "2030-05-07T11:43:20.000Z",
      updated_at: "2030-05-07T11:43:40.000Z",
      heartbeat_at: "2030-05-07T11:43:40.000Z",
      runner_ack_at: "2030-05-07T11:43:25.000Z",
      selected_count: 10,
      current_step: "wait_for_active_tab"
    }
  };
  const waitingForTabDeckVm = getActionDeckViewModel(waitingForTabDeckState);
  const waitingForTabPanelVm = getScannerControlPanelViewModel(waitingForTabDeckState);
  const waitingForTabMainVm = getDouyinScannerMainViewModel(waitingForTabDeckState);
  assert.equal(waitingForTabDeckVm.health.safety.value, "Paused", "canonical waiting-for-active-tab runtime must surface paused safety state in the action deck");
  assert.equal(waitingForTabDeckVm.alert?.title, "Waiting for tab", "canonical waiting-for-active-tab runtime must preserve waiting-tab alert title in the action deck");
  assert.equal(waitingForTabDeckVm.alert?.message, "Return to the Douyin tab to continue collecting.");
  assert.equal(waitingForTabPanelVm.headerStatus, "Waiting for tab", "scanner control panel must preserve waiting-for-active-tab wording");
  assert.equal(waitingForTabMainVm.header_status, "Waiting for tab", "main scanner view must preserve waiting-for-active-tab wording");
  assert.equal(waitingForTabMainVm.progress.label, "Waiting for tab", "main scanner progress label must preserve waiting-for-active-tab wording");
  assert.equal(waitingForTabMainVm.alert?.title, "Waiting for tab", "main scanner alert title must preserve waiting-for-active-tab wording");
  assert.equal(waitingForTabMainVm.alert?.message, "Return to the Douyin tab to continue collecting.", "waiting-for-active-tab alert detail must preserve the canonical resume hint");

  const runtimeWaitingState = {
    ...queued,
    collect_job: {
      ...queued.collect_job,
      state: "waiting_for_active_tab" as const,
      job_id: "collect_job_runtime_waiting_1",
      started_at: "2030-05-07T11:43:20.000Z",
      updated_at: "2030-05-07T11:43:40.000Z",
      heartbeat_at: "2030-05-07T11:43:40.000Z",
      runner_ack_at: "2030-05-07T11:43:25.000Z",
      selected_count: 10,
      current_step: "wait_for_active_tab"
    },
    active_collect_runtime: {
      ...queued.active_collect_runtime,
      job_id: "collect_job_runtime_waiting_1",
      canonical_state: "waiting_for_active_tab" as const,
      canonical_phase: "collecting" as const,
      current_step: "wait_for_active_tab",
      current_aweme_id: null,
      current_item_index: 4,
      selected_count: 10,
      attempted_count: 4,
      succeeded_count: 3,
      failed_count: 0,
      skipped_count: 0,
      heartbeat_at: "2030-05-07T11:43:40.000Z",
      lock_owner: "collect_job_runtime_waiting_1",
      lock_expires_at: "2030-05-07T11:44:10.000Z",
      last_update_source: "runner.wait_for_active_tab",
      updated_at: "2030-05-07T11:43:40.000Z",
      trace: {
        ...queued.active_collect_runtime.trace,
        summary: {
          ...(queued.active_collect_runtime.trace.summary ?? {}),
          trace_progress_active_batch_runtime_required: "yes",
          trace_progress_visible_status_source: "active_collect_runtime",
          trace_progress_visible_phase_source: "active_collect_runtime",
          trace_progress_runtime_status_committed: "waiting_for_active_tab",
          trace_progress_runtime_phase_committed: "collecting"
        },
        per_item_backend_writes: {
          ...(queued.active_collect_runtime.trace.per_item_backend_writes ?? {})
        }
      }
    },
    profile_scan: {
      ...queued.profile_scan,
      diagnostics: {
        ...(queued.profile_scan.diagnostics && typeof queued.profile_scan.diagnostics === "object" ? queued.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_tab_inactive_evidence: "target_tab_inactive",
        trace_collect_tab_inactive_state: "inactive"
      }
    }
  };
  const runtimeWaitingMainVm = getDouyinScannerMainViewModel(runtimeWaitingState);
  assert.equal(runtimeWaitingMainVm.progress.label, "Waiting for tab", "runtime-authoritative waiting status must override legacy collecting wording");
  assert.equal(runtimeWaitingMainVm.progress.detail, "Return to the Douyin tab to continue collecting.", "runtime-authoritative waiting status must keep the canonical resume hint");

  const runtimeOpeningState = {
    ...queued,
    collect_job: {
      ...queued.collect_job,
      state: "running" as const,
      job_id: "collect_job_runtime_opening_1",
      started_at: "2030-05-07T11:43:20.000Z",
      updated_at: "2030-05-07T11:43:28.000Z",
      heartbeat_at: "2030-05-07T11:43:28.000Z",
      runner_ack_at: "2030-05-07T11:43:21.000Z",
      selected_count: 10,
      current_step: "open_target_modal"
    },
    active_collect_runtime: {
      ...queued.active_collect_runtime,
      job_id: "collect_job_runtime_opening_1",
      canonical_state: "running" as const,
      canonical_phase: "opening_target" as const,
      current_step: "open_target_modal",
      current_aweme_id: queued.harvest.queue[0]!.aweme_id,
      current_item_index: 0,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 0,
      succeeded_count: 0,
      failed_count: 0,
      skipped_count: 0,
      heartbeat_at: "2030-05-07T11:43:28.000Z",
      lock_owner: "collect_job_runtime_opening_1",
      lock_expires_at: "2030-05-07T11:43:58.000Z",
      last_update_source: "runner.open_target_modal",
      updated_at: "2030-05-07T11:43:28.000Z",
      trace: {
        ...queued.active_collect_runtime.trace,
        summary: {
          ...(queued.active_collect_runtime.trace.summary ?? {}),
          trace_progress_active_batch_runtime_required: "yes",
          trace_progress_visible_status_source: "active_collect_runtime",
          trace_progress_visible_phase_source: "active_collect_runtime",
          trace_progress_runtime_status_committed: "collecting",
          trace_progress_runtime_phase_committed: "opening_target"
        },
        per_item_backend_writes: {
          ...(queued.active_collect_runtime.trace.per_item_backend_writes ?? {})
        }
      }
    }
  };
  const runtimeOpeningMainVm = getDouyinScannerMainViewModel(runtimeOpeningState);
  assert.equal(runtimeOpeningMainVm.progress.label, "Collecting", "runtime-authoritative active batch keeps collecting as the committed visible label while opening is in-flight");
  assert.equal(runtimeOpeningMainVm.progress.detail, "Collecting batch: 5/15 processed, 0 saved.", "runtime-authoritative opening-step state keeps the existing active-batch progress detail stable");


  const emptyScanResult = { ...withDryRun(withVerify(baseState())), profile_scan: { ...withVerify(baseState()).profile_scan, accepted_target_count: 0, targets: [], target_details: [] }, verify: { ...withVerify(baseState()).verify, verified_target_count: 0, accepted_target_count: 0, targets: [], target_details: [] }, harvest: { ...withDryRun(withVerify(baseState())).harvest, planned_total: 0, queue_preview: [] }, target_status: { new: 0, incomplete: 0, complete: 0, failed: 0, skipped: 0, unknown: 0 } };
  const emptyScanVm = getScannerControlPanelViewModel(emptyScanResult);
  assert.equal(emptyScanVm.action.key, "scan_profile");
  assert.equal(emptyScanVm.profileScanned, false, "zero-result scan must keep strict profile readiness false");
  assert.equal(emptyScanVm.scanDataVisible, true, "zero-result scan must still render scanner counters and empty-result guidance");
  assert.equal(emptyScanVm.emptyState, "No eligible videos found.");

  const partialScanState: WholeProfileHarvestState = {
    ...withDryRun(withVerify(baseState())),
    profile_scan: {
      ...withVerify(baseState()).profile_scan,
      accepted_target_count: 199,
      targets: Array.from({ length: 199 }, (_, index) => `7634192733514502${String(index).padStart(3, "0")}`),
      diagnostics: {
        ...(withVerify(baseState()).profile_scan.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 203,
        profile_queue_total_count: 199,
        missing_profile_video_count: 4,
        profile_scan_incomplete_reason: "dom_settled_before_all_cards_loaded",
        scan_finalization_result: "incomplete",
        profile_scan_source_ledger: "network_probe+dom_probe",
        network_post_exhausted_evidence_gate_passed_22C12B: "no",
        minimal_scan_active_profile_post_fetch_enabled_22C12B: "no",
        minimal_scan_active_profile_post_fetch_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: null,
        minimal_scan_active_profile_post_only_aweme_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: null,
        minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "none",
        minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: 0,
        minimal_scan_active_profile_post_template_found_22C13B: "unknown",
        minimal_scan_active_profile_post_template_source_22C13B: "none",
        minimal_scan_active_profile_post_template_endpoint_path_22C13B: "none",
        minimal_scan_active_profile_post_template_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "unknown",
        minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_secret_keys_present_22C13B: "unknown",
        minimal_scan_active_profile_post_template_secret_query_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: "none",
        minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: "none",
        minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_data_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_result_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B: {},
        minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: [],
        active_profile_post_fetch_page_count: 0,
        active_profile_post_fetch_page_cap: 60,
        active_profile_post_fetch_page_cap_hit_count: 0,
        active_profile_post_fetch_page_cap_hit_while_has_more_count: 0,
        active_profile_post_fetch_runtime_timeout_ms: 12000,
        active_profile_post_fetch_runtime_timeout_hit: "no",
        active_profile_post_fetch_continuation_policy: "has_more_driven_22C13B",
        active_profile_post_fetch_fallback_cycle_eligible: "no",
        active_profile_post_fetch_fallback_cycle_attempted: "no",
        active_profile_post_fetch_fallback_cycle_stop_reason: "none",
        active_profile_post_fetch_fallback_cycle_has_more_state: "unknown",
        active_profile_post_fetch_fallback_cycle_request_count: 0,
        active_profile_post_fetch_fallback_cycle_batch_count: 0
      }
    },
    verify: {
      ...withVerify(baseState()).verify,
      accepted_target_count: 199,
      verified_target_count: 199,
      targets: Array.from({ length: 199 }, (_, index) => `7634192733514502${String(index).padStart(3, "0")}`)
    },
    debug: {
      ...withDryRun(withVerify(baseState())).debug,
      last_response_summary: {
        ...(withDryRun(withVerify(baseState())).debug.last_response_summary as Record<string, unknown>),
        diagnostics_channel: "runtime_debug_diagnostics",
        expected_profile_video_count: 203,
        profile_queue_total_count: 199,
        missing_profile_video_count: 4,
        profile_scan_incomplete_reason: "dom_settled_before_all_cards_loaded",
        scan_finalization_result: "incomplete",
        profile_scan_source_ledger: "network_probe+dom_probe",
        network_post_exhausted_evidence_gate_passed_22C12B: "no",
        minimal_scan_active_profile_post_fetch_enabled_22C12B: "no",
        minimal_scan_active_profile_post_fetch_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: "sec_uid_missing_from_profile_url",
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: null,
        minimal_scan_active_profile_post_only_aweme_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: null,
        minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "none",
        minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: [],
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: "no",
        minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: 0,
        minimal_scan_active_profile_post_template_found_22C13B: "unknown",
        minimal_scan_active_profile_post_template_source_22C13B: "none",
        minimal_scan_active_profile_post_template_endpoint_path_22C13B: "none",
        minimal_scan_active_profile_post_template_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "unknown",
        minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_secret_keys_present_22C13B: "unknown",
        minimal_scan_active_profile_post_template_secret_query_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: "none",
        minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: "none",
        minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_data_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_response_result_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B: {},
        minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: [],
        active_profile_post_fetch_page_count: 0,
        active_profile_post_fetch_page_cap: 60,
        active_profile_post_fetch_page_cap_hit_count: 0,
        active_profile_post_fetch_page_cap_hit_while_has_more_count: 0,
        active_profile_post_fetch_runtime_timeout_ms: 12000,
        active_profile_post_fetch_runtime_timeout_hit: "no",
        active_profile_post_fetch_continuation_policy: "has_more_driven_22C13B",
        active_profile_post_fetch_fallback_cycle_eligible: "no",
        active_profile_post_fetch_fallback_cycle_attempted: "no",
        active_profile_post_fetch_fallback_cycle_stop_reason: "none",
        active_profile_post_fetch_fallback_cycle_has_more_state: "unknown",
        active_profile_post_fetch_fallback_cycle_request_count: 0,
        active_profile_post_fetch_fallback_cycle_batch_count: 0
      }
    }
  };
  const partialScanVm = getScannerControlPanelViewModel(partialScanState);
  assert.equal(partialScanVm.profileScanned, false, "incomplete scan must remain strictly not-ready for collecting");
  assert.equal(partialScanVm.scanDataVisible, true, "incomplete scan must expose partial counters in popup");
  assert.equal(partialScanVm.headerStatus, "199 / 203 videos", "incomplete scan header must show expected/found context");
  assert.equal(partialScanVm.emptyState, "Profile scan incomplete: expected 203, found 199, missing 4.");
  assert.equal(partialScanVm.action.key, "scan_profile", "incomplete scan must keep canonical retry action");

  const partialScanMainVm = getDouyinScannerMainViewModel(partialScanState);
  assert.equal(partialScanMainVm.primary_action?.key, "scan_profile", "incomplete scan must keep Start Collecting disabled by canonical primary action");

  const severeDomOnlyState: WholeProfileHarvestState = {
    ...partialScanState,
    debug: {
      ...partialScanState.debug,
      last_response_summary: {
        ...(partialScanState.debug.last_response_summary as Record<string, unknown>),
        expected_profile_video_count: 203,
        profile_queue_total_count: 25,
        missing_profile_video_count: 178,
        scan_completeness_gate_result: "blocked",
        scan_completeness_gate_reason: "dom_only_fallback_under_expected_active_fetch_active_profile_post_response_status_non_zero",
        scan_completeness_found_count: 25,
        scan_completeness_ready_blocked: "yes",
        scan_completeness_dom_only_fallback: "yes",
        scan_completeness_active_fetch_meaningful: "no"
      }
    }
  };
  const severeDomOnlyMainVm = getDouyinScannerMainViewModel(severeDomOnlyState);
  const severeDomOnlyPanelVm = getScannerControlPanelViewModel(severeDomOnlyState);
  assert.equal(severeDomOnlyMainVm.primary_action?.key, "scan_profile", "severe DOM-only partial scan must keep retry Scan Profile as primary action");
  assert.notEqual(severeDomOnlyPanelVm.action.title, "Calibrate 4 Points", "severe DOM-only partial scan must not route to calibration");
  assert.equal(severeDomOnlyMainVm.alert?.title, "Profile scan incomplete");
  assert.match(severeDomOnlyMainVm.alert?.message ?? "", /active profile API failed; found 25 of expected 203/);

  const resumableBudgetState: WholeProfileHarvestState = {
    ...partialScanState,
    workflow: {
      ...partialScanState.workflow,
      scan: { ...partialScanState.workflow.scan, status: "idle", updated_at: "2026-05-06T10:10:00.000Z", completed_at: "2026-05-06T10:10:00.000Z", last_error: "incomplete_api_budget_exhausted" },
      active_task: null,
      action_lock: null
    },
    scan_job: {
      ...partialScanState.scan_job,
      status: "completed",
      expected_count: 203,
      total_discovered: 199,
      total_persisted: 199,
      page_count: 128,
      request_count: 128,
      has_more_state: true,
      last_status_code: 0,
      last_error: "incomplete_api_budget_exhausted"
    },
    profile_scan: {
      ...partialScanState.profile_scan,
      status: "success",
      diagnostics: {
        ...(partialScanState.profile_scan.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 203,
        profile_queue_total_count: 199,
        missing_profile_video_count: 4,
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
        scan_progress_discovered: 199,
        scan_progress_expected: 203,
        scan_progress_remaining: 4,
        scan_progress_pages: 128,
        scan_progress_requests: 128
      }
    },
    debug: {
      ...partialScanState.debug,
      last_response_summary: {
        ...(partialScanState.debug.last_response_summary as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 203,
        profile_queue_total_count: 199,
        missing_profile_video_count: 4,
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
        scan_progress_discovered: 199,
        scan_progress_expected: 203,
        scan_progress_remaining: 4,
        scan_progress_pages: 128,
        scan_progress_requests: 128
      }
    }
  };
  const resumableBudgetPanelVm = getScannerControlPanelViewModel(resumableBudgetState);
  const resumableBudgetMainVm = getDouyinScannerMainViewModel(resumableBudgetState);
  assert.equal(resumableBudgetPanelVm.action.key, "scan_profile", "page-budget resumable scan must keep Scan Profile as the canonical action key");
  assert.equal(resumableBudgetPanelVm.action.buttonLabel, "Continue Scan", "page-budget resumable panel action must show Continue Scan");
  const resumableBudgetPanelCopy = resumableBudgetPanelVm.emptyState ?? resumableBudgetPanelVm.primaryAction.description ?? "";
  assert.match(resumableBudgetPanelCopy, /Large profile scan paused at page budget \(128 pages\)\./, "page-budget resumable panel copy must explain the page budget pause");
  assert.doesNotMatch(resumableBudgetPanelCopy, /Profile scan incomplete/, "page-budget resumable panel copy must not use blocking incomplete wording");
  assert.equal(resumableBudgetMainVm.primary_action?.key, "scan_profile", "page-budget resumable main action must keep Scan Profile key");
  assert.equal(resumableBudgetMainVm.primary_action?.label, "Continue Scan", "page-budget resumable main action must show Continue Scan");
  assert.match(resumableBudgetMainVm.primary_action?.reason ?? "", /Continue Scan will fetch the remaining unseen pages|saved continuation cursor|healthy pagination batch/, "page-budget resumable main action reason must explain checkpoint continuation");
  assert.equal(resumableBudgetMainVm.alert?.title, "Continue Scan", "page-budget resumable main alert must use continuation title");
  assert.match(resumableBudgetMainVm.alert?.message ?? "", /Large profile scan paused at page budget \(128 pages\)\./, "page-budget resumable alert must explain the budget pause");
  assert.match(resumableBudgetMainVm.alert?.message ?? "", /Current-run progress excludes previously persisted history/, "page-budget resumable alert must explain current-run versus persisted-history semantics");
  assert.match(resumableBudgetMainVm.alert?.message ?? "", /Continue Scan will fetch the remaining unseen pages|saved continuation cursor|healthy pagination batch/, "page-budget resumable alert must guide continuation without source-failure wording");
  assert.doesNotMatch(resumableBudgetMainVm.alert?.message ?? "", /active profile API failed|Profile scan incomplete/, "page-budget resumable alert must not report source failure or blocking incomplete copy");
  assert.match(resumableBudgetMainVm.progress.detail, /Current-run progress excludes previously persisted history/, "page-budget resumable progress detail must keep current-run progress separate from persisted history");

  const partialScanProgressVm = getWholeProfileHarvestProgressViewModel(partialScanState);
  const partialScanTechValue = (label: string): string | undefined => partialScanProgressVm.details.technical_rows.find((row) => row.label === label)?.value;
  const partialPostScanCounterPipelineTrace = JSON.parse(partialScanTechValue("POST_SCAN_COUNTER_PIPELINE_TRACE") ?? "{}") as Record<string, Record<string, unknown>>;
  assert.equal(partialPostScanCounterPipelineTrace.scan_result?.trace_scan_completed, "no", "incomplete scan trace must not report scan completion");
  assert.equal(partialPostScanCounterPipelineTrace.snapshot_state?.trace_counter_snapshot_exists, "no", "incomplete scan trace must not report counter snapshot usage");
  assert.equal(partialPostScanCounterPipelineTrace.final_popup_render_input?.trace_popup_tiles_render_used_snapshot, "no", "incomplete scan trace must not render popup tiles from snapshots");
  assert.equal(partialScanTechValue("Profile expected video count"), "203", "advanced diagnostics must show expected scan count when present");
  assert.equal(partialScanTechValue("Profile found video count"), "199", "advanced diagnostics must show found scan count");
  assert.equal(partialScanTechValue("Profile missing video count"), "4", "advanced diagnostics must show missing scan count");
  assert.equal(partialScanTechValue("Profile scan incomplete reason"), "dom_settled_before_all_cards_loaded", "advanced diagnostics must show incomplete reason");
  assert.equal(partialScanTechValue("Profile scan source ledger"), "network_probe+dom_probe", "advanced diagnostics must show source ledger when present");
  assert.equal(partialScanTechValue("Network collection stop reason"), "no + exhaustion_evidence_not_strong", "advanced diagnostics must gate weak stop-reason-only exhaustion evidence");
  assert.equal(partialScanTechValue("Active profile-post fetch enabled"), "no", "advanced diagnostics must always render active profile-post enablement state");
  assert.equal(partialScanTechValue("Active profile-post fetch attempted"), "no", "advanced diagnostics must render not-attempted active profile-post fetch state");
  assert.equal(partialScanTechValue("Active profile-post fetch stop reason"), "sec_uid_missing_from_profile_url", "advanced diagnostics must render active profile-post stop reason");
  assert.equal(partialScanTechValue("Active profile-post fetch not-attempted reason"), "sec_uid_missing_from_profile_url", "advanced diagnostics must render active profile-post not-attempted reason");
  assert.equal(partialScanTechValue("Active profile-post fetch target count"), "0", "advanced diagnostics must render active profile-post target count");
  assert.equal(partialScanTechValue("Active profile-post fetch has-more state"), "unknown", "advanced diagnostics must render active profile-post has-more state even when missing");
  assert.equal(partialScanTechValue("Active profile-post active-only aweme count"), "0", "advanced diagnostics must render active-only contribution count");
  assert.equal(partialScanTechValue("Active profile-post fetch request count"), "0", "advanced diagnostics must render active profile-post request count");
  assert.equal(partialScanTechValue("Active profile-post fetch batch count"), "0", "advanced diagnostics must render active profile-post batch count");
  assert.equal(partialScanTechValue("Active profile-post fetch page count"), "0", "advanced diagnostics must render active profile-post page count");
  assert.equal(partialScanTechValue("Active profile-post fetch page cap"), "60", "advanced diagnostics must render active profile-post page cap");
  assert.equal(partialScanTechValue("Active profile-post fetch page cap hit count"), "0", "advanced diagnostics must render active profile-post page-cap hit count");
  assert.equal(partialScanTechValue("Active profile-post fetch page cap hit while has-more count"), "0", "advanced diagnostics must render active profile-post has-more-at-cap diagnostics");
  assert.equal(partialScanTechValue("Active profile-post fetch runtime timeout ms"), "12000", "advanced diagnostics must render active profile-post runtime timeout threshold");
  assert.equal(partialScanTechValue("Active profile-post fetch runtime timeout hit"), "no", "advanced diagnostics must render active profile-post runtime timeout hit state");
  assert.equal(partialScanTechValue("Active profile-post fetch continuation policy"), "has_more_driven_22C13B", "advanced diagnostics must render active profile-post continuation policy");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle eligible"), "no", "advanced diagnostics must render active profile-post fallback-cycle eligibility");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle attempted"), "no", "advanced diagnostics must render active profile-post fallback-cycle attempted state");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle stop reason"), "none", "advanced diagnostics must render active profile-post fallback-cycle stop reason");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle has-more state"), "unknown", "advanced diagnostics must render active profile-post fallback-cycle has-more state");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle request count"), "0", "advanced diagnostics must render active profile-post fallback-cycle request count");
  assert.equal(partialScanTechValue("Active profile-post fallback-cycle batch count"), "0", "advanced diagnostics must render active profile-post fallback-cycle batch count");
  assert.equal(partialScanTechValue("Active profile-post fetch endpoint variant attempts"), "0", "advanced diagnostics must render active profile-post endpoint attempt counts");
  assert.equal(partialScanTechValue("Active profile-post fetch endpoint variant success"), "none", "advanced diagnostics must render active profile-post endpoint success path fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch endpoint attempt samples"), "none", "advanced diagnostics must render active profile-post endpoint attempt samples even when absent");
  assert.equal(partialScanTechValue("Active profile-post fetch parser route"), "none", "advanced diagnostics must render parser route fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch parser routes tried"), "none", "advanced diagnostics must render parser routes tried fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch parser direct routes tried"), "none", "advanced diagnostics must render parser direct-routes fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch parser direct match count"), "0", "advanced diagnostics must render parser direct match count fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch parser fallback attempted"), "no", "advanced diagnostics must render parser fallback attempted state");
  assert.equal(partialScanTechValue("Active profile-post fetch parser fallback match count"), "0", "advanced diagnostics must render parser fallback match counts");
  assert.equal(partialScanTechValue("Active profile-post fetch parser fallback candidate count"), "0", "advanced diagnostics must render parser fallback candidate counts");
  assert.equal(partialScanTechValue("Active profile-post fetch parser fallback visited nodes"), "0", "advanced diagnostics must render parser fallback traversal evidence");
  assert.equal(partialScanTechValue("Active profile-post fetch error"), "none", "advanced diagnostics must render active profile-post error field even when absent");
  assert.equal(partialScanTechValue("Active profile-post fetch response shape"), "unknown", "advanced diagnostics must render active profile-post response shape field even when absent");
  assert.equal(partialScanTechValue("Active profile-post template found"), "unknown", "advanced diagnostics must render active profile-post template found fallback");
  assert.equal(partialScanTechValue("Active profile-post template source"), "none", "advanced diagnostics must render active profile-post template source fallback");
  assert.equal(partialScanTechValue("Active profile-post template endpoint path"), "none", "advanced diagnostics must render active profile-post template endpoint fallback");
  assert.equal(partialScanTechValue("Active profile-post template query keys"), "none", "advanced diagnostics must render active profile-post template query keys fallback");
  assert.equal(partialScanTechValue("Active profile-post template required query keys"), "none", "advanced diagnostics must render active profile-post template required query keys fallback");
  assert.equal(partialScanTechValue("Active profile-post template required query keys available"), "unknown", "advanced diagnostics must render active profile-post template required-query-keys availability fallback");
  assert.equal(partialScanTechValue("Active profile-post template missing required query keys"), "none", "advanced diagnostics must render active profile-post template missing required query keys fallback");
  assert.equal(partialScanTechValue("Active profile-post template secret keys present"), "unknown", "advanced diagnostics must render active profile-post template secret key presence fallback");
  assert.equal(partialScanTechValue("Active profile-post template secret query keys"), "none", "advanced diagnostics must render active profile-post template secret query keys fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch response status code"), "none", "advanced diagnostics must render active profile-post response status code fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch response status message"), "none", "advanced diagnostics must render active profile-post response status message fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch response top-level keys"), "none", "advanced diagnostics must render active profile-post response top-level keys fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch response data keys"), "none", "advanced diagnostics must render active profile-post response data keys fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch response result keys"), "none", "advanced diagnostics must render active profile-post response result keys fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch parser path counts"), "none", "advanced diagnostics must render active profile-post parser path counts fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch list sample keys"), "none", "advanced diagnostics must render active profile-post list sample keys fallback");
  assert.equal(partialScanTechValue("Active profile-post fetch reject reasons"), "none", "advanced diagnostics must render active profile-post reject reasons fallback");

  const partialScanLedgerObjectState: WholeProfileHarvestState = {
    ...partialScanState,
    profile_scan: {
      ...partialScanState.profile_scan,
      diagnostics: {
        ...(partialScanState.profile_scan.diagnostics as Record<string, unknown>),
        profile_scan_source_ledger: {
          requested_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
          network_profile_post_count: 199,
          network_profile_post_passive_count: 173,
          network_profile_post_active_count: 199,
          network_profile_post_active_only_count: 26,
          dom_profile_scoped_target_count: 3,
          dom_profile_scoped_supplement_count: 2,
          dom_profile_scoped_rejected_count: 1,
          current_video_supplemented: false,
          merged_target_count: 199
        }
      }
    },
    debug: {
      ...partialScanState.debug,
      last_response_summary: {
        ...(partialScanState.debug.last_response_summary as Record<string, unknown>),
        profile_scan_source_ledger: {
          requested_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
          network_profile_post_count: 199,
          network_profile_post_passive_count: 173,
          network_profile_post_active_count: 199,
          network_profile_post_active_only_count: 26,
          dom_profile_scoped_target_count: 3,
          dom_profile_scoped_supplement_count: 2,
          dom_profile_scoped_rejected_count: 1,
          current_video_supplemented: false,
          merged_target_count: 199
        }
      }
    }
  };
  const partialScanLedgerObjectVm = getWholeProfileHarvestProgressViewModel(partialScanLedgerObjectState);
  const partialScanLedgerObjectTechValue = (label: string): string | undefined => partialScanLedgerObjectVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(partialScanLedgerObjectTechValue("Profile scan source ledger"), "requested=https://www.douyin.com/user/MS4wLjABCD; network_post=199; dom_scoped=3; dom_supplement=2; dom_rejected=1; current_video_supplemented=no; merged=199; network_post_passive=173; network_post_active=199; network_post_active_only=26", "advanced diagnostics must stringify object-form source ledger into a stable readable summary");

  const partialScanActiveProfilePostAttemptedState: WholeProfileHarvestState = {
    ...partialScanState,
    profile_scan: {
      ...partialScanState.profile_scan,
      diagnostics: {
        ...(partialScanState.profile_scan.diagnostics as Record<string, unknown>),
        active_profile_post: {
          enabled: "yes",
          attempted: "yes",
          stop_reason: "network_post_has_more_false",
          not_attempted_reason: null,
          target_count: 27,
          has_more_state: "false",
          only_aweme_count: 6,
          request_count: 3,
          batch_count: 2,
          page_count: 2,
          page_cap: 60,
          page_cap_hit_count: 0,
          page_cap_hit_while_has_more_count: 0,
          runtime_timeout_ms: 12000,
          runtime_timeout_hit: "no",
          continuation_policy: "has_more_driven_22C13B",
          fallback_cycle_eligible: "yes",
          fallback_cycle_attempted: "yes",
          fallback_cycle_stop_reason: "network_post_has_more_false",
          fallback_cycle_has_more_state: "false",
          fallback_cycle_request_count: 1,
          fallback_cycle_batch_count: 1,
          error: null,
          response_shape: "ok",
          endpoint_variant_attempt_count: 3,
          endpoint_variant_success: "/aweme/v1/web/aweme/post/",
          endpoint_attempt_samples: [
            { page: 1, endpoint_path: "/aweme/v1/web/aweme/post", result: "response_not_ok", status: 404 },
            { page: 1, endpoint_path: "/aweme/v1/web/aweme/post/", result: "batch_ok", status: 200, parser_route: "fallback:data" }
          ],
          parser_route: "fallback:data",
          parser_routes_tried: ["primary_payload", "fallback:data"],
          parser_direct_routes_tried: ["primary_payload", "direct:data", "direct:data.aweme_list"],
          parser_direct_match_count: 0,
          parser_fallback_attempted: "yes",
          parser_fallback_match_count: 1,
          parser_fallback_candidate_count: 2,
          parser_fallback_visited_nodes: 4,
          template_found: "yes",
          template_source: "performance_resource",
          template_endpoint_path: "/aweme/v1/web/aweme/post/",
          template_query_keys: ["sec_user_id", "max_cursor", "count", "msToken"],
          template_required_query_keys: ["sec_user_id", "count", "max_cursor"],
          template_required_query_keys_available: "yes",
          template_missing_required_query_keys: [],
          template_secret_keys_present: "yes",
          template_secret_query_keys: ["msToken"],
          response_status_code: 0,
          response_status_msg: "success",
          response_top_level_keys: ["status_code", "status_msg", "data", "extra"],
          response_data_keys: ["aweme_list", "has_more", "max_cursor", "min_cursor"],
          response_result_keys: [],
          parser_path_counts: { "data.aweme_list": 1, "result.aweme_list": 2 },
          list_sample_keys: ["aweme_id", "desc", "author"],
          reject_reasons: ["response_not_ok", "extractor_no_targets"]
        },
        active_profile_post_fetch_enabled: "yes",
        active_profile_post_fetch_attempted: "yes",
        active_profile_post_fetch_stop_reason: "network_post_has_more_false",
        active_profile_post_fetch_not_attempted_reason: "none",
        active_profile_post_fetch_target_count: 27,
        active_profile_post_fetch_has_more_state: "false",
        active_profile_post_only_aweme_count: 6,
        active_profile_post_fetch_request_count: 3,
        active_profile_post_fetch_batch_count: 2,
        active_profile_post_fetch_page_count: 2,
        active_profile_post_fetch_page_cap: 60,
        active_profile_post_fetch_page_cap_hit_count: 0,
        active_profile_post_fetch_page_cap_hit_while_has_more_count: 0,
        active_profile_post_fetch_runtime_timeout_ms: 12000,
        active_profile_post_fetch_runtime_timeout_hit: "no",
        active_profile_post_fetch_continuation_policy: "has_more_driven_22C13B",
        active_profile_post_fetch_fallback_cycle_eligible: "yes",
        active_profile_post_fetch_fallback_cycle_attempted: "yes",
        active_profile_post_fetch_fallback_cycle_stop_reason: "network_post_has_more_false",
        active_profile_post_fetch_fallback_cycle_has_more_state: "false",
        active_profile_post_fetch_fallback_cycle_request_count: 1,
        active_profile_post_fetch_fallback_cycle_batch_count: 1,
        active_profile_post_fetch_endpoint_variant_attempt_count: 3,
        active_profile_post_fetch_endpoint_variant_success: "/aweme/v1/web/aweme/post/",
        active_profile_post_fetch_endpoint_attempt_samples: [
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post", result: "response_not_ok", status: 404 },
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post/", result: "batch_ok", status: 200, parser_route: "fallback:data" }
        ],
        active_profile_post_fetch_parser_route: "fallback:data",
        active_profile_post_fetch_parser_routes_tried: ["primary_payload", "fallback:data"],
        active_profile_post_fetch_parser_direct_routes_tried: ["primary_payload", "direct:data", "direct:data.aweme_list"],
        active_profile_post_fetch_parser_direct_match_count: 0,
        active_profile_post_fetch_parser_fallback_attempted: "yes",
        active_profile_post_fetch_parser_fallback_match_count: 1,
        active_profile_post_fetch_parser_fallback_candidate_count: 2,
        active_profile_post_fetch_parser_fallback_visited_nodes: 4,
        active_profile_post_fetch_error: "none",
        active_profile_post_fetch_response_shape: "ok",
        active_profile_post_template_found: "yes",
        active_profile_post_template_source: "performance_resource",
        active_profile_post_template_endpoint_path: "/aweme/v1/web/aweme/post/",
        active_profile_post_template_query_keys: ["sec_user_id", "max_cursor", "count", "msToken"],
        active_profile_post_template_required_query_keys: ["sec_user_id", "count", "max_cursor"],
        active_profile_post_template_required_query_keys_available: "yes",
        active_profile_post_template_missing_required_query_keys: [],
        active_profile_post_template_secret_keys_present: "yes",
        active_profile_post_template_secret_query_keys: ["msToken"],
        active_profile_post_fetch_response_status_code: 0,
        active_profile_post_fetch_response_status_msg: "success",
        active_profile_post_fetch_response_top_level_keys: ["status_code", "status_msg", "data", "extra"],
        active_profile_post_fetch_response_data_keys: ["aweme_list", "has_more", "max_cursor", "min_cursor"],
        active_profile_post_fetch_response_result_keys: [],
        active_profile_post_fetch_parser_path_counts: { "data.aweme_list": 1, "result.aweme_list": 2 },
        active_profile_post_fetch_list_sample_keys: ["aweme_id", "desc", "author"],
        active_profile_post_fetch_reject_reasons: ["response_not_ok", "extractor_no_targets"]
      }
    },
    debug: {
      ...partialScanState.debug,
      last_response_summary: {
        ...(partialScanState.debug.last_response_summary as Record<string, unknown>),
        active_profile_post: {
          enabled: "yes",
          attempted: "yes",
          stop_reason: "network_post_has_more_false",
          not_attempted_reason: null,
          target_count: 27,
          has_more_state: "false",
          only_aweme_count: 6,
          request_count: 3,
          batch_count: 2,
          page_count: 2,
          page_cap: 60,
          page_cap_hit_count: 0,
          page_cap_hit_while_has_more_count: 0,
          runtime_timeout_ms: 12000,
          runtime_timeout_hit: "no",
          continuation_policy: "has_more_driven_22C13B",
          fallback_cycle_eligible: "yes",
          fallback_cycle_attempted: "yes",
          fallback_cycle_stop_reason: "network_post_has_more_false",
          fallback_cycle_has_more_state: "false",
          fallback_cycle_request_count: 1,
          fallback_cycle_batch_count: 1,
          error: null,
          response_shape: "ok",
          endpoint_variant_attempt_count: 3,
          endpoint_variant_success: "/aweme/v1/web/aweme/post/",
          endpoint_attempt_samples: [
            { page: 1, endpoint_path: "/aweme/v1/web/aweme/post", result: "response_not_ok", status: 404 },
            { page: 1, endpoint_path: "/aweme/v1/web/aweme/post/", result: "batch_ok", status: 200, parser_route: "fallback:data" }
          ],
          parser_route: "fallback:data",
          parser_routes_tried: ["primary_payload", "fallback:data"],
          parser_direct_routes_tried: ["primary_payload", "direct:data", "direct:data.aweme_list"],
          parser_direct_match_count: 0,
          parser_fallback_attempted: "yes",
          parser_fallback_match_count: 1,
          parser_fallback_candidate_count: 2,
          parser_fallback_visited_nodes: 4,
          template_found: "yes",
          template_source: "performance_resource",
          template_endpoint_path: "/aweme/v1/web/aweme/post/",
          template_query_keys: ["sec_user_id", "max_cursor", "count", "msToken"],
          template_required_query_keys: ["sec_user_id", "count", "max_cursor"],
          template_required_query_keys_available: "yes",
          template_missing_required_query_keys: [],
          template_secret_keys_present: "yes",
          template_secret_query_keys: ["msToken"],
          response_status_code: 0,
          response_status_msg: "success",
          response_top_level_keys: ["status_code", "status_msg", "data", "extra"],
          response_data_keys: ["aweme_list", "has_more", "max_cursor", "min_cursor"],
          response_result_keys: [],
          parser_path_counts: { "data.aweme_list": 1, "result.aweme_list": 2 },
          list_sample_keys: ["aweme_id", "desc", "author"],
          reject_reasons: ["response_not_ok", "extractor_no_targets"]
        },
        active_profile_post_fetch_enabled: "yes",
        active_profile_post_fetch_attempted: "yes",
        active_profile_post_fetch_stop_reason: "network_post_has_more_false",
        active_profile_post_fetch_not_attempted_reason: "none",
        active_profile_post_fetch_target_count: 27,
        active_profile_post_fetch_has_more_state: "false",
        active_profile_post_only_aweme_count: 6,
        active_profile_post_fetch_request_count: 3,
        active_profile_post_fetch_batch_count: 2,
        active_profile_post_fetch_page_count: 2,
        active_profile_post_fetch_page_cap: 60,
        active_profile_post_fetch_page_cap_hit_count: 0,
        active_profile_post_fetch_page_cap_hit_while_has_more_count: 0,
        active_profile_post_fetch_runtime_timeout_ms: 12000,
        active_profile_post_fetch_runtime_timeout_hit: "no",
        active_profile_post_fetch_continuation_policy: "has_more_driven_22C13B",
        active_profile_post_fetch_fallback_cycle_eligible: "yes",
        active_profile_post_fetch_fallback_cycle_attempted: "yes",
        active_profile_post_fetch_fallback_cycle_stop_reason: "network_post_has_more_false",
        active_profile_post_fetch_fallback_cycle_has_more_state: "false",
        active_profile_post_fetch_fallback_cycle_request_count: 1,
        active_profile_post_fetch_fallback_cycle_batch_count: 1,
        active_profile_post_fetch_endpoint_variant_attempt_count: 3,
        active_profile_post_fetch_endpoint_variant_success: "/aweme/v1/web/aweme/post/",
        active_profile_post_fetch_endpoint_attempt_samples: [
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post", result: "response_not_ok", status: 404 },
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post/", result: "batch_ok", status: 200, parser_route: "fallback:data" }
        ],
        active_profile_post_fetch_parser_route: "fallback:data",
        active_profile_post_fetch_parser_routes_tried: ["primary_payload", "fallback:data"],
        active_profile_post_fetch_parser_direct_routes_tried: ["primary_payload", "direct:data", "direct:data.aweme_list"],
        active_profile_post_fetch_parser_direct_match_count: 0,
        active_profile_post_fetch_parser_fallback_attempted: "yes",
        active_profile_post_fetch_parser_fallback_match_count: 1,
        active_profile_post_fetch_parser_fallback_candidate_count: 2,
        active_profile_post_fetch_parser_fallback_visited_nodes: 4,
        active_profile_post_fetch_error: "none",
        active_profile_post_fetch_response_shape: "ok",
        active_profile_post_template_found: "yes",
        active_profile_post_template_source: "performance_resource",
        active_profile_post_template_endpoint_path: "/aweme/v1/web/aweme/post/",
        active_profile_post_template_query_keys: ["sec_user_id", "max_cursor", "count", "msToken"],
        active_profile_post_template_required_query_keys: ["sec_user_id", "count", "max_cursor"],
        active_profile_post_template_required_query_keys_available: "yes",
        active_profile_post_template_missing_required_query_keys: [],
        active_profile_post_template_secret_keys_present: "yes",
        active_profile_post_template_secret_query_keys: ["msToken"],
        active_profile_post_fetch_response_status_code: 0,
        active_profile_post_fetch_response_status_msg: "success",
        active_profile_post_fetch_response_top_level_keys: ["status_code", "status_msg", "data", "extra"],
        active_profile_post_fetch_response_data_keys: ["aweme_list", "has_more", "max_cursor", "min_cursor"],
        active_profile_post_fetch_response_result_keys: [],
        active_profile_post_fetch_parser_path_counts: { "data.aweme_list": 1, "result.aweme_list": 2 },
        active_profile_post_fetch_list_sample_keys: ["aweme_id", "desc", "author"],
        active_profile_post_fetch_reject_reasons: ["response_not_ok", "extractor_no_targets"]
      }
    }
  };
  const partialScanActiveProfilePostAttemptedVm = getWholeProfileHarvestProgressViewModel(partialScanActiveProfilePostAttemptedState);
  const partialScanActiveProfilePostAttemptedTechValue = (label: string): string | undefined => partialScanActiveProfilePostAttemptedVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch enabled"), "yes", "advanced diagnostics must render attempted active profile-post enablement state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch attempted"), "yes", "advanced diagnostics must render attempted active profile-post fetch state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch stop reason"), "network_post_has_more_false", "advanced diagnostics must render attempted active profile-post stop reason");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch not-attempted reason"), "none", "advanced diagnostics must keep not-attempted reason explicit when attempted");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch target count"), "27", "advanced diagnostics must render attempted active profile-post target count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch has-more state"), "false", "advanced diagnostics must render attempted active profile-post has-more state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post active-only aweme count"), "6", "advanced diagnostics must render attempted active-only contribution count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch request count"), "3", "advanced diagnostics must render attempted active profile-post request count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch batch count"), "2", "advanced diagnostics must render attempted active profile-post batch count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch page count"), "2", "advanced diagnostics must render attempted active profile-post page count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch page cap"), "60", "advanced diagnostics must render attempted active profile-post page cap");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch page cap hit count"), "0", "advanced diagnostics must render attempted active profile-post page-cap hit count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch page cap hit while has-more count"), "0", "advanced diagnostics must render attempted active profile-post page-cap/has-more diagnostics");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch runtime timeout ms"), "12000", "advanced diagnostics must render attempted active profile-post runtime timeout threshold");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch runtime timeout hit"), "no", "advanced diagnostics must render attempted active profile-post runtime timeout hit state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch continuation policy"), "has_more_driven_22C13B", "advanced diagnostics must render attempted active profile-post continuation policy");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle eligible"), "yes", "advanced diagnostics must render attempted active profile-post fallback-cycle eligibility");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle attempted"), "yes", "advanced diagnostics must render attempted active profile-post fallback-cycle attempted state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle stop reason"), "network_post_has_more_false", "advanced diagnostics must render attempted active profile-post fallback-cycle stop reason");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle has-more state"), "false", "advanced diagnostics must render attempted active profile-post fallback-cycle has-more state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle request count"), "1", "advanced diagnostics must render attempted active profile-post fallback-cycle request count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fallback-cycle batch count"), "1", "advanced diagnostics must render attempted active profile-post fallback-cycle batch count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch endpoint variant attempts"), "3", "advanced diagnostics must render attempted endpoint variant attempts");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch endpoint variant success"), "/aweme/v1/web/aweme/post/", "advanced diagnostics must render attempted endpoint variant success");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch endpoint attempt samples")?.includes("batch_ok") ?? false, true, "advanced diagnostics must render attempted endpoint attempt samples");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser route"), "fallback:data", "advanced diagnostics must render attempted parser route");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser routes tried"), "primary_payload | fallback:data", "advanced diagnostics must render attempted parser routes tried");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser direct routes tried"), "primary_payload | direct:data | direct:data.aweme_list", "advanced diagnostics must render attempted parser direct routes tried");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser direct match count"), "0", "advanced diagnostics must render attempted parser direct match count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser fallback attempted"), "yes", "advanced diagnostics must render attempted parser fallback attempted");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser fallback match count"), "1", "advanced diagnostics must render attempted parser fallback match count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser fallback candidate count"), "2", "advanced diagnostics must render attempted parser fallback candidate count");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser fallback visited nodes"), "4", "advanced diagnostics must render attempted parser fallback visited nodes");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch error"), "none", "advanced diagnostics must render attempted active profile-post error field");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response shape"), "ok", "advanced diagnostics must render attempted active profile-post response shape field");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template found"), "yes", "advanced diagnostics must render attempted active profile-post template found state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template source"), "performance_resource", "advanced diagnostics must render attempted active profile-post template source state");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template endpoint path"), "/aweme/v1/web/aweme/post/", "advanced diagnostics must render attempted active profile-post template endpoint path");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template query keys"), "sec_user_id | max_cursor | count | msToken", "advanced diagnostics must render attempted active profile-post template query keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template required query keys"), "sec_user_id | count | max_cursor", "advanced diagnostics must render attempted active profile-post template required query keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template required query keys available"), "yes", "advanced diagnostics must render attempted active profile-post template required-query-keys availability");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template missing required query keys"), "none", "advanced diagnostics must render attempted active profile-post template missing required query keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template secret keys present"), "yes", "advanced diagnostics must render attempted active profile-post template secret key presence");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post template secret query keys"), "msToken", "advanced diagnostics must render attempted active profile-post template secret query keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response status code"), "0", "advanced diagnostics must render attempted active profile-post response status code");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response status message"), "success", "advanced diagnostics must render attempted active profile-post response status message");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response top-level keys"), "status_code | status_msg | data | extra", "advanced diagnostics must render attempted active profile-post response top-level keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response data keys"), "aweme_list | has_more | max_cursor | min_cursor", "advanced diagnostics must render attempted active profile-post response data keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch response result keys"), "none", "advanced diagnostics must render attempted active profile-post response result keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser path counts")?.includes("\"data.aweme_list\":1") ?? false, true, "advanced diagnostics must render attempted active profile-post parser path counts");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch parser path counts")?.includes("\"result.aweme_list\":2") ?? false, true, "advanced diagnostics must render attempted active profile-post parser path counts");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch list sample keys"), "aweme_id | desc | author", "advanced diagnostics must render attempted active profile-post list sample keys");
  assert.equal(partialScanActiveProfilePostAttemptedTechValue("Active profile-post fetch reject reasons"), "response_not_ok | extractor_no_targets", "advanced diagnostics must render attempted active profile-post reject reasons");

  const partialScanUnknownIncompleteReasonState: WholeProfileHarvestState = {
    ...partialScanState,
    profile_scan: {
      ...partialScanState.profile_scan,
      diagnostics: {
        ...(partialScanState.profile_scan.diagnostics as Record<string, unknown>),
        profile_scan_incomplete_reason: null,
        profile_scan_incomplete: "yes",
        scan_finalization_result: "incomplete"
      }
    },
    debug: {
      ...partialScanState.debug,
      last_response_summary: {
        ...(partialScanState.debug.last_response_summary as Record<string, unknown>),
        profile_scan_incomplete_reason: null,
        profile_scan_incomplete: "yes",
        scan_finalization_result: "incomplete"
      }
    }
  };
  const partialScanUnknownIncompleteReasonVm = getWholeProfileHarvestProgressViewModel(partialScanUnknownIncompleteReasonState);
  const partialScanUnknownIncompleteReasonTechValue = (label: string): string | undefined => partialScanUnknownIncompleteReasonVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(partialScanUnknownIncompleteReasonTechValue("Profile scan incomplete reason"), "unknown", "advanced diagnostics must fall back to unknown when scan is incomplete but reason is absent");

  const classifiedEmptyQueue = withClassification(withDryRun(withVerify(baseState())), 0);
  const classifiedEmptyVm = getScannerControlPanelViewModel(classifiedEmptyQueue);
  assert.equal(classifiedEmptyVm.action.key, "open_capture_inbox");
  const classifiedEmptyCopy = classifiedEmptyVm.emptyState ?? classifiedEmptyVm.primaryAction.description ?? "";
  assert.equal(classifiedEmptyCopy, "No new or incomplete videos to collect.");
  assert.equal(classifiedEmptyVm.counts.queueCount, 0);

  const continuationState = withSafeBatchContinuation({
    ...withClassification(unclassifiedQueued, 15),
    harvest_options: { ...unclassifiedQueued.harvest_options, batch: "next_5", batch_limit: 5 }
  });
  const continuationVm = getScannerControlPanelViewModel(continuationState);
  const continuationMainVm = getDouyinScannerMainViewModel(continuationState);
  const continuationMessage = "Batch complete: 10 saved, 5 remaining. Click Continue Next 5 to process the next batch.";
  assert.equal(
    isTerminalBatchContinuation(continuationState, deriveAuthoritativeProfileCounters(continuationState).pending_count),
    true,
    "safe batch continuation fixture must register as terminal batch continuation"
  );
  assert.equal(continuationVm.action.key, "start_collecting", "safe batch continuation must keep the Start Collecting action key");
  assert.equal(continuationVm.action.buttonLabel, "Continue Next 5");
  assert.equal(continuationVm.primaryAction.label, "Continue Next 5");
  assert.equal(continuationVm.emptyState ?? continuationVm.primaryAction.description, continuationMessage);
  assert.equal(continuationVm.action.description, continuationMessage);
  assert.equal(continuationMainVm.primary_action?.key, "start_collecting");
  assert.equal(continuationMainVm.primary_action?.label, "Continue Next 5");
  assert.equal(continuationMainVm.primary_action?.reason, continuationMessage);
  assert.equal(continuationMainVm.progress.detail, continuationMessage);
  assert.notEqual(continuationVm.action.key, "resume", "safe batch continuation must not route through Resume");
  assert.equal(continuationState.harvest.queue.length, 15, "continuation UX must not clear the collection queue");
  assert.equal(continuationState.calibration.point_count, unclassifiedQueued.calibration.point_count, "continuation UX fixture keeps calibration intact");
  assert.equal(continuationState.capture_session_id, unclassifiedQueued.capture_session_id, "continuation UX must not clear the capture session");
  assert.equal(continuationState.harvest.current_index, 9, "continuation UX must preserve the current index from the batch checkpoint");

  const completedContinuationState: WholeProfileHarvestState = {
    ...continuationState,
    phase: "profile_collection_complete",
    scan_job: {
      ...continuationState.scan_job,
      status: "completed",
      total_persisted: 3162,
      expected_count: 3162,
      remaining_estimate: 0,
      has_more_state: false
    },
    profile_scan: {
      ...continuationState.profile_scan,
      status: "success",
      accepted_target_count: 3162,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_finalization_result: "success",
        count_semantics_status: "full_match",
        count_semantics_reason: "displayed_count_matches_persisted_count",
        displayed_profile_count: 3162,
        displayed_profile_count_source: "active_works_tab_dom_text",
        displayed_profile_count_raw_text: "作品 3162",
        collectable_count: 3162,
        persisted_count: 3162,
        final_cumulative_collectable_count: 3162,
        final_display_authority: "cumulative_persisted_count",
        final_header_count: 3162,
        final_counter_count: 3162,
        header_counter_authority_match: "yes",
        continuation_batch_new_count: 666,
        continuation_batch_raw_count: 666,
        continuation_batch_accepted_count: 666,
        persisted_total_before_continuation: 2496,
        persisted_total_after_continuation: 3162,
        unavailable_or_unlisted_count: 0,
        over_displayed_count: 0
      }
    },
    verify: {
      ...continuationState.verify,
      status: "success",
      accepted_target_count: 3162,
      verified_target_count: 3162,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_finalization_result: "success",
        count_semantics_status: "full_match",
        count_semantics_reason: "displayed_count_matches_persisted_count",
        displayed_profile_count: 3162,
        collectable_count: 3162,
        persisted_count: 3162,
        final_cumulative_collectable_count: 3162,
        final_display_authority: "cumulative_persisted_count",
        final_header_count: 3162,
        final_counter_count: 3162,
        header_counter_authority_match: "yes"
      }
    },
    debug: {
      ...continuationState.debug,
      last_response_summary: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_finalization_result: "success",
        count_semantics_status: "full_match",
        count_semantics_reason: "displayed_count_matches_persisted_count",
        displayed_profile_count: 3162,
        collectable_count: 3162,
        persisted_count: 3162,
        final_cumulative_collectable_count: 3162,
        final_display_authority: "cumulative_persisted_count",
        final_header_count: 3162,
        final_counter_count: 3162,
        header_counter_authority_match: "yes",
        continuation_batch_new_count: 666,
        persisted_total_before_continuation: 2496,
        persisted_total_after_continuation: 3162
      }
    },
    harvest: {
      ...continuationState.harvest,
      planned_total: 3162,
      pending: 3162,
      queue: Array.from({ length: 3162 }, (_, index) => ({
        index: index + 1,
        aweme_id: `76341927335145${String(index).padStart(5, "0")}`,
        capture_status: "new" as const,
        status: "pending" as const,
        attempts: 0,
        checkpoint_sequence: null,
        extraction_result: null,
        last_error: null,
        capture_inbox_item_id: null,
        source_url: `https://www.douyin.com/video/76341927335145${String(index).padStart(5, "0")}`,
        profile_card_evidence: {}
      }))
    },
    target_status: {
      ...continuationState.target_status,
      new: 3162,
      incomplete: 0,
      complete: 0,
      failed: 0,
      skipped: 0,
      unknown: 0
    }
  };
  const completedContinuationPanelVm = getScannerControlPanelViewModel(completedContinuationState);
  const completedContinuationMainVm = getDouyinScannerMainViewModel(completedContinuationState);
  const metricValue = (vm: ReturnType<typeof getDouyinScannerMainViewModel>, label: string): string | undefined => vm.stats_summary.metrics.find((row) => row.label === label)?.value;
  assert.equal(completedContinuationPanelVm.headerStatus, "3162 / 3162 videos", "completed continuation panel header must use cumulative final authority");
  assert.equal(completedContinuationPanelVm.counts.newCount, 3162, "completed continuation panel counters must use cumulative persisted authority");
  assert.equal(completedContinuationPanelVm.counts.queueCount, 3162, "completed continuation panel queue count must stay aligned with cumulative persisted authority in the terminal fixture");
  assert.equal(completedContinuationMainVm.header_status, "3162 / 3162 videos", "completed continuation main header must use cumulative final authority");
  assert.equal(metricValue(completedContinuationMainVm, "Videos found"), "3162 / 3162", "completed continuation main metric must label the cumulative collectable count");
  assert.equal(metricValue(completedContinuationMainVm, "New"), "3162", "completed continuation main New counter must not fall back to batch delta");
  assert.equal(metricValue(completedContinuationMainVm, "Queued"), "3162", "completed continuation main Queued counter must align with cumulative terminal authority");

  const completedNoPendingVm = getScannerControlPanelViewModel({
    ...continuationState,
    phase: "profile_collection_complete",
    harvest: { ...continuationState.harvest, pending: 0, queue: continuationState.harvest.queue.map((item) => ({ ...item, status: "extracted" as const })) }
  });
  assert.notEqual(completedNoPendingVm.action.buttonLabel, "Continue Next 5", "completed zero-pending state must not show continuation copy");

  const failedContinuationVm = getScannerControlPanelViewModel({
    ...continuationState,
    harvest: { ...continuationState.harvest, failed: 1 },
    debug: { ...continuationState.debug, last_response_summary: { failed_count: 1, top_failure: "modal_navigation_timeout" } }
  });
  assert.notEqual(failedContinuationVm.action.buttonLabel, "Continue Next 5", "failed safe-batch state with a top failure must not show continuation copy");

  const incompleteStoredFourPointCalibration = getScannerControlPanelViewModel({
    ...withClassification(withVerify(baseState())),
    calibration: {
      status: "unknown",
      point_count: 0,
      source_key: null,
      viewport_warning: null,
      points: { like_count: {}, comment_count: {}, favorite_count: {}, share_count: {} }
    } as WholeProfileHarvestState["calibration"] & { points: Record<string, unknown> }
  });
  assert.equal(incompleteStoredFourPointCalibration.health.calibration, "Cal needed");
  assert.equal(incompleteStoredFourPointCalibration.action.key, "calibrate");

  const storedFourPointReady = getScannerControlPanelViewModel({
    ...withClassification(withVerify(baseState())),
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      source_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      profile_url: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      point_count: 4,
      source_key: null,
      viewport_warning: null,
      points: canonicalCalibrationPoints()
    }
  });
  assert.equal(storedFourPointReady.health.calibration, "Cal ready");
  assert.equal(storedFourPointReady.action.key, "start_collecting");
}

{
  const scanRunning = getScannerControlPanelViewModel({
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
  });
  assert.equal(scanRunning.headerStatus, "Scanning");
  assert.equal(scanRunning.action.key, "scan_profile");
  assert.equal(scanRunning.action.title, "Scanning Profile");
  assert.equal(scanRunning.action.buttonLabel, "Scanning...");
  assert.equal(scanRunning.action.disabledReason, null);

  const classifying = getScannerControlPanelViewModel({
    ...withVerify(baseState()),
    workflow: {
      ...withVerify(baseState()).workflow,
      classification: {
        ...withVerify(baseState()).workflow.classification,
        status: "running",
        started_at: "2030-05-07T11:44:00.000Z",
        updated_at: "2030-05-07T11:44:00.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "classify_profile",
      action_lock: "classify_profile"
    },
    updated_at: "2030-05-07T11:44:00.000Z"
  });
  assert.equal(classifying.headerStatus, "Classifying");
  assert.equal(classifying.action.key, "scan_profile");
  assert.equal(classifying.action.title, "Classifying Videos");
  assert.equal(classifying.action.buttonLabel, "Classifying...");
  assert.equal(classifying.action.disabledReason, null);

  const contradictionVm = getScannerControlPanelViewModel(withVerify(baseState()));
  assert.notEqual(contradictionVm.headerStatus, "Collecting");
  assert.equal(contradictionVm.action.key, "scan_profile");

  const legacyRunningVm = getScannerControlPanelViewModel({
    ...withClassification(withVerify(baseState())),
    harvest: { ...withClassification(withVerify(baseState())).harvest, status: "running", started_at: "2030-05-07T11:43:00.000Z", updated_at: "2030-05-07T11:43:00.000Z" },
    updated_at: "2030-05-07T11:43:00.000Z"
  });
  assert.notEqual(legacyRunningVm.headerStatus, "Collecting");
  assert.notEqual(legacyRunningVm.action.key, "pause");
}

{
  const extracted = withExtracted(withClassification(withDryRun(withVerify(baseState()))));
  const vm = getWholeProfileHarvestProgressViewModel(extracted);
  assert.equal(vm.operator_help.capture_inbox_cta, null);
  assert.equal(vm.operator_help.troubleshooting.includes("If Save to Capture Inbox is disabled, create a scan session and run a data check first."), true);
  assert.equal(vm.operator_help.safety_tips.includes("Start with Save 1 Video before Save to Capture Inbox on a new profile."), true);
}

const mainHtml = popupHtml.slice(popupHtml.indexOf("<main"), popupHtml.indexOf("</main>") + "</main>".length);
assert.match(mainHtml, /id="scannerControlPanelRoot"[^>]*class="[^"]*scanner-shell[^"]*scp-shell/, "popup must render the compact scanner control panel shell");
assert.match(mainHtml, /class="[^"]*scanner-hero[^"]*scp-topbar/, "popup must render the compact scanner hero");
assert.match(mainHtml, /class="[^"]*scanner-health-inline[^"]*scp-health-row/, "popup must render the compact inline health row");
assert.match(mainHtml, /id="scannerHeaderStatus"[^>]*>Ready</, "popup badge must not show 0 videos before profile scan");
assert.match(mainHtml, /id="scannerChipApi"[^>]*>API not checked</, "popup must render API not checked before backend health is checked");
assert.match(mainHtml, /id="scannerEmptyState"[^>]*class="[^"]*scanner-hint[^"]*"[^>]*>Scan a profile to build the collection plan\.</, "popup must render compact pre-scan hint copy");
assert.match(mainHtml, /id="scannerStatsGrid"[^>]*hidden/, "popup must render the compact stats grid hidden before scan");
assert.match(mainHtml, /id="scannerPrimaryActionButton"[^>]*>Scan Profile<\/button>/, "popup must render one scanner primary action button with Scan Profile fallback copy");
assert.match(mainHtml, /id="scannerSettingsSection"[^>]*data-settings-expanded="false"/, "popup settings must be collapsed by default");
assert.match(mainHtml, /id="scannerSettingsSummaryValue"[^>]*>New \+ incomplete · Next 10 · Safe</, "popup settings must show the collapsed settings summary");
assert.match(mainHtml, /id="scannerSettingsFields"[^>]*hidden/, "popup settings fields must stay hidden until Edit is clicked");
assert.match(popupHtml, /id="wholeProfileHarvestMode"/, "popup must render main-screen mode select");
assert.match(popupHtml, /id="wholeProfileHarvestBatch"/, "popup must render main-screen batch select");
assert.match(popupHtml, /id="wholeProfileHarvestSpeed"/, "popup must render main-screen speed select");
assert.match(popupHtml, /id="scannerOpenCaptureInboxButton"[^>]*class="[^"]*scanner-secondary-button-blue[^"]*"/, "popup must render scanner capture inbox footer action as secondary blue");
assert.match(popupHtml, /id="scannerOpenAdvancedButton"[^>]*class="[^"]*scanner-secondary-button-neutral[^"]*"/, "popup must render scanner advanced action as neutral");
assert.match(popupHtml, /id="scannerResetButton"[^>]*class="[^"]*scanner-danger-ghost[^"]*"/, "popup Reset action must use danger ghost style class");
assert.match(popupHtml, /id="scannerResetButton"[^>]*type="button"/, "popup Reset action must be a non-submit button");
assert.match(popupHtml, /id="scannerResetModal"[^>]*role="dialog"[^>]*hidden/, "popup must render hidden custom reset modal dialog");
assert.match(popupHtml, /id="scannerResetModalTitle"[^>]*>Reset scanner</, "reset action sheet must use the required title");
assert.match(popupHtml, /Backend Capture Inbox data stays safe\./, "reset action sheet must use compact backend-safe subtitle");
assert.match(popupHtml, /No backend sessions or items will be deleted\./, "reset action sheet footer must explain backend sessions and items are kept");
assert.match(popupHtml, /id="scannerResetActionSheet"/, "reset modal must render compact action sheet view");
assert.match(popupHtml, /id="scannerResetCurrentRunButton"[^>]*data-reset-mode="current_run"[\s\S]*Fix stuck run[\s\S]*Clear locks only[\s\S]*Keeps profile, queue, session/, "reset modal must expose compact current-run action row");
assert.match(popupHtml, /id="scannerResetRescanProfileButton"[^>]*data-reset-mode="current_profile_rescan"[\s\S]*Refresh profile[\s\S]*Scan this profile again[\s\S]*Skips collected videos/, "reset modal must expose compact rescan action row");
assert.match(popupHtml, /id="scannerResetNewProfileButton"[^>]*data-reset-mode="new_profile"[\s\S]*Switch profile[\s\S]*Prepare for another user[\s\S]*Clears local queue\/session/, "reset modal must expose compact switch-profile action row");
assert.match(popupHtml, /data-recommended-badge hidden>Recommended</, "reset action rows must include hidden recommended badges");
assert.match(popupHtml, /id="scannerResetSuggestion"[^>]*>To collect another user, use Switch profile\.</, "reset action sheet must include completed-queue switch suggestion");
assert.match(popupHtml, /id="scannerResetInlineError"[^>]*role="alert"[^>]*hidden>Reset failed\. Check Advanced diagnostics\.</, "reset action sheet must include inline failure message");
assert.match(popupHtml, /id="scannerResetConfirmSwitchView"[\s\S]*id="scannerResetConfirmTitle">Switch profile\?<\/h2>[\s\S]*Local queue\/session for this profile will be cleared\. Backend data will not be deleted\.[\s\S]*id="scannerResetConfirmCancelButton"[^>]*>Cancel<[\s\S]*id="scannerResetConfirmSwitchButton"[^>]*>Switch profile</, "Switch profile must use inline confirmation view");
assert.match(popupHtml, /id="scannerResetCancelButton"[^>]*>Cancel</, "reset modal must expose cancel action");
assert.doesNotMatch(popupHtml, /Choose what you want to reset|Reset current run|Rescan this profile|Start new profile|Keeps:<\/strong>|Clears:<\/strong>|Use when collection is stuck|Scan this profile again to find new videos/, "reset action sheet must remove the old long card copy");
assert.match(popupHtml, /id="deckPanelResults"/, "popup must render results panel container");
assert.match(popupHtml, /id="deckPanelAdvanced"/, "popup must render advanced panel container");
assert.match(popupHtml, /id="wholeProfileQueuePreviewPanel"/, "popup must render queue preview as collapsed details");
assert.match(popupHtml, /id="wholeProfileProgressDetails"/, "popup must render progress details container");
assert.match(popupHtml, /id="wholeProfileQueuePreviewRows"/, "popup must render queue preview rows");
assert.match(popupHtml, /id="wholeProfileExtractionResultsRows"/, "popup must render extraction result rows");
assert.match(popupHtml, /id="wholeProfileBackendResultsRows"/, "popup must render backend result rows");
assert.doesNotMatch(mainHtml, /id="scannerProfileMetrics"/, "popup main screen must remove separate profile summary metrics");
assert.doesNotMatch(mainHtml, /id="scannerPlanMetrics"/, "popup main screen must remove separate plan summary metrics");
assert.doesNotMatch(mainHtml, /class="scanner-card"/, "popup main screen must remove the old scanner-card stack");
assert.doesNotMatch(mainHtml, /class="scanner-chip-row"/, "popup main screen must remove the old chip row class");
assert.doesNotMatch(mainHtml, /Douyin Profile Scanner|Profile scan summary|Scan plan summary|Queue Preview|Debug Details|Technical Details|Payload Guard|Flush Batch|Test First|Test Last|Test Random/, "forbidden old text must be removed from the main screen");
assert.doesNotMatch(mainHtml, /Queue Preview/, "popup main screen must not render Queue Preview");
assert.doesNotMatch(mainHtml, /Payload Guard/, "popup main screen must not render Payload Guard");
assert.doesNotMatch(mainHtml, /Flush Batch/, "popup main screen must not render Flush Batch");
assert.doesNotMatch(popupHtml, /Show Progress/, "progress must not require a separate Show Progress button");

assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{/, "popup must style the scanner control panel shell");
assert.match(popupCss, /\.scanner-shell,\s*\n\.scp-shell\s*\{[\s\S]*background:\s*radial-gradient/, "popup scanner shell must use premium light styling");
assert.match(popupCss, /\.scanner-hero,\s*\n\.scp-topbar\s*\{/, "popup must style the compact hero");
assert.match(popupCss, /\.scanner-hero,\s*\n\.scp-topbar\s*\{[\s\S]*background:\s*linear-gradient/, "popup hero must use the premium blue gradient");
assert.match(popupCss, /\.scanner-health-inline,\s*\n\.scp-health-row\s*\{[\s\S]*display:\s*flex/, "health row must render as compact inline chips");
assert.match(popupCss, /\.scanner-stats-grid,\s*\n\.scp-counters-block\s*\{/, "stats block must use compact counters");
assert.match(popupCss, /\.scanner-primary-card,\s*\n\.scp-action-block\s*\{/, "popup must style the scanner primary action card");
assert.match(popupCss, /\.scanner-primary-button,\s*\n\.scp-action-block button\s*\{[\s\S]*min-height:\s*38px;[\s\S]*background:\s*linear-gradient/, "popup primary action must remain visually primary");
assert.match(popupCss, /\.scanner-empty-state,\s*\n\.scanner-hint\s*\{[\s\S]*padding:\s*7px 10px;[\s\S]*background:\s*rgba\(248, 250, 252, 0\.72\)/, "popup empty state must be a lighter compact hint card");
assert.match(popupCss, /\.scanner-bottom-dock,\s*\n\.scp-bottom-bar\s*\{/, "popup must style the bottom actions dock");
assert.match(popupCss, /\.scanner-danger-ghost,[\s\S]*#scannerResetButton[\s\S]*background:\s*transparent;[\s\S]*color:\s*#b91c1c/, "popup Reset action must be danger ghost instead of primary");
assert.match(popupCss, /\.scanner-settings-fields\s*\{[\s\S]*repeat\(3, minmax\(0, 1fr\)\);/, "expanded settings fields must render three compact columns");
assert.match(popupCss, /\.scanner-settings-fields\[hidden\]\s*\{[\s\S]*display:\s*none/, "collapsed settings fields must not render by default");
assert.match(popupCss, /\.compact-list-section\s*\{/, "popup must still style compact results and queue sections");
assert.match(popupCss, /\.backend-flow--results\s*\{/, "results panel must style relocated backend flow");
assert.match(popupCss, /\.scanner-reset-modal\s*\{[\s\S]*position:\s*fixed/, "reset modal must render as fixed in-popup overlay");
assert.match(popupCss, /\.scanner-reset-modal__sheet\s*\{[\s\S]*border-radius:\s*22px;[\s\S]*overflow:\s*hidden/, "reset modal sheet must use compact polished action-sheet styling without scroll-first cards");
assert.match(popupCss, /\.scanner-reset-action-row\s*\{[\s\S]*grid-template-columns:\s*34px minmax\(0, 1fr\) auto;[\s\S]*min-height:\s*62px/, "reset action rows must use compact row layout");
assert.match(popupCss, /\.scanner-reset-action-row\[aria-busy="true"\]::after,[\s\S]*\.scanner-reset-confirm-primary\[aria-busy="true"\]::after[\s\S]*Resetting\.\.\./, "reset modal must show Resetting text while running");
assert.match(popupCss, /\.scanner-reset-action-row--recommended\s*\{[\s\S]*border-color:\s*#93c5fd/, "recommended reset action must be visually highlighted");
assert.match(popupCss, /\.deck-panel\s*\{/, "popup must still style advanced overlay panels");
assert.match(popupCss, /\.operator-guide\s*\{/, "popup must style operator guide panels");
assert.match(popupCss, /\.helper--warning\s*\{/, "popup must style warning helper text");
assert.match(popupCss, /\.helper--success\s*\{/, "popup must style success helper text");
assert.doesNotMatch(popupCss, /\.scanner-card\s*\{/, "popup css must remove the old scanner-card rules");
assert.doesNotMatch(popupCss, /\.scanner-chip-row\s*\{/, "popup css must remove the old scanner-chip-row rules");
assert.doesNotMatch(popupCss, /\.scanner-progress\s*\{/, "popup css must remove the old standalone progress strip rules");
assert.doesNotMatch(popupCss, /\.scanner-footer\s*\{/, "popup css must remove the old scanner footer rules");
assert.doesNotMatch(popupCss, /word-break:\s*break-all/, "progress area must not degrade into one-character wrapping");

assert.match(popupSource, /getScannerControlPanelViewModel\(state\)/, "popup must render scanner main state from the scanner control panel view model");
assert.match(popupSource, /popupStateSubscriptionActive/, "popup must track whether live whole-profile state listeners are installed");
assert.match(popupSource, /popupLastStateUpdateAt/, "popup must track the timestamp of the latest live state update or render trigger");
assert.match(popupSource, /popupLastStateUpdateSource/, "popup must track the source of the latest live state update or render trigger");
assert.match(popupSource, /popupRenderedStateVersion/, "popup must track the last rendered whole-profile state version");
assert.match(popupSource, /popupLastStateUpdateSource = "storage\.onChanged"/, "popup storage listener must mark storage.onChanged as the live update source");
assert.match(popupSource, /popupLastStateUpdateSource = "runtime\.onMessage"/, "popup runtime listener must mark runtime.onMessage as the live update source");
assert.match(popupSource, /popupStateSubscriptionActive = true[\s\S]*popupStateSubscriptionActive = false/s, "popup must mark subscription active on install and inactive on unload");
assert.match(popupSource, /popupRenderedStateVersion = wholeProfileHarvestRenderSeq/, "popup render path must record the rendered state version");
assert.match(popupSource, /async function renderWholeProfileHarvestProductState\(\): Promise<void> {[\s\S]*popupLastStateUpdateSource = "renderWholeProfileHarvestProductState"/s, "popup render entrypoint must tag direct render refreshes as their own source");
assert.match(popupSource, /renderDouyinScannerMainScreen\(state(?:, latestScannerRenderContext)?\);/, "popup must render the scanner main screen");
assert.match(popupSource, /scannerPrimaryActionButton\?\.addEventListener\("click", \(event\) => void runWholeProfilePrimaryActionFromPopup\(event\)\)/, "scanner primary action must reuse the existing whole-profile action handler with event cancellation");
assert.match(popupSource, /scannerOpenCaptureInboxButton\?\.addEventListener\("click", \(\) => void openCaptureInboxWebAppFromPopup\(\)\)/, "scanner footer Capture Inbox action must open the web Capture Inbox");
assert.match(popupSource, /scannerOpenAdvancedButton\?\.addEventListener\("click", \(\) => void setDeckActivePanel\("advanced"\)\)/, "scanner footer advanced action must open the advanced panel");
assert.match(popupHtml, /22A-2 ACTIVE SCANNER RESET BUTTON[\s\S]*id="scannerResetButton"[^>]*type="button"/, "active footer Reset button must carry the Phase 22A-2 marker and remain non-submit");
assert.match(popupSource, /scannerResetButton\?\.addEventListener\("click", \(event\) => openWholeProfileResetModal\(event, "active_footer"\)\)/, "scanner Reset action must open the custom modal from the footer path");
assert.match(popupSource, /resetWholeProfileHarvestButton\?\.addEventListener\("click", \(event\) => openWholeProfileResetModal\(event, "advanced_maintenance"\)\)/, "advanced Reset action must open the custom modal from the maintenance path");
assert.match(popupSource, /scannerResetCancelButton\?\.addEventListener\("click", \(\) => closeWholeProfileResetModal\(\)\)/, "reset modal Cancel must close the modal");
assert.match(popupSource, /event\.key === "Escape"[\s\S]*closeWholeProfileResetModal\(\)/, "reset modal must close on Escape");
assert.match(popupSource, /scannerResetOptionButtons\.forEach[\s\S]*runWholeProfileResetModeFromModal/, "reset modal action rows must dispatch reset modes");
assert.match(popupSource, /resetMode !== "current_run"[\s\S]*resetMode !== "current_profile_rescan"[\s\S]*resetMode !== "new_profile"/, "reset modal dispatch must restrict modes to the three UI choices");
assert.match(popupSource, /button\.disabled = running[\s\S]*aria-busy/, "reset options must be disabled while reset is running");
assert.match(popupSource, /Current run reset\. Profile queue and session were kept\./, "current run success message must stay unchanged");
assert.match(popupSource, /Ready for a new profile\. Open a Douyin profile and click Scan Profile\./, "new profile success message must match Phase 22E-3 copy");
assert.match(popupSource, /reset_kept_calibration[\s\S]*reset_kept_settings[\s\S]*reset_kept_session[\s\S]*reset_kept_queue[\s\S]*reset_cleared_session[\s\S]*reset_cleared_queue/, "reset diagnostics must include keep and clear flags");
assert.doesNotMatch(popupSource, /window\.prompt\("Reset options:/, "scanner reset flow must not use native prompt for reset options");
assert.match(popupSource, /if \(resetMode === "new_profile"\) \{[\s\S]*showWholeProfileSwitchConfirm\(\);[\s\S]*return;[\s\S]*\}/, "Switch profile row must open inline confirmation before dispatch");
assert.match(popupSource, /scannerResetConfirmSwitchButton\?\.addEventListener\("click", \(event\) => void resetWholeProfileHarvestStateFromPopup\("new_profile"/, "Switch profile confirmation must dispatch new_profile mode");
assert.match(popupSource, /scannerResetConfirmCancelButton\?\.addEventListener\("click", \(\) => showWholeProfileResetActionSheet\(\)\)/, "confirmation Cancel must return to action sheet");
assert.match(popupSource, /resetModeRecommendedReason[\s\S]*profile_switch_detected[\s\S]*stale_or_locked/, "reset modal must compute lightweight recommended actions");
assert.match(popupSource, /scannerResetSuggestionEl[\s\S]*completedQueue[\s\S]*every\(\(item\) => item\.status === "extracted" \|\| item\.status === "skipped"\)/, "completed queue must show Switch profile suggestion");
assert.match(popupSource, /scannerResetInlineErrorEl[\s\S]*Reset failed\. Check Advanced diagnostics\./, "reset failure must keep modal open with inline error");
assert.match(popupSource, /function openWholeProfileResetModal\(event\?: Event, source: "active_footer" \| "advanced_maintenance" = "advanced_maintenance"\)/, "modal opener must accept the click event and source marker");
assert.match(popupSource, /event\?\.preventDefault\(\);[\s\S]*event\?\.stopPropagation\(\);[\s\S]*scannerResetModalEl\.hidden = false/, "modal opener must cancel the click before showing the modal");
assert.match(popupSource, /markWholeProfileResetClicked\(source, new Date\(\)\.toISOString\(\), resetMode\);/, "reset handler must mark clicked diagnostics before async reset operation");
assert.match(popupHtml, /Reset scanner[\s\S]*Fix stuck run[\s\S]*Refresh profile[\s\S]*Switch profile/, "reset modal must expose compact reset action choices");
assert.match(popupSource, /function markWholeProfileResetClicked[\s\S]*const preserveActiveCollectRuntime = popupMustPreserveActiveCollectRuntime\(baseState\);[\s\S]*reset_result: "clicked"[\s\S]*reset_storage_write_status: "pending"[\s\S]*last_response_summary: preserveActiveCollectRuntime/s, "reset clicked diagnostics must avoid clobbering active runner-owned response summaries");
assert.match(popupSource, /await resetScannerWorkflowState\(createWholeProfilePopupRuntime\(\), \{ mode: resetMode/, "reset handler must pass explicit reset mode to canonical storage write");
assert.match(popupSource, /const storedState = await readWholeProfileHarvestState\(chrome\.storage\.local, new Date\(\)\.toISOString\(\)\);[\s\S]*renderWholeProfileHarvestProductStateFromState\(storedState, "none"\);/s, "reset handler must reload canonical reset state after storage write and re-render immediately");
assert.match(popupSource, /wholeProfileResetGeneration/, "reset handler must use a generation guard against older async restores");
assert.doesNotMatch(popupSource, /window\.location\.reload|location\.reload|chrome\.runtime\.reload/, "reset path must not reload the popup, page, or extension");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function resetWholeProfileHarvestStateFromPopup"), popupSource.indexOf("async function copyWholeProfileDebugJsonFromPopup")), /postJson|fetch\(|createCanonicalHarvestSession|flushCanonicalHarvestPayload/, "reset rendering must not call backend APIs");
assert.match(popupHtml, /22A-3 ACTIVE SCANNER PAUSE BUTTON/, "popup HTML must mark the active scanner pause button");
assert.match(popupSource, /22A-3 ACTIVE SCANNER PAUSE BUTTON/, "popup source must mark the active scanner pause button listener");
assert.match(popupHtml, /22A-4 ACTIVE SCANNER RESUME BUTTON/, "popup HTML must mark the active scanner resume button");
assert.match(popupSource, /22A-4 ACTIVE SCANNER RESUME BUTTON/, "popup source must mark the active scanner resume button paths");
assert.match(popupSource, /scannerPauseResumeButton\?\.addEventListener\("click", \(event\) => void runScannerPauseResumeButtonFromPopup\(event\)\)/, "scanner pause resume action must pass the click event to explicit state-based pause/resume routing");
assert.match(popupSource, /async function markWholeProfilePauseClicked[\s\S]*const preserveActiveCollectRuntime = popupMustPreserveActiveCollectRuntime\(baseState\);[\s\S]*last_action_clicked: "pause"[\s\S]*last_action_result: "clicked"[\s\S]*pause_requested: true[\s\S]*pause_source: source[\s\S]*last_response_summary: preserveActiveCollectRuntime/s, "pause handler must preserve runner-owned response diagnostics while still marking immediate clicked pause request state");
assert.match(popupSource, /async function markWholeProfileResumeClicked[\s\S]*const preserveActiveCollectRuntime = popupMustPreserveActiveCollectRuntime\(baseState\);[\s\S]*last_action_clicked: "resume"[\s\S]*last_action_result: nextTarget \? "clicked" : "blocked"[\s\S]*last_response_summary: preserveActiveCollectRuntime && nextTarget[\s\S]*pause_requested: false/s, "resume handler must preserve runner-owned response diagnostics for active runtime resumes while still clearing pause flags immediately");
assert.match(popupSource, /function primaryActionDispatchTarget\(actionKey: ScannerActionKey\): string[\s\S]*case "scan_profile":[\s\S]*return "dispatchBackgroundScanProfileAction22C11B"[\s\S]*case "review_overcollection":[\s\S]*return "reviewOvercollection"[\s\S]*case "calibrate":[\s\S]*return "runCalibrationWorkflow"[\s\S]*case "start_collecting":[\s\S]*return "runStartCollectingWorkflow"/s, "Phase 22C-11B primary action dispatcher must force Scan Profile through the minimal background route and keep overcollection review out of normal scan dispatch");
assert.match(popupSource, /async function handlePrimaryActionClick\(actionKey: ScannerActionKey, label: string\): Promise<void>[\s\S]*switch \(actionKey\)/, "Phase 22B-4 primary action handler must dispatch by action key, not label text");
assert.match(popupSource, /case "review_overcollection":[\s\S]*showOvercollectionReviewPanelFromPopup\(\)[\s\S]*return;/, "primary action handler must open the inline overcollection review panel without rerunning Scan Profile");
assert.match(popupSource, /case "open_capture_inbox":[\s\S]*openCaptureInboxWebAppFromPopup\(\)/, "open_capture_inbox primary action must open the web Capture Inbox");
const primaryActionHandlerSource = popupSource.slice(popupSource.indexOf("async function handlePrimaryActionClick"), popupSource.indexOf("async function runWholeProfilePrimaryActionFromPopup"));
const startCollectingHandlerCase = primaryActionHandlerSource.slice(primaryActionHandlerSource.indexOf('case "start_collecting":'), primaryActionHandlerSource.indexOf('case "pause":'));
assert.match(startCollectingHandlerCase, /return runWholeProfileHarvestProductFromPopup\(\)/, "Start Collecting action key must route only to the Start Collecting popup workflow");
assert.doesNotMatch(startCollectingHandlerCase, /startCalibration|runCalibrationWorkflow|REUP_DOUYIN_START_RIGHT_RAIL_CALIBRATION/, "Start Collecting dispatch case must never start calibration");
assert.match(popupSource, /async function runWholeProfilePrimaryActionFromPopup\(event\?: Event\): Promise<void> {[\s\S]*const state = await readWholeProfileHarvestProductState\(\);[\s\S]*const vm = getScannerControlPanelViewModel\(state\);[\s\S]*await handlePrimaryActionClick\(vm\.primaryAction\.key, vm\.primaryAction\.label\);[\s\S]*}/s, "popup primary action click path must resolve the scanner control panel primary action before dispatch");
assert.match(popupSource, /last_primary_action_key_clicked[\s\S]*last_primary_action_label_clicked[\s\S]*last_primary_action_dispatch_target/s, "primary action clicks must persist Phase 22B-4 key, label, and dispatch diagnostics");
assert.match(popupSource, /REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION/, "Start Collecting must proactively ask the content script to stop calibration mode first");
assert.match(popupSource, /calibration_mode_active_before_start:[\s\S]*calibrationStop\.activeBeforeStop[\s\S]*calibration_mode_stopped_before_start:[\s\S]*calibrationStop\.stopped/s, "Start Collecting must pass calibration mode cleanup diagnostics into the controller");
assert.match(contentScriptSource, /REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION[\s\S]*ensureCalibrationModeStopped\(\)[\s\S]*calibration_mode_active_before_stop[\s\S]*calibration_mode_stopped/s, "content script must expose an explicit calibration mode stop/cleanup message");
assert.match(contentScriptSource, /function ensureCalibrationModeStopped\(\): \{ activeBeforeStop: boolean; stopped: boolean \}[\s\S]*activeCalibrationMode\.cleanup\(\)[\s\S]*activeCalibrationMode = null/s, "content script calibration cleanup must remove active click-capture mode before Start Collecting");
assert.match(popupSource, /case "resume":[\s\S]*handleResumeCollectingClick\("primary_action_card"\)/, "primary action card Resume must use the active strict dispatcher resume handler");
assert.match(popupSource, /workflow\.collection\.status === "paused"[\s\S]*handleResumeCollectingClick\("footer_pause_resume_button"\)/, "footer Resume must use the active resume handler");
assert.match(popupSource, /wholeProfileQueuePreviewRowsEl/, "popup must render queue preview rows separately from main cards");
assert.match(popupSource, /wholeProfileExtractionResultsRowsEl/, "popup must render extraction result rows separately from main cards");
assert.match(popupSource, /wholeProfileBackendResultsRowsEl/, "popup must render backend result rows separately from main cards");
assert.match(popupSource, /WHOLE_PROFILE_UI_PREFS_KEY/, "popup must persist overlay panel preferences locally");
assert.match(popupSource, /getRunTabViewModel\(state, readiness, actionState\)/, "popup may keep the compact run view model for relocated results and advanced content");
assert.match(popupSource, /active_tab:\s*"run"\s*\|\s*"results"\s*\|\s*"advanced"/, "popup source must persist advanced tab state");
assert.match(popupSource, /document\.body\.dataset\.scannerProgressTone = vm\.health\.safety === "Check"/, "popup must expose scanner progress tone for UI state styling");
assert.match(popupSource, /viewModel\.operator_help\.action_help/, "popup must wire contextual help from the whole-profile operator help view model");
assert.doesNotMatch(popupSource, /dryRunFirstButton|dryRunLastButton/, "popup main run wiring must not keep first\/last dry-run buttons");
assert.doesNotMatch(viewModelSource, /douyinHarvestRuntimeV2|douyinSafeHarvestRun|smartHarvestState|harvestProgress/, "view model must not depend on V2 or legacy runtime state");
assert.match(viewModelSource, /Resume requested at[\s\S]*Resume runner target[\s\S]*Collection status[\s\S]*Pending count[\s\S]*Saved count/s, "Advanced diagnostics must expose resume, collection, and counter fields");

{
  const resetLikeState = {
    ...withClassification(withExtracted(withDryRun(withVerify(baseState())))),
    calibration: { status: "calibrated" as const, point_count: 4, source_key: "douyinRightRailCalibration", viewport_warning: null },
    debug: {
      ...baseState().debug,
      last_action_clicked: "reset",
      last_action_result: "success",
      last_request_summary: {
        reset_at: "2026-05-06T12:10:00.000Z",
        reset_kept_calibration: true,
        reset_kept_settings: true,
        reset_background_cancel_status: "not_applicable_local_controller"
      },
      last_response_summary: {
        reset_result: "success",
        reset_at: "2026-05-06T12:10:00.000Z",
        reset_storage_write_status: "success",
        queueCount: 0,
        active_task: null,
        busy: false
      }
    }
  };
  const hardCleared = {
    ...createWholeProfileHarvestIdleState("2026-05-06T12:10:00.000Z"),
    profile_url: resetLikeState.profile_url,
    page_context: resetLikeState.page_context,
    calibration: resetLikeState.calibration,
    harvest_options: resetLikeState.harvest_options,
    debug: resetLikeState.debug
  };
  const panelVm = getScannerControlPanelViewModel(hardCleared);
  const mainVm = getDouyinScannerMainViewModel(hardCleared);
  const progressVm = getWholeProfileHarvestProgressViewModel(hardCleared);
  assert.equal(panelVm.headerStatus, "Ready", "after reset the hero badge must be Ready, not a stale video count");
  assert.equal(panelVm.profileScanned, false, "after reset the stats grid should be hidden because profile scan is cleared");
  assert.equal(panelVm.action.key, "scan_profile", "after reset primary scanner action must be Scan Profile");
  assert.equal(panelVm.counts.queueCount, 0, "after reset queue count must be zero");
  assert.equal(mainVm.header_status, "Ready", "main scanner VM must not restore stale 58 videos after reset");
  assert.equal(mainVm.primary_action?.label, "Scan Profile", "main scanner VM must show Scan Profile after reset");
  assert.equal(mainVm.stats_summary.metrics[2]?.value, "0", "main scanner VM queue metric must be zero after reset");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Reset result" && row.value === "success"), true, "Advanced diagnostics must show reset success");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Reset storage write" && row.value === "success"), true, "Advanced diagnostics must show reset storage write status");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Reset kept calibration" && row.value === "yes"), true, "Advanced diagnostics must show calibration was kept");
}

{
  const canonicalState = withClassification(withExtracted(withDryRun(withVerify(baseState()))));
  const panelVm = getScannerControlPanelViewModel(canonicalState);
  const mainVm = getDouyinScannerMainViewModel(canonicalState);
  const progressVm = getWholeProfileHarvestProgressViewModel(canonicalState);
  const canonicalAction = getCanonicalScannerPrimaryAction(canonicalState);

  assert.equal(panelVm.action.key, canonicalAction.key, "scanner control panel must use the canonical primary action key");
  assert.equal(panelVm.action.buttonLabel, canonicalAction.label, "scanner control panel must use the canonical primary action label outside safe-batch continuation");
  assert.equal(mainVm.primary_action?.key, canonicalAction.key, "scanner main VM must use the canonical primary action key");
  assert.equal(mainVm.primary_action?.label, canonicalAction.label, "scanner main VM must use the canonical primary action label outside safe-batch continuation");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Canonical calibration ready"), true, "Advanced diagnostics must expose canonical calibration readiness");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Canonical calibration source"), true, "Advanced diagnostics must expose canonical calibration source");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Primary action key" && row.value === canonicalAction.key), true, "Advanced diagnostics must expose the canonical primary action key");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Primary action selector version" && row.value === canonicalAction.decisionTrace.selector_version), true, "Advanced diagnostics must expose the canonical selector version");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "State machine version" && row.value === "22C-9Z-3"), true, "Advanced diagnostics must expose the scanner state machine version");
  assert.equal(progressVm.details.technical_rows.some((row) => row.label === "Primary action decision trace" && row.value.includes(canonicalAction.decisionTrace.selector_version)), true, "Advanced diagnostics must expose the primary action decision trace");
}

{
  const activeState = {
    ...withClassification(withDryRun(withVerify(baseState()))),
    workflow: {
      ...withClassification(withDryRun(withVerify(baseState()))).workflow,
      collection: { ...withClassification(withDryRun(withVerify(baseState()))).workflow.collection, status: "running" as const }
    },
    profile_scan: {
      ...withClassification(withDryRun(withVerify(baseState()))).profile_scan,
      diagnostics: {
        ...(withClassification(withDryRun(withVerify(baseState()))).profile_scan.diagnostics && typeof withClassification(withDryRun(withVerify(baseState()))).profile_scan.diagnostics === "object" ? withClassification(withDryRun(withVerify(baseState()))).profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_run_id: "batch_run_authoritative_lock",
        batch_heartbeat_at: new Date().toISOString()
      }
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(activeState, Date.parse("2026-05-06T12:01:30.000Z"));
  const canonicalAction = getCanonicalScannerPrimaryAction(activeState);
  const panelVm = getScannerControlPanelViewModel(activeState);
  const mainVm = getDouyinScannerMainViewModel(activeState);

  assert.equal(runnerLock.active, true, "authoritative runner lock must activate while safe-batch collection is locked");
  assert.equal(runnerLock.reason, "collection_running", "authoritative runner lock must explain collection_running");
  assert.equal(runnerLock.diagnostics.collection_runner_active, "yes", "runner lock diagnostics must expose active runner yes");
  assert.notEqual(canonicalAction.key, "start_collecting", "active authoritative runner lock must not expose Start Collecting as the primary action");
  assert.equal(canonicalAction.label, "Collecting videos...", "active authoritative runner lock must force the collecting label");
  assert.equal(canonicalAction.enabled, false, "active authoritative runner lock must disable duplicate primary action dispatch");
  assert.equal(panelVm.action.buttonLabel, "Collecting videos...", "scanner panel sanitizer must force collecting label");
  assert.equal(panelVm.action.enabled, false, "scanner panel sanitizer must disable duplicate Start Collecting");
  assert.equal(mainVm.primary_action?.label, "Collecting videos...", "main scanner sanitizer must force collecting label");
  assert.equal(mainVm.primary_action?.enabled, false, "main scanner sanitizer must disable duplicate Start Collecting");
}

{
  const state = authoritativeReconciliationFixtureState();
  const counters = deriveAuthoritativeProfileCounters(state);
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(counters.queue_total, 111, "authoritative counters must keep scan queue total as 111");
  assert.equal(counters.backend_profile_captured_count, 30, "authoritative counters must read backend captured count from verify_response.counts.captured");
  assert.equal(counters.backend_item_count, 30, "authoritative counters must read backend item count from verify_response.items");
  assert.equal(counters.already_collected_in_scan_count, 30, "authoritative counters must match 30 backend items back to the scan queue");
  assert.equal(counters.profile_already_collected_count, 30, "authoritative counters must correct stale already-collected zero to 30");
  assert.equal(counters.profile_eligible_count, 81, "authoritative counters must compute 111 minus 30 as 81 eligible");
  assert.equal(counters.pending_count, 81, "authoritative counters must compute pending from reconciled eligible count");
  assert.equal(counters.diagnostics.current_batch_saved_count_ignored_for_already_collected, "yes", "current-batch saved count must not become total profile already-collected count");
  assert.equal(popupMetrics.profile.profile_total_count, 111, "popup metrics must keep profile total count at 111");
  assert.equal(popupMetrics.profile.already_collected_count, 30, "popup metrics must use backend reconciliation for already-collected count");
  assert.equal(popupMetrics.profile.new_count, 81, "popup metrics must derive profile-level New from 111 minus 30");
  assert.equal(popupMetrics.profile.eligible_count, 81, "popup metrics must derive profile-level eligible from the same authority as New");
  assert.equal(popupMetrics.profile.queue_count, 81, "popup metrics must derive profile-level Queue from the same authority as New");
  assert.equal(popupMetrics.active_runner.active_runner_remaining_count, 109, "popup metrics may expose raw pending only as active-runner remaining");
  assert.equal(popupMetrics.diagnostics.popup_metrics_raw_pending_count, 109, "popup metrics diagnostics must expose raw pending count separately");
  assert.equal(popupMetrics.diagnostics.popup_metrics_raw_batch_pending_count, 111, "popup metrics diagnostics must expose raw batch pending count separately");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "profile tiles must declare durable post-scan snapshot authority");
  assert.equal(popupMetrics.diagnostics.popup_metrics_post_scan_counter_snapshot_status, "applied", "popup metrics must expose applied post-scan snapshot status");
  assert.equal(popupMetrics.diagnostics.popup_metrics_post_scan_counter_snapshot_source, "backend_capture_inbox_profile_summary", "popup metrics must expose backend Capture Inbox summary source");
  assert.equal(popupMetrics.diagnostics.popup_metrics_raw_pending_ignored_for_profile_tiles, true, "raw pending must be ignored for profile tiles when reconciliation authority exists");
  assert.equal(technicalValue("Profile already collected count"), "30", "Advanced diagnostics must render reconciled already-collected count, not stale 0");
  assert.equal(technicalValue("Profile eligible count"), "81", "Advanced diagnostics must render reconciled pending/eligible count, not stale 101");
  assert.equal(technicalValue("Popup metrics new count"), "81", "Advanced diagnostics must render reconciled popup New count");
  assert.equal(technicalValue("Popup metrics queue count"), "81", "Advanced diagnostics must render reconciled popup Queue count");
  assert.equal(technicalValue("Popup metrics raw pending count"), "109", "Advanced diagnostics must preserve raw pending as raw/runner state");
  assert.equal(technicalValue("Popup metrics raw batch pending count"), "111", "Advanced diagnostics must preserve raw batch pending as raw/runner state");
  assert.equal(technicalValue("Popup metrics raw pending ignored for profile tiles"), "true", "Advanced diagnostics must state raw pending was ignored for profile tiles");
  assert.equal(technicalValue("Profile queue total count"), "111", "Advanced diagnostics must render authoritative queue total");
  const trace = JSON.parse(technicalValue("POST_SCAN_COUNTER_PIPELINE_TRACE") ?? "{}");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_exists, "yes", "post-scan pipeline trace must expose that the snapshot exists");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_source, "backend_capture_inbox_profile_summary", "post-scan pipeline trace must expose snapshot source");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_status, "applied", "post-scan pipeline trace must expose snapshot status");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_scanned_total, 111, "post-scan pipeline trace must expose scanned total");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_backend_captured, 30, "post-scan pipeline trace must expose backend captured");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_backend_ready, 19, "post-scan pipeline trace must expose backend ready");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_backend_dup, 0, "post-scan pipeline trace must expose backend dup");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_backend_fail, 0, "post-scan pipeline trace must expose backend fail");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_new, 81, "post-scan pipeline trace must expose snapshot New count");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_incomplete, 11, "post-scan pipeline trace must expose snapshot Incomplete count");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_need_retry, 0, "post-scan pipeline trace must expose snapshot Need retry count");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_already_collected, 30, "post-scan pipeline trace must expose snapshot Already collected count");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_queue, 81, "post-scan pipeline trace must expose snapshot Queue count");
  assert.equal(trace.final_popup_render_input.trace_popup_tiles_render_used_snapshot, "yes", "post-scan pipeline trace must expose popup snapshot usage");
  const collectTrace = JSON.parse(technicalValue("POST_COLLECT_PIPELINE_TRACE") ?? "{}");
  assert.equal(collectTrace.batch_start.trace_collect_popup_route_hit, "yes", "post-collect trace must show popup dispatch reached Start Collecting");
  assert.equal(collectTrace.batch_start.trace_collect_popup_dispatch_target, "runStartCollectingWorkflow", "post-collect trace must expose popup dispatch target");
  assert.equal(collectTrace.batch_start.trace_collect_controller_entry_hit, "yes", "post-collect trace must show controller entry reached Start Collecting");
  assert.equal(collectTrace.batch_start.trace_collect_batch_runner_entry_hit, "yes", "post-collect trace must show safe batch runner entry");
  assert.equal(collectTrace.batch_start.trace_collect_started, "yes", "post-collect trace must show collection started from batch diagnostics");
  assert.equal(collectTrace.batch_start.trace_collect_initial_backend_captured, 30, "post-collect trace must expose initial backend captured from snapshot");
  assert.equal(collectTrace.batch_start.trace_collect_initial_backend_ready, 19, "post-collect trace must expose initial backend ready from snapshot");
  assert.equal(collectTrace.batch_start.trace_collect_initial_new, 81, "post-collect trace must expose initial New count from snapshot");
  assert.equal(collectTrace.batch_start.trace_collect_initial_queue, 81, "post-collect trace must expose initial Queue count from snapshot");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_backend_captured, 30, "post-collect trace must preserve pre-batch backend captured count");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_backend_ready, 19, "post-collect trace must preserve pre-batch backend ready count");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_backend_dup, 0, "post-collect trace must preserve pre-batch backend duplicate count");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_backend_fail, 0, "post-collect trace must preserve pre-batch backend failed count");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_new, 81, "post-collect trace must preserve pre-batch New count");
  assert.equal(collectTrace.batch_start.trace_collect_pre_batch_queue, 81, "post-collect trace must preserve pre-batch Queue count");
  assert.equal(collectTrace.batch_start.trace_collect_post_batch_backend_captured, 32, "post-collect trace must expose post-batch backend captured count separately");
  assert.equal(collectTrace.batch_start.trace_collect_post_batch_backend_ready, 21, "post-collect trace must expose post-batch backend ready count separately");
  assert.equal(collectTrace.batch_start.trace_collect_post_batch_new, 79, "post-collect trace must expose post-batch New count separately");
  assert.equal(collectTrace.batch_start.trace_collect_post_batch_queue, 79, "post-collect trace must expose post-batch Queue count separately");
  assert.equal(collectTrace.batch_start.trace_collect_batch_delta_captured, 2, "post-collect trace must expose captured delta");
  assert.equal(collectTrace.batch_start.trace_collect_batch_delta_queue, -2, "post-collect trace must expose queue delta");
  assert.equal(collectTrace.batch_start.trace_collect_selected_count, 2, "post-collect trace must expose selected batch count");
  assert.equal(collectTrace.batch_start.trace_collect_batch_limit, 10, "post-collect trace must expose batch limit");
  assert.deepEqual(collectTrace.batch_start.trace_collect_selected_aweme_ids_first_10, ["700000000000000030", "700000000000000031"], "post-collect trace must expose selected aweme ids");
  assert.equal(collectTrace.queue_filtering.trace_collect_queue_filtering_endpoint, "/douyin-extension/capture-inbox/profile-items", "post-collect trace must expose the backend profile-items endpoint used for queue filtering");
  assert.equal(collectTrace.queue_filtering.trace_collect_queue_filtering_status, "success", "post-collect trace must expose successful backend profile-items status");
  assert.equal(collectTrace.queue_filtering.backend_captured_aweme_id_count, 30, "post-collect trace must expose backend captured aweme ID count");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_count_source, "backend_profile_items_response.counts.captured", "post-collect trace must expose backend captured count source");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_id_set_source, "backend_profile_items_response.items.aweme_ids", "post-collect trace must expose backend captured ID set source");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_counts_and_ids_same_response, "yes", "post-collect trace must prove counts and IDs came from the same backend response");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_aweme_id_count_expected, 30, "post-collect trace must expose expected backend captured aweme ID count");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_aweme_id_count_actual, 30, "post-collect trace must expose actual backend captured aweme ID count");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_id_set_stale, "no", "post-collect trace must expose stale ID-set status");
  assert.equal(collectTrace.queue_filtering.trace_collect_backend_captured_id_set_stale_reason, null, "post-collect trace must expose stale ID-set reason");
  assert.equal(collectTrace.queue_filtering.trace_collect_selection_blocked, "no", "post-collect trace must expose trace-level selection blocked flag");
  assert.equal(collectTrace.queue_filtering.trace_collect_selection_block_reason, null, "post-collect trace must expose trace-level selection block reason");
  assert.equal(collectTrace.queue_filtering.filtered_collectable_count, 81, "post-collect trace must expose filtered collectable count");
  assert.equal(collectTrace.queue_filtering.skipped_already_captured_count, 30, "post-collect trace must expose skipped already-captured count");
  assert.equal(collectTrace.queue_filtering.selected_ids_already_captured_count, 0, "post-collect trace must prove selected IDs were not already captured");
  assert.deepEqual(collectTrace.queue_filtering.selected_ids_already_captured_first_10, [], "post-collect trace must expose first selected already-captured IDs for debugging");
  assert.equal(collectTrace.queue_filtering.was_in_backend_captured_set_before_collect, "no", "post-collect trace must expose whether selected IDs were in backend set before collect");
  assert.equal(collectTrace.queue_filtering.backend_captured_id_set_available, "yes", "post-collect trace must prove backend captured ID set availability");
  assert.equal(collectTrace.queue_filtering.backend_captured_id_set_incomplete, "no", "post-collect trace must prove backend captured ID set completeness");
  assert.equal(collectTrace.queue_filtering.selection_blocked, "no", "post-collect trace must expose whether selection was blocked");
  assert.equal(collectTrace.queue_filtering.selection_block_reason, null, "post-collect trace must expose selection block reason");
  assert.equal(collectTrace.queue_filtering.used_for_selection, "yes", "post-collect trace must prove backend captured ID filtering was used for selection");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].was_in_backend_captured_set_before_collect, "no", "post-collect trace must expose pre-collect backend set membership per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].expected_backend_operation, "create", "post-collect trace must expose expected backend operation per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_operation_result, "created", "post-collect trace must expose backend operation result per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_profile_capture_delta_effect, "newly_captured_for_profile", "post-collect trace must expose profile-level capture delta effect per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_summary_missing_this_id_before_collect, "yes", "post-collect trace must expose whether backend summary lacked the item before collect");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_match_diagnostics, null, "post-collect trace must expose backend match diagnostics only when needed");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_write_attempted, true, "post-collect trace must expose backend write attempted per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_http_status, 200, "post-collect trace must expose backend HTTP status per item");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].backend_capture_inbox_item_id, "capture_item_30", "post-collect trace must expose saved Capture Inbox item id");
  assert.equal(collectTrace.per_item_backend_writes.trace_collect_item_results[0].final_status, "saved_verified", "post-collect trace must expose final item status");
  const persistentTrace = JSON.parse(technicalValue("PERSISTENT_COLLECT_JOB_TRACE") ?? "{}");
  assert.equal(persistentTrace.trace_collect_job_state, "idle", "persistent collect job trace must render idle state when no collect job is active");
  assert.equal(collectTrace.collect_job.trace_collect_job_state, "idle", "post-collect trace must include persistent collect job state");
}

{
  const state: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_fresh_1",
      profile_identifier: "https://www.douyin.com/user/MS4wLjABAAAAfixture",
      normalized_profile_identifier: "https://www.douyin.com/user/ms4w.ljabaaaafixture",
      state: "running",
      started_at: new Date(Date.now() - 20_000).toISOString(),
      updated_at: new Date(Date.now() - 10_000).toISOString(),
      heartbeat_at: new Date(Date.now() - 10_000).toISOString(),
      runner_ack_at: new Date(Date.now() - 19_000).toISOString(),
      current_step: "after_backend_write",
      current_aweme_id: "700000000000000030",
      current_item_index: 30,
      batch_limit: 10,
      selected_count: 2,
      attempted_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      skipped_count: 0,
      lock_owner: "collect_job_fresh_1",
      lock_acquired_at: new Date(Date.now() - 20_000).toISOString(),
      lock_expires_at: new Date(Date.now() + 45_000).toISOString(),
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 5,
      lock_released: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(state, Date.parse("2026-05-06T12:01:30.000Z"));
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const persistentTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "PERSISTENT_COLLECT_JOB_TRACE")?.value ?? "{}");
  const collectTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_COLLECT_PIPELINE_TRACE")?.value ?? "{}");

  assert.equal(runnerLock.active, true, "fresh persistent collect job must suppress duplicate Start Collecting after popup reopen");
  assert.equal(runnerLock.source, "collect_job", "fresh persistent collect job must be the runner-lock source");
  assert.equal(persistentTrace.trace_collect_job_id, "collect_job_fresh_1", "persistent collect job trace must expose job id");
  assert.equal(persistentTrace.trace_collect_job_state, "running", "persistent collect job trace must expose running state");
  assert.equal(persistentTrace.trace_collect_job_current_step, "after_backend_write", "persistent collect job trace must expose current step");
  assert.equal(persistentTrace.trace_collect_job_recovery_available, false, "fresh collect job must not show recovery availability");
  assert.equal(collectTrace.collect_job.trace_collect_job_id, "collect_job_fresh_1", "post-collect trace must embed persistent collect job trace");
}

{
  const softStaleState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAAfixture",
      scanned_total: 111,
      backend_captured: 105,
      backend_ready: 19,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 105,
      incomplete: 86,
      need_retry: 0,
      new: 6,
      queue: 6,
      backend_captured_aweme_ids: [],
      applied_at: "2026-05-06T12:00:00.000Z"
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_soft_stale_alive_1",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:00:30.000Z",
      heartbeat_at: "2026-05-06T12:00:59.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "after_backend_write",
      current_aweme_id: "700000000000000109",
      current_item_index: 109,
      batch_limit: 5,
      selected_count: 5,
      attempted_count: 5,
      succeeded_count: 5,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 105,
      pre_batch_queue: 6,
      lock_owner: "collect_job_soft_stale_alive_1",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:01:44.000Z",
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 8,
      lock_released: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(softStaleState, Date.parse("2026-05-06T12:01:30.000Z"));
  const popupMetrics = deriveReconciledPopupMetrics(softStaleState);
  const progressVm = getWholeProfileHarvestProgressViewModel(softStaleState);
  const collectTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_COLLECT_PIPELINE_TRACE")?.value ?? "{}");

  assert.equal(runnerLock.active, true, "soft-stale collect job with progress signals must still block duplicate Start Collecting");
  assert.equal(runnerLock.source, "collect_job", "alive active collect job must use the canonical collect-job lock source");
  assert.equal(runnerLock.diagnostics.trace_collect_job_soft_stale, "no", "alive active collect progress must not be downgraded to soft stale");
  assert.equal(runnerLock.diagnostics.trace_collect_job_hard_stale, "no", "soft stale must not be hard stale");
  assert.equal(runnerLock.diagnostics.trace_collect_job_may_be_alive, "yes", "soft stale with progress must be treated as possibly alive");
  // Profile tiles stay on post_scan_counter_snapshot during active collect (no in-flight heartbeat flicker).
  assert.equal(popupMetrics.profile.already_collected_count, 105, "profile tiles must keep stable post-scan snapshot captured during active collect");
  assert.equal(popupMetrics.profile.queue_count, 6, "profile tiles must keep stable post-scan snapshot queue during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "profile tiles must declare post-scan snapshot authority during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_ignore_inflight_progress, "yes", "profile tiles must ignore in-flight collect progress");
  assert.equal(popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_active_collect_job, "no", "post-scan snapshot must remain authoritative for profile tiles during active collect");
  assert.equal(collectTrace.final_popup_render_input.trace_collect_counter_authority, "post_scan_counter_snapshot", "post-collect trace must expose post-scan snapshot counter authority");
  assert.equal(collectTrace.final_popup_render_input.trace_collect_popup_already_collected, 105, "post-collect trace must render stable snapshot captured counter");
  assert.equal(collectTrace.final_popup_render_input.trace_collect_popup_queue, 6, "post-collect trace must render stable snapshot queue counter");
}

{
  const staleState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_stale_1",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:00:10.000Z",
      heartbeat_at: "2026-05-06T12:00:10.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "unknown_idle_gap",
      current_aweme_id: null,
      current_item_index: null,
      selected_count: 0,
      attempted_count: 0,
      succeeded_count: 0,
      lock_owner: "collect_job_stale_1",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:00:55.000Z",
      recoverable: false,
      lock_released: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(staleState, Date.parse("2026-05-06T12:03:00.000Z"));

  assert.equal(runnerLock.active, false, "hard-stale persistent collect job without selected progress must not keep Start Collecting blocked forever");
  assert.equal(runnerLock.diagnostics.trace_collect_job_recoverable, true, "hard-stale persistent collect job diagnostics must be recoverable");
  assert.equal(runnerLock.diagnostics.trace_collect_job_hard_stale, "yes", "hard-stale persistent collect job diagnostics must expose hard stale");
  assert.equal(runnerLock.diagnostics.trace_collect_job_stale_reason, "collect_job_hard_stale", "hard-stale persistent collect job diagnostics must expose hard stale reason");
}

{
  const safeDelayAliveState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_safe_delay_alive_1",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:00.000Z",
      heartbeat_at: "2026-05-06T12:01:00.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "before_safe_delay",
      current_aweme_id: "7634192733514500004",
      current_item_index: 4,
      batch_limit: 5,
      selected_count: 5,
      attempted_count: 4,
      succeeded_count: 4,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 30,
      pre_batch_queue: 81,
      lock_owner: "collect_job_safe_delay_alive_1",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:01:40.000Z",
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 12,
      lock_released: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(safeDelayAliveState, Date.parse("2026-05-06T12:02:31.000Z"));
  const popupMetrics = deriveReconciledPopupMetrics(safeDelayAliveState);
  const canonicalAction = getCanonicalScannerPrimaryAction(safeDelayAliveState);

  assert.equal(runnerLock.active, true, "safe-delay job with runner ack and progress must remain locked even when lock expiry is old");
  assert.equal(runnerLock.diagnostics.trace_collect_job_hard_stale, "no", "known alive safe-delay progress must not be hard stale");
  assert.equal(runnerLock.diagnostics.trace_collect_stale_check_clear_lock_allowed, "no", "known alive safe-delay progress must deny stale lock clear");
  assert.equal(runnerLock.diagnostics.trace_collect_stale_check_clear_lock_denied_reason, "active_runner_known_alive_progress", "denied stale clear reason must be explicit");
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "running", "expired but alive safe-delay state must render active collecting state");
  assert.notEqual(canonicalAction.label, "Start Collecting", "canonical action must not flicker to Start while live safe-delay job exists");
  assert.equal(popupMetrics.profile.already_collected_count, 30, "profile tiles stay on post-scan snapshot during active collect (no in-flight pre-batch+succeeded flicker)");
  assert.equal(popupMetrics.profile.queue_count, 81, "profile tiles stay on post-scan snapshot queue during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "profile tiles must declare post-scan snapshot authority during active collect");
}

{
  const afterSafeDelayAliveState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    profile_scan: {
      ...authoritativeReconciliationFixtureState().profile_scan,
      diagnostics: {
        ...(authoritativeReconciliationFixtureState().profile_scan.diagnostics && typeof authoritativeReconciliationFixtureState().profile_scan.diagnostics === "object"
          ? authoritativeReconciliationFixtureState().profile_scan.diagnostics as Record<string, unknown>
          : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_batch_runner_entry_hit: "yes",
        trace_collect_started: "yes",
        trace_collect_popup_already_collected: 33,
        trace_collect_popup_new: 102,
        trace_collect_popup_queue: 102,
        trace_counter_selected_captured: 33,
        trace_counter_selected_queue: 102,
        trace_counter_selected_new: 102,
        active_counter_job_id: "collect_job_after_safe_delay_alive_3r3a"
      }
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_after_safe_delay_alive_3r3a",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:27.000Z",
      heartbeat_at: "2026-05-06T12:01:27.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "after_safe_delay",
      current_aweme_id: "7636339652122758434",
      current_item_index: 8,
      batch_limit: 5,
      selected_count: 5,
      attempted_count: 3,
      succeeded_count: 3,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 30,
      pre_batch_queue: 105,
      lock_owner: "collect_job_after_safe_delay_alive_3r3a",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:01:20.000Z",
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 9,
      lock_released: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(afterSafeDelayAliveState, Date.parse("2026-05-06T12:01:35.000Z"));
  const popupMetrics = deriveReconciledPopupMetrics(afterSafeDelayAliveState);
  const canonicalAction = getCanonicalScannerPrimaryAction(afterSafeDelayAliveState);

  assert.equal(runnerLock.active, true, "after_safe_delay active progress must preserve collect lock despite expired TTL");
  assert.equal(runnerLock.diagnostics.trace_collect_stale_check_may_be_alive, "yes", "after_safe_delay active progress must be considered alive");
  assert.equal(runnerLock.diagnostics.trace_collect_stale_check_hard_stale_allowed, "no", "after_safe_delay active progress must deny hard stale");
  assert.equal(runnerLock.diagnostics.trace_collect_stale_check_lock_clear_allowed, "no", "after_safe_delay active progress must deny lock clear");
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "running", "active safe-delay state must remain running in the popup");
  assert.equal(canonicalAction.label, "Collecting videos...", "active safe-delay state must not flicker to Start Collecting");
  assert.equal(runnerLock.diagnostics.trace_collect_job_lock_expired, false, "fresh live safe-delay diagnostics must not report lock expired");
  assert.equal(runnerLock.diagnostics.trace_collect_job_lock_expired_raw, true, "raw expired lock remains visible for diagnostics");
  assert.equal(runnerLock.diagnostics.trace_collect_job_lock_expired_suppressed, "yes", "fresh live heartbeat must explicitly suppress raw lock expiry");
  assert.equal(popupMetrics.profile.already_collected_count, 30, "profile tiles stay on post-scan snapshot during active collect (ignore in-flight diagnostic progress)");
  assert.equal(popupMetrics.profile.queue_count, 81, "profile tiles stay on post-scan snapshot queue during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "profile tiles must declare post-scan snapshot authority");
  assert.equal(popupMetrics.diagnostics.trace_counter_monotonic_guard_applied, "no", "in-flight diagnostic progress must not latch profile tiles above snapshot");
}

{
  const splitBrainState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    profile_scan: {
      ...authoritativeReconciliationFixtureState().profile_scan,
      diagnostics: {
        ...(authoritativeReconciliationFixtureState().profile_scan.diagnostics && typeof authoritativeReconciliationFixtureState().profile_scan.diagnostics === "object"
          ? authoritativeReconciliationFixtureState().profile_scan.diagnostics as Record<string, unknown>
          : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_job_action_blocked_reason: "fresh_collect_job_running",
        trace_collect_tab_inactive_state: null,
        trace_collect_popup_already_collected: 10,
        trace_collect_popup_queue: 101,
        trace_counter_selected_captured: 12,
        trace_counter_selected_queue: 99,
        trace_counter_selected_new: 99,
        trace_counter_selected_source: "last_committed_counter_latch",
        trace_counter_render_generation: 8,
        last_rendered_captured: 12,
        last_rendered_queue: 99,
        last_rendered_new: 99,
        active_counter_job_id: "collect_job_split_brain_3r3b"
      }
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_split_brain_3r3b",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:00.000Z",
      heartbeat_at: "2026-05-06T12:01:00.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "after_safe_delay",
      current_aweme_id: "7636339652122758434",
      current_item_index: 8,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 2,
      succeeded_count: 2,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 10,
      pre_batch_queue: 101,
      lock_owner: "collect_job_split_brain_3r3b",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:01:45.000Z",
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 10,
      lock_released: false
    },
    active_collect_runtime: {
      ...authoritativeReconciliationFixtureState().active_collect_runtime,
      job_id: "collect_job_split_brain_3r3b",
      runtime_generation: 9,
      render_generation: 8,
      canonical_state: "running",
      canonical_phase: "collecting",
      current_step: "after_safe_delay",
      current_aweme_id: "7636339652122758434",
      current_item_index: 8,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 2,
      succeeded_count: 2,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 10,
      pre_batch_queue: 101,
      latest_progress_captured: 12,
      latest_progress_queue: 99,
      latest_progress_new: 99,
      heartbeat_at: "2026-05-06T12:01:00.000Z",
      lock_owner: "collect_job_split_brain_3r3b",
      lock_expires_at: "2026-05-06T12:01:45.000Z",
      last_update_source: "runner.after_safe_delay",
      trace: {
        ...authoritativeReconciliationFixtureState().active_collect_runtime.trace,
        queue_filtering: {
          queue_filtering_source: "runtime_store",
          queue_filtering_filtered_collectable_count: 99
        },
        per_item_backend_writes: {
          batch_item_loop_entered: true,
          batch_item_loop_current_aweme_id: "7636339652122758434",
          batch_item_loop_current_index: 8,
          recent_batch_item_results: [
            {
              index: 8,
              aweme_id: "7636339652122758434",
              backend_operation_result: "created",
              final_status: "saved_verified"
            }
          ]
        },
        timing: {
          trace_collect_batch_timing_total_ms: 4200,
          trace_collect_batch_timing_avg_item_ms: 2100,
          trace_collect_batch_timing_item_count: 2,
          trace_collect_batch_timing_recent_items: [2100, 2100]
        },
        summary: {
          trace_collect_job_popup_render_state: "running",
          trace_collect_runtime_render_generation: 8,
          trace_collect_popup_already_collected: 12,
          trace_collect_popup_queue: 99,
          trace_collect_popup_new: 99,
          trace_counter_selected_captured: 12,
          trace_counter_selected_queue: 99,
          trace_counter_selected_new: 99,
          trace_counter_selected_source: "active_collect_runtime"
        }
      },
      updated_at: "2026-05-06T12:01:00.000Z"
    }
  };
  const nowMs = Date.parse("2026-05-06T12:01:20.000Z");
  const runnerLock = deriveAuthoritativeRunnerLock(splitBrainState, nowMs);
  const canonicalAction = getCanonicalScannerPrimaryAction(splitBrainState);
  const popupMetrics = deriveReconciledPopupMetrics(splitBrainState);
  const progressView = getWholeProfileHarvestProgressViewModel(splitBrainState);
  const technicalRows = Object.fromEntries(progressView.details.technical_rows.map((row) => [row.label, row.value]));

  assert.equal(runnerLock.active, true, "Phase 3R-3B active collect job must remain active while heartbeat is fresh");
  assert.equal(runnerLock.diagnostics.trace_collect_heartbeat_age_ms_recomputed, 20_000, "heartbeat age must be recomputed from the supplied runtime clock and heartbeat_at");
  assert.equal(runnerLock.diagnostics.trace_collect_heartbeat_age_source, "runtime_now_minus_heartbeat_at", "heartbeat diagnostics must expose the runtime clock source");
  assert.equal(runnerLock.diagnostics.trace_collect_lock_should_be_held_for_live_job, "yes", "live collect job must keep the lock held while running");
  assert.equal(runnerLock.diagnostics.trace_collect_waiting_for_active_tab_allowed, "no", "waiting_for_active_tab must be denied without explicit tab inactivity evidence");
  assert.equal(runnerLock.diagnostics.trace_collect_waiting_for_active_tab_denied_reason, "no_explicit_tab_inactive_evidence", "denied tab wait reason must be explicit");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_warning, "no", "matching runtime and collect job ids must not trigger coherence warnings");
  assert.equal(runnerLock.diagnostics.trace_collect_runtime_coherence_warning_reason, null, "coherence warning reason must remain null when ids are coherent");
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "running", "canonical active collect state must stay running instead of waiting_for_active_tab");
  assert.equal(runnerLock.diagnostics.trace_ui_action_block_render_suppressed, "yes", "passive action-block reason must be suppressed during active running collect");
  assert.equal(canonicalAction.label, "Collecting videos...", "canonical action must render the active collecting label without exposing Start Collecting");
  assert.equal(canonicalAction.disabledReason, null, "canonical active action must not show generic passive Action blocked text");
  assert.equal(popupMetrics.profile.already_collected_count, 30, "profile tiles must keep post-scan snapshot captured during active collect");
  assert.equal(popupMetrics.profile.queue_count, 81, "profile tiles must keep post-scan snapshot queue during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "profile tiles must declare post-scan snapshot authority during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_ignore_inflight_progress, "yes", "profile tiles must ignore in-flight collect progress");
  assert.equal(popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_active_collect_job, "no", "post-scan snapshot must remain authoritative for profile tiles during active collect");
  assert.equal(popupMetrics.diagnostics.popup_metrics_snapshot_runtime_authority_blocked, "no", "active runtime must not block snapshot authority for profile tiles");
  assert.equal(popupMetrics.diagnostics.trace_counter_selected_source, "post_scan_counter_snapshot", "counter selection source must stay on post-scan snapshot for profile tiles");
  assert.equal(popupMetrics.diagnostics.popup_metrics_active_collect_runtime_job_id, "collect_job_split_brain_3r3b", "popup metrics diagnostics must still expose the active runtime job id");
  assert.equal(popupMetrics.diagnostics.popup_metrics_active_collect_runtime_state, "running", "popup metrics diagnostics must still expose the active runtime state");
  assert.equal(technicalRows["Collection status"], "running", "progress view technical rows must prefer the canonical runtime collection state during active collect");
  assert.equal(technicalRows["Collection state summary"], "running;queue=111;pending=111", "progress view collection summary must prefer the canonical runtime collection state during active collect");
  assert.equal(technicalRows["Primary action label"], "Collecting videos...", "progress view technical rows must keep the active collecting action label");
}

{
  const hybridCompletedDelayedRunningState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    status: "harvesting",
    phase: "harvesting",
    workflow: {
      ...authoritativeReconciliationFixtureState().workflow,
      collection: {
        ...authoritativeReconciliationFixtureState().workflow.collection,
        status: "running",
        started_at: "2026-05-06T12:00:00.000Z",
        updated_at: "2026-05-06T12:01:29.000Z",
        completed_at: null,
        last_error: null
      },
      active_task: "collect_videos",
      action_lock: "start_collecting"
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_hybrid_completed_delayed_running",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:29.000Z",
      heartbeat_at: "2026-05-06T12:01:29.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "after_backend_write",
      current_aweme_id: "700000000000000030",
      current_item_index: 30,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 10,
      succeeded_count: 10,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 30,
      pre_batch_queue: 81,
      lock_owner: "collect_job_hybrid_completed_delayed_running",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:02:30.000Z",
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 10,
      lock_released: false
    },
    active_collect_runtime: {
      ...authoritativeReconciliationFixtureState().active_collect_runtime,
      job_id: "collect_job_hybrid_completed_delayed_running",
      runtime_generation: 12,
      render_generation: 11,
      canonical_state: "running",
      canonical_phase: "collecting",
      current_step: "after_backend_write",
      current_aweme_id: "700000000000000030",
      current_item_index: 30,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 10,
      succeeded_count: 10,
      failed_count: 0,
      skipped_count: 0,
      pre_batch_backend_captured: 30,
      pre_batch_queue: 81,
      latest_progress_captured: 40,
      latest_progress_queue: 71,
      latest_progress_new: 71,
      heartbeat_at: "2026-05-06T12:01:29.000Z",
      lock_owner: "collect_job_hybrid_completed_delayed_running",
      lock_expires_at: "2026-05-06T12:02:30.000Z",
      last_update_source: "hybrid_readback.delayed_1500ms",
      trace: {
        ...authoritativeReconciliationFixtureState().active_collect_runtime.trace,
        summary: {
          trace_collect_popup_already_collected: 40,
          trace_collect_popup_queue: 71,
          trace_collect_popup_new: 71,
          trace_counter_selected_source: "active_collect_runtime"
        }
      },
      updated_at: "2026-05-06T12:01:29.000Z"
    },
    debug: {
      ...authoritativeReconciliationFixtureState().debug,
      last_response_summary: {
        ...(authoritativeReconciliationFixtureState().debug.last_response_summary as Record<string, unknown>),
        hybrid_collector_completed: "yes",
        hybrid_runner_backend_write_status: 200,
        hybrid_runner_write_ok_count: 10,
        hybrid_readback_immediate_collection_status: "idle",
        hybrid_readback_immediate_collect_job_state: "completed",
        hybrid_readback_immediate_runtime_canonical_state: "idle",
        hybrid_readback_delayed_1500ms_collection_status: "idle",
        hybrid_readback_delayed_1500ms_collect_job_state: "running",
        hybrid_readback_delayed_1500ms_runtime_canonical_state: "running"
      }
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(hybridCompletedDelayedRunningState, Date.parse("2026-05-06T12:01:30.000Z"));
  const popupMetrics = deriveReconciledPopupMetrics(hybridCompletedDelayedRunningState);
  const canonicalAction = getCanonicalScannerPrimaryAction(hybridCompletedDelayedRunningState);
  const mainVm = getDouyinScannerMainViewModel(hybridCompletedDelayedRunningState);
  const controlPanelVm = getScannerControlPanelViewModel(hybridCompletedDelayedRunningState);
  const progressView = getWholeProfileHarvestProgressViewModel(hybridCompletedDelayedRunningState);
  const technicalRows = Object.fromEntries(progressView.details.technical_rows.map((row) => [row.label, row.value]));

  assert.equal(runnerLock.active, false, "hybrid completion must release delayed stale running collect_job/runtime lock");
  assert.equal(runnerLock.source, "hybrid_collector_completed_override", "hybrid completion must be the authoritative stale-running override");
  assert.equal(canonicalAction.key, "start_collecting", "remaining eligible queue must show Start Collecting after hybrid completion");
  assert.equal(canonicalAction.enabled, true, "Start Collecting must not stay disabled after hybrid backend write completed");
  assert.notEqual(canonicalAction.label, "Collecting videos...", "stale active runtime must not keep the popup in Collecting videos state after hybrid completion");
  assert.notEqual(canonicalAction.disabledReason, "Wait for the current step to finish.", "hybrid completion must not render generic Action blocked wait text");
  assert.equal(popupMetrics.profile.already_collected_count, 30, "hybrid completion must prefer stable backend post-scan snapshot over stale delayed runtime counters");
  assert.equal(popupMetrics.profile.queue_count, 81, "hybrid completion must keep queue counters from the stable snapshot instead of stale runtime progress");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority, "post_scan_counter_snapshot", "post-scan snapshot must own popup tiles once hybrid completion is authoritative");
  assert.notEqual(popupMetrics.diagnostics.popup_metrics_active_collect_runtime_authoritative, "yes", "stale delayed runtime must not remain authoritative after hybrid completion");
  assert.notEqual(popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_active_collect_job, "yes", "post-scan snapshot must not be ignored after hybrid completion");
  assert.notEqual(mainVm.primary_action?.label, "Collecting videos...", "main scanner view must not show stale Collecting videos label after hybrid completion");
  assert.notEqual(mainVm.alert?.title, "Action blocked", "main scanner view must not show Action blocked after hybrid completion");
  assert.notEqual(controlPanelVm.emptyState, "Profile scan incomplete: expected 111, found 0, missing 111.", "control panel must not replace successful hybrid collect UX with a blocking scan-incomplete message");
  assert.notEqual(technicalRows["Primary action label"], "Collecting videos...", "progress technical rows must not preserve stale Collecting videos label after hybrid completion");
}

{
  const activeBatchProgressState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    status: "harvesting",
    phase: "stopped_after_one_item",
    harvest: {
      ...authoritativeReconciliationFixtureState().harvest,
      backend: {
        ...authoritativeReconciliationFixtureState().harvest.backend,
        one_item_flush: {
          ...authoritativeReconciliationFixtureState().harvest.backend.one_item_flush,
          status: "succeeded",
          capture_inbox_item_id: "legacy_one_item_1",
          verify_status: "verified",
          item_created_or_updated: true
        },
        batch_flush: {
          ...authoritativeReconciliationFixtureState().harvest.backend.batch_flush,
          status: "idle"
        }
      }
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_progress_quarantine_3r4g",
      state: "running",
      started_at: "2026-05-06T12:00:00.000Z",
      updated_at: "2026-05-06T12:01:00.000Z",
      heartbeat_at: "2026-05-06T12:01:00.000Z",
      runner_ack_at: "2026-05-06T12:00:01.000Z",
      current_step: "before_safe_delay",
      current_aweme_id: "7636339652122758434",
      current_item_index: 8,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 9,
      succeeded_count: 8,
      failed_count: 1,
      skipped_count: 0,
      lock_owner: "collect_job_progress_quarantine_3r4g",
      lock_acquired_at: "2026-05-06T12:00:00.000Z",
      lock_expires_at: "2026-05-06T12:01:45.000Z",
      lock_released: false
    },
    active_collect_runtime: {
      ...authoritativeReconciliationFixtureState().active_collect_runtime,
      job_id: "collect_job_progress_quarantine_3r4g",
      canonical_state: "running",
      canonical_phase: "collecting",
      current_step: "before_safe_delay",
      selected_count: 10,
      attempted_count: 9,
      succeeded_count: 8,
      failed_count: 1,
      skipped_count: 0,
      heartbeat_at: "2026-05-06T12:01:00.000Z"
    }
  };
  const progressSummary = wholeProfileProgressSummary(activeBatchProgressState);

  assert.equal(progressSummary.Status, "collecting", "active batch progress must ignore legacy harvesting status");
  assert.equal(progressSummary.Phase, "running", "active batch progress must suppress stopped_after_one_item phase");
  assert.match(progressSummary["One-item flush"] ?? "", /^quarantined during active batch/, "one-item flush must be quarantined during active batch");
  assert.equal(progressSummary["One-item flush ready"], "quarantined during active batch", "one-item readiness must be quarantined during active batch");
  assert.match(progressSummary["Batch flush"] ?? "", /^running · 9\/10 attempted · terminal 9\/10/, "batch flush must surface active batch job counters instead of idle");
  assert.equal(progressSummary["Batch flush ready"], "active batch runner owns flush", "batch flush readiness must identify active runner ownership");
}

{
  const waitingNowMs = Date.now();
  const waitingHeartbeatAt = new Date(waitingNowMs - 30_000).toISOString();
  const waitingStartedAt = new Date(waitingNowMs - 45_000).toISOString();
  const tabInactiveState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    profile_scan: {
      ...authoritativeReconciliationFixtureState().profile_scan,
      diagnostics: {
        ...(authoritativeReconciliationFixtureState().profile_scan.diagnostics && typeof authoritativeReconciliationFixtureState().profile_scan.diagnostics === "object" ? authoritativeReconciliationFixtureState().profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_tab_inactive_evidence: "active_tab_mismatch",
        trace_collect_target_tab_id: 101,
        trace_collect_active_tab_id: 202
      }
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_tab_inactive_3r3b",
      state: "running_tab_inactive",
      started_at: waitingStartedAt,
      updated_at: waitingStartedAt,
      heartbeat_at: waitingHeartbeatAt,
      runner_ack_at: new Date(waitingNowMs - 44_000).toISOString(),
      current_step: "after_safe_delay",
      current_aweme_id: "7636339652122758434",
      current_item_index: 8,
      batch_limit: 10,
      selected_count: 10,
      attempted_count: 0,
      succeeded_count: 0,
      failed_count: 0,
      skipped_count: 0,
      lock_owner: "collect_job_tab_inactive_3r3b",
      lock_acquired_at: waitingStartedAt,
      lock_expires_at: new Date(waitingNowMs + 60_000).toISOString(),
      recoverable: false,
      stale_reason: null,
      heartbeat_updates_count: 1,
      lock_released: false
    },
    active_collect_runtime: {
      ...authoritativeReconciliationFixtureState().active_collect_runtime,
      job_id: null,
      canonical_state: "idle",
      canonical_phase: null,
      heartbeat_at: null,
      updated_at: null
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(tabInactiveState, waitingNowMs);
  const waitingPanelVm = getScannerControlPanelViewModel(tabInactiveState);
  const waitingMainVm = getDouyinScannerMainViewModel(tabInactiveState);

  assert.equal(runnerLock.active, true, "soft-stale collect job with explicit tab inactivity evidence must stay duplicate-click blocked");
  assert.equal(runnerLock.source, "collect_job", "fresh inactive tab evidence must preserve the active collect-job source");
  assert.equal(runnerLock.diagnostics.trace_collect_waiting_for_active_tab_allowed, "yes", "waiting_for_active_tab is allowed only with explicit inactive tab evidence");
  assert.equal(runnerLock.diagnostics.trace_collect_tab_inactive_evidence, "active_tab_mismatch", "tab inactivity diagnostics must expose the proof source");
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "waiting_for_active_tab", "canonical state may become waiting_for_active_tab only when tab inactivity is proven");
  assert.equal(waitingPanelVm.headerStatus, "Waiting for tab", "scanner control panel must preserve waiting-for-active-tab wording");
  assert.equal(waitingMainVm.header_status, "Waiting for tab", "main scanner view must preserve waiting-for-active-tab wording");
  assert.equal(waitingMainVm.progress.label, "Waiting for tab", "main scanner progress label must preserve waiting-for-active-tab wording");
  assert.equal(waitingMainVm.progress.detail, "Return to the Douyin tab to continue collecting.", "waiting-for-active-tab progress detail must preserve the canonical resume hint");
}

{
  const startupState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    workflow: {
      ...authoritativeReconciliationFixtureState().workflow,
      active_task: null,
      action_lock: null,
      collection: { ...authoritativeReconciliationFixtureState().workflow.collection, status: "idle" }
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_starting_no_ack_1",
      state: "starting",
      started_at: "2026-05-06T12:01:20.000Z",
      updated_at: "2026-05-06T12:01:20.000Z",
      heartbeat_at: "2026-05-06T12:01:20.000Z",
      runner_ack_at: null,
      startup_deadline_at: "2026-05-06T12:01:30.000Z",
      startup_timeout_ms: 10_000,
      current_step: "starting",
      lock_owner: "collect_job_starting_no_ack_1",
      lock_acquired_at: "2026-05-06T12:01:20.000Z",
      lock_expires_at: "2026-05-06T12:01:30.000Z",
      lock_released: false,
      recoverable: false
    }
  };
  const staleViewState = {
    action: { key: "pause", buttonLabel: "Collecting videos...", enabled: false, disabledReason: "collection_running" as string | null },
    primary_action: { key: "pause", label: "Collecting videos...", enabled: false, reason: "collection_running" as string | null },
    counts: { newCount: 81, incompleteCount: 11, alreadyCollectedCount: 30, queueCount: 81 },
    compact_metrics: { pending: 81, saved: 30 },
    details: { technical_rows: [] as Array<{ label: string; value: string }> }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(startupState, Date.parse("2026-05-06T12:01:25.000Z"));
  const canonicalAction = getCanonicalScannerPrimaryAction(startupState);
  const panelVm = getScannerControlPanelViewModel(startupState);
  const mainVm = getDouyinScannerMainViewModel(startupState);
  const sanitized = sanitizePopupViewState(staleViewState, startupState);

  assert.equal(runnerLock.active, false, "starting collect job without runner ack must not create a running lock");
  assert.equal(runnerLock.diagnostics.trace_collect_startup_runner_ack_received, "no", "startup diagnostics must expose missing runner ack");
  assert.equal(runnerLock.diagnostics.trace_collect_startup_state, "waiting_for_runner_ack", "startup diagnostics must expose waiting-for-ack state before timeout");
  assert.equal(runnerLock.diagnostics.trace_collect_ui_state, "start_recoverable", "startup-only state must render as start/retry recoverable, not collecting");
  assert.equal(runnerLock.diagnostics.trace_ui_contradiction_detected, "no_collecting_without_runner_ack", "diagnostics must flag attempted collecting UI without runner ack");
  assert.notEqual(canonicalAction.label, "Collecting videos...", "canonical action must not claim collecting before runner ack");
  assert.notEqual(panelVm.action.buttonLabel, "Collecting videos...", "panel VM must not claim collecting before runner ack");
  assert.notEqual(mainVm.primary_action?.label, "Collecting videos...", "main VM must not claim collecting before runner ack");
  assert.notEqual(sanitized.action.buttonLabel, "Collecting videos...", "sanitizer must remove stale collecting label before runner ack");
  assert.equal(sanitized.action.enabled, true, "sanitizer must leave Start/Retry available before runner ack");
}

{
  const startupTimedOutState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_starting_timeout_1",
      state: "starting",
      started_at: "2026-05-06T12:01:20.000Z",
      updated_at: "2026-05-06T12:01:20.000Z",
      heartbeat_at: "2026-05-06T12:01:20.000Z",
      runner_ack_at: null,
      startup_deadline_at: "2026-05-06T12:01:30.000Z",
      startup_timeout_ms: 10_000,
      current_step: "starting",
      lock_owner: "collect_job_starting_timeout_1",
      lock_acquired_at: "2026-05-06T12:01:20.000Z",
      lock_expires_at: "2026-05-06T12:01:30.000Z",
      lock_released: false,
      recoverable: false
    }
  };
  const runnerLock = deriveAuthoritativeRunnerLock(startupTimedOutState, Date.parse("2026-05-06T12:01:35.000Z"));

  assert.equal(runnerLock.active, false, "startup timeout without runner ack must not keep Start Collecting blocked");
  assert.equal(runnerLock.diagnostics.trace_collect_startup_state, "startup_timeout", "startup timeout diagnostics must be explicit");
  assert.equal(runnerLock.diagnostics.trace_ui_primary_action, "start_or_retry_available", "startup timeout must expose retry availability");
}

{
  const regressiveStartupState: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAAfixture",
      scanned_total: 111,
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 111,
      need_retry: 0,
      new: 111,
      queue: 111,
      backend_captured_aweme_ids: [],
      applied_at: "2026-05-06T12:01:00.000Z"
    },
    collect_job: {
      ...authoritativeReconciliationFixtureState().collect_job,
      job_id: "collect_job_start_failed_counter_guard_1",
      state: "start_failed_recoverable",
      started_at: "2026-05-06T12:01:20.000Z",
      updated_at: "2026-05-06T12:01:31.000Z",
      heartbeat_at: "2026-05-06T12:01:31.000Z",
      runner_ack_at: null,
      startup_deadline_at: "2026-05-06T12:01:30.000Z",
      startup_timeout_ms: 10_000,
      current_step: "startup_failed",
      last_error: "collect_runner_not_started",
      failure_reason: "collect_runner_not_started",
      lock_owner: null,
      lock_expires_at: null,
      lock_released: true,
      recoverable: true
    }
  };
  const popupMetrics = deriveReconciledPopupMetrics(regressiveStartupState);
  const progressVm = getWholeProfileHarvestProgressViewModel(regressiveStartupState);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(popupMetrics.profile.already_collected_count, 30, "startup/recovery counter guard must not regress verified backend captured count to zero");
  assert.equal(popupMetrics.profile.queue_count, 81, "startup/recovery counter guard must keep verified backend queue count instead of stale post-scan queue");
  assert.equal(popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_startup_recovery, "yes", "counter diagnostics must expose ignored regressive startup snapshot");
  assert.equal(popupMetrics.diagnostics.popup_metrics_counter_authority_monotonic_guard, "verified_backend_snapshot", "counter diagnostics must expose monotonic backend authority");
  assert.equal(technicalValue("Profile already collected count"), "30", "advanced diagnostics must render guarded backend captured count");
}

{
  const state = requestOnlyStartCollectingTraceFixtureState();
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const collectTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_COLLECT_PIPELINE_TRACE")?.value ?? "{}");
  assert.equal(collectTrace.batch_start.trace_collect_popup_route_hit, "yes", "post-collect trace must surface popup route hit even before controller response summary updates");
  assert.equal(collectTrace.batch_start.trace_collect_controller_entry_hit, "no", "post-collect trace must distinguish popup-only dispatch from controller entry");
  assert.equal(collectTrace.batch_start.trace_collect_batch_runner_entry_hit, "no", "post-collect trace must distinguish popup-only dispatch from batch runner entry");
  assert.equal(collectTrace.batch_start.trace_collect_started, "no", "post-collect trace must not claim batch collection started from popup-only diagnostics");
}

{
  const state = controllerExitBeforeBatchTraceFixtureState();
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const collectTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_COLLECT_PIPELINE_TRACE")?.value ?? "{}");
  assert.equal(collectTrace.batch_start.trace_collect_controller_entry_hit, "yes", "post-collect trace must show controller entry before an early exit");
  assert.equal(collectTrace.batch_start.trace_collect_batch_runner_entry_hit, "no", "post-collect trace must show the batch runner was not entered after controller early exit");
  assert.equal(collectTrace.batch_start.trace_collect_started, "no", "post-collect trace must not claim collection started after controller early exit");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_before_batch_runner, "yes", "post-collect trace must expose controller exit before batch runner");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_stage, "calibration_ready", "post-collect trace must expose the exact controller exit stage");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_reason, "Calibrate 4 Points first.", "post-collect trace must expose the exact controller exit reason");
  assert.equal(collectTrace.batch_start.trace_collect_preflight_result, "blocked", "post-collect trace must expose blocked preflight result");
  assert.equal(collectTrace.batch_start.trace_collect_blocked_reason, "Calibrate 4 Points first.", "post-collect trace must expose blocked reason");
  assert.equal(collectTrace.batch_start.trace_collect_runtime_open_direct_modal_present, "yes", "post-collect trace must expose runtime openDirectModal capability");
  assert.equal(collectTrace.batch_start.trace_collect_runtime_extract_modal_metrics_present, "yes", "post-collect trace must expose runtime extractModalMetrics capability");
}

{
  const state = authoritativeReconciliationFixtureState();
  const staleBuildingPayloadState: WholeProfileHarvestState = {
    ...state,
    debug: {
      ...state.debug,
      last_request_summary: {
        start_collecting_controller_entry_hit: true,
        start_collecting_controller_entered_at: "2026-05-06T12:13:00.000Z",
        start_collecting_stage: "clicked",
        start_collecting_controller_exit_before_batch_runner: false
      },
      last_response_summary: {
        start_collecting_stage: "building_payload",
        last_scanner_result: "building_payload",
        collect_batch_runner_entry_hit: false,
        batch_runner_called: false
      }
    }
  };
  const progressVm = getWholeProfileHarvestProgressViewModel(staleBuildingPayloadState);
  const collectTrace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_COLLECT_PIPELINE_TRACE")?.value ?? "{}");
  assert.equal(collectTrace.batch_start.trace_collect_controller_entry_hit, "yes", "stale building_payload trace must still show controller entry");
  assert.equal(collectTrace.batch_start.trace_collect_batch_runner_entry_hit, "no", "stale building_payload trace must still show no batch runner entry");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_before_batch_runner, "no", "stale building_payload trace must not invent a controller exit without the explicit exit flag");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_stage, null, "stale building_payload trace must not present item-stage building_payload as a controller exit stage");
  assert.equal(collectTrace.batch_start.trace_collect_controller_exit_reason, null, "stale building_payload trace must not present a null-reason controller exit");
}

{
  const state: WholeProfileHarvestState = {
    ...authoritativeReconciliationFixtureState(),
    post_scan_counter_snapshot: null,
    debug: { ...authoritativeReconciliationFixtureState().debug, last_request_summary: {}, last_response_summary: {} },
    profile_scan: { ...authoritativeReconciliationFixtureState().profile_scan, diagnostics: {} },
    verify: { ...authoritativeReconciliationFixtureState().verify, diagnostics: {} }
  };
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const trace = JSON.parse(progressVm.details.technical_rows.find((row) => row.label === "POST_SCAN_COUNTER_PIPELINE_TRACE")?.value ?? "{}");
  assert.equal(trace.backend_summary_request.trace_backend_summary_called, "no", "post-scan pipeline trace must show backend_summary_called=no when no backend summary call diagnostics exist");
  assert.equal(trace.snapshot_state.trace_counter_snapshot_exists, "no", "post-scan pipeline trace must show missing snapshot when no snapshot exists");
}

{
  const base = authoritativeReconciliationFixtureState();
  const state: WholeProfileHarvestState = {
    ...base,
    profile_scan: {
      ...base.profile_scan,
      diagnostics: {
        ...(base.profile_scan.diagnostics && typeof base.profile_scan.diagnostics === "object" ? base.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_stop_authoritative: "runtime_debug_must_not_drive_stop",
        scan_stop: "runtime_debug_must_not_drive_stop"
      }
    },
    verify: {
      ...base.verify,
      stop_reason: "legacy_verify_stop_reason",
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_stop_authoritative: "network_post_has_more_false",
        scan_stop: "legacy_scan_stop_must_not_drive_ui",
        canonical_scanner_stop_reason: "legacy_canonical_stop_must_not_drive_ui"
      }
    },
    debug: {
      ...base.debug,
      last_response_summary: {
        ...(base.debug.last_response_summary && typeof base.debug.last_response_summary === "object" ? base.debug.last_response_summary as Record<string, unknown> : {}),
        scanStop: "legacy_scanStop_must_not_drive_ui",
        scan_stop: "legacy_debug_scan_stop_must_not_drive_ui",
        canonical_scanner_stop_reason: "legacy_debug_canonical_stop_must_not_drive_ui"
      }
    }
  };
  const progressVm = getWholeProfileHarvestProgressViewModel(state);
  const progressSummary = wholeProfileProgressSummary(state);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(progressSummary["Stop reason"], "network_post_has_more_false", "progress summary stop reason must prefer scan_authority_diagnostics authoritative stop and ignore runtime_debug_diagnostics");
  assert.equal(technicalValue("Scan stop"), "network_post_has_more_false", "advanced diagnostics scan stop must prefer scan_authority_diagnostics authoritative stop and ignore runtime_debug_diagnostics");
}

{
  const state = authoritativeReconciliationFixtureState();
  const staleViewState = {
    action: { key: "start_collecting", buttonLabel: "Start Collecting", enabled: true, disabledReason: null as string | null },
    primary_action: { key: "start_collecting", label: "Start Collecting", enabled: true, reason: null as string | null },
    counts: { newCount: 108, incompleteCount: 1, alreadyCollectedCount: 0, queueCount: 101 },
    compact_metrics: { pending: 101, saved: 0 },
    details: { technical_rows: [{ label: "Profile already collected count", value: "0" }, { label: "Profile eligible count", value: "101" }] }
  };
  const activeState = {
    ...state,
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_run_id: "batch_run_authoritative_sanitize",
        batch_heartbeat_at: new Date().toISOString()
      }
    }
  };
  const sanitized = sanitizePopupViewState(staleViewState, activeState);

  assert.equal(sanitized.action.key, "pause", "sanitizer must correct stale start_collecting action while runner lock is active");
  assert.equal(sanitized.action.buttonLabel, "Collecting videos...", "sanitizer must correct stale Start Collecting label while runner lock is active");
  assert.equal(sanitized.action.enabled, false, "sanitizer must disable stale Start Collecting action while runner lock is active");
  assert.equal(sanitized.primary_action?.label, "Collecting videos...", "sanitizer must correct stale primary action label before render");
  assert.equal(sanitized.counts.newCount, 81, "sanitizer must correct stale New count from backend verification authority");
  assert.equal(sanitized.counts.alreadyCollectedCount, 30, "sanitizer must correct stale already-collected zero from backend verification authority");
  assert.equal(sanitized.counts.queueCount, 81, "sanitizer must correct stale pending count from backend verification authority");
  assert.equal(sanitized.details.technical_rows.find((row) => row.label === "Profile already collected count")?.value, "30", "sanitizer must correct stale technical already-collected row");
  assert.equal(sanitized.diagnostics?.duplicate_start_suppressed, undefined, "view sanitizer must not mark duplicate click suppression unless click handler suppressed dispatch");
  assert.equal(sanitized.diagnostics?.primary_action_locked_reason, "collection_running", "view sanitizer must export authoritative primary action lock reason");
}

{
  const state = authoritativeReconciliationFixtureState();
  const panelVm = getScannerControlPanelViewModel(state);
  const mainVm = getDouyinScannerMainViewModel(state);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;

  assert.equal(panelVm.counts.newCount, 81, "scanner panel New tile must use final reconciled profile metrics instead of raw target_status.new 108");
  assert.equal(panelVm.counts.incompleteCount, 11, "scanner panel Incomplete tile must use backend Capture Inbox card captured-ready-dup-fail");
  assert.equal(panelVm.counts.failedCount, 0, "scanner panel Need retry tile must use backend Capture Inbox card fail count");
  assert.equal(panelVm.counts.alreadyCollectedCount, 30, "scanner panel already-collected tile must use backend reconciliation");
  assert.equal(panelVm.counts.queueCount, 81, "scanner panel Queue tile must use final reconciled profile metrics");
  assert.equal(statValue("New"), "81", "main scanner New tile must use final reconciled profile metrics instead of raw target_status.new 108");
  assert.equal(statValue("Queued"), "81", "main scanner Queued tile must use final reconciled profile metrics instead of raw pending 109");
  assert.equal(deriveReconciledPopupMetrics(state).diagnostics.popup_metrics_raw_pending_ignored_for_profile_tiles, true, "main scanner metrics authority must state raw pending was ignored for profile tiles");
}

{
  const state = authoritativeReconciliationFixtureState();
  const activeState: WholeProfileHarvestState = {
    ...state,
    workflow: {
      ...state.workflow,
      active_task: "collect_videos",
      action_lock: "collect_videos",
      collection: {
        ...state.workflow.collection,
        status: "running",
        updated_at: new Date().toISOString()
      }
    },
    harvest: {
      ...state.harvest,
      current_index: 3,
      updated: 2
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        batch_collection_ui_state: "collecting_videos_locked",
        batch_heartbeat_at: new Date().toISOString(),
        active_runner_current_index: 3,
        active_runner_saved_this_run: 2,
        pending_count: 109,
        profile_batch_pending_count: 111
      }
    }
  };
  const mainVm = getDouyinScannerMainViewModel(activeState);
  const popupMetrics = deriveReconciledPopupMetrics(activeState);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;

  assert.equal(mainVm.primary_action?.label, "Collecting videos...", "active collection primary action must remain collecting label");
  assert.equal(mainVm.primary_action?.enabled, false, "active collection primary action must suppress duplicate dispatch");
  assert.equal(statValue("New"), "81", "active collection must not let raw pending replace profile-level New");
  assert.equal(statValue("Queued"), "81", "active collection must not let raw pending replace profile-level Queue");
  assert.equal(popupMetrics.active_runner.active_runner_remaining_count, 109, "active runner pending may remain available only as active-runner remaining");
  assert.equal(popupMetrics.active_runner.active_runner_current_index, 3, "active runner current index must be separated from profile metrics");
  assert.equal(popupMetrics.active_runner.active_runner_saved_this_run, 2, "active runner saved-this-run must be separated from profile metrics");
}

{
  const state = authoritativeReconciliationFixtureState();
  const queue = state.harvest.queue;
  const completedState: WholeProfileHarvestState = {
    ...state,
    phase: "batch_safe_mode_completed",
    status: "verified",
    harvest: {
      ...state.harvest,
      failed: 0
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        verify_response: {
          counts: { captured: 40, ready: 71, needs_action: 0 },
          items_count: 40,
          items: queue.slice(0, 40).map((item, index) => ({ id: `backend_complete_${index}`, aweme_id: item.aweme_id }))
        }
      }
    }
  };
  const panelVm = getScannerControlPanelViewModel(completedState);
  const mainVm = getDouyinScannerMainViewModel(completedState);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;

  assert.equal(panelVm.counts.newCount, 71, "completed batch New tile must update from latest backend authority");
  assert.equal(panelVm.counts.queueCount, 71, "completed batch Queue tile must update from latest backend authority");
  assert.equal(statValue("New"), "71", "completed batch main New tile must update from latest backend authority");
  assert.equal(statValue("Queued"), "71", "completed batch main Queue tile must update from latest backend authority");
  assert.equal(panelVm.action.buttonLabel, "Continue Next 10", "completed batch with remaining queue must show Continue Next 10");
  assert.equal(mainVm.primary_action?.label, "Continue Next 10", "completed batch main action must show Continue Next 10");
}

{
  const state = authoritativeReconciliationFixtureState();
  const queue = state.harvest.queue.slice(0, 100);
  const largeProfileState: WholeProfileHarvestState = {
    ...state,
    target_status: { ...state.target_status, new: 100, incomplete: 0, complete: 0, unknown: 0 },
    harvest: {
      ...state.harvest,
      queue,
      queue_preview: queue.map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })),
      pending: 100,
      planned_total: 983
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 983,
        queue_total_visible: 100,
        queue_counter_authority: "queue_total_persisted",
        profile_queue_total_count: 983,
        profile_batch_pending_count: 983
      }
    },
    verify: {
      ...state.verify,
      diagnostics: {
        ...(state.verify.diagnostics && typeof state.verify.diagnostics === "object" ? state.verify.diagnostics as Record<string, unknown> : {}),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 983,
        queue_total_visible: 100,
        queue_counter_authority: "queue_total_persisted",
        profile_queue_total_count: 983,
        profile_batch_pending_count: 983
      }
    }
  };
  const panelVm = getScannerControlPanelViewModel(largeProfileState);
  const mainVm = getDouyinScannerMainViewModel(largeProfileState);
  const progressVm = getWholeProfileHarvestProgressViewModel(largeProfileState);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(panelVm.counts.newCount, 983, "large profile New tile must use persisted queue total instead of visible preview window");
  assert.equal(panelVm.counts.queueCount, 983, "large profile Queue tile must use persisted queue total instead of visible preview window");
  assert.equal(statValue("New"), "983", "large profile main New stat must use persisted queue total");
  assert.equal(statValue("Queued"), "983", "large profile main Queued stat must use persisted queue total");
  assert.equal(technicalValue("Queue counter authority"), "queue_total_persisted", "large profile diagnostics must expose persisted queue counter authority");
  assert.equal(technicalValue("Preview window"), "100", "large profile diagnostics must expose visible preview window separately");
}

{
  const state = authoritativeReconciliationFixtureState();
  const queue = state.harvest.queue.slice(0, 100);
  const stableState: WholeProfileHarvestState = {
    ...state,
    updated_at: "2026-05-06T12:30:00.000Z",
    workflow: {
      ...state.workflow,
      active_task: "scan_profile",
      action_lock: "scan_profile",
      scan: { ...state.workflow.scan, status: "running" }
    },
    scan_job: {
      ...state.scan_job,
      scan_job_id: "scan_run_stable_1",
      status: "running",
      profile_identifier: "MS4wLjABAAAAfixture",
      page_count: 9,
      request_count: 12,
      has_more_state: true,
      last_status_code: 0,
      total_discovered: 989,
      total_persisted: 989,
      expected_count: 1000,
      remaining_estimate: 11
    },
    harvest: {
      ...state.harvest,
      queue,
      queue_preview: queue.map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })),
      pending: 100,
      planned_total: 989
    },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        ...(state.profile_scan.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 989,
        queue_total_visible: 100,
        profile_queue_total_count: 989
      }
    },
    verify: {
      ...state.verify,
      diagnostics: {
        ...(state.verify.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 989,
        queue_total_visible: 100,
        profile_queue_total_count: 989
      }
    },
    debug: {
      ...state.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_run_id: "scan_run_stable_1",
        scan_progress_discovered: 989,
        scan_progress_expected: 1000,
        scan_progress_remaining: 11,
        scan_progress_pages: 9,
        scan_progress_requests: 12,
        scan_progress_status_code: 0,
        scan_progress_phase_label: "Scanning profile",
        popup_counter_authority_selected: "scan_job_total_persisted",
        popup_counter_authority_previous: "post_scan_counter_snapshot",
        popup_counter_authority_switch_blocked_stale: "yes",
        popup_counter_authority_reason: "blocked_stale_state_version",
        popup_counter_state_version: "2026-05-06T12:30:00.000Z",
        popup_counter_authority_total: 989,
        popup_active_scan_run_id: "scan_run_stable_1",
        popup_render_scan_run_id: "scan_run_stable_1",
        popup_render_dropped_stale_run_update: "no",
        popup_render_profile_switch_detected: "no"
      }
    }
  };
  const panelVm = getScannerControlPanelViewModel(stableState);
  const mainVm = getDouyinScannerMainViewModel(stableState);
  const progressVm = getWholeProfileHarvestProgressViewModel(stableState);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(panelVm.headerStatus, "Scanning 989 / 1000", "active scan header must show progress count with expected context");
  assert.equal(panelVm.scanProgress.active, true, "running scan must expose active scan progress model");
  assert.equal(panelVm.scanProgress.discovered, 989, "running scan progress must use discovered progress authority");
  assert.equal(panelVm.scanProgress.expected, 1000, "running scan progress must expose expected count separately");
  assert.equal(panelVm.emptyState, "Scanning profile videos... Progress is still updating.", "active scan must show neutral progress copy instead of final incomplete warning");
  assert.match(panelVm.scanProgress.detail, /API pagination is running/, "active scan copy must say the scan is API pagination rather than visible page scrolling");
  assert.notEqual(mainVm.alert?.title, "Profile scan incomplete", "active scan must not render final incomplete warning");
  assert.equal(mainVm.alert?.title, "Scanning profile videos", "active scan must render neutral scan-progress alert");
  assert.equal(mainVm.progress.label, "Scanning profile videos", "main progress label must identify active scan progress");
  assert.equal(mainVm.progress.value, "989/1000", "main progress value must show active discovered/expected count");
  assert.equal(technicalValue("popup_counter_authority_selected"), "scan_job_total_persisted", "advanced rows must expose selected popup counter authority");
  assert.equal(technicalValue("popup_counter_authority_previous"), "post_scan_counter_snapshot", "advanced rows must expose previous popup counter authority");
  assert.equal(technicalValue("popup_counter_authority_switch_blocked_stale"), "yes", "advanced rows must expose stale switch blocking");
  assert.equal(technicalValue("popup_counter_state_version"), "2026-05-06T12:30:00.000Z", "advanced rows must expose popup state version");
  assert.equal(technicalValue("Pages fetched"), "9", "fast progress rows must expose pages fetched");
  assert.equal(technicalValue("Request count"), "12", "fast progress rows must expose request count");
  assert.equal(technicalValue("Has more"), "true", "fast progress rows must expose has-more state");
  assert.equal(technicalValue("Persisted total"), "989", "fast progress rows must expose persisted total authority");
  assert.equal(technicalValue("Expected"), "1000", "fast progress rows must expose expected count");
  assert.equal(technicalValue("Remaining estimate"), "11", "fast progress rows must expose remaining estimate");
  assert.equal(technicalValue("Last status code"), "0", "fast progress rows must expose last status code");
  assert.equal(progressVm.cards.profile.title, "Scan progress", "running scan must show dedicated scan progress card");
  assert.equal(progressVm.cards.profile.summary, "Scanning profile", "running scan progress card must expose phase label");
  assert.equal(progressVm.cards.profile.metrics.find((metric) => metric.label === "Discovered so far")?.value, "989", "scan progress card must show discovered authority");
  assert.equal(progressVm.cards.profile.metrics.find((metric) => metric.label === "Expected")?.value, "1000", "scan progress card must show expected authority");
  assert.equal(progressVm.cards.profile.metrics.find((metric) => metric.label === "Remaining estimate")?.value, "11", "scan progress card must show remaining estimate");
  assert.equal(progressVm.cards.profile.metrics.find((metric) => metric.label === "Pages / requests")?.value, "9 / 12", "scan progress card must show pages and requests");
  assert.equal(technicalValue("Scan progress panel"), "active", "technical rows must expose active scan progress panel mode");
  assert.equal(technicalValue("scan_progress_discovered"), "989", "technical rows must expose scan_progress_discovered");
  assert.equal(technicalValue("scan_progress_expected"), "1000", "technical rows must expose scan_progress_expected");
  assert.equal(technicalValue("scan_progress_remaining"), "11", "technical rows must expose scan_progress_remaining");
  assert.equal(technicalValue("scan_progress_pages"), "9", "technical rows must expose scan_progress_pages");
  assert.equal(technicalValue("scan_progress_requests"), "12", "technical rows must expose scan_progress_requests");
  assert.equal(technicalValue("scan_progress_status_code"), "0", "technical rows must expose scan_progress_status_code");
  assert.equal(technicalValue("scan_progress_phase_label"), "Scanning profile", "technical rows must expose scan_progress_phase_label");
  assert.equal(technicalValue("Queue total snapshot"), "989", "queue total snapshot row must map to persisted authority during scan");
  assert.equal(technicalValue("Preview window snapshot"), "100", "preview snapshot row must stay separate from total during scan");
  assert.equal(technicalValue("Displaying first N preview items"), "100", "displaying-first row must clarify preview size during scan");
  assert.match(progressVm.details.queue_preview_label, /preview\/state snapshot/, "queue preview label must make in-progress snapshot status explicit");
}

{
  const base = authoritativeReconciliationFixtureState();
  const queue = base.harvest.queue.slice(0, 100);
  const activeState: WholeProfileHarvestState = {
    ...base,
    phase: "scan_running",
    workflow: { ...base.workflow, active_task: "scan_profile", action_lock: "scan_profile", scan: { ...base.workflow.scan, status: "running" } },
    scan_job: { ...base.scan_job, scan_job_id: "scan_run_truthful_progress", status: "running", page_count: 50, request_count: 50, has_more_state: true, last_status_code: 0, total_discovered: 996, total_persisted: 991, expected_count: 996, remaining_estimate: 5 },
    harvest: { ...base.harvest, queue, queue_preview: queue.map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })), pending: 100, planned_total: 991 },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 991,
        queue_total_visible: 100,
        profile_queue_total_count: 991,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_fetch_stop_reason: "active_profile_post_response_status_non_zero",
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no"
      }
    },
    verify: { ...base.verify, diagnostics: { diagnostics_channel: "scan_authority_diagnostics", large_profile_mode: "yes", queue_total_persisted: 991, queue_total_visible: 100, profile_queue_total_count: 991 } },
    debug: {
      ...base.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_run_id: "scan_run_truthful_progress",
        scan_progress_discovered: 996,
        scan_progress_expected: 996,
        scan_job_total_discovered: 996,
        scan_job_total_persisted: 991,
        scan_progress_pages: 50,
        scan_progress_requests: 50,
        scan_progress_phase_label: "Scanning profile"
      }
    }
  };
  const panelVm = getScannerControlPanelViewModel(activeState);
  const mainVm = getDouyinScannerMainViewModel(activeState);

  assert.equal(panelVm.scanProgress.active, true, "running scan must expose progress");
  assert.equal(panelVm.scanProgress.discovered, 996, "active scan progress must follow current-run authority rather than persisted repository totals");
  assert.equal(panelVm.scanProgress.expected, 996, "active scan progress must keep expected separate");
  assert.equal(panelVm.headerStatus, "Scanning 996 / 996", "active scan header must reflect current-run authority while the scan is active");
  assert.equal(panelVm.primaryAction.key, "scan_profile", "active scan must keep Scan Profile as the current primary action");
  assert.equal(panelVm.primaryAction.title, "Scanning Profile", "active scan primary action title must be normalized to the running state");
  assert.equal(panelVm.primaryAction.label, "Scanning...", "active scan primary action label must be normalized to the running state");
  assert.equal(panelVm.primaryAction.enabled, false, "active scan primary action must be non-reentrant");
  assert.equal(panelVm.primaryAction.disabledReason, null, "active scan progress must suppress stale source-failure disabled reasons in the view model");
  assert.equal(panelVm.action.buttonLabel, "Scanning...", "active scan action button label must be normalized to the running state");
  assert.equal(panelVm.action.disabledReason, null, "active scan action must not leak stale source-failure disabled reasons");
  assert.equal(mainVm.progress.value, "996/996", "main scan progress value must follow active current-run authority");
}

{
  const base = authoritativeReconciliationFixtureState();
  const terminalState: WholeProfileHarvestState = {
    ...base,
    phase: "scan_finished",
    workflow: {
      ...base.workflow,
      active_task: "scan_profile",
      action_lock: "scan_profile",
      scan: { ...base.workflow.scan, status: "success" }
    },
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_terminal_stale_progress",
      status: "completed",
      page_count: 50,
      request_count: 50,
      total_discovered: 990,
      total_persisted: 990,
      expected_count: 995,
      remaining_estimate: 5
    },
    profile_scan: {
      ...base.profile_scan,
      status: "success",
      accepted_target_count: 990,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_run_id: "scan_run_terminal_stale_progress",
        scan_finalization_result: "completed_with_warning",
        expected_profile_video_count: 995,
        queue_total_persisted: 990,
        active_profile_post_fetch_page_count: 50,
        active_profile_post_fetch_request_count: 50
      }
    },
    verify: { ...base.verify, status: "success", verified_target_count: 990, accepted_target_count: 990 },
    debug: {
      ...base.debug,
      last_response_summary: {
        diagnostics_channel: "runtime_debug_diagnostics",
        scan_run_id: "scan_run_terminal_stale_progress",
        scan_progress_discovered: 60,
        scan_progress_expected: 995,
        scan_progress_pages: 0,
        scan_progress_requests: 0,
        scan_progress_phase_label: "Scanning profile videos",
        popup_progress_active_rendered: "no",
        popup_progress_render_source: "terminal_scan_state",
        popup_progress_render_run_id: "scan_run_terminal_stale_progress",
        popup_progress_render_discovered: "none",
        popup_progress_render_expected: "none",
        popup_progress_render_pages: "none",
        popup_progress_render_requests: "none",
        popup_progress_cleared_after_terminal: "yes",
        popup_progress_stale_ignored_reason: "terminal_scan_state"
      }
    }
  };
  const panelVm = getScannerControlPanelViewModel(terminalState);
  const mainVm = getDouyinScannerMainViewModel(terminalState);
  const progressVm = getWholeProfileHarvestProgressViewModel(terminalState);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(panelVm.scanProgress.active, false, "terminal scan must clear stale active scan progress even when workflow locks are stale");
  assert.notEqual(panelVm.headerStatus, "Scanning 60 / 995", "terminal scan header must not render stale active progress counts");
  assert.notEqual(panelVm.emptyState, "Scanning profile videos... Progress is still updating.", "terminal scan must not keep active progress copy");
  assert.notEqual(mainVm.progress.value, "60/995", "main progress must not use stale runtime progress after terminal finalization");
  assert.equal(technicalValue("Scan progress panel"), "inactive", "technical rows must show inactive scan progress panel after terminal state");
  assert.equal(technicalValue("scan_progress_discovered"), "none", "terminal diagnostics must ignore stale runtime scan_progress_discovered");
  assert.equal(technicalValue("scan_progress_pages"), "none", "terminal diagnostics must ignore stale runtime scan_progress_pages");
  assert.equal(technicalValue("popup_progress_active_rendered"), "no", "popup diagnostics must expose that active progress was not rendered");
  assert.equal(technicalValue("popup_progress_cleared_after_terminal"), "yes", "popup diagnostics must expose terminal progress clearing");
  assert.equal(technicalValue("popup_progress_stale_ignored_reason"), "terminal_scan_state", "popup diagnostics must explain stale progress rejection");
}

{
  const base = authoritativeReconciliationFixtureState();
  const queue = base.harvest.queue.slice(0, 100);
  const nearCompleteState: WholeProfileHarvestState = {
    ...base,
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_warning_1",
      status: "completed",
      has_more_state: false,
      last_status_code: 0,
      total_persisted: 983,
      expected_count: 984,
      remaining_estimate: 1
    },
    harvest: {
      ...base.harvest,
      queue,
      queue_preview: queue.map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })),
      planned_total: 983
    },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: {
        ...(base.profile_scan.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 983,
        queue_total_visible: 100,
        profile_queue_total_count: 983
      }
    },
    verify: {
      ...base.verify,
      diagnostics: {
        ...(base.verify.diagnostics as Record<string, unknown>),
        diagnostics_channel: "scan_authority_diagnostics",
        large_profile_mode: "yes",
        queue_total_persisted: 983,
        queue_total_visible: 100,
        profile_queue_total_count: 983
      }
    },
    debug: { ...base.debug, last_response_summary: { diagnostics_channel: "runtime_debug_diagnostics", popup_counter_authority_selected: "scan_job_total_persisted", popup_counter_authority_total: 983 } }
  };
  const mainVm = getDouyinScannerMainViewModel(nearCompleteState);
  const progressVm = getWholeProfileHarvestProgressViewModel(nearCompleteState);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;

  assert.equal(mainVm.alert?.title, "Scan completed with warning", "tiny terminal expected gap must use warning-complete UI title instead of incomplete failure wording");
  assert.match(mainVm.alert?.message ?? "", /Scan completed with warning: found 983 of 984/, "warning message must report truthful persisted vs expected counts");
  assert.match(mainVm.alert?.message ?? "", /unavailable, hidden, deleted, filtered, or not returned by Douyin/, "warning message must explain plausible non-blocking gap causes");
  assert.doesNotMatch(mainVm.alert?.message ?? "", /Profile scan incomplete/, "completed_with_warning must not use blocking incomplete wording");
  assert.equal(technicalValue("popup_near_complete_warning_applied"), "yes", "near-complete diagnostics must show UI warning applied");
  assert.equal(technicalValue("popup_near_complete_gap_count"), "1", "near-complete diagnostics must expose gap count");
  assert.equal(technicalValue("popup_near_complete_threshold_used"), "10", "near-complete diagnostics must expose max of count and 1 percent threshold");
}

{
  const base = authoritativeReconciliationFixtureState();
  const mixedState: WholeProfileHarvestState = {
    ...base,
    status: "failed",
    scan_job: {
      ...base.scan_job,
      scan_job_id: "scan_run_status_5_mixed",
      status: "failed",
      page_count: 1,
      request_count: 4,
      retry_count: 4,
      last_status_code: 5,
      last_error: "active_profile_post_response_status_non_zero_terminal",
      total_discovered: 0,
      total_persisted: 953,
      expected_count: 1000
    },
    profile_scan: {
      ...base.profile_scan,
      status: "failed",
      accepted_target_count: 0,
      targets: [],
      target_details: [],
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 1000,
        large_profile_mode: "yes",
        queue_total_persisted: 953,
        active_profile_post_fetch_response_status_code: 5,
        active_profile_post_fetch_stop_reason: "active_profile_post_response_status_non_zero",
        active_profile_post_template_found: "no",
        active_profile_post_template_required_query_keys_available: "no",
        expected_count_gate_meaningful_active_fetch: "no",
        expected_count_gate_dom_only_convergence_allowed: "no",
        current_run_found_count: 0,
        persisted_total_count: 953
      }
    },
    verify: { ...base.verify, status: "failed", verified_target_count: 0, accepted_target_count: 0, targets: [], target_details: [] }
  };
  const staleResumeActiveState: WholeProfileHarvestState = {
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
      scan_job_id: "scan_run_stale_resume_current_run_authority",
      status: "running",
      page_count: 3,
      request_count: 3,
      last_status_code: 0,
      last_error: null,
      total_discovered: 953,
      total_persisted: 953,
      has_more_state: true,
      expected_count: 1000
    },
    profile_scan: {
      ...base.profile_scan,
      status: "running",
      accepted_target_count: 0,
      targets: [],
      target_details: [],
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        expected_profile_video_count: 1000,
        large_profile_mode: "yes",
        queue_total_persisted: 953,
        stale_resume_detected: "yes",
        stale_resume_recovery_attempted: "yes",
        stale_resume_recovery_result: "restarted_from_fresh_cursor",
        fresh_cursor_restart_attempted: "yes",
        fresh_cursor_restart_result: "restarted",
        current_run_found_count: 0,
        current_run_new_inserted_total: 0,
        current_run_effective_progress_total: 0,
        persisted_total_count: 953,
        scan_progress_discovered: 0,
        scan_progress_pages: 3,
        scan_progress_requests: 3,
        scan_progress_phase_label: "Refreshing scan cursor"
      }
    },
    verify: { ...base.verify, status: "idle", verified_target_count: 0, accepted_target_count: 0, targets: [], target_details: [] }
  };
  const mainVm = getDouyinScannerMainViewModel(mixedState);
  const panelVm = getScannerControlPanelViewModel(mixedState);
  const readiness = getWholeProfileHarvestReadiness(mixedState);
  const statValue = (label: string): string | undefined => mainVm.stats_summary.metrics.find((metric) => metric.label === label)?.value;

  assert.equal(mainVm.current_run_found_count, 0, "failed first-page current run must not inherit persisted total");
  assert.equal(mainVm.persisted_total_count, 953, "persisted history must be shown separately");
  assert.equal(mainVm.display_mode, "persisted_history_authority");
  assert.equal(mainVm.mixed_state_warning, "Current scan run failed/retrying; displayed total includes persisted history.");
  assert.equal(mainVm.alert?.message, "Current scan run failed/retrying; displayed total includes persisted history.");
  assert.equal(statValue("Found this run"), "0");
  assert.equal(statValue("Persisted total"), "953");
  assert.equal(panelVm.videosFound, 0, "control panel videosFound must use current-run count in mixed failure state");
  assert.equal(panelVm.persisted_total_count, 953);
  assert.equal(readiness.profile_scan_ready, false, "mixed failed active-source state must not be scan-ready");

  const staleResumeVm = getDouyinScannerMainViewModel(staleResumeActiveState);
  assert.equal(staleResumeVm.current_run_found_count, 0, "stale-resume recovery progress must not inherit persisted history");
  assert.equal(staleResumeVm.persisted_total_count, null, "active stale-resume recovery must not switch to persisted-history authority");
  assert.equal(staleResumeVm.display_mode, "current_run_authority");
  assert.equal(staleResumeVm.mixed_state_warning, null);
  assert.equal(staleResumeVm.progress.value, "0/1000");
  assert.match(staleResumeVm.progress.detail, /exclude previously persisted repository history/i);
}

{
  const base = authoritativeReconciliationFixtureState();
  const queue = base.harvest.queue.slice(0, 100);
  const warningState: WholeProfileHarvestState = {
    ...base,
    post_scan_counter_snapshot: null,
    scan_job: { ...base.scan_job, status: "completed", total_persisted: 983, expected_count: 984, remaining_estimate: 1 },
    harvest: {
      ...base.harvest,
      queue,
      queue_preview: queue.map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: "new" as const, source_url: item.source_url, title: null, thumbnail_url: null })),
      planned_total: 983,
      pending: 983
    },
    profile_scan: {
      ...base.profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        scan_finalization_result: "completed_with_warning",
        expected_profile_video_count: 984,
        scan_job_total_persisted: 983,
        queue_total_visible: 100,
        profile_queue_total_count: 983,
        api_pagination_attempted: "yes",
        api_pagination_page_count: 50,
        api_pagination_request_count: 50,
        api_pagination_has_more_final: false,
        displayed_profile_count: 984,
        displayed_profile_count_source: "active_works_tab_dom_text",
        displayed_profile_count_raw_text: "作品 984",
        api_raw_count: 983,
        api_unique_count: 983,
        api_has_more_final: false,
        collectable_count: 983,
        persisted_count: 983,
        secondary_recovery_attempted: "yes",
        secondary_recovered_count: 0,
        unavailable_or_unlisted_count: 1,
        count_semantics_status: "completed_with_displayed_count_mismatch",
        count_semantics_reason: "displayed_count_not_fully_collectable",
        final_gap_reason: "displayed_count_not_fully_collectable",
        final_gap_classification: "displayed_count_mismatch",
        secondary_gap_probe_attempted: "yes",
        api_pagination_final_cursor: "terminal_cursor_fixture",
        api_pagination_total_raw_targets: 983,
        api_pagination_total_persisted_targets: 983,
        api_pagination_total_persisted: 983,
        api_pagination_expected: 984,
        api_pagination_remaining: 1,
        api_pagination_stop_reason: "has_more_false"
      }
    },
    verify: { ...base.verify, diagnostics: { diagnostics_channel: "scan_authority_diagnostics", scan_finalization_result: "completed_with_warning", expected_profile_video_count: 984, scan_job_total_persisted: 983, queue_total_visible: 100, profile_queue_total_count: 983, api_pagination_attempted: "yes", api_pagination_page_count: 50, api_pagination_request_count: 50, api_pagination_has_more_final: false, api_pagination_final_has_more: false, displayed_profile_count: 984, displayed_profile_count_source: "active_works_tab_dom_text", displayed_profile_count_raw_text: "作品 984", api_raw_count: 983, api_unique_count: 983, api_has_more_final: false, collectable_count: 983, persisted_count: 983, secondary_recovery_attempted: "yes", secondary_recovered_count: 0, unavailable_or_unlisted_count: 1, count_semantics_status: "completed_with_displayed_count_mismatch", count_semantics_reason: "displayed_count_not_fully_collectable", final_gap_reason: "displayed_count_not_fully_collectable", final_gap_classification: "displayed_count_mismatch", secondary_gap_probe_attempted: "yes", api_pagination_final_cursor: "terminal_cursor_fixture", api_pagination_total_raw_targets: 983, api_pagination_total_persisted_targets: 983, api_pagination_total_persisted: 983, api_pagination_expected: 984, api_pagination_remaining: 1, api_pagination_stop_reason: "has_more_false" } }
  };
  const counters = deriveAuthoritativeProfileCounters(warningState);
  const popupMetrics = deriveReconciledPopupMetrics(warningState);
  const mainVm = getDouyinScannerMainViewModel(warningState);
  const panelVm = getScannerControlPanelViewModel(warningState);
  const progressVm = getWholeProfileHarvestProgressViewModel(warningState);
  const technicalValue = (label: string): string | undefined => progressVm.details.technical_rows.find((row) => row.label === label)?.value;
  assert.equal(counters.queue_total, 983, "authoritative counters must use persisted scan total when terminal queue is only a preview window");
  assert.equal(popupMetrics.profile.profile_total_count, 983, "popup profile total must not regress to preview-window length without a snapshot");
  assert.equal(popupMetrics.diagnostics.popup_metrics_profile_total_source, "authoritative_profile_counters.queue_total");
  assert.equal(mainVm.alert?.title, "Scan completed with warning", "completed_with_warning must render non-blocking warning UI");
  assert.match(mainVm.alert?.message ?? "", /saved 983 collectable videos/, "count semantics mismatch copy must label the collectable total");
  assert.match(mainVm.alert?.message ?? "", /Douyin displays 984/, "count semantics mismatch copy must distinguish Douyin displayed profile count");
  assert.match(mainVm.alert?.message ?? "", /could not be found in the API or verified secondary sources/, "count semantics mismatch copy must explain verified unlisted items");
  assert.doesNotMatch(mainVm.alert?.message ?? "", /Profile scan incomplete/, "completed_with_warning copy must not label a usable scan incomplete");
  assert.doesNotMatch(panelVm.emptyState ?? "", /Profile scan incomplete/, "completed_with_warning control-panel empty state must not use blocking incomplete wording");
  assert.match(panelVm.emptyState ?? "", /saved 983 collectable videos/, "completed_with_warning control-panel empty state must label collectable saved videos");
  assert.match(panelVm.emptyState ?? "", /Douyin displays 984/, "completed_with_warning control-panel empty state must show Douyin displayed profile count separately");
  assert.match(panelVm.emptyState ?? "", /could not be found in the API or verified secondary sources/, "completed_with_warning control-panel empty state must explain verified unlisted items");
  assert.equal(mainVm.status_chips.find((chip) => chip.label === "API")?.value, "Collectable", "API chip must show collectable semantics when paginated requests ran");
  assert.equal(getActionDeckViewModel(warningState).health.api.value, "Fetched", "action deck API badge must not stay idle after paginated requests ran");
  assert.equal(panelVm.health.api, "API ready", "control panel API badge must not stay API not checked after paginated requests ran");
  assert.equal(technicalValue("Active profile-post fetch attempted"), "yes", "advanced diagnostics must reflect API pagination as an attempted active profile-post fetch");
  assert.equal(technicalValue("Active profile-post fetch request count"), "50", "advanced diagnostics must mirror scan-job API pagination request count");
  assert.equal(technicalValue("Active profile-post fetch page count"), "50", "advanced diagnostics must mirror scan-job API pagination page count");
  assert.equal(technicalValue("Active profile-post fetch has-more state"), "false", "advanced diagnostics must mirror terminal API pagination has_more state");
  assert.equal(technicalValue("api_pagination_raw_items_total"), "unknown", "fixture without raw accounting should remain visibly unknown rather than fabricating zero");
  assert.equal(technicalValue("api_pagination_per_page_raw_counts"), "[]", "fixture without preserved producer arrays should surface empty accounting evidence");
  const trace = JSON.parse(technicalValue("POST_SCAN_COUNTER_PIPELINE_TRACE") ?? "{}") as Record<string, Record<string, unknown>>;
  assert.equal(trace.scan_result?.trace_scan_completed, "yes", "usable completed_with_warning scan trace must not report scan_completed=no");
  assert.equal(trace.scan_result?.trace_scan_usable, "yes", "usable completed_with_warning scan trace must expose trace_scan_usable=yes");
  const overcountState: WholeProfileHarvestState = {
    ...warningState,
    calibration: { ...warningState.calibration, status: "missing", point_count: 0 },
    scan_job: { ...warningState.scan_job, total_persisted: 478, expected_count: 475, remaining_estimate: 0 },
    harvest: { ...warningState.harvest, planned_total: 478, pending: 478 },
    profile_scan: {
      ...warningState.profile_scan,
      accepted_target_count: 478,
      diagnostics: {
        ...(warningState.profile_scan.diagnostics as Record<string, unknown>),
        scan_finalization_result: "completed_with_warning",
        expected_profile_video_count: 475,
        scan_job_total_persisted: 478,
        profile_queue_total_count: 478,
        displayed_profile_count: 475,
        api_raw_count: 478,
        api_unique_count: 478,
        collectable_count: 478,
        persisted_count: 478,
        unavailable_or_unlisted_count: 0,
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["7634192733514501476", "7634192733514501477", "7634192733514501478"],
        over_displayed_extra_items_exact: [
          { aweme_id: "7634192733514501476", page_index: 47, raw_index: 0, accepted_index: 475, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" },
          { aweme_id: "7634192733514501477", page_index: 47, raw_index: 1, accepted_index: 476, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" },
          { aweme_id: "7634192733514501478", page_index: 47, raw_index: 2, accepted_index: 477, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" }
        ],
        over_displayed_itemized_reason_summary: "7634192733514501476:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501477:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501478:valid_same_profile_item_hidden_from_visible_count_basis",
        count_semantics_status: "completed_with_api_over_displayed_count",
        count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_verdict_reason: "validated_same_profile_api_over_display",
        scan_health_required_user_action: "proceed_with_non_blocking_same_profile_api_over_display_warning",
        forensic_export_available: "yes",
        forensic_export_storage_key: "whole_profile_overcollection_forensic_export_22C14Q",
        forensic_export_scan_run_id: warningState.scan_job.scan_job_id,
        accepted_target_ledger_present: "yes",
        accepted_target_ledger_count: 478,
        accepted_target_ledger_matches_accepted_total: true,
        over_displayed_boundary_start_index: 475,
        over_displayed_visible_boundary_index: 475,
        over_displayed_boundary_end_index: 478
      }
    },
    verify: {
      ...warningState.verify,
      accepted_target_count: 478,
      verified_target_count: 478,
      diagnostics: {
        ...(warningState.verify.diagnostics as Record<string, unknown>),
        scan_finalization_result: "completed_with_warning",
        expected_profile_video_count: 475,
        scan_job_total_persisted: 478,
        profile_queue_total_count: 478,
        displayed_profile_count: 475,
        api_raw_count: 478,
        api_unique_count: 478,
        collectable_count: 478,
        persisted_count: 478,
        unavailable_or_unlisted_count: 0,
        over_displayed_count: 3,
        over_displayed_validation_status: "validated_same_profile",
        over_displayed_same_profile_validated: "yes",
        over_displayed_extra_ids_exact: ["7634192733514501476", "7634192733514501477", "7634192733514501478"],
        over_displayed_extra_items_exact: [
          { aweme_id: "7634192733514501476", page_index: 47, raw_index: 0, accepted_index: 475, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" },
          { aweme_id: "7634192733514501477", page_index: 47, raw_index: 1, accepted_index: 476, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" },
          { aweme_id: "7634192733514501478", page_index: 47, raw_index: 2, accepted_index: 477, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: "18800", same_profile_validated: "yes", source_profile_identifier: "MS4wLjABAAAAvalidated-profile", target_profile_identifier: "MS4wLjABAAAAvalidated-profile", requested_profile_identifier: "MS4wLjABAAAAvalidated-profile", author_sec_uid: "MS4wLjABAAAAvalidated-profile", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" }
        ],
        over_displayed_itemized_reason_summary: "7634192733514501476:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501477:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501478:valid_same_profile_item_hidden_from_visible_count_basis",
        count_semantics_status: "completed_with_api_over_displayed_count",
        count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count",
        scan_health_verdict: "ready_api_over_displayed_count",
        scan_health_verdict_reason: "validated_same_profile_api_over_display",
        scan_health_required_user_action: "proceed_with_non_blocking_same_profile_api_over_display_warning",
        forensic_export_available: "yes",
        forensic_export_storage_key: "whole_profile_overcollection_forensic_export_22C14Q",
        forensic_export_scan_run_id: warningState.scan_job.scan_job_id,
        accepted_target_ledger_present: "yes",
        accepted_target_ledger_count: 478,
        accepted_target_ledger_matches_accepted_total: true,
        over_displayed_boundary_start_index: 475,
        over_displayed_visible_boundary_index: 475,
        over_displayed_boundary_end_index: 478
      }
    }
  };
  const overcountMainVm = getDouyinScannerMainViewModel(overcountState);
  const overcountPanelVm = getScannerControlPanelViewModel(overcountState);
  const overcountRunTabVm = getRunTabViewModel(overcountState, getWholeProfileHarvestReadiness(overcountState), getWholeProfileHarvestActionState(overcountState));
  const overcountActionDeckVm = getActionDeckViewModel(overcountState);
  assert.ok(overcountMainVm.primary_action, "validated same-profile overcount main view model must expose a next action");
  assert.equal(overcountMainVm.primary_action?.key, "calibrate", "validated same-profile overcount must allow the next safe action instead of review when calibration is still missing");
  assert.equal(overcountPanelVm.action.key, "calibrate", "control panel must allow calibration for validated same-profile overcount");
  assert.equal(overcountRunTabVm.primary_action?.key, "calibrate", "run tab must surface calibrate as the next action for validated same-profile overcount when calibration is missing");
  assert.equal(overcountActionDeckVm.currentStep.primaryActionKey, "calibrate", "action deck must not block validated same-profile overcount behind review");
  assert.equal(overcountMainVm.stats_summary.metrics.find((row) => row.label === "Videos found")?.value, "478 collectable", "validated API overcount must not render misleading persisted/displayed ratio");
  assert.doesNotMatch(JSON.stringify(overcountMainVm), /478 \/ 475 videos/, "validated API overcount UI must not render 478 / 475 videos as a normal full match");
  assert.equal(overcountMainVm.alert?.title, "API returned additional same-profile videos", "validated API overcount main alert must be a non-blocking same-profile warning");
  assert.match(overcountMainVm.alert?.message ?? "", /^API returned 3 additional same-profile videos beyond visible profile count\./, "validated API overcount warning must start with the exact required message");
  assert.match(overcountMainVm.alert?.message ?? "", /Visible profile count: 475\./, "validated API overcount warning must show visible profile count breakdown");
  assert.match(overcountMainVm.alert?.message ?? "", /API collectable count: 478\./, "validated API overcount warning must show collectable count breakdown");
  assert.match(overcountMainVm.alert?.message ?? "", /Additional same-profile API videos: 3\./, "validated API overcount warning must show additional same-profile video breakdown");
  assert.equal(overcountRunTabVm.alert?.title, "API returned additional same-profile videos", "run tab must expose the same non-blocking validated same-profile warning");
  assert.match(overcountRunTabVm.alert?.message ?? "", /^API returned 3 additional same-profile videos beyond visible profile count\./, "run tab warning must start with the exact required message");
  assert.equal(overcountActionDeckVm.alert?.title, "API returned additional same-profile videos", "action deck must expose the same non-blocking validated same-profile warning");
  assert.match(overcountActionDeckVm.alert?.message ?? "", /API collectable count: 478\./, "action deck warning must include collectable count breakdown");
  assert.match(overcountPanelVm.emptyState ?? "", /^API returned 3 additional same-profile videos beyond visible profile count\./, "control panel overcount copy must use the non-blocking validated same-profile warning wording");
  assert.match(overcountPanelVm.emptyState ?? "", /Visible profile count: 475\./, "control panel overcount copy must show visible count breakdown");
  assert.match(overcountPanelVm.emptyState ?? "", /API collectable count: 478\./, "control panel overcount copy must show collectable count breakdown");
  assert.match(overcountPanelVm.emptyState ?? "", /Additional same-profile API videos: 3\./, "control panel overcount copy must show additional same-profile video breakdown");

  const calibratedOvercountState: WholeProfileHarvestState = {
    ...overcountState,
    calibration: { ...overcountState.calibration, status: "calibrated", point_count: 4 }
  };
  const calibratedOvercountVm = getDouyinScannerMainViewModel(calibratedOvercountState);
  const calibratedOvercountPanelVm = getScannerControlPanelViewModel(calibratedOvercountState);
  assert.ok(calibratedOvercountVm.primary_action, "validated same-profile overcount main view model must expose start collecting after calibration is ready");
  assert.equal(calibratedOvercountVm.primary_action?.key, "start_collecting", "validated same-profile overcount must allow collecting once calibration is ready");
  assert.equal(calibratedOvercountPanelVm.action.key, "start_collecting", "control panel must allow collecting for validated same-profile overcount after calibration");

  const overcollectionReviewState: WholeProfileHarvestState = {
    ...overcountState,
    profile_scan: {
      ...overcountState.profile_scan,
      diagnostics: {
        ...(overcountState.profile_scan.diagnostics as Record<string, unknown>),
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "overcollected_needs_validation",
        scan_health_verdict: "failed_or_warning_overcollection_validation_needed"
      }
    },
    verify: {
      ...overcountState.verify,
      diagnostics: {
        ...(overcountState.verify.diagnostics as Record<string, unknown>),
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        count_semantics_status: "overcollected_needs_validation",
        scan_health_verdict: "failed_or_warning_overcollection_validation_needed"
      }
    }
  };
  const overcollectionReviewVm = getDouyinScannerMainViewModel(overcollectionReviewState);
  const overcollectionReviewPanelVm = getScannerControlPanelViewModel(overcollectionReviewState);
  assert.ok(overcollectionReviewVm.primary_action, "unvalidated terminal overcollection must render a primary action object");
  assert.equal(overcollectionReviewVm.primary_action.key, "review_overcollection", "unvalidated terminal overcollection must render a review-specific primary action, not generic Scan Profile");
  assert.match(overcollectionReviewVm.primary_action.label, /Review Overcollection/, "unvalidated terminal overcollection must label the review state explicitly");
  assert.equal(overcollectionReviewVm.primary_action.enabled, true, "unvalidated terminal overcollection review must stay actionable so the operator can copy exact forensic evidence");
  assert.match(overcollectionReviewVm.primary_action.reason ?? "", /Over-display exact-item validation is required|scan is complete but not ready|review/i, "unvalidated terminal overcollection must explain the exact-item validation requirement");
  assert.equal(overcollectionReviewPanelVm.action.key, "review_overcollection", "control panel must also render the review-specific overcollection state");
  assert.equal(overcollectionReviewVm.alert?.tone, "warning", "review_overcollection must render a warning main alert, not calibration/info");
  assert.match(overcollectionReviewVm.alert?.title ?? "", /Scan needs review|Review overcollection/, "review_overcollection main alert must be review-specific");
  assert.doesNotMatch(overcollectionReviewVm.alert?.title ?? "", /Calibration needed/, "review_overcollection main alert must not ask for calibration");
  const overcollectionReviewRunTabVm = getRunTabViewModel(overcollectionReviewState, getWholeProfileHarvestReadiness(overcollectionReviewState), getWholeProfileHarvestActionState(overcollectionReviewState));
  const overcollectionReviewActionDeckVm = getActionDeckViewModel(overcollectionReviewState);
  assert.equal(overcollectionReviewRunTabVm.alert?.tone, "warning", "review_overcollection run tab alert must be warning");
  assert.match(overcollectionReviewRunTabVm.alert?.title ?? "", /Scan needs review|Review overcollection/, "review_overcollection run tab alert must be review-specific");
  assert.equal(overcollectionReviewActionDeckVm.alert?.tone, "warning", "review_overcollection action deck alert must be warning");
  assert.match(overcollectionReviewActionDeckVm.alert?.title ?? "", /Scan needs review|Review overcollection/, "review_overcollection action deck alert must be review-specific");

  const contradictoryReadyOvercollectionState: WholeProfileHarvestState = {
    ...overcountState,
    profile_scan: {
      ...overcountState.profile_scan,
      diagnostics: {
        ...(overcountState.profile_scan.diagnostics as Record<string, unknown>),
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        over_displayed_extra_ids_exact: [],
        over_displayed_extra_items_exact: [],
        over_displayed_itemized_reason_summary: null,
        count_semantics_status: "completed_with_api_over_displayed_count",
        scan_health_verdict: "ready_api_over_displayed_count"
      }
    },
    verify: {
      ...overcountState.verify,
      diagnostics: {
        ...(overcountState.verify.diagnostics as Record<string, unknown>),
        over_displayed_validation_status: "needs_validation",
        over_displayed_same_profile_validated: "no",
        over_displayed_extra_ids_exact: [],
        over_displayed_extra_items_exact: [],
        over_displayed_itemized_reason_summary: null,
        count_semantics_status: "completed_with_api_over_displayed_count",
        scan_health_verdict: "ready_api_over_displayed_count"
      }
    }
  };
  const contradictoryReadyOvercollectionVm = getDouyinScannerMainViewModel(contradictoryReadyOvercollectionState);
  const contradictoryReadyOvercollectionPanelVm = getScannerControlPanelViewModel(contradictoryReadyOvercollectionState);
  assert.ok(contradictoryReadyOvercollectionVm.primary_action, "contradictory ready overdisplay must render a review primary action object");
  assert.equal(contradictoryReadyOvercollectionVm.primary_action.key, "review_overcollection", "ready overdisplay strings without proof must route to Review Overcollection, not calibration");
  assert.equal(contradictoryReadyOvercollectionPanelVm.action.key, "review_overcollection", "control panel must also block contradictory ready overdisplay strings");
}

assert.match(popupSource, /type PopupCounterAuthorityLock = {[\s\S]*authority: "scan_job_total_persisted" \| "queue_total_persisted" \| "post_scan_counter_snapshot" \| "queue_preview_length"/s, "popup must define stable counter authority lock with all priority sources");
assert.match(popupSource, /function popupTerminalForensicOverlayDiagnostics22C14Q\(state: WholeProfileHarvestState, forensicExport: PopupOvercollectionForensicExport22C14Q\): Record<string, unknown> \| null {[\s\S]*scanRunId !== currentRunId[\s\S]*finalVerdict === "validated_same_profile"[\s\S]*forensic_export_available: "yes"[\s\S]*accepted_target_ledger_present: "yes"[\s\S]*over_displayed_extra_ids_exact: extraIds[\s\S]*over_displayed_extra_items_exact: extraItems[\s\S]*count_semantics_status: "completed_with_api_over_displayed_count"[\s\S]*count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count"[\s\S]*scan_health_verdict: "ready_api_over_displayed_count"[\s\S]*scan_health_required_user_action: "proceed_with_non_blocking_same_profile_api_over_display_warning"/s, "popup must derive same-run validated forensic overlay diagnostics before canonical readiness and action selectors run");
assert.match(popupSource, /const countSemanticsBlock = {[\s\S]*forensic_export_available: diagnostics\.forensic_export_available \?\? \(countSemanticsOverDisplayedCount != null && countSemanticsExtraIdsExact\.length > 0 && countSemanticsExtraItemsExact\.length > 0 && diagnostics\.over_displayed_validation_status === "validated_same_profile" \? "yes" : null\)[\s\S]*count_semantics_reason: diagnostics\.count_semantics_reason \?\? \(countSemanticsOverDisplayedCount != null && countSemanticsOverDisplayedCount > 0 && diagnostics\.over_displayed_validation_status === "validated_same_profile" \? "itemized_valid_same_profile_api_items_beyond_visible_count" : null\)[\s\S]*scan_health_required_user_action: diagnostics\.scan_health_required_user_action \?\? \(countSemanticsOverDisplayedCount != null && countSemanticsOverDisplayedCount > 0 && diagnostics\.over_displayed_validation_status === "validated_same_profile" \? "proceed_with_non_blocking_same_profile_api_over_display_warning" : null\)/s, "popup freeze log compact count semantics must hydrate validated same-profile forensic bridge fields and non-blocking action wording");
assert.match(popupSource, /async function readWholeProfileHarvestProductState\(\): Promise<WholeProfileHarvestState> {[\s\S]*readWholeProfileHarvestState\(chrome\.storage\.local, now\)[\s\S]*OVERCOLLECTION_FORENSIC_EXPORT_STORAGE_KEY_22C14Q[\s\S]*HYBRID_COLLECTION_DONE_KEY[\s\S]*applyHybridCollectionDoneOverride\(state, parseHybridCollectionDoneSignal\(doneStored\[HYBRID_COLLECTION_DONE_KEY\]\)\)[\s\S]*applyPopupTerminalForensicOverlay22C14Q\(/s, "popup canonical state reader must load forensic export and hybrid_collection_done, apply done override, then apply the terminal overlay before rendering");
assert.match(popupSource, /function popupScanDiagnosticsRecord\(state: WholeProfileHarvestState\): Record<string, unknown> {[\s\S]*22C-14H progress authority keeps terminal scan-authority diagnostics immutable[\s\S]*runtimeRequestDiagnostics[\s\S]*runtimeResponseDiagnostics[\s\S]*runtimeProgressRunMatches[\s\S]*state\.workflow\.scan\.status === "running"[\s\S]*typeof runtimeDiagnostics\.scan_progress_discovered !== "undefined"[\s\S]*runtimeProgressActive \? \{ \.\.\.authorityDiagnostics, \.\.\.runtimeDiagnostics \} : authorityDiagnostics/s, "popup scan diagnostics must merge same-run active runtime progress so live scan counts cannot freeze behind stale authority diagnostics");
assert.match(popupSource, /function popupScanDiagnosticsRecord\(state: WholeProfileHarvestState\): Record<string, unknown> {[\s\S]*state\.phase !== "scan_finished"[\s\S]*state\.workflow\.scan\.status === "running"/s, "popup runtime progress diagnostics must not override terminal scan-authority diagnostics after finalization");
assert.match(popupSource, /popup_progress_active_rendered[\s\S]*popup_progress_render_source[\s\S]*popup_progress_render_run_id[\s\S]*popup_progress_cleared_after_terminal[\s\S]*popup_progress_stale_ignored_reason/s, "popup stable render diagnostics must expose active progress render authority and terminal stale-progress clearing");
assert.match(viewModelSource, /Active progress snapshots are only valid while the matching scan run is actively scanning; final scan state must clear stale progress\./, "view model must document the terminal stale-progress guard before applying it");
assert.match(viewModelSource, /function scanRuntimeProgressActive22C14J\(state: WholeProfileHarvestState, runtime: Record<string, unknown>\): boolean {[\s\S]*state\.phase !== "scan_finished"[\s\S]*state\.workflow\.scan\.status === "running"[\s\S]*state\.scan_job\.status === "running" \|\| state\.scan_job\.status === "retry_wait"/s, "view model runtime scan progress merge must be active-run and terminal-state gated");
assert.match(popupSource, /function decoratePopupStateForStableRender\(state: WholeProfileHarvestState, source: string\): WholeProfileHarvestState \| null {[\s\S]*popupVersionIsOlder\(stateVersion, previous\.stateVersion\)[\s\S]*blocked_stale_state_version[\s\S]*candidate\.priority > previous\.priority[\s\S]*blocked_authority_downgrade_same_run/s, "popup stable render decorator must block stale versions and lower-priority authority downgrades");
assert.match(popupSource, /staleCrossRunUpdate[\s\S]*staleSameRunTerminalRegression[\s\S]*popupLastCoherentAuthorityState[\s\S]*terminal_state_blocks_non_terminal_render/s, "popup render pinning must keep the last coherent authority snapshot when stale running updates arrive after terminal state");
assert.match(popupSource, /const decoratedState = {[\s\S]*popupLastCoherentAuthorityState = decoratedState;[\s\S]*return decoratedState;/s, "popup render pinning must remember the decorated state so stale fallback keeps popup runtime diagnostics");
assert.match(popupSource, /return diagnosticRunId \?\? state\.run_id \?\? state\.scan_job\.scan_job_id/s, "popup render run id must prefer scan_authority_diagnostics over stale scan_job ids");
assert.match(popupSource, /scanJobBelongsToRun[\s\S]*state\.scan_job\.total_persisted : 0/s, "popup counters must not mix stale scan_job totals from a different authority run");
assert.match(popupSource, /popupRenderRunLock && popupRenderRunLock\.profileKey !== profileKey[\s\S]*popupLastCoherentAuthorityState = null[\s\S]*profileSwitchDetected = "yes"/s, "popup render pinning must reset intentionally on profile switch");

assert.match(popupSource, /const suppressPassiveActionBlocked = vm\.scanProgress\.active \|\| vm\.primaryAction\.key === "pause" \|\| vm\.primaryAction\.label === "Collecting videos\.\.\.";/, "popup must suppress Action blocked while active scan progress is visible");
assert.match(popupSource, /scannerEmptyStateEl\.dataset\.tone = vm\.emptyStateTone/, "popup must render empty-state tone for metrics-miss hints");
assert.match(popupSource, /scannerPrimaryActionButton\.classList\.toggle\("scanner-primary-button-warning"/, "popup must apply warning styling for metrics-miss skip actions");
assert.match(popupSource, /DOUYIN_SCANNER_SKIP_HYBRID_INCOMPLETE/, "popup must dispatch Skip incomplete through the background service worker");
assert.match(popupSource, /dispatchBackgroundSkipHybridIncompleteAction/, "popup must route Skip incomplete through a dedicated background dispatcher");
assert.match(popupSource, /button\?\.dataset\.actionKey as ScannerActionKey/, "popup primary click must dispatch the rendered button action key");
assert.match(viewModelSource, /getScannerControlPanelViewModelUnreconciled\(state: WholeProfileHarvestState\): ScannerControlPanelViewModel {[\s\S]*const canonicalPrimaryAction = getCanonicalScannerPrimaryAction\(state\);[\s\S]*const scanProgress = activeScanProgress22C14G\(state\);[\s\S]*const action: ScannerControlPanelViewModel\["action"\] = scanProgress\.active[\s\S]*key: "scan_profile",[\s\S]*buttonLabel: scanProgress\.phaseLabel === "Finalizing scan" \? "Finalizing\.\.\." : "Scanning\.\.\.",[\s\S]*disabledReason: null[\s\S]*unresolvedOvercollectionReviewActive\(state, scanDiagnostics\) \? "review_overcollection" : canonicalPrimaryAction\.key,[\s\S]*buttonLabel: actionLabel/s, "scanner control panel must derive its primary action from the canonical selector, but normalize active scan progress to a non-blocked Scanning state");
assert.match(viewModelSource, /getDouyinScannerMainViewModelUnreconciled\(state: WholeProfileHarvestState\): DouyinScannerMainViewModel {[\s\S]*const canonicalPrimaryAction = getCanonicalScannerPrimaryAction\(state\);[\s\S]*const primaryCode = unresolvedOvercollectionReviewActive\(state, scanDiagnostics\)[\s\S]*\? "review_overcollection"[\s\S]*: canonicalPrimaryAction\.key;[\s\S]*const scanContinuation = primaryCode === "scan_profile" && scanBudgetContinuation;[\s\S]*const primaryLabel = unresolvedOvercollectionReviewActive\(state, scanDiagnostics\)[\s\S]*\? "Review Overcollection"[\s\S]*: scanContinuation[\s\S]*canonicalPrimaryAction\.label;[\s\S]*key: primaryCode,[\s\S]*label: primaryLabel,[\s\S]*enabled: unresolvedOvercollectionReviewActive\(state, scanDiagnostics\) \? true : canonicalPrimaryAction\.enabled/s, "scanner main VM must derive its primary action key from the canonical selector while allowing scan and safe-batch continuation labels");
assert.match(viewModelSource, /getWholeProfileHarvestProgressViewModelUnreconciled\(state: WholeProfileHarvestState\): WholeProfileHarvestProgressViewModel {[\s\S]*const canonicalPrimaryAction = getCanonicalScannerPrimaryAction\(state\);[\s\S]*const canonicalCalibration = getCanonicalCalibrationReady\(state\);[\s\S]*label: "Canonical calibration ready"[\s\S]*label: "Primary action selector version"/s, "advanced diagnostics must expose canonical calibration and primary action metadata from the same selector path");

{
  const metricsMissBase = applyHybridNetworkCacheModeFlagToState(
    withClassification(withDryRun(withVerify(baseState())), 2),
    true
  );
  const metricsMissState: WholeProfileHarvestState = {
    ...metricsMissBase,
    scan_job: {
      ...metricsMissBase.scan_job,
      status: "completed",
      total_persisted: 999,
      expected_count: 999
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAAmetrics-miss",
      scanned_total: 999,
      backend_captured: 997,
      backend_ready: 997,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 997,
      incomplete: 0,
      need_retry: 0,
      new: 2,
      queue: 2,
      applied_at: "2026-05-06T12:05:00.000Z"
    },
    debug: {
      ...metricsMissBase.debug,
      last_response_summary: {
        ...(metricsMissBase.debug.last_response_summary as Record<string, unknown>),
        hybrid_runner_outcome: "write_pending_only",
        hybrid_runner_write_ok_count: 0,
        hybrid_runner_flush_ready_count: 0,
        hybrid_runner_per_item_count: 2,
        hybrid_runner_pre_skip_pending: 2
      }
    }
  };
  const metricsMissVm = getScannerControlPanelViewModel(metricsMissState);
  assert.equal(metricsMissVm.primaryAction.label, "Skip 2 incomplete", "metrics-miss leftovers must promote Skip N incomplete as the primary button");
  assert.equal(metricsMissVm.primaryAction.key, "skip_hybrid_incomplete", "metrics-miss skip must dispatch a dedicated skip action");
  assert.equal(metricsMissVm.primaryAction.title, "Finish collection", "metrics-miss leftovers must retitle the action card to Finish collection");
  assert.equal(metricsMissVm.primaryAction.tone, "warning", "metrics-miss skip must use warning button styling");
  assert.equal(metricsMissVm.emptyStateTone, "warning", "metrics-miss retry hint must use warning tone");
  assert.doesNotMatch(metricsMissVm.primaryAction.description, /Use “Skip incomplete”/, "metrics-miss copy must not reference a button label that is not shown");
  assert.equal(metricsMissVm.emptyState, "Tip: Open the Douyin profile tab, scroll to load video cards, then collect again before skipping.");

  const metricsMissNoPlanState: WholeProfileHarvestState = {
    ...metricsMissState,
    debug: {
      ...metricsMissState.debug,
      last_response_summary: {
        ...(metricsMissState.debug.last_response_summary as Record<string, unknown>),
        hybrid_network_cache_mode_flag: "disabled"
      }
    }
  };
  const metricsMissNoPlanVm = getScannerControlPanelViewModel(metricsMissNoPlanState);
  assert.equal(metricsMissNoPlanVm.primaryAction.label, "Skip 2 incomplete", "metrics-miss skip must remain available when hybrid metrics plan is unavailable");
  assert.equal(metricsMissNoPlanVm.primaryAction.key, "skip_hybrid_incomplete", "metrics-miss skip must keep dedicated action when metrics plan is unavailable");
}

console.log("wholeProfileHarvest stepper/summary view-model tests passed");

