import { deriveAuthoritativeRunnerLock } from "./authoritativePopupState.js";
import type { WholeProfileHarvestQueueItem, WholeProfileHarvestResult, WholeProfileHarvestState } from "./state.js";

export type ScannerErrorCategory =
  | "safety_captcha"
  | "safety_login"
  | "safety_security"
  | "tab_context_lost"
  | "modal_open_failed"
  | "modal_aweme_mismatch"
  | "extraction_failed"
  | "metadata_incomplete"
  | "finalized_metadata_mismatch"
  | "payload_guard_failed"
  | "secret_debug_leakage"
  | "backend_network_error"
  | "backend_schema_error"
  | "backend_verify_failed"
  | "duplicate_detected"
  | "no_pending"
  | "pause_requested"
  | "stale_recovered"
  | "unknown";

export type OperatorMessageLevel = "info" | "warning" | "error" | "success";
export type RecentItemResultStatus = "saved" | "skipped" | "retry" | "failed" | "incomplete" | "duplicate";

export type ScannerErrorClassification = {
  category: ScannerErrorCategory;
  operator_message: string;
  retryable: boolean;
  should_stop_batch: boolean;
  target_status_after_error: WholeProfileHarvestQueueItem["status"] | null;
  next_action: string;
};

export type OperatorStatusMessage = {
  message: string;
  level: OperatorMessageLevel;
  next_step: string;
  diagnostics: {
    operator_message: string;
    operator_message_level: OperatorMessageLevel;
    operator_next_step: string;
  };
};

export type ScannerNormalizedViewState = {
  state: WholeProfileHarvestState;
  diagnostics: {
    state_normalized: boolean;
    state_normalization_reason: string | null;
    impossible_state_detected: boolean;
    impossible_state_repaired: boolean;
  };
};

export type WholeProfileRunSummary = {
  run_id: string | null;
  profile_url: string | null;
  session_id: string | null;
  started_at: string | null;
  finished_at: string | null;
  requested_limit: number | "all" | null;
  effective_limit: number | "all" | null;
  processed_count: number;
  saved_count: number;
  verified_count: number;
  skipped_count: number;
  retry_count: number;
  failed_count: number;
  pending_remaining: number;
  stop_reason: string | null;
  safety_status: WholeProfileHarvestState["safety"]["safety_status"];
  next_action: string;
};

export type RecentItemResult = {
  aweme_id: string;
  short_caption: string | null;
  status: RecentItemResultStatus;
  backend_item_id: string | null;
  metadata_status: string | null;
  posted_display: string | null;
  duration_text: string | null;
  error: string | null;
  saved_at: string | null;
};

export type CounterInvariantResult = {
  counters: {
    newCount: number;
    incompleteCount: number;
    retryCount: number;
    alreadyCollectedCount: number;
    queueCount: number;
  };
  diagnostics: {
    counter_invariant_passed: boolean;
    counter_invariant_error: string | null;
    counters_reconciled_at: string;
  };
};

export type WholeProfileRunExportReport = {
  schema_version: "douyin_extension_run_report.v1";
  profile_url: string | null;
  session_id: string | null;
  run_summaries: WholeProfileRunSummary[];
  counts: CounterInvariantResult["counters"];
  recent_item_results: RecentItemResult[];
  failures: Array<{ aweme_id: string; error_code: string | null; error: string | null; stage: string | null }>;
  retry_items: Array<{ aweme_id: string; attempts: number; last_error: string | null }>;
  safety_events: Array<{ status: string; reason: string | null; at: string | null }>;
  timestamp: string;
  diagnostics: {
    export_report_available: boolean;
    export_report_sanitized: boolean;
    export_report_size_bytes: number;
  };
};

