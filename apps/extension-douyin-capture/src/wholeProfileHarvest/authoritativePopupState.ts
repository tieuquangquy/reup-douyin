import type { CanonicalScannerPrimaryAction, ScannerActionKey } from "./readiness.js";
import { resolveScannedTotalFromState, mergeScanAuthorityDiagnostics } from "./backendCollectAuthority.js";
import { buildProfileCollectContractFromState } from "./profileCollectContract.js";
import { resolveDisplayedProfileVideoLimit } from "./displayedProfileQueueCap.js";
import { isHybridCollectJobLiveForPresentation } from "./collectDisplaySmoothing.js";
import { partialCollectTileCounts, persistedScanJobTotalsTrustedForStoredProfile } from "./profileContext.js";
import type { WholeProfileHarvestState } from "./state.js";

const RUNNER_LOCK_RECENT_MS = 30 * 1000;
const TERMINAL_COLLECTION_STATES = new Set(["batch_safe_mode_completed", "completed", "failed", "user_paused", "interrupted", "cancelled", "paused", "stuck", "recoverable_stuck", "paused_stale_recovered"]);
const IN_PROGRESS_START_STAGES = new Set(["clicked", "session_verified", "target_selected", "opening_target", "extracting_metadata", "building_payload", "guarding_payload", "verifying_item", "saving_item", "batch_collecting", "after_checkpoint"]);
const BACKEND_ID_ALIASES = ["aweme_id", "source_video_external_id", "video_external_id", "external_id", "metadata_json.extracted_aweme_id", "metadata_json.target_aweme_id", "metadata_json.profile_card_evidence.aweme_id", "raw_payload_json.aweme_id", "raw_payload_json.profile_card_evidence.aweme_id"] as const;
const SCAN_ID_ALIASES = ["aweme_id", "source_video_external_id", "video_external_id", "external_id", "target_aweme_id", "extracted_aweme_id", "source_url.modal_id"] as const;

export type RunnerLockState = {
  active: boolean;
  reason: "collection_running" | null;
  source: string | null;
  diagnostics: Record<string, unknown>;
};

export type AuthoritativeProfileCounters = {
  queue_total: number;
  backend_profile_captured_count: number;
  backend_item_count: number;
  already_collected_in_scan_count: number;
  profile_already_collected_count: number;
  profile_eligible_count: number;
  pending_count: number;
  skipped_saved_targets_count: number;
  applied: boolean;
  diagnostics: Record<string, unknown>;
};

export type ReconciledPopupMetrics = {
  profile: {
    profile_total_count: number;
    already_collected_count: number;
    ready_count: number;
    duplicate_count: number;
    failed_count: number;
    incomplete_count: number;
    need_retry_count: number;
    new_count: number;
    eligible_count: number;
    queue_count: number;
  };
  active_runner: {
    active_runner_remaining_count: number;
    active_runner_current_index: number;
    active_runner_saved_this_run: number;
    active_runner_failed_this_run: number;
    active_runner_skipped_this_run: number;
  };
  diagnostics: Record<string, unknown>;
};

export type SanitizedPopupViewState<T> = T & {
  diagnostics?: Record<string, unknown>;
};

type MutablePopupViewState = {
  primaryAction?: { key?: string; label?: string; enabled?: boolean; disabledReason?: string | null; reason?: string | null; buttonLabel?: string };
  primary_action?: { key?: string; label?: string; enabled?: boolean; reason?: string | null } | null;
  action?: { key?: string; buttonLabel?: string; enabled?: boolean; disabledReason?: string | null; label?: string };
  counts?: { newCount?: number; incompleteCount?: number; failedCount?: number; alreadyCollectedCount?: number; queueCount?: number };
  compact_metrics?: { pending?: number; saved?: number };
  stats_summary?: { metrics?: Array<{ label: string; value: string }> };
  details?: { technical_rows?: Array<{ label: string; value: string }> };
  diagnostics?: Record<string, unknown>;
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function diagnosticsRecordByChannel22C13B(value: unknown, channel: "scan_authority_diagnostics"): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const valueRecord = value as Record<string, unknown>;
  const candidateChannel = typeof valueRecord.diagnostics_channel === "string" ? valueRecord.diagnostics_channel : null;
  if (candidateChannel == null) return valueRecord;
  return candidateChannel === channel ? valueRecord : {};
}

function debugSummary(state: WholeProfileHarvestState): Record<string, unknown> {
  const runtime = state.active_collect_runtime;
  const runtimeSummary = record(runtime.trace.summary);
  const runtimeQueueFiltering = record(runtime.trace.queue_filtering);
  const runtimePerItemWrites = record(runtime.trace.per_item_backend_writes);
  const runtimeTiming = record(runtime.trace.timing);
  const runtimeActive = runtime.job_id !== null && (runtime.canonical_state === "starting" || runtime.canonical_state === "running" || runtime.canonical_state === "waiting_for_active_tab" || runtime.canonical_state === "paused_tab_inactive" || runtime.canonical_state === "recoverable_stuck" || runtime.canonical_state === "start_failed_recoverable");
  const scanAuthorityDiagnostics = {
    ...diagnosticsRecordByChannel22C13B(state.profile_scan.diagnostics, "scan_authority_diagnostics"),
    ...diagnosticsRecordByChannel22C13B(state.verify.diagnostics, "scan_authority_diagnostics")
  };
  return {
    ...scanAuthorityDiagnostics,
    ...(runtimeActive ? {
      ...runtimeSummary,
      trace_canonical_collect_state: runtime.canonical_state,
      trace_collect_job_popup_render_state: runtime.canonical_state,
      trace_collect_job_id: runtime.job_id,
      trace_collect_job_current_step: runtime.current_step,
      trace_collect_job_current_aweme_id: runtime.current_aweme_id,
      trace_collect_job_current_item_index: runtime.current_item_index,
      trace_collect_job_selected_count: runtime.selected_count,
      trace_collect_job_attempted_count: runtime.attempted_count,
      trace_collect_job_succeeded_count: runtime.succeeded_count,
      trace_collect_job_failed_count: runtime.failed_count,
      trace_collect_job_skipped_count: runtime.skipped_count,
      trace_collect_pre_batch_backend_captured: runtime.pre_batch_backend_captured,
      trace_collect_pre_batch_backend_ready: runtime.pre_batch_backend_ready,
      trace_collect_pre_batch_backend_dup: runtime.pre_batch_backend_dup,
      trace_collect_pre_batch_backend_fail: runtime.pre_batch_backend_fail,
      trace_collect_pre_batch_new: runtime.pre_batch_new,
      trace_collect_pre_batch_queue: runtime.pre_batch_queue,
      trace_collect_popup_already_collected: runtime.latest_progress_captured,
      trace_collect_popup_queue: runtime.latest_progress_queue,
      trace_collect_popup_new: runtime.latest_progress_new,
      trace_collect_job_heartbeat_at: runtime.heartbeat_at,
      trace_collect_job_lock_owner: runtime.lock_owner,
      trace_collect_job_lock_expires_at: runtime.lock_expires_at,
      trace_collect_runtime_generation: runtime.runtime_generation,
      trace_collect_runtime_render_generation: runtime.render_generation,
      trace_collect_runtime_last_update_source: runtime.last_update_source,
      queue_filtering: Object.keys(runtimeQueueFiltering).length > 0 ? runtimeQueueFiltering : undefined,
      batch_item_loop_entered: runtimePerItemWrites.batch_item_loop_entered,
      batch_item_loop_selected_count: runtimePerItemWrites.batch_item_loop_selected_count,
      batch_item_loop_attempted_count: runtimePerItemWrites.batch_item_loop_attempted_count,
      batch_item_loop_returned_count: runtimePerItemWrites.batch_item_loop_returned_count,
      batch_item_loop_result_appended_count: runtimePerItemWrites.batch_item_loop_result_appended_count,
      batch_item_loop_exit_reason: runtimePerItemWrites.batch_item_loop_exit_reason,
      batch_item_loop_last_stage: runtimePerItemWrites.batch_item_loop_last_stage,
      batch_item_loop_current_aweme_id: runtimePerItemWrites.batch_item_loop_current_aweme_id,
      batch_item_loop_current_index: runtimePerItemWrites.batch_item_loop_current_index,
      recent_batch_item_results: runtimePerItemWrites.recent_batch_item_results,
      trace_collect_batch_timing_total_ms: runtimeTiming.trace_collect_batch_timing_total_ms,
      trace_collect_batch_timing_avg_item_ms: runtimeTiming.trace_collect_batch_timing_avg_item_ms,
      trace_collect_batch_timing_item_count: runtimeTiming.trace_collect_batch_timing_item_count,
      trace_collect_batch_timing_recent_items: runtimeTiming.trace_collect_batch_timing_recent_items
    } : {})
  };
}

function timestampMs(value: unknown): number | null {
  if (typeof value !== "string" || value.length === 0) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function numberValue(value: unknown, fallback = 0): number {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(numeric) ? Math.max(0, Math.round(numeric)) : fallback;
}

const COLLECT_JOB_KNOWN_ALIVE_STEPS = new Set([
  "starting",
  "runner_acknowledged",
  "queue_filtering",
  "selecting_items",
  "before_item",
  "before_modal_open",
  "opening_modal",
  "modal_opened",
  "extracting",
  "backend_write",
  "after_backend_write",
  "before_safe_delay",
  "safe_delay_waiting",
  "after_safe_delay",
  "before_next_item",
  "waiting_for_modal",
  "waiting_for_extract",
  "waiting_for_backend_write",
  "waiting_for_post_batch_summary",
  "before_post_batch_summary_refresh",
  "post_batch_summary_refresh"
]);

function collectJobLatestBackendCaptured(job: WholeProfileHarvestState["collect_job"], diagnostics: Record<string, unknown>): number | null {
  const candidates = [
    job.post_batch_backend_captured,
    diagnostics.trace_collect_popup_already_collected,
    diagnostics.post_collect_backend_captured_count,
    diagnostics.post_batch_summary_backend_captured_count,
    diagnostics.backend_reconciliation_backend_profile_captured_count,
    diagnostics.session_ribbon_captured_count
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "number" && Number.isFinite(candidate)) return candidate;
  }
  return null;
}

function collectJobProgressSignals(job: WholeProfileHarvestState["collect_job"], diagnostics: Record<string, unknown>): Record<string, boolean> {
  const latestBackendCaptured = collectJobLatestBackendCaptured(job, diagnostics);
  const backendProgress = typeof job.pre_batch_backend_captured === "number" && latestBackendCaptured !== null && latestBackendCaptured > job.pre_batch_backend_captured;
  return {
    attempted_count: job.attempted_count > 0,
    succeeded_count: job.succeeded_count > 0,
    current_item_index: job.current_item_index !== null,
    current_aweme_id: job.current_aweme_id !== null,
    backend_progress: backendProgress,
    runner_ack_selected: Boolean(job.runner_ack_at) && job.selected_count > 0,
    batch_runner_entry_hit: diagnostics.trace_collect_batch_runner_entry_hit === "yes" || diagnostics.batch_runner_called === true,
    collect_started: diagnostics.trace_collect_started === "yes",
    selected_count: job.selected_count > 0,
    recent_item_result: Array.isArray(diagnostics.recent_batch_item_results) && diagnostics.recent_batch_item_results.length > 0
  };
}

