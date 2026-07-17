import { getWholeProfileHarvestReadiness, type WholeProfileHarvestReadiness } from "./readiness.js";
import type { WholeProfileHarvestState } from "./state.js";

export function wholeProfileProgressSummary(
  state: WholeProfileHarvestState,
  readiness: WholeProfileHarvestReadiness = getWholeProfileHarvestReadiness(state)
): Record<string, string> {
  const currentHarvestTarget = state.harvest.current_aweme_id ?? state.dry_run.sampled_aweme_ids[state.dry_run.current_index] ?? "none";
  const batchLimit = state.harvest.batch_limit === "all" ? "all" : String(state.harvest.batch_limit);
  const previewRows = state.harvest.queue_preview.slice(0, 10).map((item) => `#${item.index + 1} ${item.aweme_id} · ${item.capture_status}`).join("\n") || "none";
  const failureSummary = state.harvest.failure_summary;
  const topFailure = failureSummary?.top_failure_reasons[0] ? `${failureSummary.top_failure_reasons[0].code} x ${failureSummary.top_failure_reasons[0].count}` : "none";
  const recentRows = state.harvest.results.slice(-10).map((result) => {
    const label = result.status === "extracted" ? "EXTRACTED" : result.status === "skipped" ? "SKIP" : "FAIL";
    const detail = result.status === "extracted" ? result.source_used ?? "modal_extract" : result.error_code ?? result.error ?? "none";
    return `#${result.index} ${label} · ${detail} · aweme ${result.aweme_id} · stage ${result.stage ?? "none"}`;
  }).join("\n") || "none";
  const lastError = typeof state.last_error === "string" ? state.last_error : state.last_error ? `${state.last_error.code}: ${state.last_error.message}` : "none";
  const responseSummary = typeof state.debug.last_response_summary === "object" && state.debug.last_response_summary ? state.debug.last_response_summary as Record<string, unknown> : null;
  const requestSummary = typeof state.debug.last_request_summary === "object" && state.debug.last_request_summary ? state.debug.last_request_summary as Record<string, unknown> : null;
  const collectJob = state.collect_job;
  const runtime = state.active_collect_runtime;
  const activeCollectJob = Boolean(
    collectJob.runner_ack_at
    && !collectJob.lock_released
    && ["running", "running_tab_inactive", "waiting_for_active_tab", "paused_tab_inactive", "recovering"].includes(collectJob.state)
  );
  const activeRuntimeAuthority = Boolean(
    runtime.job_id
    && runtime.job_id === collectJob.job_id
    && ["starting", "running", "waiting_for_modal", "waiting_for_extract", "waiting_for_backend_write", "waiting_for_post_batch_summary", "waiting_for_active_tab", "paused_tab_inactive"].includes(runtime.canonical_state)
  );
  const activeBatchCollect = activeCollectJob || activeRuntimeAuthority;
  const visibleStatus = activeBatchCollect
    ? activeRuntimeAuthority && runtime.canonical_state === "waiting_for_active_tab"
      ? "waiting_for_active_tab"
      : activeRuntimeAuthority && runtime.canonical_state === "paused_tab_inactive"
        ? "paused_tab_inactive"
        : "collecting"
    : state.status;
  const visiblePhase = activeBatchCollect
    ? activeRuntimeAuthority
      ? runtime.canonical_state
      : collectJob.current_step || collectJob.state || "running"
    : state.phase;
  const backendCaptureSession = state.harvest.backend.capture_session;
  const payloadPreview = state.harvest.backend.payload_preview;
  const oneItemFlush = state.harvest.backend.one_item_flush;
  const batchFlush = state.harvest.backend.batch_flush;
  const captureSession = backendCaptureSession.session_id ? `${backendCaptureSession.status}:${backendCaptureSession.session_id.slice(0, 8)}` : backendCaptureSession.status;
  const captureSessionFailure = backendCaptureSession.status === "failed" ? `${String(responseSummary?.url ?? requestSummary?.url ?? "unknown_url")} status=${String(responseSummary?.status ?? "unknown")} code=${String(backendCaptureSession.error_code ?? responseSummary?.error_code ?? "unknown")}` : "none";
  const payloadPreviewSummary = payloadPreview.target_aweme_id
    ? `${payloadPreview.status} · aweme ${payloadPreview.target_aweme_id} · removed ${payloadPreview.removed_fields.length}`
    : payloadPreview.status;
  const payloadGuardSummary = !payloadPreview.guard
    ? "none"
    : payloadPreview.guard.ok
      ? "ok"
      : `${payloadPreview.guard.code ?? "payload_contains_disallowed_field_local"} · ${payloadPreview.guard.offending_paths.join(",") || payloadPreview.guard.path || "unknown"}`;
  const captchaSummary = !state.safety.captcha_detected
    ? "none"
    : [
      state.safety.captcha_reason ?? "captcha_detected",
      state.safety.checkpoint_detected ? "checkpoint" : null,
      state.safety.login_required ? "login_required" : null,
      state.safety.abnormal_traffic_detected ? "abnormal_traffic" : null
    ].filter(Boolean).join(" · ");
  const delaySummary = state.safety.last_delay_ms === null
    ? "none"
    : `${state.safety.last_delay_ms}ms · started ${state.safety.last_delay_started_at ?? "unknown"} · completed ${state.safety.last_delay_completed_at ?? "pending"}`;
  const scheduledPauseSummary = state.safety.scheduled_pause_active
    ? `active until ${state.safety.scheduled_pause_until ?? "unknown"}`
    : state.safety.last_scheduled_pause_ms === null
      ? "none"
      : `${state.safety.last_scheduled_pause_ms}ms · last pause at ${state.safety.last_pause_at ?? "unknown"}`;
  const tabHealthSummary = `${state.safety.tab_health.status} · ${state.safety.tab_health.page_type ?? "unknown"} · ${state.safety.tab_health.current_url ?? "unknown_url"}`;
  const resumeCheckSummary = `${state.safety.resume_check.status} · blocked=${state.safety.resume_check.blocked_reason ?? "none"}`;
  const oneItemFlushSummary = activeBatchCollect
    ? `quarantined during active batch · legacy ${oneItemFlush.status}`
    : oneItemFlush.capture_inbox_item_id
      ? `${oneItemFlush.status} · item ${oneItemFlush.capture_inbox_item_id}`
      : oneItemFlush.status;
  const oneItemVerifySummary = activeBatchCollect
    ? "quarantined during active batch"
    : oneItemFlush.item_created_or_updated === null
      ? oneItemFlush.verify_status
      : `${oneItemFlush.verify_status} · created_or_updated=${oneItemFlush.item_created_or_updated ? "yes" : "no"}`;
  const oneItemErrorSummary = activeBatchCollect
    ? "quarantined during active batch"
    : !oneItemFlush.error
      ? "none"
      : `${oneItemFlush.error.code ?? "unknown"} · ${oneItemFlush.error.message ?? "unknown"}`;
  const collectJobAttempted = typeof collectJob.attempted_count === "number" ? collectJob.attempted_count : 0;
  const collectJobSucceeded = typeof collectJob.succeeded_count === "number" ? collectJob.succeeded_count : 0;
  const collectJobFailed = typeof collectJob.failed_count === "number" ? collectJob.failed_count : 0;
  const collectJobSkipped = typeof collectJob.skipped_count === "number" ? collectJob.skipped_count : 0;
  const collectJobSelected = typeof collectJob.selected_count === "number" ? collectJob.selected_count : 0;
  const collectJobTerminal = collectJobSucceeded + collectJobFailed + collectJobSkipped;
  const traceOneItemFlushRendered = oneItemFlushSummary;
  const traceBatchFlushRaw = `${batchFlush.status} · ${batchFlush.processed}/${batchFlush.queue_total} processed · ok ${batchFlush.succeeded} · skip ${batchFlush.skipped} · fail ${batchFlush.failed} · pending ${batchFlush.pending}`;
  const batchFlushSummary = activeBatchCollect && batchFlush.status === "idle"
    ? `running · ${collectJobAttempted}/${collectJobSelected} attempted · terminal ${collectJobTerminal}/${collectJobSelected} · ok ${collectJobSucceeded} · skip ${collectJobSkipped} · fail ${collectJobFailed} · step ${collectJob.current_step ?? "running"}`
    : `${batchFlush.status} · ${batchFlush.processed}/${batchFlush.queue_total} processed · ok ${batchFlush.succeeded} · skip ${batchFlush.skipped} · fail ${batchFlush.failed} · pending ${batchFlush.pending}`;
  const batchFlushCurrent = batchFlush.current_aweme_id
    ? `${batchFlush.current_index + 1}/${batchFlush.queue_total} · aweme ${batchFlush.current_aweme_id}`
    : batchFlush.resume_from_index === null
      ? "none"
      : `resume from ${batchFlush.resume_from_index + 1}/${batchFlush.queue_total}`;
  const batchFlushVerifySummary = `${batchFlush.last_verify_status} · last ${batchFlush.last_flushed_aweme_id ?? "none"}`;
  const batchFlushErrorSummary = !batchFlush.last_error_code
    ? "none"
    : `${batchFlush.last_error_code} · ${batchFlush.last_error_message ?? "unknown"}`;
  const diagnosticsRecordByChannel22C13B = (value: unknown, channel: "scan_authority_diagnostics" | "runtime_debug_diagnostics"): Record<string, unknown> => {
    if (!value || typeof value !== "object") return {};
    const record = value as Record<string, unknown>;
    const candidateChannel = typeof record.diagnostics_channel === "string" ? record.diagnostics_channel : null;
    if (candidateChannel == null) return record;
    return candidateChannel === channel ? record : {};
  };
  const scanDiagnostics = {
    ...diagnosticsRecordByChannel22C13B(state.profile_scan.diagnostics, "scan_authority_diagnostics"),
    ...diagnosticsRecordByChannel22C13B(state.verify.diagnostics, "scan_authority_diagnostics")
  };
  const profileDomProbe = scanDiagnostics.profile_dom_probe && typeof scanDiagnostics.profile_dom_probe === "object" ? scanDiagnostics.profile_dom_probe as Record<string, unknown> : null;
  const scanActionTrace = scanDiagnostics.scan_profile_action_trace && typeof scanDiagnostics.scan_profile_action_trace === "object" ? scanDiagnostics.scan_profile_action_trace as Record<string, unknown> : null;
  const diagnosticString = (key: string): string => {
    const value = scanDiagnostics[key];
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "none";
  };
  const domProbeMessage = diagnosticString("profile_dom_probe_message") !== "none" ? diagnosticString("profile_dom_probe_message") : diagnosticString("dom_probe_message_result");
  const domProbeStatus = domProbeMessage === "ok" && diagnosticString("profile_dom_probe_completed_at") !== "none"
    ? "completed"
    : diagnosticString("profile_dom_probe_status") !== "none"
      ? diagnosticString("profile_dom_probe_status")
      : ["failed", "timeout", "error"].some((value) => domProbeMessage.toLowerCase().includes(value))
        ? (domProbeMessage.toLowerCase().includes("timeout") ? "timeout" : "failed")
        : diagnosticString("profile_dom_probe_started_at") !== "none" ? "started" : "not_attempted";
  const authoritativeStopReason = (() => {
    const value = scanDiagnostics.scan_stop_authoritative;
    return typeof value === "string" && value.trim() ? value : "none";
  })();

  return {
    Status: visibleStatus,
    Phase: visiblePhase,
    "Profile URL": state.profile_url ?? "not verified",
    "Verified targets": String(state.verify.verified_target_count),
    "Accepted / rejected": `${state.verify.accepted_target_count} / ${state.verify.rejected_target_count}`,
    "Scan rounds": String(state.verify.scan_rounds),
    "Stop reason": authoritativeStopReason,
    "Scroll container": state.verify.scroll_container_found ? "found" : "not found",
    "Profile DOM probe status": domProbeStatus,
    "Scan action trace version": String(scanDiagnostics.scan_action_trace_version ?? scanActionTrace?.traceVersion ?? "none"),
    "Popup route hit": String(scanDiagnostics.popup_route_hit ?? (scanActionTrace?.popupHandlerName ? "yes" : "none")),
    "Background route hit": String(scanDiagnostics.background_route_hit ?? scanActionTrace?.backgroundHandlerName ?? "none"),
    "Controller route hit": String(scanDiagnostics.controller_route_hit ?? (scanActionTrace?.controllerName ? "yes" : "none")),
    "Tab resolved": String(scanActionTrace?.tabResolveResult ?? "none"),
    "Content script ping": String(scanActionTrace?.contentPingResult ?? "none"),
    "Content injection": String(scanActionTrace?.contentInjectionResult ?? "none"),
    "Profile grid ready": scanDiagnostics.scan_grid_ready === true ? "yes" : scanDiagnostics.scan_grid_ready === false ? "no" : "unknown",
    "Profile grid selector": String(profileDomProbe?.profileGridSelector ?? "none"),
    "Video anchor count": String(scanDiagnostics.video_link_count ?? profileDomProbe?.videoAnchorCount ?? "unknown"),
    "Aweme id count": String(profileDomProbe?.awemeIdCount ?? "unknown"),
    "Grid card candidate count": String(scanDiagnostics.grid_card_candidate_count ?? profileDomProbe?.gridCardCandidateCount ?? "unknown"),
    "Scroll container found": profileDomProbe?.scrollContainerFound === true ? "yes" : profileDomProbe?.scrollContainerFound === false ? "no" : "unknown",
    "Profile discovered count": diagnosticString("profile_discovered_count"),
    "Profile normalized count": diagnosticString("profile_normalized_count"),
    "Profile duplicate count": diagnosticString("profile_duplicate_count"),
    "Profile invalid count": diagnosticString("profile_invalid_count"),
    "Profile already collected count": diagnosticString("profile_already_collected_count"),
    "Profile eligible count": diagnosticString("profile_eligible_count"),
    "Expected profile video count": diagnosticString("expected_profile_video_count"),
    "Expected profile video count source": diagnosticString("expected_profile_video_count_source"),
    "Expected profile video count raw text": diagnosticString("expected_profile_video_count_raw_text"),
    "Expected profile video count parse ok": diagnosticString("expected_profile_video_count_parse_ok"),
    "Missing profile video count": diagnosticString("missing_profile_video_count"),
    "Profile scan completion ratio": diagnosticString("profile_scan_completion_ratio"),
    "Profile scan incomplete reason": diagnosticString("profile_scan_incomplete_reason"),
    "Profile queue total count": diagnosticString("profile_queue_total_count"),
    "Profile batch limit": diagnosticString("profile_batch_limit"),
    "Profile batch pending count": diagnosticString("profile_batch_pending_count"),
    "Profile batch mode": diagnosticString("profile_batch_mode"),
    "Profile queue limit reason": diagnosticString("profile_queue_limit_reason"),
    "Scan fallback used": diagnosticString("scan_fallback_used"),
    "Scan fallback reason": diagnosticString("scan_fallback_reason"),
    "Scan queue builder used": diagnosticString("scan_queue_builder_used"),
    "Scan no-round reason": String(scanDiagnostics.scan_no_round_reason ?? "none"),
    "Legacy route invoked": String(scanDiagnostics.legacy_route_invoked ?? scanDiagnostics.legacy_scan_profile_route_invoked ?? "none"),
    "Legacy route delegated": String(scanDiagnostics.legacy_route_delegated ?? scanDiagnostics.legacy_scan_profile_delegated_to_canonical ?? "none"),
    "Dry-run mode": state.dry_run.mode ?? "none",
    "Dry-run pass/fail": `${state.dry_run.pass} / ${state.dry_run.fail}`,
    "Harvest status": state.harvest.status,
    "Layer profile_scan/dry_run/harvest": `${readiness.profile_scan_ready ? "yes" : "no"} / ${readiness.dry_run_ready ? "yes" : "no"} / ${readiness.extraction_ready ? "yes" : "no"}`,
    "Profile scan ready": readiness.profile_scan_ready ? "yes" : "no",
    "Dry-run ready": readiness.dry_run_ready ? "yes" : "no",
    "Extraction ready": readiness.extraction_ready ? "yes" : "no",
    "Harvest mode": state.harvest_options.mode,
    "Harvest batch": state.harvest_options.batch,
    "Harvest speed": state.harvest_options.speed,
    "Unattended safe mode": state.harvest_options.unattended_safe_mode ? "on" : "off",
    "Harvest batch limit": batchLimit,
    "Harvest current target": `${state.harvest.current_index || 0} / ${state.harvest.queue.length}`,
    "Current target": currentHarvestTarget,
    "Harvest extracted/skipped/failed": `${state.harvest.updated} / ${state.harvest.skipped} / ${state.harvest.failed}`,
    "Harvest execution/checkpoints": `${state.harvest.simulation_mode} / ${state.harvest.checkpoint_count}`,
    "Harvest backend writes/pending": `${state.harvest.flushed} / ${state.harvest.pending}`,
    "Harvest resume from": state.harvest.resume_from_index === null ? "none" : String(state.harvest.resume_from_index),
    "Harvest pause message": state.harvest.pause_message ?? "none",
    "Harvest resume available": state.harvest.resume_available ? "yes" : "no",
    "Harvest last safety event": state.harvest.last_safety_event ?? "none",
    "Last checkpoint": state.harvest.last_checkpoint_at ?? "none",
    "Last success": state.harvest.last_success_at ?? "none",
    "Paused reason": state.harvest.paused_reason ?? "none",
    "Safety captcha/checkpoint": captchaSummary,
    "Safety captcha evidence": state.safety.captcha_evidence_text ?? "none",
    "Safety consecutive errors": `${state.safety.consecutive_errors} / ${state.safety.max_consecutive_errors}`,
    "Safety processed since pause": `${state.safety.processed_since_last_pause} / ${state.safety.pause_after_every}`,
    "Safety scheduled pause": scheduledPauseSummary,
    "Safety delay": delaySummary,
    "Safety tab health": tabHealthSummary,
    "Safety resume check": resumeCheckSummary,
    "Capture session": captureSession,
    "Backend session ready": readiness.backend_session_ready ? "yes" : "no",
    "Capture session diagnostics": captureSessionFailure,
    "Payload preview": payloadPreviewSummary,
    "Payload preview ready": readiness.payload_preview_ready ? "yes" : "no",
    "Payload guard": payloadGuardSummary,
    "Payload guard passed": readiness.payload_guard_passed ? "yes" : "no",
    "trace_one_item_diagnostics_quarantined_during_batch": activeBatchCollect ? "yes" : "no",
    "trace_one_item_flush_visible": activeBatchCollect ? "no" : "yes",
    "trace_one_item_flush_value_raw": oneItemFlush.capture_inbox_item_id ? `${oneItemFlush.status} · item ${oneItemFlush.capture_inbox_item_id}` : oneItemFlush.status,
    "trace_one_item_flush_value_rendered": traceOneItemFlushRendered,
    "trace_batch_flush_value_raw": traceBatchFlushRaw,
    "trace_batch_flush_value_rendered": batchFlushSummary,
    "trace_batch_flush_idle_suppressed_during_active_batch": activeBatchCollect && batchFlush.status === "idle" ? "yes" : "no",
    "trace_legacy_state_suppressed_by_batch_runtime": activeBatchCollect ? "yes" : "no",
    "trace_visible_diagnostics_source": activeBatchCollect ? "active_batch_runtime" : "state",
    "One-item flush": oneItemFlushSummary,
    "One-item flush ready": activeBatchCollect ? "quarantined during active batch" : readiness.one_item_flush_ready ? "yes" : "no",
    "One-item verify": oneItemVerifySummary,
    "One-item flush error": oneItemErrorSummary,
    "Batch flush": batchFlushSummary,
    "Batch flush ready": activeBatchCollect && batchFlush.status === "idle" ? "active batch runner owns flush" : readiness.batch_flush_ready ? "yes" : "no",
    "Batch flush current": batchFlushCurrent,
    "Batch flush checkpoints": String(batchFlush.checkpoint_count),
    "Batch flush verify": batchFlushVerifySummary,
    "Batch flush error": batchFlushErrorSummary,
    "Resume ready": readiness.resume_ready ? "yes" : "no",
    "Stop ready": readiness.stop_ready ? "yes" : "no",
    "Next recommended action": `${readiness.next_recommended_action.label} — ${readiness.next_recommended_action.reason}`,
    "Top failure": topFailure,
    "Queue preview": previewRows,
    "Target status unknown/new/incomplete/complete/failed/skipped": `${state.target_status.unknown} / ${state.target_status.new} / ${state.target_status.incomplete} / ${state.target_status.complete} / ${state.target_status.failed} / ${state.target_status.skipped}`,
    "Recent harvest rows": recentRows,
    "Last error": lastError
  };
}