const CATEGORY_DEFAULTS: Record<ScannerErrorCategory, ScannerErrorClassification> = {
  safety_captcha: { category: "safety_captcha", operator_message: "Douyin đang yêu cầu xác minh. Hãy xử lý trên tab Douyin rồi bấm Resume.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Resolve Douyin verification, then Resume." },
  safety_login: { category: "safety_login", operator_message: "Douyin yêu cầu đăng nhập. Hãy đăng nhập trên tab Douyin rồi bấm Resume.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Log in on Douyin, then Resume." },
  safety_security: { category: "safety_security", operator_message: "Douyin đang chặn bằng kiểm tra bảo mật. Hãy xử lý trên tab Douyin rồi bấm Resume.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Resolve security check, then Resume." },
  tab_context_lost: { category: "tab_context_lost", operator_message: "Không còn kết nối đúng với tab Douyin. Hãy mở lại tab profile rồi bấm Resume.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Reconnect the Douyin tab, then Resume." },
  modal_open_failed: { category: "modal_open_failed", operator_message: "Không mở được video cần lấy. Extension đã dừng an toàn để bạn kiểm tra tab Douyin.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Check Douyin tab and retry the batch." },
  modal_aweme_mismatch: { category: "modal_aweme_mismatch", operator_message: "Video mở ra không đúng với video cần lấy. Extension đã dừng an toàn.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Reconnect tab and retry from the next pending item." },
  extraction_failed: { category: "extraction_failed", operator_message: "Không đọc được metadata video. Video này đã được đưa vào nhóm retry.", retryable: true, should_stop_batch: false, target_status_after_error: "retry", next_action: "Continue with retry queue later." },
  metadata_incomplete: { category: "metadata_incomplete", operator_message: "Metadata video chưa đủ. Video này đã được đưa vào nhóm incomplete/retry.", retryable: true, should_stop_batch: false, target_status_after_error: "incomplete", next_action: "Retry incomplete items later." },
  finalized_metadata_mismatch: { category: "finalized_metadata_mismatch", operator_message: "Metadata đã finalize không khớp video mục tiêu. Extension đã dừng an toàn.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Retry after reconnecting Douyin tab." },
  payload_guard_failed: { category: "payload_guard_failed", operator_message: "Payload bị chặn do chứa dữ liệu debug/raw không an toàn. Video đã được đưa vào retry.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Open Advanced diagnostics and retry after payload cleanup." },
  secret_debug_leakage: { category: "secret_debug_leakage", operator_message: "Payload bị chặn vì có nguy cơ lộ secret/debug. Video đã được đưa vào retry.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Do not continue until payload diagnostics are clean." },
  backend_network_error: { category: "backend_network_error", operator_message: "Không kết nối được Capture Inbox. Video này đã được đưa vào nhóm retry.", retryable: true, should_stop_batch: false, target_status_after_error: "retry", next_action: "Check local API, then retry." },
  backend_schema_error: { category: "backend_schema_error", operator_message: "Capture Inbox từ chối dữ liệu video. Video này đã được đưa vào retry để kiểm tra.", retryable: false, should_stop_batch: true, target_status_after_error: "failed_permanent", next_action: "Open Advanced diagnostics before retrying." },
  backend_verify_failed: { category: "backend_verify_failed", operator_message: "Không xác minh được video trong Capture Inbox. Video này đã được đưa vào nhóm retry.", retryable: true, should_stop_batch: false, target_status_after_error: "retry", next_action: "Retry after backend is healthy." },
  duplicate_detected: { category: "duplicate_detected", operator_message: "Video đã có trong Capture Inbox, extension đã bỏ qua bản trùng.", retryable: false, should_stop_batch: false, target_status_after_error: "duplicate", next_action: "Continue with next pending video." },
  no_pending: { category: "no_pending", operator_message: "Không còn video mới cần lấy trong profile này.", retryable: false, should_stop_batch: false, target_status_after_error: null, next_action: "Scan another profile or change mode." },
  pause_requested: { category: "pause_requested", operator_message: "Extension đã tạm dừng an toàn theo yêu cầu.", retryable: true, should_stop_batch: true, target_status_after_error: null, next_action: "Press Resume when ready." },
  stale_recovered: { category: "stale_recovered", operator_message: "Extension phát hiện phiên chạy bị treo và đã dừng an toàn. Có thể bấm Resume.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Reconnect Douyin tab, then Resume." },
  unknown: { category: "unknown", operator_message: "Extension gặp lỗi chưa phân loại. Hãy mở Advanced diagnostics để kiểm tra.", retryable: true, should_stop_batch: true, target_status_after_error: "retry", next_action: "Open Advanced diagnostics, then retry if safe." }
};

function textOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return [record.code, record.message, record.error, record.reason, record.details].filter(Boolean).map(String).join(" ");
  }
  return value == null ? "" : String(value);
}

export function classifyScannerError(error: unknown): ScannerErrorClassification {
  const text = textOf(error).toLowerCase();
  const category: ScannerErrorCategory =
    text.includes("login_required") ? "safety_login" :
    text.includes("captcha") ? "safety_captcha" :
    text.includes("security") || text.includes("checkpoint") || text.includes("abnormal_traffic") ? "safety_security" :
    text.includes("running_heartbeat_stale") || text.includes("stale") ? "stale_recovered" :
    text.includes("tab_context") || text.includes("not_douyin") || text.includes("tab_missing") || text.includes("blank") ? "tab_context_lost" :
    text.includes("modal_scheduler_mismatch") || text.includes("data_integrity_mismatch") || text.includes("aweme") && text.includes("mismatch") ? "modal_aweme_mismatch" :
    text.includes("modal_navigation_timeout") || text.includes("modal_open") || text.includes("metadata_extraction_timeout") ? "modal_open_failed" :
    text.includes("required_metrics_missing") || text.includes("metadata_incomplete") ? "metadata_incomplete" :
    text.includes("finalized") && text.includes("mismatch") ? "finalized_metadata_mismatch" :
    text.includes("secret") || text.includes("debug") && text.includes("leak") ? "secret_debug_leakage" :
    text.includes("guard") || text.includes("payload") && text.includes("blocked") ? "payload_guard_failed" :
    text.includes("verify") && text.includes("not_found") || text.includes("backend_verify") ? "backend_verify_failed" :
    text.includes("schema") || text.includes("422") ? "backend_schema_error" :
    text.includes("backend") || text.includes("network") || text.includes("timeout") ? "backend_network_error" :
    text.includes("duplicate") ? "duplicate_detected" :
    text.includes("no_pending") ? "no_pending" :
    text.includes("pause") ? "pause_requested" :
    text.includes("extract") ? "extraction_failed" :
    "unknown";
  return CATEGORY_DEFAULTS[category];
}

export function normalizeScannerViewState(state: WholeProfileHarvestState): ScannerNormalizedViewState {
  const reasons: string[] = [];
  let next = state;
  if (next.status === "completed" && next.phase.toLowerCase().includes("failed")) {
    reasons.push("status_completed_phase_failed");
    next = { ...next, status: "failed" };
  }
  if (next.status === "failed" && next.harvest.backend.one_item_flush.verify_status === "verified" && !next.last_error) {
    reasons.push("failed_state_missing_error_after_verified_item");
    next = { ...next, last_error: { code: "unknown", message: "Scanner ended failed after a verified item; review diagnostics." } };
  }
  if (next.workflow.collection.status === "running" && next.workflow.active_task == null) {
    reasons.push("collection_running_without_active_task");
    next = { ...next, workflow: { ...next.workflow, active_task: "collect_videos", action_lock: next.workflow.action_lock ?? "collect_videos" } };
  }
  if (next.workflow.action_lock && next.workflow.active_task == null && next.workflow.collection.status === "idle") {
    reasons.push("orphan_action_lock");
    next = { ...next, workflow: { ...next.workflow, action_lock: null } };
  }
  if (next.harvest.backend.capture_session.status === "ready" && !next.capture_session_id && !next.harvest.backend.capture_session.session_id) {
    reasons.push("backend_session_ready_without_session_id");
    next = { ...next, harvest: { ...next.harvest, backend: { ...next.harvest.backend, capture_session: { ...next.harvest.backend.capture_session, status: "failed", error_code: "session_missing_after_ready", error_message: "Backend session was marked ready without a session id." } } } };
  }
  if (next.harvest.backend.payload_preview.status === "ready" && !next.harvest.backend.payload_preview.payload) {
    reasons.push("payload_preview_ready_without_payload");
    next = { ...next, harvest: { ...next.harvest, backend: { ...next.harvest.backend, payload_preview: { ...next.harvest.backend.payload_preview, status: "missing_result" } } } };
  }
  if ((next.status === "completed" || next.harvest.status === "completed") && next.harvest.current_aweme_id) {
    reasons.push("completed_with_current_aweme");
    next = { ...next, harvest: { ...next.harvest, current_aweme_id: null } };
  }
  return {
    state: next,
    diagnostics: {
      state_normalized: reasons.length > 0,
      state_normalization_reason: reasons.join(",") || null,
      impossible_state_detected: reasons.length > 0,
      impossible_state_repaired: reasons.length > 0
    }
  };
}