function continuationBatchSize(state: WholeProfileHarvestState): number {
  return typeof state.harvest_options.batch_limit === "number"
    ? state.harvest_options.batch_limit
    : typeof state.harvest.batch_limit === "number"
      ? state.harvest.batch_limit
      : 10;
}

function continuationButtonLabel(state: WholeProfileHarvestState): string {
  return `Continue Next ${continuationBatchSize(state)}`;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function activeCollectRuntimeMatchesJob(state: WholeProfileHarvestState): boolean {
  return state.active_collect_runtime.job_id !== null
    && state.collect_job.job_id !== null
    && state.active_collect_runtime.job_id === state.collect_job.job_id;
}

const ACTIVE_COLLECT_JOB_STATES_FOR_DONE = new Set([
  "starting",
  "running",
  "running_tab_inactive",
  "pausing"
]);

/**
 * True when an independent hybrid_collection_done key still proves the job
 * finished. Stale signals from a prior runtime_generation must not block a
 * legitimate continuation restart (same job_id, higher generation).
 */
function hybridDoneSignalIndicatesFailure(outcome: string | null | undefined): boolean {
  const normalized = String(outcome ?? "").toLowerCase();
  return normalized.includes("failed")
    || normalized.includes("all_failed")
    || normalized === "blocked_before_dispatch";
}

export function hybridCollectionDoneSignalProvesTerminal(
  state: WholeProfileHarvestState,
  doneSignal: {
    job_id: string | null;
    runtime_generation?: number;
    completed_at?: string;
    outcome?: string;
  } | null | undefined
): boolean {
  if (!doneSignal?.job_id || !doneSignal.completed_at) return false;
  if (hybridDoneSignalIndicatesFailure(doneSignal.outcome)) return false;
  if (state.collect_job.job_id !== doneSignal.job_id) return false;
  const jobGeneration = state.collect_job.runtime_generation ?? 0;
  if (jobGeneration > (doneSignal.runtime_generation ?? 0)) return false;
  if (ACTIVE_COLLECT_JOB_STATES_FOR_DONE.has(String(state.collect_job.state ?? ""))) return false;
  if (state.collect_job.state === "failed") return false;
  return true;
}

export function collectCompletionOverridesActiveCollectRuntime(state: WholeProfileHarvestState): boolean {
  const lastSummary = state.debug.last_response_summary
    && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const collectJobState = String(state.collect_job.state ?? "");
  return lastSummary.hybrid_collector_completed === "yes"
    || collectJobState === "completed"
    || collectJobState === "failed";
}

/**
 * Merge an independent hybrid_collection_done signal into state so lock
 * derivation unlocks even when a stale writer clobbered collect_job back to
 * "starting" and wiped hybrid_collector_completed from last_response_summary.
 *
 * Also restores Capture Inbox tile authority (tile_already / tile_new) when the
 * done key carries those fields — a late heartbeat can clobber main-state
 * snapshot back to pre-run counts while fossil still shows the correct card
 * totals (production: fossil tile_already=61, UI Already=41).
 *
 * Pure / sync — callers (popup read path) load the done key and pass it in.
 * Only applies when the done signal belongs to the current collect_job and the
 * job has not started a newer generation.
 */
export function applyHybridCollectionDoneOverride(
  state: WholeProfileHarvestState,
  doneSignal: {
    job_id: string | null;
    runtime_generation: number;
    completed_at: string;
    outcome: string;
    tile_already?: number;
    tile_new?: number;
    tile_queue?: number;
    scanned_total?: number;
  } | null | undefined
): WholeProfileHarvestState {
  if (!doneSignal?.job_id || !doneSignal.completed_at) return state;
  if (hybridDoneSignalIndicatesFailure(doneSignal.outcome)) return state;
  if (state.collect_job.job_id !== doneSignal.job_id) return state;
  const jobGeneration = state.collect_job.runtime_generation ?? 0;
  if (jobGeneration > (doneSignal.runtime_generation ?? 0)) return state;
  if (state.collect_job.state === "failed") return state;
  const lastSummary = state.debug.last_response_summary
    && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};

  let next = state;
  const signalAlready = typeof doneSignal.tile_already === "number" && Number.isFinite(doneSignal.tile_already)
    ? Math.max(0, Math.round(doneSignal.tile_already))
    : null;
  if (signalAlready != null) {
    const prior = state.post_scan_counter_snapshot;
    const already = Math.max(signalAlready, prior?.already_collected ?? 0);
    const scanned = Math.max(
      typeof doneSignal.scanned_total === "number" && Number.isFinite(doneSignal.scanned_total) ? doneSignal.scanned_total : 0,
      prior?.scanned_total ?? 0,
      already
    );
    const signalNew = typeof doneSignal.tile_new === "number" && Number.isFinite(doneSignal.tile_new)
      ? Math.max(0, Math.round(doneSignal.tile_new))
      : null;
    const signalQueue = typeof doneSignal.tile_queue === "number" && Number.isFinite(doneSignal.tile_queue)
      ? Math.max(0, Math.round(doneSignal.tile_queue))
      : null;
    // When we had to raise already above the signal (local floor), recompute remainder.
    const tileNew = already === signalAlready && signalNew != null
      ? signalNew
      : Math.max(0, scanned - already);
    const tileQueue = already === signalAlready && signalQueue != null
      ? signalQueue
      : tileNew;
    const tilesRegressed = (prior?.already_collected ?? 0) < already
      || prior?.status !== "applied"
      || (prior?.new ?? 0) !== tileNew
      || (prior?.queue ?? 0) !== tileQueue;
    if (tilesRegressed || prior == null) {
      next = {
        ...next,
        post_scan_counter_snapshot: {
          status: "applied",
          source: "backend_capture_inbox_profile_summary",
          profile_identifier: prior?.profile_identifier
            ?? state.scan_job.profile_identifier
            ?? state.profile_url
            ?? "unknown",
          scanned_total: scanned,
          backend_captured_aweme_ids: prior?.backend_captured_aweme_ids ?? [],
          backend_captured: Math.max(prior?.backend_captured ?? 0, already),
          backend_ready: Math.max(prior?.backend_ready ?? 0, already),
          backend_dup: prior?.backend_dup ?? 0,
          backend_fail: prior?.backend_fail ?? 0,
          already_collected: already,
          incomplete: prior?.incomplete ?? 0,
          need_retry: prior?.need_retry ?? 0,
          new: tileNew,
          queue: tileQueue,
          applied_at: doneSignal.completed_at
        },
        debug: {
          ...next.debug,
          last_response_summary: {
            ...(next.debug.last_response_summary && typeof next.debug.last_response_summary === "object"
              ? next.debug.last_response_summary as Record<string, unknown>
              : {}),
            hybrid_collection_done_tile_override_applied: "yes",
            hybrid_collection_done_tile_already: already,
            hybrid_collection_done_tile_new: tileNew
          }
        }
      };
    }
  }

  const nextSummary = next.debug.last_response_summary
    && typeof next.debug.last_response_summary === "object"
    ? next.debug.last_response_summary as Record<string, unknown>
    : {};
  if (nextSummary.hybrid_collector_completed === "yes" && next.collect_job.state === "completed") return next;
  const signalNew = typeof doneSignal.tile_new === "number" && Number.isFinite(doneSignal.tile_new)
    ? Math.max(0, Math.round(doneSignal.tile_new))
    : null;
  // Genuine continuation: done signal still shows remaining work while job looks active.
  if (ACTIVE_COLLECT_JOB_STATES_FOR_DONE.has(String(next.collect_job.state ?? "")) && signalNew != null && signalNew > 0) {
    return next;
  }
  return {
    ...next,
    collect_job: {
      ...next.collect_job,
      state: next.collect_job.state === "failed" ? "failed" : "completed",
      completed_at: next.collect_job.completed_at ?? doneSignal.completed_at,
      lock_owner: null,
      lock_expires_at: null,
      lock_released: true,
      recoverable: false,
      stale_reason: null,
      last_error: null,
      updated_at: next.collect_job.updated_at ?? doneSignal.completed_at
    },
    active_collect_runtime: {
      ...next.active_collect_runtime,
      job_id: null,
      canonical_state: "idle",
      canonical_phase: null,
      current_step: null,
      current_aweme_id: null,
      current_item_index: null,
      heartbeat_at: null,
      lock_owner: null,
      lock_expires_at: null,
      updated_at: doneSignal.completed_at
    },
    workflow: {
      ...next.workflow,
      active_task: null,
      action_lock: null,
      collection: {
        ...next.workflow.collection,
        status: "idle",
        updated_at: doneSignal.completed_at,
        completed_at: next.workflow.collection.completed_at ?? doneSignal.completed_at,
        last_error: null
      }
    },
    debug: {
      ...next.debug,
      last_response_summary: {
        ...nextSummary,
        hybrid_collector_completed: "yes",
        hybrid_collection_done_override_applied: "yes",
        hybrid_collection_done_outcome: doneSignal.outcome,
        hybrid_collection_done_completed_at: doneSignal.completed_at
      }
    }
  };
}

function activeCollectRuntimeUiAuthority(state: WholeProfileHarvestState, now = Date.now()): {
  active: boolean;
  waitingForActiveTab: boolean;
  pausedTabInactive: boolean;
  label: string;
  canonicalState: WholeProfileHarvestState["active_collect_runtime"]["canonical_state"] | "idle";
  heartbeatAgeMs: number | null;
  lockExpired: boolean;
} {
  const runtime = state.active_collect_runtime;
  const sameJob = activeCollectRuntimeMatchesJob(state);
  const waitingForActiveTab = runtime.canonical_state === "waiting_for_active_tab";
  const pausedTabInactive = runtime.canonical_state === "paused_tab_inactive";
  const runtimeCompletionOverridden = collectCompletionOverridesActiveCollectRuntime(state);
  const runtimeStepActive = sameJob && (
    runtime.canonical_state === "starting"
    || runtime.canonical_state === "running"
    || runtime.canonical_state === "waiting_for_modal"
    || runtime.canonical_state === "waiting_for_extract"
    || runtime.canonical_state === "waiting_for_backend_write"
    || runtime.canonical_state === "waiting_for_post_batch_summary"
    || waitingForActiveTab
    || pausedTabInactive
  );
  const runtimeHeartbeatAt = timestampMs(runtime.heartbeat_at ?? runtime.updated_at);
  const heartbeatAgeMs = runtimeHeartbeatAt === null ? null : Math.max(0, now - runtimeHeartbeatAt);
  const runtimeLockExpiresAt = timestampMs(runtime.lock_expires_at);
  const lockExpired = runtimeLockExpiresAt !== null && runtimeLockExpiresAt <= now;
  const active = !runtimeCompletionOverridden && runtimeStepActive && heartbeatAgeMs !== null && heartbeatAgeMs <= RUNNER_LOCK_RECENT_MS && !lockExpired;
  return {
    active,
    waitingForActiveTab,
    pausedTabInactive,
    label: waitingForActiveTab || pausedTabInactive
      ? "Paused: return to the Douyin tab to continue."
      : "Collecting videos...",
    canonicalState: sameJob ? runtime.canonical_state : "idle",
    heartbeatAgeMs,
    lockExpired
  };
}

