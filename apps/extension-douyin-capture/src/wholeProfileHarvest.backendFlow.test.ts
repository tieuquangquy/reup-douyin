import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { getWholeProfileHarvestActionState, getWholeProfileHarvestReadiness } from "./wholeProfileHarvest/readiness.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { getBackendFlushFlowViewModel } from "./wholeProfileHarvest/viewModel.js";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const viewModelSource = readFileSync(new URL("./wholeProfileHarvest/viewModel.ts", import.meta.url), "utf8");

function baseState(): WholeProfileHarvestState {
  return createWholeProfileHarvestIdleState("2026-05-06T13:00:00.000Z");
}

function canonicalCalibrationPoints(): Record<string, unknown> {
  return {
    like: { x: 100, y: 200 },
    comment: { x: 100, y: 260 },
    favorite: { x: 100, y: 320 },
    share: { x: 100, y: 380 }
  };
}

function withExtraction(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    status: "completed",
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
    profile_scan: { ...state.profile_scan, status: "success", accepted_target_count: 10 },
    verify: { ...state.verify, status: "success", accepted_target_count: 10, verified_target_count: 10 },
    dry_run: { ...state.dry_run, status: "success", pass: 3, fail: 0, mode: "random", sample_size: 3 },
    harvest_options: { ...state.harvest_options, batch: "all_remaining", mode: "new_and_incomplete", speed: "safe" },
    classification: {
      ...state.classification,
      status: "success",
      schema_version: "douyin_profile_video_classification_result.v1",
      collection_mode: "new_incomplete_failed",
      database_lookup_status: "ok",
      total_candidates: 10,
      counts: { new: 10, incomplete: 0, complete: 0, failed: 0, skipped: 0, unknown: 0, collect: 10, skip: 0 },
      collect_aweme_ids: ["7635294267413368100"],
      skip_aweme_ids: [],
      targets: [],
      diagnostics: { fixture: true }
    },
    harvest: {
      ...state.harvest,
      status: "completed",
      planned_total: 10,
      updated: 3,
      failed: 0,
      pending: 7,
      flushed: 0,
      queue: [
        {
          index: 1,
          aweme_id: "7635294267413368100",
          capture_status: "new",
          status: "extracted",
          attempts: 1,
          checkpoint_sequence: 1,
          extraction_result: null,
          last_error: null,
          capture_inbox_item_id: null,
          source_url: "https://www.douyin.com/video/7635294267413368100",
          profile_card_evidence: {}
        }
      ],
      results: [
        {
          index: 1,
          aweme_id: "7635294267413368100",
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
          started_at: "2026-05-06T13:00:00.000Z",
          completed_at: "2026-05-06T13:01:00.000Z",
          duration_seconds: 444,
          duration_text: "07:24",
          like_count: 136,
          comment_count: 3,
          favorite_count: 33,
          share_count: 12,
          current_modal_id_before: "7635294267413368100",
          current_modal_id_after: "7635294267413368100",
          extracted_aweme_id: "7635294267413368100",
          source_used: "calibrated_point_dom"
        }
      ]
    }
  };
}

function withSession(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    capture_session_id: "bd2c1384session",
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        capture_session: {
          ...state.harvest.backend.capture_session,
          status: "ready",
          session_id: "bd2c1384session"
        }
      }
    }
  };
}

function withPayload(state: WholeProfileHarvestState, guardOk = true): WholeProfileHarvestState {
  return {
    ...state,
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        payload_preview: {
          ...state.harvest.backend.payload_preview,
          status: guardOk ? "ready" : "guard_failed",
          target_aweme_id: "7635294267413368100",
          removed_fields: [{ path: "$.diagnostics", reason: "not_allowlisted" }],
          guard: {
            ok: guardOk,
            offending_paths: guardOk ? [] : ["$.profile_card_evidence.capture_session_id", "$.diagnostics", "$.raw_evidence_summary.debug"]
          },
          payload: { aweme_id: "7635294267413368100" },
          summary: { aweme_id: "7635294267413368100" }
        }
      }
    }
  };
}

function withOneItemSuccess(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        one_item_flush: {
          ...state.harvest.backend.one_item_flush,
          status: "succeeded",
          capture_inbox_item_id: "abc123456",
          item_created_or_updated: true,
          verify_status: "verified"
        }
      }
    }
  };
}

function withOneItemSchemaRejected(state: WholeProfileHarvestState): WholeProfileHarvestState {
  const responseSummary = {
    response_summary_status: "error",
    http_status: 422,
    backend_code: "http_422_schema_error",
    validation_error_paths: [["body", "items", 0, "raw_dom_detail_metrics", "duration_seconds"]],
    response_json_parse_status: "json_parsed"
  };
  return {
    ...state,
    harvest: {
      ...state.harvest,
      last_backend_response: responseSummary,
      backend: {
        ...state.harvest.backend,
        one_item_flush: {
          ...state.harvest.backend.one_item_flush,
          status: "failed",
          response_summary: responseSummary,
          error: { code: "backend_schema_rejected", message: "Backend rejected the payload schema.", details: responseSummary },
          verify_status: "idle"
        }
      }
    }
  };
}