export function buildRunSummary(state: WholeProfileHarvestState): WholeProfileRunSummary {
  const response = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object" ? state.debug.last_response_summary as Record<string, unknown> : {};
  const retryCount = state.harvest.queue.filter((item) => item.status === "retry" || item.status === "failed_recoverable").length;
  const verifiedCount = state.harvest.queue.filter((item) => item.status === "backend_verified" || item.status === "complete" || item.capture_inbox_item_id).length;
  const stopReason = typeof response.batch_stop_reason === "string" ? response.batch_stop_reason : state.harvest.paused_reason ?? state.harvest.backend.batch_flush.last_error_code ?? null;
  return {
    run_id: state.run_id,
    profile_url: state.profile_url,
    session_id: state.capture_session_id ?? state.harvest.backend.capture_session.session_id,
    started_at: state.harvest.started_at ?? state.started_at,
    finished_at: state.harvest.updated_at ?? state.updated_at,
    requested_limit: typeof response.requested_batch_limit === "number" ? response.requested_batch_limit : state.harvest_options.batch_limit,
    effective_limit: typeof response.effective_batch_limit === "number" ? response.effective_batch_limit : state.harvest.batch_limit,
    processed_count: state.harvest.processed,
    saved_count: state.harvest.updated,
    verified_count: verifiedCount,
    skipped_count: state.harvest.skipped,
    retry_count: retryCount,
    failed_count: state.harvest.failed,
    pending_remaining: state.harvest.pending,
    stop_reason: stopReason,
    safety_status: state.safety.safety_status,
    next_action: getOperatorStatusMessage(state).next_step
  };
}

function resultStatus(result: WholeProfileHarvestResult): RecentItemResultStatus {
  if (result.capture_inbox_item_id) return "saved";
  if (result.status === "skipped") return "skipped";
  if (result.error_code?.includes("duplicate")) return "duplicate";
  if (result.error_code?.includes("required_metrics") || result.error_code?.includes("metadata")) return "incomplete";
  if (result.status === "failed") return classifyScannerError(result.error_code ?? result.error ?? result.error_message).retryable ? "retry" : "failed";
  return "incomplete";
}

export function buildRecentItemResults(state: WholeProfileHarvestState): RecentItemResult[] {
  const detailsByAweme = new Map(state.profile_scan.target_details.map((item) => [item.aweme_id, item]));
  return state.harvest.results.slice(-10).map((result) => {
    const detail = detailsByAweme.get(result.aweme_id);
    return {
      aweme_id: result.aweme_id,
      short_caption: (result.caption ?? detail?.caption ?? detail?.title ?? null)?.slice(0, 80) ?? null,
      status: resultStatus(result),
      backend_item_id: result.capture_inbox_item_id ?? null,
      metadata_status: result.capture_inbox_item_id ? "verified" : result.metrics_extracted ? "extracted" : "missing",
      posted_display: result.posted_display ?? result.posted_text ?? detail?.posted_text ?? null,
      duration_text: result.duration_text ?? detail?.duration_text ?? null,
      error: result.error_message ?? result.error ?? null,
      saved_at: result.capture_inbox_item_id ? result.completed_at : null
    };
  });
}