function nested(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, key) => record(current)[key], value);
}

function firstId(value: unknown, aliases: readonly string[]): string | null {
  for (const alias of aliases) {
    const candidate = stringValue(nested(value, alias));
    if (candidate) return candidate;
  }
  return null;
}

function awemeFromUrl(value: unknown): string | null {
  const raw = stringValue(value);
  if (!raw) return null;
  const modal = raw.match(/[?&]modal_id=(\d+)/i)?.[1];
  if (modal) return modal;
  return raw.match(/\/video\/(\d+)/i)?.[1] ?? null;
}

function backendVerifyResponse(state: WholeProfileHarvestState): Record<string, unknown> {
  const diagnostics = debugSummary(state);
  const debugVerify = record(diagnostics.verify_response);
  if (Object.keys(debugVerify).length > 0) return debugVerify;
  const oneItemVerify = record(state.harvest.backend.one_item_flush.verify_response);
  if (Object.keys(oneItemVerify).length > 0) return oneItemVerify;
  return {};
}

function backendItemsFromState(state: WholeProfileHarvestState): Array<Record<string, unknown>> {
  const response = backendVerifyResponse(state);
  const items = response.items;
  if (Array.isArray(items)) return items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
  const raw = record(response.raw);
  if (Array.isArray(raw.items)) return raw.items.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"));
  return [];
}

function terminalReached(state: WholeProfileHarvestState, diagnostics: Record<string, unknown>): boolean {
  const candidates = [state.phase, state.status, state.workflow.collection.status, diagnostics.batch_collection_ui_state, diagnostics.start_collecting_stage, diagnostics.last_scanner_result, diagnostics.scan_finalization_result];
  return candidates.some((value) => TERMINAL_COLLECTION_STATES.has(String(value ?? "")));
}

