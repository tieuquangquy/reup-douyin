import assert from "node:assert/strict";

import {
  buildExportRunReport,
  buildHardeningDiagnostics,
  buildRecentItemResults,
  buildRunSummary,
  classifyScannerError,
  evaluateCounterInvariant,
  getOperatorStatusMessage,
  normalizeScannerViewState,
  type ScannerErrorCategory
} from "./wholeProfileHarvest/hardening.js";
import { deriveAuthoritativeRunnerLock } from "./wholeProfileHarvest/authoritativePopupState.js";
import { createWholeProfileHarvestIdleState, type WholeProfileHarvestQueueItem, type WholeProfileHarvestResult, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";

const NOW = "2026-05-09T20:00:00.000Z";

function baseState(): WholeProfileHarvestState {
  return createWholeProfileHarvestIdleState(NOW);
}

function queueItem(patch: Partial<WholeProfileHarvestQueueItem>): WholeProfileHarvestQueueItem {
  return {
    index: 0,
    aweme_id: "7000000000000000001",
    capture_status: "new",
    status: "new",
    attempts: 0,
    retry_count: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    last_attempt_at: null,
    saved_at: null,
    capture_inbox_item_id: null,
    backend_item_id: null,
    metadata_status: null,
    source_url: null,
    thumbnail_url: null,
    caption: null,
    profile_card_evidence: {},
    ...patch
  };
}

function result(patch: Partial<WholeProfileHarvestResult>): WholeProfileHarvestResult {
  const base: WholeProfileHarvestResult = {
    index: 0,
    aweme_id: "7000000000000000001",
    status: "extracted",
    stage: null,
    attempts: 1,
    checkpoint_sequence: null,
    error: null,
    error_code: null,
    error_message: null,
    modal_opened: true,
    modal_id_matched: true,
    metrics_extracted: true,
    payload_built: true,
    backend_called: true,
    backend_status: 200,
    backend_error_code: null,
    capture_inbox_item_id: "item_1",
    target_url: null,
    data_integrity_status: "passed",
    profile_card_evidence: {},
    started_at: NOW,
    completed_at: NOW,
    like_count: null,
    comment_count: null,
    favorite_count: null,
    share_count: null,
    duration_text: "00:10",
    posted_text: "1 ngày trước",
    posted_display: "1 ngày trước",
    caption: "caption",
    thumbnail_url: null,
    duration_seconds: null,
    current_modal_id_before: null,
    current_modal_id_after: null,
    extracted_aweme_id: patch.aweme_id ?? "7000000000000000001"
  };
  return { ...base, ...patch };
}

const categoryCases: Array<[unknown, ScannerErrorCategory, boolean]> = [
  ["captcha_required", "safety_captcha", true],
  ["login_required", "safety_login", true],
  ["security checkpoint", "safety_security", true],
  ["tab_context_lost", "tab_context_lost", true],
  ["modal_open_failed", "modal_open_failed", true],
  ["modal_scheduler_mismatch aweme mismatch", "modal_aweme_mismatch", true],
  ["extract failed", "extraction_failed", true],
  ["required_metrics_missing", "metadata_incomplete", true],
  ["finalized metadata mismatch", "finalized_metadata_mismatch", true],
  ["payload blocked by guard", "payload_guard_failed", true],
  ["secret debug leak", "secret_debug_leakage", true],
  ["backend network timeout", "backend_network_error", true],
  ["backend schema 422", "backend_schema_error", false],
  ["backend_verify not_found", "backend_verify_failed", true],
  ["duplicate", "duplicate_detected", false],
  ["no_pending", "no_pending", false],
  ["pause requested", "pause_requested", true],
  ["running_heartbeat_stale", "stale_recovered", true],
  ["unmapped", "unknown", true]
];

for (const [input, expectedCategory, retryable] of categoryCases) {
  const mapped = classifyScannerError(input);
  assert.equal(mapped.category, expectedCategory, `classifies ${String(input)}`);
  assert.equal(mapped.retryable, retryable, `retryable flag for ${expectedCategory}`);
  assert.ok(mapped.operator_message.length > 0, `operator message for ${expectedCategory}`);
  assert.ok(mapped.next_action.length > 0, `next action for ${expectedCategory}`);
  assert.equal(typeof mapped.should_stop_batch, "boolean", `stop flag for ${expectedCategory}`);
}

{
  const normalized = normalizeScannerViewState({
    ...baseState(),
    status: "completed",
    phase: "batch_failed",
    workflow: { ...baseState().workflow, action_lock: "collect_videos", active_task: null }
  });
  assert.equal(normalized.diagnostics.state_normalized, true);
  assert.equal(normalized.diagnostics.impossible_state_detected, true);
  assert.equal(normalized.diagnostics.impossible_state_repaired, true);
  assert.equal(normalized.state.status, "failed");
}

{
  const state: WholeProfileHarvestState = {
    ...baseState(),
    status: "paused",
    harvest: { ...baseState().harvest, status: "paused", pause_message: "Đã tạm dừng an toàn." }
  };
  const message = getOperatorStatusMessage(state);
  assert.equal(message.level, "warning");
  assert.match(message.message, /tạm dừng|Đã tạm dừng/i);
  assert.equal(message.diagnostics.operator_message, message.message);
}

{
  const state: WholeProfileHarvestState = {
    ...baseState(),
    harvest: {
      ...baseState().harvest,
      pause_message: "Return to the Douyin tab to continue collecting."
    },
    profile_scan: {
      ...baseState().profile_scan,
      diagnostics: {
        diagnostics_channel: "scan_authority_diagnostics",
        trace_collect_tab_inactive_evidence: "target_tab_inactive",
        trace_collect_tab_inactive_state: "inactive"
      }
    },
    collect_job: {
      ...baseState().collect_job,
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
  const runnerLock = deriveAuthoritativeRunnerLock(state, Date.parse("2030-05-07T11:43:40.000Z"));
  assert.equal(runnerLock.active, true);
  assert.equal(runnerLock.diagnostics.trace_ui_canonical_state, "waiting_for_active_tab");
  const message = getOperatorStatusMessage(state);
  assert.equal(message.level, "warning");
  assert.equal(message.message, "Return to the Douyin tab to continue collecting.");
  assert.equal(message.next_step, "Return to the Douyin tab, then press Resume if collection does not continue automatically.");
}

{
  const state = {
    ...baseState(),
    run_id: "run_1",
    profile_url: "https://www.douyin.com/user/MS4wLjAB",
    capture_session_id: "session_1",
    harvest: {
      ...baseState().harvest,
      processed: 4,
      updated: 2,
      skipped: 1,
      failed: 1,
      pending: 3,
      queue: [
        queueItem({ status: "complete", capture_inbox_item_id: "item_1" }),
        queueItem({ aweme_id: "7000000000000000002", status: "backend_verified" }),
        queueItem({ aweme_id: "7000000000000000003", status: "retry" })
      ]
    },
    debug: { ...baseState().debug, last_response_summary: { requested_batch_limit: 10, effective_batch_limit: 10, batch_stop_reason: "batch_limit_reached" } }
  };
  const summary = buildRunSummary(state);
  assert.equal(summary.run_id, "run_1");
  assert.equal(summary.requested_limit, 10);
  assert.equal(summary.effective_limit, 10);
  assert.equal(summary.processed_count, 4);
  assert.equal(summary.saved_count, 2);
  assert.equal(summary.verified_count, 2);
  assert.equal(summary.skipped_count, 1);
  assert.equal(summary.retry_count, 1);
  assert.equal(summary.failed_count, 1);
  assert.equal(summary.pending_remaining, 3);
  assert.equal(summary.stop_reason, "batch_limit_reached");
}

{
  const state = {
    ...baseState(),
    profile_scan: {
      ...baseState().profile_scan,
      target_details: [{ aweme_id: "7000000000000000001", caption: "profile caption", title: null, posted_text: "hôm qua", duration_text: "00:08" } as any]
    },
    harvest: {
      ...baseState().harvest,
      results: Array.from({ length: 12 }, (_, index) => result({ aweme_id: `70000000000000000${String(index).padStart(2, "0")}`, caption: `caption ${index}` }))
    }
  };
  const recent = buildRecentItemResults(state);
  assert.equal(recent.length, 10);
  assert.equal(recent[0]?.aweme_id, "7000000000000000002");
  assert.equal(recent.at(-1)?.status, "saved");
  assert.ok(!JSON.stringify(recent).includes("raw_dom"));
}

{
  const state = {
    ...baseState(),
    harvest: {
      ...baseState().harvest,
      pending: 3,
      queue: [
        queueItem({ status: "new", capture_status: "new" }),
        queueItem({ aweme_id: "7000000000000000002", status: "incomplete", capture_status: "incomplete" }),
        queueItem({ aweme_id: "7000000000000000003", status: "retry", capture_status: "failed" }),
        queueItem({ aweme_id: "7000000000000000004", status: "complete", capture_status: "complete", capture_inbox_item_id: "item_4" })
      ]
    }
  };
  const invariant = evaluateCounterInvariant(state, NOW);
  assert.equal(invariant.counters.newCount, 1);
  assert.equal(invariant.counters.incompleteCount, 1);
  assert.equal(invariant.counters.retryCount, 1);
  assert.equal(invariant.counters.queueCount, 3);
  assert.equal(invariant.counters.alreadyCollectedCount, 1);
  assert.equal(invariant.diagnostics.counter_invariant_passed, true);
}

{
  const state: WholeProfileHarvestState = {
    ...baseState(),
    profile_url: "https://www.douyin.com/user/MS4wLjAB",
    capture_session_id: "session_1",
    harvest: {
      ...baseState().harvest,
      queue: [queueItem({ status: "retry", last_error: "backend network timeout", attempts: 2 })],
      results: [result({ status: "failed", error_code: "backend_network_error", error_message: "network failed", capture_inbox_item_id: null })]
    },
    safety: { ...baseState().safety, safety_status: "safe", safety_reason: null }
  };
  const report = buildExportRunReport(state, NOW);
  const serialized = JSON.stringify(report);
  assert.equal(report.schema_version, "douyin_extension_run_report.v1");
  assert.equal(report.diagnostics.export_report_available, true);
  assert.equal(report.diagnostics.export_report_sanitized, true);
  assert.ok(report.diagnostics.export_report_size_bytes > 0);
  assert.ok(!/token|cookie|raw_dom|raw_script|headers|debug_payload/i.test(serialized));
  assert.equal(report.recent_item_results.length, 1);
  assert.equal(report.failures.length, 1);
}

{
  const state = {
    ...baseState(),
    last_error: { code: "backend_schema_rejected", message: "schema 422" },
    harvest: { ...baseState().harvest, pending: 0 }
  };
  const diagnostics = buildHardeningDiagnostics(state, NOW);
  assert.equal(diagnostics.last_run_summary_available, true);
  assert.equal(diagnostics.last_error_category, "backend_schema_error");
  assert.equal(diagnostics.last_error_retryable, false);
  assert.equal(diagnostics.export_report_available, true);
  assert.equal(diagnostics.operator_message_level, "error");
}

console.log("wholeProfileHarvest.hardening.test passed");