export function evaluateCounterInvariant(state: WholeProfileHarvestState, at = new Date().toISOString()): CounterInvariantResult {
  const alreadyCollectedCount = state.harvest.queue.filter((item) => item.status === "backend_verified" || item.status === "complete" || item.status === "already_collected" || Boolean(item.capture_inbox_item_id)).length;
  const retryCount = state.harvest.queue.filter((item) => item.status === "retry" || item.status === "failed_recoverable").length;
  const incompleteCount = state.harvest.queue.filter((item) => item.status === "incomplete" || item.status === "needs_metadata" || item.capture_status === "incomplete").length;
  const newCount = state.harvest.queue.filter((item) => {
    if (item.status === "backend_verified" || item.status === "complete" || item.status === "already_collected" || Boolean(item.capture_inbox_item_id)) return false;
    if (item.status === "retry" || item.status === "failed_recoverable") return false;
    if (item.status === "incomplete" || item.status === "needs_metadata" || item.capture_status === "incomplete") return false;
    return item.status === "new" || item.status === "pending" || item.capture_status === "new";
  }).length;
  const queueCount = newCount + incompleteCount + retryCount;
  const displayedPending = state.harvest.pending;
  const passed = queueCount === displayedPending || displayedPending === 0 || state.harvest.status === "completed";
  return {
    counters: { newCount, incompleteCount, retryCount, alreadyCollectedCount, queueCount },
    diagnostics: {
      counter_invariant_passed: passed,
      counter_invariant_error: passed ? null : `queue=${queueCount} pending=${displayedPending}`,
      counters_reconciled_at: at
    }
  };
}

export function getOperatorStatusMessage(state: WholeProfileHarvestState): OperatorStatusMessage {
  const runnerLock = deriveAuthoritativeRunnerLock(state);
  const canonicalUiState = String(runnerLock.diagnostics.trace_ui_canonical_state ?? "idle");
  const waitingForActiveTab = canonicalUiState === "waiting_for_active_tab";
  const pausedTabInactive = canonicalUiState === "paused_tab_inactive";
  const paused = state.status === "paused" || state.harvest.status === "paused";
  let message: string;
  let level: OperatorMessageLevel = "info";
  let nextStep = "Continue the workflow.";
  if (state.safety.safety_user_action_required || state.safety.captcha_detected) {
    const category = state.safety.login_required ? "safety_login" : state.safety.checkpoint_detected ? "safety_security" : "safety_captcha";
    const mapped = CATEGORY_DEFAULTS[category];
    message = mapped.operator_message;
    level = "warning";
    nextStep = mapped.next_action;
  } else if (state.safety.safety_status === "stale") {
    const mapped = CATEGORY_DEFAULTS.stale_recovered;
    message = mapped.operator_message;
    level = "warning";
    nextStep = mapped.next_action;
  } else if (state.phase === "blocked" || state.debug.last_action_result === "blocked") {
    const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
      ? state.debug.last_response_summary as Record<string, unknown>
      : {};
    const blockedReason = typeof summary.start_collecting_blocked_reason === "string"
      ? summary.start_collecting_blocked_reason
      : null;
    const raw = typeof state.last_error === "string"
      ? state.last_error
      : blockedReason ?? "Start Collecting was blocked.";
    message = raw.replace(/^Start Collecting failed:\s*/i, "");
    level = "error";
    nextStep = "Fix the issue above, then press Start Collecting again.";
  } else if (state.phase === "batch_safe_mode_no_pending" || state.debug.last_action_result === "no_pending") {
    const mapped = CATEGORY_DEFAULTS.no_pending;
    message = mapped.operator_message;
    level = "success";
    nextStep = mapped.next_action;
  } else if (state.collect_job.state === "failed" && state.collect_job.last_error) {
    message = state.collect_job.last_error;
    level = "error";
    nextStep = "Fix the issue above, then press Start Collecting again.";
  } else if (state.harvest.status === "failed" && state.last_error) {
    const mapped = classifyScannerError(state.last_error);
    message = typeof state.last_error === "string" ? state.last_error : mapped.operator_message;
    level = "error";
    nextStep = "Fix the issue above, then press Start Collecting again.";
  } else if (state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed" || state.last_error) {
    const mapped = classifyScannerError(state.last_error ?? state.harvest.backend.batch_flush.last_error_code ?? state.harvest.backend.one_item_flush.error?.code);
    message = mapped.operator_message;
    level = mapped.should_stop_batch ? "error" : "warning";
    nextStep = mapped.next_action;
  } else if (state.status === "completed" || state.harvest.status === "completed") {
    message = `Đã lấy xong ${state.harvest.processed} video. Còn ${state.harvest.pending} video trong hàng đợi.`;
    level = "success";
    nextStep = state.harvest.pending > 0 ? "Click Start Collecting again for the next safe batch." : "No pending videos remain.";
  } else if (waitingForActiveTab || pausedTabInactive || paused) {
    message = state.harvest.pause_message ?? "Extension đã tạm dừng an toàn. Có thể bấm Resume khi tab Douyin sẵn sàng.";
    level = "warning";
    nextStep = waitingForActiveTab || pausedTabInactive
      ? "Return to the Douyin tab, then press Resume if collection does not continue automatically."
      : "Press Resume when the Douyin tab is ready.";
  } else {
    message = state.profile_scan.accepted_target_count > 0 ? "Profile đã sẵn sàng. Có thể chạy Start Collecting." : "Hãy Scan Profile để bắt đầu.";
    nextStep = state.profile_scan.accepted_target_count > 0 ? "Start Collecting next safe batch." : "Scan Profile.";
  }
  return { message, level, next_step: nextStep, diagnostics: { operator_message: message, operator_message_level: level, operator_next_step: nextStep } };
}