export function deriveAuthoritativeRunnerLock(state: WholeProfileHarvestState, now = Date.now()): RunnerLockState {
  const diagnostics = debugSummary(state);
  const collectJob = state.collect_job;

  // SAFETY: if collect_job is terminal, NEVER return active=true regardless
  // of what active_collect_runtime or debug diagnostics say. This prevents
  // edge cases where stale debug fields (e.g., batch_collection_ui_state,
  // batch_heartbeat_at) cause the popup to stay stuck at "Collecting videos..."
  // after the Hybrid runner completes.  Cast to string to avoid TS narrowing.
  const collectJobTerminalState = collectJob.state as string;
  if (collectJobTerminalState === "completed" || collectJobTerminalState === "failed") {
    return {
      active: false,
      reason: null,
      source: "collect_job_terminal",
      diagnostics: {
        collection_runner_active: "no",
        primary_action_locked_reason: null,
        primary_action_lock_source: "collect_job_terminal",
        trace_collect_job_id: collectJob.job_id,
        trace_collect_job_state: collectJob.state,
        trace_ui_canonical_state: collectJobTerminalState === "completed" ? "completed" : "failed",
        collect_job_terminal_guard: "yes"
      }
    };
  }

  // --- HYBRID COLLECTOR COMPLETION OVERRIDE ---
  // Phase 4 hybrid runner sets hybrid_collector_completed="yes" in
  // debug.last_response_summary AFTER it has written to the backend,
  // cleared the active_collect_runtime, and finalized the collect_job.
  // This field is set AFTER finishPersistentCollectJob + state normalization,
  // so it survives any normalization that might reset collect_job.state.
  // NOTE: diagnostics from debugSummary() does NOT include
  // last_response_summary, so we read it directly from state.
  const lastSummary = state.debug.last_response_summary
    && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  if (lastSummary.hybrid_collector_completed === "yes") {
    return {
      active: false,
      reason: null,
      source: "hybrid_collector_completed_override",
      diagnostics: {
        collection_runner_active: "no",
        primary_action_locked_reason: null,
        primary_action_lock_source: "hybrid_collector_completed_override",
        trace_collect_job_id: collectJob.job_id,
        trace_collect_job_state: collectJob.state,
        trace_ui_canonical_state: "completed",
        hybrid_collector_completed_override: "yes"
      }
    };
  }

  const runtime = state.active_collect_runtime;
  const runtimeUi = activeCollectRuntimeUiAuthority(state, now);
  const runtimeStepSuggestsActive = runtime.canonical_state === "starting"
    || runtime.canonical_state === "running"
    || runtime.canonical_state === "waiting_for_modal"
    || runtime.canonical_state === "waiting_for_extract"
    || runtime.canonical_state === "waiting_for_backend_write"
    || runtime.canonical_state === "waiting_for_post_batch_summary"
    || runtime.canonical_state === "waiting_for_active_tab"
    || runtime.canonical_state === "paused_tab_inactive";
  const runtimeJobMismatch = runtime.job_id !== null
    && collectJob.job_id !== null
    && runtime.job_id !== collectJob.job_id;
  const runtimeFreshOnMismatchedJob = runtimeStepSuggestsActive
    && runtimeJobMismatch
    && runtimeUi.heartbeatAgeMs !== null
    && runtimeUi.heartbeatAgeMs <= RUNNER_LOCK_RECENT_MS
    && !runtimeUi.lockExpired;
  const runtimeCoherenceWarning = runtimeFreshOnMismatchedJob;
  const runtimeCoherenceWarningReason = runtimeCoherenceWarning
    ? "runtime_job_mismatch_with_fresh_heartbeat"
    : runtimeJobMismatch
      ? "runtime_job_mismatch_without_fresh_heartbeat"
      : null;
  const heartbeatNowMs = now;
  const heartbeatNowIso = new Date(heartbeatNowMs).toISOString();
  const heartbeatAt = timestampMs(collectJob.heartbeat_at ?? collectJob.updated_at);
  const heartbeatAgeMs = heartbeatAt === null ? null : Math.max(0, heartbeatNowMs - heartbeatAt);
  const lockExpiresAt = timestampMs(collectJob.lock_expires_at);
  const rawLockExpired = lockExpiresAt !== null && lockExpiresAt <= heartbeatNowMs;
  const startupDeadlineAt = timestampMs(collectJob.startup_deadline_at);
  const startupTimedOut = collectJob.state === "starting" && !collectJob.runner_ack_at && (startupDeadlineAt !== null ? startupDeadlineAt <= now : heartbeatAgeMs === null || heartbeatAgeMs > 10_000);
  const runnerAckReceived = Boolean(collectJob.runner_ack_at) && collectJob.state !== "starting";
  const activeCollectJob = runnerAckReceived && (collectJob.state === "running" || collectJob.state === "running_tab_inactive" || collectJob.state === "waiting_for_active_tab" || collectJob.state === "paused_tab_inactive" || collectJob.state === "recovering");
  const startupRecoverable = collectJob.state === "starting" || collectJob.state === "start_failed_recoverable" || collectJob.state === "start_blocked_tab_inactive" || collectJob.state === "recoverable_stuck" || collectJob.state === "aborted_by_user_fix_stuck";
  const currentStep = String(collectJob.current_step ?? collectJob.state ?? "");
  const progressSignals = collectJobProgressSignals(collectJob, diagnostics);
  const progressExists = Object.values(progressSignals).some(Boolean);
  const knownAliveStep = COLLECT_JOB_KNOWN_ALIVE_STEPS.has(currentStep);
  const latestBackendCaptured = collectJobLatestBackendCaptured(collectJob, diagnostics);
  const runnerStarted = runnerAckReceived || progressSignals.batch_runner_entry_hit === true || progressSignals.collect_started === true;
  const freshHeartbeatAliveCandidate = activeCollectJob && heartbeatAgeMs !== null && heartbeatAgeMs <= RUNNER_LOCK_RECENT_MS && runnerStarted && knownAliveStep && progressExists;
  const mayBeAlive = activeCollectJob && runnerStarted && knownAliveStep && progressExists;
  const lockExpired = rawLockExpired && !freshHeartbeatAliveCandidate;
  const rawHardStaleCollectJob = activeCollectJob && (heartbeatAgeMs === null || heartbeatAgeMs > 120_000 || rawLockExpired && heartbeatAgeMs > 90_000);
  const hardStaleCollectJob = rawHardStaleCollectJob && !mayBeAlive;
  const targetTabId = diagnostics.trace_collect_target_tab_id ?? diagnostics.target_tab_id ?? diagnostics.douyin_tab_id ?? null;
  const activeTabId = diagnostics.trace_collect_active_tab_id ?? diagnostics.active_tab_id ?? null;
  const targetTabActive = typeof diagnostics.trace_collect_target_tab_active === "boolean" ? diagnostics.trace_collect_target_tab_active : targetTabId !== null && activeTabId !== null ? String(targetTabId) === String(activeTabId) : null;
  const explicitTabInactive = diagnostics.trace_collect_tab_inactive_evidence === "target_tab_inactive" || diagnostics.trace_collect_tab_inactive_evidence === "content_script_inactive" || diagnostics.trace_collect_tab_inactive_evidence === "active_tab_mismatch" || diagnostics.trace_collect_tab_inactive_state === "inactive";
  const tabInactiveProven = explicitTabInactive || targetTabActive === false || collectJob.state === "paused_tab_inactive" || collectJob.state === "running_tab_inactive";
  const tabInactiveEvidence = tabInactiveProven ? explicitTabInactive ? String(diagnostics.trace_collect_tab_inactive_evidence ?? diagnostics.trace_collect_tab_inactive_state ?? "explicit_inactive") : targetTabActive === false ? "active_tab_mismatch" : collectJob.state : null;
  const softStaleCollectJob = false;
  const freshCollectJob = activeCollectJob && !softStaleCollectJob && !hardStaleCollectJob;
  const staleCollectJob = hardStaleCollectJob;
  const waitingForActiveTabAllowed = activeCollectJob && tabInactiveProven;
  const softStaleLockAllowed = false;
  const workflowCollectionRunning = state.workflow.collection.status === "running";
  const workflowCollectionUpdatedAtMs = timestampMs(state.workflow.collection.updated_at);
  const workflowCollectionStartedAtMs = timestampMs(state.workflow.collection.started_at);
  const workflowCollectionHeartbeatMs = workflowCollectionUpdatedAtMs ?? workflowCollectionStartedAtMs;
  const workflowCollectionHeartbeatAgeMs = workflowCollectionHeartbeatMs === null ? null : Math.max(0, now - workflowCollectionHeartbeatMs);
  const workflowCollectionFresh = workflowCollectionRunning && workflowCollectionHeartbeatAgeMs !== null && workflowCollectionHeartbeatAgeMs <= RUNNER_LOCK_RECENT_MS;
  const debugBatchUiState = String(diagnostics.batch_collection_ui_state ?? "");
  const debugBatchHeartbeatAtMs = timestampMs(diagnostics.batch_heartbeat_at);
  const debugBatchHeartbeatAgeMs = debugBatchHeartbeatAtMs === null ? null : Math.max(0, now - debugBatchHeartbeatAtMs);
  const debugBatchLockActive = debugBatchUiState === "collecting_videos_locked" && debugBatchHeartbeatAgeMs !== null && debugBatchHeartbeatAgeMs <= RUNNER_LOCK_RECENT_MS;
  const explicitPausedOrRecovered = state.status === "paused"
    || state.phase === "paused_stale_recovered"
    || state.workflow.collection.status === "paused"
    || collectJob.state === "stuck"
    || collectJob.state === "recoverable_stuck"
    || diagnostics.last_scanner_result === "stale_recovered"
    || diagnostics.trace_collect_job_popup_render_state === "recoverable_stuck"
    || diagnostics.trace_collect_job_final_state === "stuck";
  const explicitPausedOrRecoveredReason = explicitPausedOrRecovered
    ? state.phase === "paused_stale_recovered"
      ? "paused_stale_recovered"
      : state.workflow.collection.status === "paused"
        ? "workflow_collection_paused"
        : collectJob.state === "stuck" || diagnostics.trace_collect_job_final_state === "stuck"
          ? "collect_job_stuck"
          : collectJob.state === "recoverable_stuck" || diagnostics.trace_collect_job_popup_render_state === "recoverable_stuck"
            ? "collect_job_recoverable_stuck"
            : diagnostics.last_scanner_result === "stale_recovered"
              ? "stale_recovered"
              : "status_paused"
    : null;
  const canonicalUiState = runtimeUi.active
    ? runtimeUi.waitingForActiveTab
      ? "waiting_for_active_tab"
      : runtimeUi.pausedTabInactive
        ? "paused_tab_inactive"
        : "running"
    : explicitPausedOrRecovered
      ? "recoverable_stuck"
      : waitingForActiveTabAllowed
        ? "waiting_for_active_tab"
        : collectJob.state === "paused_tab_inactive"
          ? "paused_tab_inactive"
          : activeCollectJob
            ? "running"
          : collectJob.state === "completed"
            ? "completed"
            : staleCollectJob
              ? "recoverable_stuck"
              : startupTimedOut || collectJob.state === "start_failed_recoverable"
                ? "start_failed_recoverable"
                : startupRecoverable
                  ? "start_recoverable"
                  : "idle";
  const lockShouldBeHeld = activeCollectJob && !staleCollectJob && !collectJob.lock_released;
  const baseDiagnostics: Record<string, unknown> = {
    collection_runner_active: "no",
    primary_action_locked_reason: null,
    primary_action_lock_source: "none",
    trace_collect_job_id: collectJob.job_id,
    trace_collect_job_state: collectJob.state,
    trace_collect_job_heartbeat_age_ms: heartbeatAgeMs,
    trace_collect_job_lock_expired: lockExpired,
    trace_collect_job_lock_expired_raw: rawLockExpired,
    trace_collect_job_lock_expired_suppressed: rawLockExpired && !lockExpired ? "yes" : "no",
    trace_collect_job_lock_expired_suppressed_reason: rawLockExpired && !lockExpired ? "authoritative_runtime_heartbeat_fresh" : null,
    trace_collect_heartbeat_now_iso: heartbeatNowIso,
    trace_collect_heartbeat_now_ms: heartbeatNowMs,
    trace_collect_heartbeat_at_ms: heartbeatAt,
    trace_collect_heartbeat_age_ms_recomputed: heartbeatAgeMs,
    trace_collect_heartbeat_age_source: "runtime_now_minus_heartbeat_at",
    trace_collect_heartbeat_age_consistent: "yes",
    trace_collect_heartbeat_age_inconsistency_reason: null,
    trace_collect_heartbeat_stale_derived: activeCollectJob && (heartbeatAgeMs === null || heartbeatAgeMs > RUNNER_LOCK_RECENT_MS) ? "yes" : "no",
    trace_collect_lock_ttl_ms: 45_000,
    trace_collect_lock_expired_derived: lockExpired ? "yes" : "no",
    trace_collect_lock_expired_reason: lockExpired ? "lock_expires_at_lte_runtime_now" : rawLockExpired ? "suppressed_fresh_live_heartbeat_progress" : null,
    trace_collect_lock_should_be_held_for_live_job: lockShouldBeHeld ? "yes" : "no",
    trace_collect_lock_release_attempted: collectJob.lock_released ? "yes" : "no",
    trace_collect_lock_release_allowed: collectJob.lock_released && !lockShouldBeHeld ? "yes" : "no",
    trace_collect_lock_release_denied_reason: collectJob.lock_released && lockShouldBeHeld ? "live_collect_job_must_hold_lock" : null,
    trace_collect_job_recoverable: collectJob.recoverable || softStaleCollectJob || staleCollectJob,
    trace_collect_job_soft_stale: softStaleCollectJob ? "yes" : "no",
    trace_collect_job_hard_stale: hardStaleCollectJob ? "yes" : "no",
    trace_collect_job_may_be_alive: mayBeAlive ? "yes" : "no",
    trace_collect_stale_check_started: "yes",
    trace_collect_stale_check_current_step: currentStep,
    trace_collect_stale_check_known_alive_step: knownAliveStep ? "yes" : "no",
    trace_collect_stale_check_progress_signals: progressSignals,
    trace_collect_stale_check_progress_exists: progressExists ? "yes" : "no",
    trace_collect_stale_check_backend_captured_before: collectJob.pre_batch_backend_captured,
    trace_collect_stale_check_backend_captured_latest: latestBackendCaptured,
    trace_collect_stale_check_backend_progress_detected: progressSignals.backend_progress ? "yes" : "no",
    trace_collect_stale_check_runner_ack_received: runnerAckReceived ? "yes" : "no",
    trace_collect_stale_check_batch_runner_entry_hit: progressSignals.batch_runner_entry_hit ? "yes" : "no",
    trace_collect_stale_check_may_be_alive: mayBeAlive ? "yes" : "no",
    trace_collect_stale_check_hard_stale_allowed: staleCollectJob ? "yes" : "no",
    trace_collect_stale_check_hard_stale_denied_reason: !staleCollectJob && rawHardStaleCollectJob && mayBeAlive ? "active_runner_known_alive_progress" : null,
    trace_collect_stale_check_lock_clear_allowed: staleCollectJob ? "yes" : "no",
    trace_collect_stale_check_lock_clear_denied_reason: !staleCollectJob && rawHardStaleCollectJob && mayBeAlive ? "active_runner_known_alive_progress" : null,
    trace_collect_stale_check_clear_lock_allowed: staleCollectJob ? "yes" : "no",
    trace_collect_stale_check_clear_lock_denied_reason: !staleCollectJob && rawHardStaleCollectJob && mayBeAlive ? "active_runner_known_alive_progress" : null,
    trace_collect_stale_check_state_decision: canonicalUiState,
    trace_collect_tab_inactive_check_started: "yes",
    trace_collect_target_tab_id: targetTabId,
    trace_collect_active_tab_id: activeTabId,
    trace_collect_target_tab_active: targetTabActive,
    trace_collect_tab_inactive_evidence: tabInactiveEvidence,
    trace_collect_tab_inactive_evidence_source: tabInactiveProven ? explicitTabInactive ? "diagnostics" : targetTabActive === false ? "browser_active_tab" : "collect_job_state" : null,
    trace_collect_waiting_for_active_tab_allowed: waitingForActiveTabAllowed ? "yes" : "no",
    trace_collect_waiting_for_active_tab_denied_reason: waitingForActiveTabAllowed ? null : "no_explicit_tab_inactive_evidence",
    trace_collect_state_before_tab_decision: collectJob.state,
    trace_collect_state_after_tab_decision: canonicalUiState,
    trace_collect_job_tab_inactive_state: waitingForActiveTabAllowed ? canonicalUiState : null,
    trace_collect_job_stale_reason: startupTimedOut ? "collect_runner_not_started" : staleCollectJob ? collectJob.stale_reason ?? "collect_job_hard_stale" : softStaleCollectJob ? collectJob.stale_reason ?? "collect_job_soft_stale_tab_or_popup_inactive" : collectJob.stale_reason,
    trace_collect_startup_state: collectJob.state === "starting" ? startupTimedOut ? "startup_timeout" : "waiting_for_runner_ack" : collectJob.state,
    trace_collect_startup_started_at: collectJob.started_at,
    trace_collect_startup_deadline_at: collectJob.startup_deadline_at,
    trace_collect_startup_timeout_ms: collectJob.startup_timeout_ms,
    trace_collect_startup_runner_ack_received: runnerAckReceived ? "yes" : "no",
    trace_collect_startup_runner_ack_at: collectJob.runner_ack_at,
    trace_collect_startup_failed_reason: collectJob.failure_reason,
    trace_collect_ui_state: canonicalUiState,
    trace_ui_state: canonicalUiState,
    trace_ui_canonical_state: canonicalUiState,
    trace_canonical_collect_state: canonicalUiState,
    trace_canonical_collect_state_inputs: { collect_job_state: collectJob.state, runner_ack_received: runnerAckReceived, may_be_alive: mayBeAlive, fresh_collect_job: freshCollectJob, soft_stale_collect_job: softStaleCollectJob, hard_stale_collect_job: hardStaleCollectJob, tab_inactive_proven: tabInactiveProven, active_collect_runtime_state: runtime.canonical_state, active_collect_runtime_job_id: runtime.job_id, active_collect_runtime_authoritative: runtimeUi.active ? "yes" : "no" },
    trace_canonical_collect_state_source: runtimeUi.active ? "active_collect_runtime" : "authoritative_popup_state_reducer",
    trace_canonical_collect_state_previous: collectJob.state,
    trace_canonical_collect_state_next: canonicalUiState,
    trace_canonical_collect_state_changed: canonicalUiState !== collectJob.state ? "yes" : "no",
    trace_canonical_collect_state_change_reason: canonicalUiState !== collectJob.state ? "canonical_runtime_priority" : null,
    trace_progress_diagnostics_status_source: activeCollectJob ? "canonical_collect_state" : "legacy_state",
    trace_progress_diagnostics_phase_source: activeCollectJob ? "canonical_collect_state" : "legacy_state",
    trace_progress_active_batch_runtime_required: runtimeUi.active ? "yes" : "no",
    trace_progress_visible_status_source: runtimeUi.active ? "active_collect_runtime" : activeCollectJob ? "canonical_collect_state" : "legacy_state",
    trace_progress_visible_phase_source: runtimeUi.active ? "active_collect_runtime" : activeCollectJob ? "canonical_collect_state" : "legacy_state",
    trace_progress_visible_status_source_allowed: runtimeUi.active ? "yes" : activeCollectJob ? "guarded_yes" : "legacy_yes",
    trace_progress_visible_phase_source_allowed: runtimeUi.active ? "yes" : activeCollectJob ? "guarded_yes" : "legacy_yes",
    trace_progress_legacy_phase_candidate: String(state.phase ?? "idle"),
    trace_progress_legacy_phase_suppressed: runtimeUi.active && String(state.phase ?? "") !== canonicalUiState ? "yes" : "no",
    trace_progress_legacy_status_candidate: String(state.status ?? "idle"),
    trace_progress_legacy_status_suppressed: runtimeUi.active && !["waiting_for_active_tab", "paused_tab_inactive", "running"].includes(String(state.status ?? "")) ? "yes" : "no",
    trace_progress_action_lock_phase_candidate: String(state.workflow.action_lock ?? "none"),
    trace_progress_action_lock_phase_suppressed: runtimeUi.active && state.workflow.action_lock !== null ? "yes" : "no",
    trace_progress_stale_phase_candidate: startupTimedOut ? "start_failed_recoverable" : staleCollectJob ? "recoverable_stuck" : softStaleCollectJob ? "soft_stale_candidate" : "none",
    trace_progress_stale_phase_suppressed: runtimeUi.active && (startupTimedOut || staleCollectJob || softStaleCollectJob) ? "yes" : "no",
    trace_progress_runtime_phase_committed: canonicalUiState,
    trace_progress_runtime_status_committed: runtimeUi.waitingForActiveTab ? "waiting_for_active_tab" : runtimeUi.pausedTabInactive ? "paused_tab_inactive" : runtimeUi.active ? "collecting" : canonicalUiState,
    trace_progress_phase_flicker_blocked: runtimeUi.active ? "yes" : "no",
    trace_progress_status_flicker_blocked: runtimeUi.active ? "yes" : "no",
    trace_legacy_one_item_status_suppressed_during_batch_collect: activeCollectJob ? "yes" : "no",
    trace_ui_state_inputs: { collect_job_state: collectJob.state, runner_ack_received: runnerAckReceived, fresh_collect_job: freshCollectJob, soft_stale_collect_job: softStaleCollectJob, hard_stale_collect_job: hardStaleCollectJob, known_alive_step: knownAliveStep, progress_exists: progressExists, active_collect_runtime_state: runtime.canonical_state, active_collect_runtime_job_id: runtime.job_id, active_collect_runtime_authoritative: runtimeUi.active ? "yes" : "no" },
    trace_ui_state_source: runtimeUi.active ? "active_collect_runtime" : activeCollectJob ? "collect_job" : startupRecoverable ? "collect_job_recoverable" : "none",
    trace_ui_start_button_enabled: runtimeUi.active ? "no" : "yes",
    trace_ui_start_collecting_render_blocked_reason: runtimeUi.active ? "active_collect_runtime_heartbeat_alive" : null,
    trace_ui_collecting_button_enabled: "no",
    trace_ui_action_blocked_visible: "no",
    trace_ui_action_blocked_reason: null,
    trace_ui_primary_action_source: "canonical_collect_state",
    trace_ui_badge_source: "canonical_collect_state",
    trace_ui_action_blocked_source: canonicalUiState === "running" ? "suppressed_during_running" : "canonical_collect_state",
    trace_action_block_render_suppressed_during_running: canonicalUiState === "running" ? "yes" : "no",
    trace_ui_action_block_render_suppressed: canonicalUiState === "running" ? "yes" : "no",
    trace_ui_duplicate_click_suppressed: runtimeUi.active ? "yes" : "no",
    trace_ui_flicker_guard_applied: runtimeUi.active ? "yes" : "no",
    trace_ui_previous_render_state: diagnostics.trace_ui_next_render_state ?? null,
    trace_ui_next_render_state: canonicalUiState,
    trace_ui_render_generation: numberValue(diagnostics.trace_ui_render_generation, 0) + 1,
    trace_ui_primary_action: canonicalUiState === "running" || canonicalUiState === "waiting_for_active_tab" || canonicalUiState === "paused_tab_inactive" ? "pause_disabled" : "start_or_retry_available",
    trace_ui_contradiction_detected: collectJob.state === "starting" && !runnerAckReceived ? "no_collecting_without_runner_ack" : "no",
    trace_ui_contradiction_reason: collectJob.state === "starting" && !runnerAckReceived ? "startup_without_runner_ack" : null,
    trace_collect_workflow_status: state.workflow.collection.status,
    trace_collect_workflow_heartbeat_age_ms: workflowCollectionHeartbeatAgeMs,
    trace_collect_workflow_fresh: workflowCollectionFresh ? "yes" : "no",
    trace_collect_debug_batch_ui_state: debugBatchUiState || null,
    trace_collect_debug_batch_heartbeat_age_ms: debugBatchHeartbeatAgeMs,
    trace_collect_debug_batch_lock_active: debugBatchLockActive ? "yes" : "no",
    trace_collect_explicit_paused_or_recovered: explicitPausedOrRecovered ? "yes" : "no",
    trace_collect_explicit_paused_or_recovered_reason: explicitPausedOrRecoveredReason,
    trace_collect_runtime_coherence_warning: runtimeCoherenceWarning ? "yes" : "no",
    trace_collect_runtime_coherence_warning_reason: runtimeCoherenceWarningReason,
    trace_collect_runtime_coherence_expected_job_id: collectJob.job_id,
    trace_collect_runtime_coherence_runtime_job_id: runtime.job_id,
    trace_collect_runtime_coherence_runtime_state: runtime.canonical_state,
    trace_collect_runtime_coherence_runtime_heartbeat_age_ms: runtimeUi.heartbeatAgeMs,
    trace_collect_runtime_coherence_runtime_lock_expired: runtimeUi.lockExpired,
    trace_collect_runtime_coherence_runtime_ui_authoritative: runtimeUi.active ? "yes" : "no"
  };
  if (runtimeUi.active) return {
    active: true,
    reason: "collection_running",
    source: "active_collect_runtime",
    diagnostics: {
      ...baseDiagnostics,
      collection_runner_active: "yes",
      primary_action_locked_reason: "collection_running",
      primary_action_lock_source: "active_collect_runtime",
      trace_collect_runtime_authoritative: "yes",
      trace_collect_runtime_authoritative_state: runtime.canonical_state,
      trace_collect_runtime_authoritative_job_id: runtime.job_id
    }
  };
  if (startupRecoverable || startupTimedOut) return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
  if (explicitPausedOrRecovered) return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
  if (staleCollectJob) return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
  if (terminalReached(state, diagnostics)) return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
  if (state.workflow.collection.status === "pausing") return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
  if (freshCollectJob || waitingForActiveTabAllowed) return {
    active: true,
    reason: "collection_running",
    source: "collect_job",
    diagnostics: {
      ...baseDiagnostics,
      collection_runner_active: "yes",
      primary_action_locked_reason: "collection_running",
      primary_action_lock_source: "collect_job",
      trace_collect_runtime_authoritative: "no",
      trace_collect_runtime_authoritative_state: runtime.canonical_state,
      trace_collect_runtime_authoritative_job_id: runtime.job_id
    }
  };
  if (debugBatchLockActive) return {
    active: true,
    reason: "collection_running",
    source: "debug.batch_collection_ui_state",
    diagnostics: {
      ...baseDiagnostics,
      collection_runner_active: "yes",
      primary_action_locked_reason: "collection_running",
      primary_action_lock_source: "debug.batch_collection_ui_state",
      trace_collect_runtime_authoritative: "no",
      trace_collect_runtime_authoritative_state: runtime.canonical_state,
      trace_collect_runtime_authoritative_job_id: runtime.job_id
    }
  };
  if (workflowCollectionFresh) return {
    active: true,
    reason: "collection_running",
    source: "workflow.collection.status",
    diagnostics: {
      ...baseDiagnostics,
      collection_runner_active: "yes",
      primary_action_locked_reason: "collection_running",
      primary_action_lock_source: "workflow.collection.status",
      trace_collect_runtime_authoritative: "no",
      trace_collect_runtime_authoritative_state: runtime.canonical_state,
      trace_collect_runtime_authoritative_job_id: runtime.job_id
    }
  };
  return { active: false, reason: null, source: null, diagnostics: baseDiagnostics };
}