function withBatchRunning(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    harvest: {
      ...state.harvest,
      backend: {
        ...state.harvest.backend,
        batch_flush: {
          ...state.harvest.backend.batch_flush,
          status: "running",
          queue_total: 7,
          current_index: 2,
          current_aweme_id: "7635294267413368102",
          processed: 2,
          succeeded: 2,
          failed: 0,
          skipped: 0,
          pending: 5
        }
      }
    }
  };
}

{
  const state = withExtraction(baseState());
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps.length, 4);
  assert.equal(vm.steps[0]?.key, "session");
  assert.equal(vm.steps[1]?.key, "payload");
  assert.equal(vm.steps[2]?.key, "flush_one");
  assert.equal(vm.steps[3]?.key, "flush_batch");
  assert.equal(vm.steps[0]?.enabled, true);
  assert.equal(vm.steps[0]?.disabled_reason, null);
  assert.equal(vm.next_backend_action.label, "Create Scan Session");
}

{
  const state = withSession(withExtraction(baseState()));
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[0]?.status, "done");
  assert.match(vm.steps[0]?.summary ?? "", /ready: bd2c1384/);
  assert.equal(vm.next_backend_action.label, "Data check");
}

{
  const state = withPayload(withSession(withExtraction(baseState())), true);
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[1]?.status, "done");
  assert.equal(vm.steps[1]?.summary, "Data check passed");
  assert.equal(vm.next_backend_action.label, "Save 1 Video");
}

{
  const state = withPayload(withSession(withExtraction(baseState())), false);
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[1]?.status, "failed");
  assert.equal(vm.steps[2]?.enabled, false);
  assert.equal(vm.steps[2]?.disabled_reason, "Data check failed. Fix save data before saving.");
  assert.equal(vm.next_backend_action.label, "Data check failed");
  assert.equal(vm.compact_guard_rows.some((row) => row.value === "$.profile_card_evidence.capture_session_id"), true);
}

{
  const state = withOneItemSuccess(withPayload(withSession(withExtraction(baseState())), true));
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[2]?.status, "done");
  assert.match(vm.steps[2]?.summary ?? "", /item abc12345/);
  assert.equal(vm.steps[3]?.enabled, true);
  assert.equal(vm.next_backend_action.label, "Save to Capture Inbox");
  assert.equal(vm.flush_result_rows.some((row) => row.label === "Item id" && row.value === "abc12345"), true);
}

{
  const state = withOneItemSchemaRejected(withPayload(withSession(withExtraction(baseState())), true));
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[2]?.status, "failed");
  assert.equal(vm.details_rows.some((row) => row.label === "Last flush response" && row.value === "available in Details"), true);
}

{
  const state = withBatchRunning(withOneItemSuccess(withPayload(withSession(withExtraction(baseState())), true)));
  const vm = getBackendFlushFlowViewModel(state, getWholeProfileHarvestReadiness(state), getWholeProfileHarvestActionState(state));
  assert.equal(vm.steps[3]?.status, "active");
  assert.equal(vm.next_backend_action.label, "Save to Capture Inbox is running");
  assert.equal(vm.summary.batch_flush, "running");
  assert.equal(vm.flush_result_rows.some((row) => row.label === "Flushed / Failed / Skipped / Pending" && row.value === "2 / 0 / 0 / 5"), true);
}

assert.match(popupHtml, /Save to Capture Inbox/, "popup must render guided backend save section");
assert.match(popupHtml, /backendFlowSessionStatus/, "popup must render backend session status row");
assert.match(popupHtml, /backendFlowPayloadStatus/, "popup must render backend payload status row");
assert.match(popupHtml, /backendFlowFlushOneStatus/, "popup must render backend flush-one status row");
assert.match(popupHtml, /backendFlowFlushBatchStatus/, "popup must render backend flush-batch status row");
assert.match(popupHtml, /id="wholeProfileBackendFlowRows"/, "popup must render backend flow rows container");
assert.match(popupSource, /Batch flush will write multiple Capture Inbox items sequentially\. Continue\?/, "flush batch must confirm larger writes");
assert.match(popupSource, /wholeProfileBackendNextActionTitleEl/, "popup must render backend next action");
assert.match(popupSource, /wholeProfileCaptureInboxCtaEl/, "popup must render Capture Inbox CTA");
assert.match(viewModelSource, /getBackendFlushFlowViewModel/, "view model must expose backend flush flow");
assert.doesNotMatch(viewModelSource, /douyinHarvestRuntimeV2|douyinSafeHarvestRun|smartHarvestState/, "backend flow must not use V2 or legacy runtime state");

console.log("wholeProfileHarvest backend guided flow tests passed");