function sanitizeForReport(value: unknown, depth = 0): unknown {
  if (depth > 5) return "[truncated]";
  if (value == null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") return value.length > 500 ? `${value.slice(0, 500)}…` : value;
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => sanitizeForReport(item, depth + 1));
  if (typeof value === "object") {
    const clean: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      const lower = key.toLowerCase();
      if (["token", "cookie", "authorization", "headers", "raw_dom", "raw_script", "payload", "debug_payload", "secret"].some((blocked) => lower.includes(blocked))) continue;
      clean[key] = sanitizeForReport(child, depth + 1);
    }
    return clean;
  }
  return null;
}

export function buildExportRunReport(state: WholeProfileHarvestState, at = new Date().toISOString()): WholeProfileRunExportReport {
  const counters = evaluateCounterInvariant(state, at);
  const reportWithoutDiagnostics = {
    schema_version: "douyin_extension_run_report.v1" as const,
    profile_url: state.profile_url,
    session_id: state.capture_session_id ?? state.harvest.backend.capture_session.session_id,
    run_summaries: [buildRunSummary(state)],
    counts: counters.counters,
    recent_item_results: buildRecentItemResults(state),
    failures: state.harvest.results.filter((result) => result.status === "failed").slice(-20).map((result) => ({ aweme_id: result.aweme_id, error_code: result.error_code, error: result.error_message ?? result.error, stage: result.stage })),
    retry_items: state.harvest.queue.filter((item) => item.status === "retry" || item.status === "failed_recoverable").slice(0, 50).map((item) => ({ aweme_id: item.aweme_id, attempts: item.attempts, last_error: item.last_error })),
    safety_events: [{ status: state.safety.safety_status, reason: state.safety.safety_reason, at: state.safety.safety_last_checked_at }],
    timestamp: at
  };
  const sanitized = sanitizeForReport(reportWithoutDiagnostics) as Omit<WholeProfileRunExportReport, "diagnostics">;
  const size = JSON.stringify(sanitized).length;
  return { ...sanitized, diagnostics: { export_report_available: true, export_report_sanitized: true, export_report_size_bytes: size } };
}

export function buildHardeningDiagnostics(state: WholeProfileHarvestState, at = new Date().toISOString()): Record<string, unknown> {
  const normalized = normalizeScannerViewState(state);
  const operator = getOperatorStatusMessage(normalized.state);
  const summary = buildRunSummary(normalized.state);
  const recent = buildRecentItemResults(normalized.state);
  const counters = evaluateCounterInvariant(normalized.state, at);
  const error = classifyScannerError(normalized.state.last_error ?? normalized.state.harvest.backend.batch_flush.last_error_code ?? null);
  const report = buildExportRunReport(normalized.state, at);
  return {
    ...normalized.diagnostics,
    ...operator.diagnostics,
    last_run_summary_available: true,
    last_run_processed_count: summary.processed_count,
    last_run_saved_count: summary.saved_count,
    last_run_failed_count: summary.failed_count,
    last_run_pending_remaining: summary.pending_remaining,
    last_run_stop_reason: summary.stop_reason,
    recent_item_results_count: recent.length,
    recent_item_results_updated_at: normalized.state.updated_at,
    last_error_category: error.category,
    last_error_retryable: error.retryable,
    last_error_next_action: error.next_action,
    ...counters.diagnostics,
    ...report.diagnostics
  };
}