export function isTerminalBatchContinuation(state: WholeProfileHarvestState, pendingCount: number): boolean {
  const diagnostics = debugSummary(state);
  const topFailure = stringValue(diagnostics.top_failure);
  const topFailureNone = topFailure == null || topFailure === "none";
  return state.phase === "batch_safe_mode_completed" && pendingCount > 0 && numberValue(state.harvest.failed) === 0 && topFailureNone;
}

export function deriveAuthoritativeProfileCounters(state: WholeProfileHarvestState): AuthoritativeProfileCounters {
  const diagnostics = debugSummary(state);
  const queue = state.harvest.queue;
  const queueIds = new Set<string>();
  for (const item of queue) {
    const id = firstId(item, SCAN_ID_ALIASES) ?? awemeFromUrl(record(item).source_url);
    if (id) queueIds.add(id);
  }
  const backendItems = backendItemsFromState(state);
  const response = backendVerifyResponse(state);
  const counts = record(response.counts);
  const backendCaptured = numberValue(counts.captured ?? diagnostics.session_ribbon_captured_count ?? diagnostics.backend_reconciliation_backend_profile_captured_count, backendItems.length);
  const backendIds = backendItems.map((item) => firstId(item, BACKEND_ID_ALIASES)).filter((id): id is string => Boolean(id));
  const matchedIds = new Set(backendIds.filter((id) => queueIds.has(id)));
  const persistedTotalsTrusted = persistedScanJobTotalsTrustedForStoredProfile(state);
  const persistedQueueTotal = persistedTotalsTrusted
    ? numberValue(
      diagnostics.queue_total_persisted ?? diagnostics.scan_job_total_persisted ?? diagnostics.profile_queue_total_count ?? state.scan_job.total_persisted,
      0
    )
    : 0;
  const visibleQueueTotal = numberValue(diagnostics.queue_total_visible, queue.length || state.harvest.queue_preview.length);
  const queueTotal = persistedQueueTotal > 0 && persistedQueueTotal >= visibleQueueTotal
    ? persistedQueueTotal
    : queue.length || numberValue(diagnostics.profile_queue_total_count, state.harvest.queue_preview.length);
  const beforeApply = numberValue(diagnostics.profile_already_collected_count, 0);
  const reconciledDiagnosticCount = numberValue(diagnostics.profile_already_collected_count_after_apply ?? diagnostics.backend_reconciliation_matched_count, 0);
  const alreadyCollected = queueTotal > 0 ? matchedIds.size || reconciledDiagnosticCount : backendCaptured;
  const eligible = Math.max(0, queueTotal - alreadyCollected);
  const mismatch = queueTotal > 0 && backendCaptured > 0 && matchedIds.size === 0;
  const applied = backendItems.length > 0 || backendCaptured > 0 || persistedQueueTotal > 0;
  const unmatchedBackend = backendIds.filter((id) => !queueIds.has(id));
  const unmatchedScanCount = Math.max(0, queueIds.size - matchedIds.size);
  return {
    queue_total: queueTotal,
    backend_profile_captured_count: backendCaptured,
    backend_item_count: backendItems.length,
    already_collected_in_scan_count: alreadyCollected,
    profile_already_collected_count: alreadyCollected,
    profile_eligible_count: eligible,
    pending_count: eligible,
    skipped_saved_targets_count: alreadyCollected,
    applied,
    diagnostics: {
      backend_reconciliation_counter_source: backendItems.length > 0 ? "backend_verify_response_items" : backendCaptured > 0 ? "backend_verify_response_counts" : "scan_queue",
      backend_reconciliation_applied_to_profile_counters: applied ? "yes" : "no",
      backend_reconciliation_backend_profile_captured_count: backendCaptured,
      backend_reconciliation_backend_item_count: backendItems.length,
      backend_reconciliation_matched_count: matchedIds.size,
      backend_reconciliation_unmatched_backend_count: unmatchedBackend.length,
      backend_reconciliation_unmatched_scan_count: unmatchedScanCount,
      backend_reconciliation_mismatch: mismatch ? "yes" : "no",
      backend_reconciliation_unmatched_backend_sample: unmatchedBackend.slice(0, 5).join(", "),
      backend_reconciliation_scan_sample: Array.from(queueIds).slice(0, 5).join(", "),
      backend_reconciliation_id_aliases_checked: [...BACKEND_ID_ALIASES, ...SCAN_ID_ALIASES].join(", "),
      profile_already_collected_count_before_apply: beforeApply,
      profile_already_collected_count_after_apply: alreadyCollected,
      profile_already_collected_count: alreadyCollected,
      profile_eligible_count: eligible,
      pending_count: eligible,
      profile_queue_total_count: queueTotal,
      profile_counters_overwritten_after_reconciliation: "no",
      profile_counter_authority: backendItems.length > 0 ? "backend_verify_response_items" : "backend_verify_response_counts",
      current_batch_saved_count_ignored_for_already_collected: "yes"
    }
  };
}

export function deriveReconciledPopupMetrics(state: WholeProfileHarvestState): ReconciledPopupMetrics {
  const diagnostics = debugSummary(state);
  const counters = deriveAuthoritativeProfileCounters(state);
  const responseCounts = record(backendVerifyResponse(state).counts);
  const snapshot = state.post_scan_counter_snapshot;
  const runtime = state.active_collect_runtime;
  const runtimeSameJob = activeCollectRuntimeMatchesJob(state);
  const runtimeCompletionOverridden = collectCompletionOverridesActiveCollectRuntime(state);
  const runtimeCountersActive = !runtimeCompletionOverridden && runtimeSameJob && (
    runtime.canonical_state === "starting"
    || runtime.canonical_state === "running"
    || runtime.canonical_state === "waiting_for_modal"
    || runtime.canonical_state === "waiting_for_extract"
    || runtime.canonical_state === "waiting_for_backend_write"
    || runtime.canonical_state === "waiting_for_post_batch_summary"
    || runtime.canonical_state === "waiting_for_active_tab"
    || runtime.canonical_state === "paused_tab_inactive"
  );
  const collectJobActiveForCounters = !runtimeCompletionOverridden && (runtimeCountersActive || Boolean(state.collect_job.runner_ack_at) && (state.collect_job.state === "running" || state.collect_job.state === "running_tab_inactive" || state.collect_job.state === "waiting_for_active_tab" || state.collect_job.state === "paused_tab_inactive" || state.collect_job.state === "recovering"));
  const runtimeProgressCaptured = typeof runtime.latest_progress_captured === "number" && Number.isFinite(runtime.latest_progress_captured)
    ? runtime.latest_progress_captured
    : typeof runtime.pre_batch_backend_captured === "number"
      ? runtime.pre_batch_backend_captured + Math.max(0, runtime.succeeded_count)
      : null;
  const collectJobProgressCaptured = runtimeCountersActive && runtimeProgressCaptured !== null
    ? runtimeProgressCaptured
    : typeof diagnostics.trace_collect_popup_already_collected === "number" && Number.isFinite(diagnostics.trace_collect_popup_already_collected)
      ? diagnostics.trace_collect_popup_already_collected
      : typeof state.collect_job.pre_batch_backend_captured === "number"
        ? state.collect_job.pre_batch_backend_captured + Math.max(0, state.collect_job.succeeded_count)
        : null;
  const runtimeProgressQueue = typeof runtime.latest_progress_queue === "number" && Number.isFinite(runtime.latest_progress_queue)
    ? runtime.latest_progress_queue
    : typeof runtime.pre_batch_queue === "number" && typeof runtime.selected_count === "number"
      ? Math.max(0, runtime.selected_count - Math.max(0, runtime.succeeded_count) - Math.max(0, runtime.failed_count) - Math.max(0, runtime.skipped_count))
      : null;
  const collectJobProgressQueue = runtimeCountersActive && runtimeProgressQueue !== null
    ? runtimeProgressQueue
    : typeof diagnostics.trace_collect_popup_queue === "number" && Number.isFinite(diagnostics.trace_collect_popup_queue)
      ? diagnostics.trace_collect_popup_queue
      : typeof state.collect_job.pre_batch_queue === "number"
        ? Math.max(0, state.collect_job.pre_batch_queue - Math.max(0, state.collect_job.succeeded_count))
        : null;
  const collectJobProgressAvailable = collectJobActiveForCounters && collectJobProgressCaptured !== null && collectJobProgressQueue !== null;
  const startupOrRecoveryState = state.collect_job.state === "starting" || state.collect_job.state === "start_failed_recoverable" || state.collect_job.state === "start_blocked_tab_inactive" || state.collect_job.state === "recoverable_stuck" || state.collect_job.state === "stuck" || state.collect_job.state === "aborted_by_user_fix_stuck";
  const verifiedBackendCaptured = Math.max(counters.backend_profile_captured_count, numberValue(diagnostics.post_scan_backend_captured_count ?? diagnostics.backend_reconciliation_backend_profile_captured_count ?? diagnostics.session_ribbon_captured_count, 0));
  // In-flight collect heartbeats must NOT own the profile tiles (New / Already
  // collected / Queue). Hybrid writes one heartbeat per item; swapping tile
  // authority to active_collect_runtime / collect_job_progress caused flicker
  // and "crazy numbers" until completion. Profile tiles stay on the stable
  // post_scan_counter_snapshot (updated only by reconcile on terminal writes).
  // active_runner_* metrics still expose this-run progress for the button area.
  const activeRuntimeAuthorityBlocksSnapshot = false;
  const snapshotWouldRegressBackend = startupOrRecoveryState && snapshot?.status === "applied" && verifiedBackendCaptured > 0 && snapshot.already_collected < verifiedBackendCaptured;
  const snapshotStaleBehindBackend = snapshot?.status === "applied" && verifiedBackendCaptured > 0 && snapshot.already_collected < verifiedBackendCaptured;
  const scanAuthorityTotal = resolveScannedTotalFromState(state);
  const contract = buildProfileCollectContractFromState(state);
  const scanDiagnostics = mergeScanAuthorityDiagnostics(state);
  const displayedLimit = resolveDisplayedProfileVideoLimit(scanDiagnostics);
  const overDisplayedPersistedQueue = displayedLimit != null
    && counters.queue_total > displayedLimit;
  const useContractTiles = displayedLimit != null;
  const snapshotStaleBehindPersistedTotal = snapshot?.status === "applied"
    && counters.queue_total > snapshot.scanned_total
    && counters.queue_total > scanAuthorityTotal;
  const snapshotApplied = snapshot?.status === "applied"
    && !snapshotWouldRegressBackend
    && !snapshotStaleBehindBackend
    && !snapshotStaleBehindPersistedTotal;
  const postScanCardAuthoritative = diagnostics.post_scan_backend_reconciliation_status === "success" && diagnostics.post_scan_counter_snapshot_applied === "yes";
  const backendReconciliationCardAuthoritative = diagnostics.backend_reconciliation_applied_to_profile_counters === "yes" && diagnostics.backend_reconciliation_used_capture_inbox_card_source !== "no";
  const snapshotProfileTotal = snapshotApplied ? snapshot.scanned_total : counters.queue_total;
  const persistedQueueAuthoritative = counters.applied && counters.queue_total > 0
    && (diagnostics.large_profile_mode === "yes"
      || (numberValue(diagnostics.queue_total_persisted, 0) > 0 && numberValue(diagnostics.queue_total_persisted, 0) === counters.queue_total)
      || counters.queue_total < scanAuthorityTotal);
  const persistedBoundProfileTotal = persistedQueueAuthoritative
    ? Math.max(snapshotApplied ? snapshot.scanned_total : 0, counters.queue_total)
    : snapshotProfileTotal;
  let profileTotal = useContractTiles ? contract.displayed_total : scanAuthorityTotal;
  if (!useContractTiles && displayedLimit != null && counters.queue_total > 0 && counters.queue_total < displayedLimit) {
    profileTotal = counters.queue_total;
  }
  const profileTotalUsesScanAuthority = profileTotal > persistedBoundProfileTotal;
  const backendCardCaptured = Math.max(snapshotWouldRegressBackend ? verifiedBackendCaptured : 0, snapshotApplied ? snapshot.already_collected : numberValue(
    postScanCardAuthoritative
      ? diagnostics.post_scan_backend_captured_count
      : backendReconciliationCardAuthoritative
        ? diagnostics.backend_reconciliation_backend_profile_captured_count
        : responseCounts.captured,
    counters.profile_already_collected_count
  ));
  const readyCount = snapshotApplied ? numberValue(snapshot.backend_ready, 0) : numberValue(
    postScanCardAuthoritative
      ? diagnostics.post_scan_backend_ready_count
      : backendReconciliationCardAuthoritative
        ? diagnostics.backend_reconciliation_backend_ready_count
        : responseCounts.ready,
    0
  );
  const duplicateCount = snapshotApplied ? numberValue(snapshot.backend_dup, 0) : numberValue(
    postScanCardAuthoritative
      ? diagnostics.post_scan_backend_duplicate_count
      : backendReconciliationCardAuthoritative
        ? diagnostics.backend_reconciliation_backend_duplicate_count ?? diagnostics.backend_reconciliation_backend_dup_count
        : responseCounts.dup ?? responseCounts.duplicate,
    0
  );
  const failedCount = snapshotApplied ? snapshot.need_retry : numberValue(
    postScanCardAuthoritative
      ? diagnostics.post_scan_backend_failed_count
      : backendReconciliationCardAuthoritative
        ? diagnostics.backend_reconciliation_backend_failed_count ?? diagnostics.backend_reconciliation_backend_fail_count
        : responseCounts.fail ?? responseCounts.failed,
    0
  );
  const incompleteCount = useContractTiles
    ? Math.max(contract.incomplete_count, snapshotApplied ? snapshot.incomplete : 0)
    : snapshotApplied
      ? snapshot.incomplete
      : Math.max(0, backendCardCaptured - readyCount - duplicateCount - failedCount);
  const alreadyCollectedBase = snapshotApplied ? snapshot.already_collected : counters.applied ? backendCardCaptured : counters.profile_already_collected_count;
  // Profile tiles use stable snapshot/base only — never in-flight heartbeat progress.
  const alreadyCollected = alreadyCollectedBase;
  const reconciledRemainingBase = useContractTiles
    ? Math.max(0, contract.new_count)
    : snapshotApplied
      ? Math.max(snapshot.new, profileTotal - alreadyCollected)
      : Math.max(0, profileTotal - alreadyCollected);
  const reconciledRemaining = reconciledRemainingBase;
  const rawPending = numberValue(diagnostics.pending_count ?? state.harvest.pending, 0);
  const rawBatchPending = numberValue(diagnostics.profile_batch_pending_count ?? diagnostics.batch_pending_count, 0);
  const activeRunnerRemaining = numberValue(
    diagnostics.active_runner_remaining_count,
    collectJobProgressAvailable && collectJobProgressQueue !== null ? collectJobProgressQueue : rawPending
  );
  const authority = snapshotApplied
    ? "post_scan_counter_snapshot"
    : counters.applied
      ? String(counters.diagnostics.profile_counter_authority ?? counters.diagnostics.backend_reconciliation_counter_source ?? "backend_reconciliation")
      : "scan_queue";
  const rawPendingIgnored = (snapshotApplied || counters.applied) && (rawPending !== reconciledRemaining || rawBatchPending !== 0 && rawBatchPending !== reconciledRemaining);
  // Monotonic latch only against prior *stable* tile renders (snapshot/backend),
  // never against in-flight heartbeat numbers left in diagnostics (those caused
  // flicker and stuck tiles one batch behind after Hybrid writes).
  const previousTileSource = stringValue(diagnostics.last_rendered_source);
  const previousWasStableTileSource = previousTileSource === "post_scan_counter_snapshot"
    || previousTileSource === "backend_reconciliation"
    || previousTileSource === "backend_verify_response_items"
    || previousTileSource === "backend_verify_response_counts"
    || previousTileSource === "backend_capture_inbox_profile_summary"
    || previousTileSource === "scan_queue";
  const previousRenderedCaptured = previousWasStableTileSource
    ? numberValue(diagnostics.last_rendered_captured, alreadyCollectedBase)
    : alreadyCollectedBase;
  const previousRenderedQueue = previousWasStableTileSource
    ? numberValue(diagnostics.last_rendered_queue, reconciledRemainingBase)
    : reconciledRemainingBase;
  const previousRenderedNew = previousWasStableTileSource
    ? numberValue(diagnostics.last_rendered_new, previousRenderedQueue)
    : reconciledRemainingBase;
  const previousRenderGeneration = numberValue(diagnostics.trace_counter_render_generation ?? diagnostics.render_generation, 0);
  const renderGeneration = previousRenderGeneration + 1;
  const activeCounterJobId = stringValue(diagnostics.active_counter_job_id) ?? state.collect_job.job_id;
  const sameCounterJob = activeCounterJobId === state.collect_job.job_id || activeCounterJobId === null || state.collect_job.job_id === null;
  const backwardCaptured = sameCounterJob && alreadyCollected < previousRenderedCaptured && previousRenderedCaptured > 0;
  const backwardQueue = sameCounterJob && reconciledRemaining > previousRenderedQueue && previousRenderedQueue >= 0 && previousRenderedCaptured > 0;
  const backwardNew = sameCounterJob && reconciledRemaining > previousRenderedNew && previousRenderedCaptured > 0;
  const snapshotSuppressedByActiveCollect = false;
  const counterCandidateRejected = backwardCaptured || backwardQueue || backwardNew;
  const selectedAlreadyCollected = backwardCaptured ? previousRenderedCaptured : alreadyCollected;
  const selectedRemaining = backwardQueue || backwardNew ? previousRenderedQueue : reconciledRemaining;
  const partialTiles = partialCollectTileCounts(selectedRemaining, selectedAlreadyCollected);
  let selectedNew = useContractTiles ? contract.new_count : partialTiles.newCount;
  let selectedQueue = useContractTiles ? contract.queue_count : partialTiles.queueCount;
  const selectedSource = backwardCaptured || backwardQueue || backwardNew
    ? String(diagnostics.trace_counter_selected_source ?? diagnostics.latest_counter_source ?? "last_committed_counter_latch")
    : authority;
  const monotonicGuardApplied = backwardCaptured || backwardQueue || backwardNew;

  return {
    profile: {
      profile_total_count: useContractTiles ? contract.displayed_total : profileTotal,
      already_collected_count: selectedAlreadyCollected,
      ready_count: readyCount,
      duplicate_count: duplicateCount,
      failed_count: failedCount,
      incomplete_count: snapshotApplied || counters.applied ? incompleteCount : 0,
      need_retry_count: snapshotApplied || counters.applied ? failedCount : 0,
      new_count: selectedNew,
      eligible_count: selectedQueue,
      queue_count: selectedQueue
    },
    active_runner: {
      active_runner_remaining_count: activeRunnerRemaining,
      active_runner_current_index: numberValue(diagnostics.active_runner_current_index ?? state.harvest.current_index, 0),
      active_runner_saved_this_run: numberValue(diagnostics.active_runner_saved_this_run ?? diagnostics.batch_success_count ?? diagnostics.saved_count_after_batch, 0),
      active_runner_failed_this_run: numberValue(diagnostics.active_runner_failed_this_run ?? diagnostics.batch_failed_count ?? state.harvest.failed, 0),
      active_runner_skipped_this_run: numberValue(diagnostics.active_runner_skipped_this_run ?? diagnostics.batch_skipped_count, 0)
    },
    diagnostics: {
      popup_metrics_reconciler_ran: "yes",
      popup_metrics_profile_total_source: profileTotalUsesScanAuthority
        ? "scan_authority"
        : snapshotApplied
          ? "post_scan_counter_snapshot.scanned_total"
          : counters.applied
            ? "authoritative_profile_counters.queue_total"
            : "scan_queue",
      popup_metrics_snapshot_applied: snapshotApplied ? "yes" : "no",
      popup_metrics_already_collected_source: selectedSource,
      popup_metrics_new_count: selectedNew,
      popup_metrics_eligible_count: selectedQueue,
      popup_metrics_queue_count: selectedQueue,
      popup_metrics_incomplete_count: snapshotApplied || counters.applied ? incompleteCount : 0,
      popup_metrics_need_retry_count: snapshotApplied || counters.applied ? failedCount : 0,
      popup_metrics_backend_ready_count: readyCount,
      popup_metrics_backend_duplicate_count: duplicateCount,
      popup_metrics_backend_failed_count: failedCount,
      popup_metrics_active_runner_remaining_count: activeRunnerRemaining,
      popup_metrics_raw_pending_count: rawPending,
      popup_metrics_raw_batch_pending_count: rawBatchPending,
      popup_metrics_profile_tiles_authority: snapshotApplied || counters.applied
        ? (profileTotalUsesScanAuthority ? "scan_authority" : selectedSource)
        : "scan_queue",
      popup_metrics_profile_tiles_ignore_inflight_progress: "yes",
      popup_metrics_collect_job_progress_available: collectJobProgressAvailable ? "yes" : "no",
      popup_metrics_collect_job_progress_captured: collectJobProgressCaptured,
      popup_metrics_collect_job_progress_queue: collectJobProgressQueue,
      popup_metrics_active_collect_runtime_authoritative: runtimeCountersActive ? "yes" : "no",
      popup_metrics_active_collect_runtime_job_id: runtime.job_id,
      popup_metrics_active_collect_runtime_state: runtime.canonical_state,
      popup_metrics_snapshot_runtime_authority_blocked: activeRuntimeAuthorityBlocksSnapshot ? "yes" : "no",
      popup_metrics_post_scan_snapshot_ignored_for_active_collect_job: snapshotSuppressedByActiveCollect ? "yes" : "no",
      popup_metrics_post_scan_snapshot_ignored_for_startup_recovery: snapshotWouldRegressBackend ? "yes" : "no",
      popup_metrics_post_scan_snapshot_ignored_for_newer_backend: snapshotStaleBehindBackend ? "yes" : "no",
      popup_metrics_post_scan_snapshot_ignored_for_newer_persisted_total: snapshotStaleBehindPersistedTotal ? "yes" : "no",
      popup_metrics_counter_authority_monotonic_guard: snapshotWouldRegressBackend ? "verified_backend_snapshot" : snapshotSuppressedByActiveCollect ? "active_collect_runtime_latch" : "not_needed",
      popup_metrics_post_scan_counter_snapshot_status: snapshot?.status ?? "missing",
      popup_metrics_post_scan_counter_snapshot_source: snapshot?.source ?? null,
      popup_metrics_post_scan_counter_snapshot_profile_identifier: snapshot?.profile_identifier ?? null,
      popup_metrics_post_scan_counter_snapshot_applied_at: snapshot?.applied_at ?? null,
      popup_metrics_raw_pending_ignored_for_profile_tiles: rawPendingIgnored,
      popup_metrics_active_runner_current_index: numberValue(diagnostics.active_runner_current_index ?? state.harvest.current_index, 0),
      popup_metrics_active_runner_saved_this_run: numberValue(diagnostics.active_runner_saved_this_run ?? diagnostics.batch_success_count ?? diagnostics.saved_count_after_batch, 0),
      popup_metrics_active_runner_failed_this_run: numberValue(diagnostics.active_runner_failed_this_run ?? diagnostics.batch_failed_count ?? state.harvest.failed, 0),
      popup_metrics_active_runner_skipped_this_run: numberValue(diagnostics.active_runner_skipped_this_run ?? diagnostics.batch_skipped_count, 0),
      trace_counter_active_collect_monotonic_enabled: collectJobActiveForCounters ? "yes" : "no",
      trace_counter_render_latch_enabled: collectJobActiveForCounters ? "yes" : "no",
      active_counter_job_id: activeCounterJobId,
      trace_counter_render_job_id: state.collect_job.job_id,
      trace_counter_render_generation: renderGeneration,
      trace_counter_previous_render_generation: previousRenderGeneration,
      trace_counter_job_id: state.collect_job.job_id,
      trace_counter_candidate_source: authority,
      trace_counter_candidate_generated_at: new Date().toISOString(),
      trace_counter_candidate_captured: alreadyCollected,
      trace_counter_candidate_queue: reconciledRemaining,
      trace_counter_candidate_new: reconciledRemaining,
      trace_counter_candidate_incomplete: incompleteCount,
      trace_counter_previous_rendered_captured: previousRenderedCaptured,
      trace_counter_previous_rendered_queue: previousRenderedQueue,
      trace_counter_selected_source: selectedSource,
      trace_counter_selected_captured: selectedAlreadyCollected,
      trace_counter_selected_queue: selectedQueue,
      trace_counter_selected_new: selectedNew,
      trace_counter_monotonic_guard_applied: monotonicGuardApplied ? "yes" : "no",
      trace_counter_monotonic_guard_reason: snapshotSuppressedByActiveCollect ? "active_collect_runtime_blocks_post_scan_snapshot" : monotonicGuardApplied ? "active_collect_progress_prevents_counter_regression" : null,
      trace_counter_render_candidate_rejected: counterCandidateRejected ? "yes" : "no",
      trace_counter_candidate_rejected: counterCandidateRejected ? "yes" : "no",
      trace_counter_render_candidate_rejected_reason: snapshotSuppressedByActiveCollect ? "post_scan_snapshot_not_authoritative_during_active_collect" : backwardCaptured ? "captured_would_decrease_for_same_job" : backwardQueue ? "queue_would_increase_for_same_job" : backwardNew ? "new_would_increase_for_same_job" : null,
      trace_counter_candidate_rejected_reason: snapshotSuppressedByActiveCollect ? "post_scan_snapshot_not_authoritative_during_active_collect" : backwardCaptured ? "captured_would_decrease_for_same_job" : backwardQueue ? "queue_would_increase_for_same_job" : backwardNew ? "new_would_increase_for_same_job" : null,
      trace_counter_backward_render_blocked: backwardCaptured || backwardQueue || backwardNew ? "yes" : "no",
      trace_counter_stale_generation_blocked: "no",
      trace_counter_tiles_same_source: "yes",
      trace_counter_render_committed: "yes",
      trace_counter_backend_reset_exception_used: "no",
      last_rendered_captured: selectedAlreadyCollected,
      last_rendered_queue: selectedQueue,
      last_rendered_new: selectedNew,
      last_rendered_incomplete: incompleteCount,
      last_rendered_need_retry: failedCount,
      last_rendered_source: selectedSource,
      last_rendered_at: new Date().toISOString(),
      max_rendered_captured_for_job: selectedAlreadyCollected,
      min_rendered_queue_for_job: selectedQueue,
      latest_rendered_ready: readyCount,
      latest_rendered_dup: duplicateCount,
      latest_rendered_fail: failedCount,
      latest_counter_source: selectedSource,
      render_generation: renderGeneration
    }
  };
}

function setTechnicalRow(rows: Array<{ label: string; value: string }> | undefined, label: string, value: string): void {
  if (!rows) return;
  const existing = rows.find((row) => row.label === label);
  if (existing) existing.value = value;
  else rows.push({ label, value });
}

export function sanitizePopupViewState<T extends MutablePopupViewState>(viewState: T, rawState: WholeProfileHarvestState): SanitizedPopupViewState<T> {
  const sanitized = viewState as SanitizedPopupViewState<T>;
  const reasons: string[] = [];
  const lock = deriveAuthoritativeRunnerLock(rawState);
  const counters = deriveAuthoritativeProfileCounters(rawState);
  const popupMetrics = deriveReconciledPopupMetrics(rawState);
  const runtimeUi = activeCollectRuntimeUiAuthority(rawState);
  if (runtimeUi.active || lock.active) {
    if (sanitized.primaryAction) {
      sanitized.primaryAction.key = "pause";
      sanitized.primaryAction.label = runtimeUi.label;
      sanitized.primaryAction.buttonLabel = runtimeUi.label;
      sanitized.primaryAction.enabled = false;
      sanitized.primaryAction.disabledReason = null;
    }
    if (sanitized.primary_action) {
      sanitized.primary_action.key = "pause";
      sanitized.primary_action.label = runtimeUi.label;
      sanitized.primary_action.enabled = false;
      sanitized.primary_action.reason = "Collection is already running.";
    }
    if (sanitized.action) {
      sanitized.action.key = "pause";
      sanitized.action.buttonLabel = runtimeUi.label;
      sanitized.action.enabled = false;
      sanitized.action.disabledReason = null;
    }
    reasons.push(runtimeUi.active ? "active_collect_runtime_primary_action" : "runner_lock_primary_action");
  } else if (lock.diagnostics.trace_collect_startup_runner_ack_received === "no" && (sanitized.action?.buttonLabel === "Collecting videos..." || sanitized.primary_action?.label === "Collecting videos..." || sanitized.primaryAction?.label === "Collecting videos...")) {
    if (sanitized.primaryAction) {
      sanitized.primaryAction.key = "start_collecting";
      sanitized.primaryAction.label = "Start Collecting";
      sanitized.primaryAction.buttonLabel = "Start Collecting";
      sanitized.primaryAction.enabled = true;
      sanitized.primaryAction.disabledReason = null;
    }
    if (sanitized.primary_action) {
      sanitized.primary_action.key = "start_collecting";
      sanitized.primary_action.label = "Start Collecting";
      sanitized.primary_action.enabled = true;
      sanitized.primary_action.reason = null;
    }
    if (sanitized.action) {
      sanitized.action.key = "start_collecting";
      sanitized.action.buttonLabel = "Start Collecting";
      sanitized.action.enabled = true;
      sanitized.action.disabledReason = null;
    }
    reasons.push("startup_without_runner_ack_primary_action_unlocked");
  }
  if (isTerminalBatchContinuation(rawState, counters.pending_count)) {
    const continuationLabel = continuationButtonLabel(rawState);
    if (sanitized.primaryAction) sanitized.primaryAction.label = continuationLabel;
    if (sanitized.primary_action) sanitized.primary_action.label = continuationLabel;
    if (sanitized.action) sanitized.action.buttonLabel = continuationLabel;
    reasons.push("batch_safe_mode_completed_pending");
  }
  if (
    !isHybridCollectJobLiveForPresentation(rawState)
    && (rawState.post_scan_counter_snapshot?.status === "applied" || popupMetrics.diagnostics.popup_metrics_collect_job_progress_available === "yes" || counters.applied && counters.profile_already_collected_count > 0)
  ) {
    if (sanitized.counts) {
      sanitized.counts.newCount = popupMetrics.profile.new_count;
      sanitized.counts.incompleteCount = popupMetrics.profile.incomplete_count;
      sanitized.counts.failedCount = popupMetrics.profile.need_retry_count;
      sanitized.counts.alreadyCollectedCount = popupMetrics.profile.already_collected_count;
      sanitized.counts.queueCount = popupMetrics.profile.queue_count;
    }
    if (sanitized.compact_metrics) sanitized.compact_metrics.pending = popupMetrics.profile.queue_count;
    if (sanitized.stats_summary?.metrics) {
      for (const metric of sanitized.stats_summary.metrics) {
        if (metric.label === "New") metric.value = String(popupMetrics.profile.new_count);
        if (metric.label === "Queued") metric.value = String(popupMetrics.profile.queue_count);
      }
    }
    setTechnicalRow(sanitized.details?.technical_rows, "Profile already collected count", String(popupMetrics.profile.already_collected_count));
    setTechnicalRow(sanitized.details?.technical_rows, "Profile eligible count", String(popupMetrics.profile.eligible_count));
    setTechnicalRow(sanitized.details?.technical_rows, "Profile queue total count", String(popupMetrics.profile.profile_total_count));
    reasons.push("backend_reconciled_profile_counters");
    reasons.push("popup_reconciled_display_metrics");
  }
  sanitized.diagnostics = {
    ...(sanitized.diagnostics ?? {}),
    ...lock.diagnostics,
    ...counters.diagnostics,
    ...popupMetrics.diagnostics,
    popup_view_state_sanitized: reasons.length > 0 ? "yes" : "no",
    popup_view_state_sanitized_reasons: reasons
  };
  return sanitized;
}

export function sanitizeCanonicalPrimaryAction(action: CanonicalScannerPrimaryAction, state: WholeProfileHarvestState): CanonicalScannerPrimaryAction {
  const lock = deriveAuthoritativeRunnerLock(state);
  const counters = deriveAuthoritativeProfileCounters(state);
  const runtimeUi = activeCollectRuntimeUiAuthority(state);
  if (!runtimeUi.active && !lock.active && !isTerminalBatchContinuation(state, counters.pending_count)) return action;
  const label = runtimeUi.active
    ? runtimeUi.label
    : lock.active && lock.diagnostics.trace_collect_stale_check_may_be_alive !== "yes" && (lock.diagnostics.trace_ui_canonical_state === "waiting_for_active_tab" || lock.diagnostics.trace_ui_canonical_state === "paused_tab_inactive" || lock.source === "collect_job_soft_stale")
      ? "Paused: return to the Douyin tab to continue."
      : lock.active
        ? "Collecting videos..."
        : continuationButtonLabel(state);
  return {
    ...action,
    key: runtimeUi.active || lock.active ? "pause" : action.key,
    title: runtimeUi.active || lock.active ? "Collecting videos" : action.title,
    label,
    enabled: runtimeUi.active || lock.active ? false : action.enabled,
    disabledReason: runtimeUi.active || lock.active ? null : action.disabledReason,
    description: runtimeUi.active || lock.active ? "Collection is running. Duplicate Start Collecting clicks are suppressed." : action.description,
    decisionTrace: {
      ...action.decisionTrace,
      collection_runner_active: runtimeUi.active || lock.active,
      primary_action_locked_reason: runtimeUi.active ? "collection_running" : lock.reason,
      selectedAction: runtimeUi.active || lock.active ? "pause" : action.decisionTrace.selectedAction,
      selected_action: runtimeUi.active || lock.active ? "pause" : action.decisionTrace.selected_action,
      pending_count: counters.pending_count,
      reason: runtimeUi.active || lock.active ? "collection_running" : action.decisionTrace.reason
    }
  };
}

export function isStartCollectingAction(actionKey: ScannerActionKey | string): boolean {
  return actionKey === "start_collecting";
}
