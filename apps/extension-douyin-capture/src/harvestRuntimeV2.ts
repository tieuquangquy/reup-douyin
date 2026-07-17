import { FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY } from "./flushQueue.js";
import type {
  FullModalHarvestItemPayload,
  FullModalHarvestLastItemSummary,
  FullModalHarvestProgress,
  FullModalHarvestProbeResult,
  HarvestRuntimeV2PauseReason,
  HarvestRuntimeV2Phase,
  HarvestRuntimeV2State,
  HarvestRuntimeV2Status,
  HarvestRuntimeV2TargetStatus,
  HarvestRuntimeV2TransitionLogEntry
} from "./types.js";

export const HARVEST_RUNTIME_V2_KEY = "douyinSafeHarvestRun";
export const HARVEST_PENDING_FLUSH_QUEUE_V2_KEY = "douyinHarvestPendingFlushQueueV2";
export const HARVEST_RUNNER_V2_SCHEMA_VERSION = "phase17c_safe_runner";
export const HARVEST_RUNTIME_TRANSITION_LOG_LIMIT = 50;

export const LEGACY_HARVEST_STORAGE_KEYS = [
  "harvestState",
  "smartHarvestState",
  "fullModalHarvestState",
  "modalHarvestProgress",
  "harvestProgress",
  "smartCaptureState",
  "resumeState",
  "douyinFullModalHarvestState",
  "douyinFullModalHarvestProgress",
  "douyinSmartCaptureHarvestState",
  "douyinSmartHarvestState",
  "douyinTargetAwemeQueue",
  "douyinPendingFlushQueue",
  "douyinRetryQueue",
  "douyinFailedQueue",
  "douyinHarvestRuntimePhase11",
  "douyinHarvestRuntimePhase12",
  "douyinHarvestRuntimePhase13",
  FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY
] as const;

export const ALLOWED_HARVEST_PAUSE_REASONS = [
  "operator_stop",
  "backend_flush_failed",
  "content_script_unavailable",
  "calibration_invalid",
  "captcha_required",
  "consecutive_failures",
  "harvest_loop_inactive"
] as const satisfies readonly Exclude<HarvestRuntimeV2PauseReason, null>[];

type HarvestRuntimeV2TargetState = HarvestRuntimeV2TargetStatus["status"];

type TransitionMeta = {
  reason?: string | null;
  caller: string;
  stack_or_location?: string | null;
  target_index?: number | null;
  aweme_id?: string | null;
};

type DerivedRuntimeStats = {
  counts: HarvestRuntimeV2State["counts"];
  processed_count: number;
  remaining_count: number;
  current_target_index: number;
  repaired_target_index: boolean;
};

export function createIdleHarvestRuntimeV2(now = new Date()): HarvestRuntimeV2State {
  const iso = now.toISOString();
  return {
    schema_version: HARVEST_RUNNER_V2_SCHEMA_VERSION,
    run_id: null,
    status: "idle",
    phase: "idle",
    pause_reason: null,
    target_aweme_ids: [],
    target_status: {},
    current_target_index: 0,
    current_aweme_id: null,
    previous_aweme_id: null,
    counts: {
      target: 0,
      updated: 0,
      failed: 0,
      skipped: 0,
      pending_flush: 0,
      flushed: 0,
      flush_attempt_count: 0,
      duplicates: 0
    },
    last_metrics: null,
    recent_items: [],
    profile_card_evidence_by_aweme_id: {},
    state_transition_log: [],
    started_at: null,
    updated_at: iso,
    heartbeat_at: null,
    last_error: null
  };
}

export function createHarvestRuntimeV2(runId: string, targetAwemeIds: string[], now = new Date(), profileCardEvidenceByAwemeId: HarvestRuntimeV2State["profile_card_evidence_by_aweme_id"] = {}): HarvestRuntimeV2State {
  const iso = now.toISOString();
  const uniqueTargetAwemeIds = [...new Set(targetAwemeIds.map((awemeId) => awemeId.trim()).filter(Boolean))];
  const targetStatus = Object.fromEntries(
    uniqueTargetAwemeIds.map((awemeId, index) => [
      awemeId,
      {
        index: index + 1,
        status: "pending",
        attempts: 0,
        last_error: null
      } satisfies HarvestRuntimeV2TargetStatus
    ])
  );
  const runtime = {
    ...createIdleHarvestRuntimeV2(now),
    run_id: runId,
    status: "running" as const,
    phase: uniqueTargetAwemeIds.length > 0 ? ("opening_target" as const) : ("completed" as const),
    target_aweme_ids: uniqueTargetAwemeIds,
    target_status: targetStatus,
    current_target_index: uniqueTargetAwemeIds.length > 0 ? 1 : 0,
    started_at: iso,
    updated_at: iso,
    heartbeat_at: iso,
    profile_card_evidence_by_aweme_id: { ...profileCardEvidenceByAwemeId }
  } satisfies HarvestRuntimeV2State;
  return deriveRuntimeState(runtime, 0);
}

export function touchHarvestRuntimeV2(runtime: HarvestRuntimeV2State, updates?: Partial<HarvestRuntimeV2State>, now = new Date()): HarvestRuntimeV2State {
  return deriveRuntimeState(
    {
      ...runtime,
      ...updates,
      updated_at: now.toISOString()
    },
    updates?.counts?.pending_flush ?? runtime.counts.pending_flush
  );
}

export function heartbeatHarvestRuntimeV2(runtime: HarvestRuntimeV2State, now = new Date()): HarvestRuntimeV2State {
  const iso = now.toISOString();
  return deriveRuntimeState(
    {
      ...runtime,
      heartbeat_at: iso,
      updated_at: iso
    },
    runtime.counts.pending_flush
  );
}

export function transitionHarvestRuntime(
  runtime: HarvestRuntimeV2State,
  nextPatch: Partial<HarvestRuntimeV2State>,
  meta: TransitionMeta,
  now = new Date()
): HarvestRuntimeV2State {
  const current = deriveRuntimeState(runtime, runtime.counts.pending_flush);
  const attemptedStatus = nextPatch.status ?? current.status;
  const attemptedPhase = nextPatch.phase ?? current.phase;
  const attemptedPauseReason = nextPatch.pause_reason ?? current.pause_reason;
  const attemptedPaused = attemptedStatus === "paused" || attemptedPhase === "paused";
  if (attemptedPaused && !isAllowedPauseReason(attemptedPauseReason)) {
    return withTransitionLog(
      deriveRuntimeState(
        {
          ...current,
          updated_at: now.toISOString()
        },
        current.counts.pending_flush
      ),
      {
        timestamp: now.toISOString(),
        from_status: current.status,
        to_status: current.status,
        from_phase: current.phase,
        to_phase: current.phase,
        reason: "rejected_unauthorized_pause",
        caller: meta.caller,
        stack_or_location: meta.stack_or_location ?? null,
        target_index: meta.target_index ?? current.current_target_index,
        aweme_id: meta.aweme_id ?? current.current_aweme_id
      }
    );
  }

  const merged = deriveRuntimeState(
    {
      ...current,
      ...nextPatch,
      updated_at: now.toISOString()
    },
    nextPatch.counts?.pending_flush ?? current.counts.pending_flush
  );
  if (
    merged.status === current.status &&
    merged.phase === current.phase &&
    merged.pause_reason === current.pause_reason &&
    merged.current_target_index === current.current_target_index &&
    merged.current_aweme_id === current.current_aweme_id
  ) {
    return merged;
  }
  return withTransitionLog(merged, {
    timestamp: now.toISOString(),
    from_status: current.status,
    to_status: merged.status,
    from_phase: current.phase,
    to_phase: merged.phase,
    reason: meta.reason ?? merged.pause_reason ?? null,
    caller: meta.caller,
    stack_or_location: meta.stack_or_location ?? null,
    target_index: meta.target_index ?? merged.current_target_index,
    aweme_id: meta.aweme_id ?? merged.current_aweme_id
  });
}

export function normalizeHarvestRuntimeV2(runtime: HarvestRuntimeV2State | null | undefined): HarvestRuntimeV2State {
  const safe =
    runtime && runtime.schema_version === HARVEST_RUNNER_V2_SCHEMA_VERSION
      ? deriveRuntimeState(runtime, runtime.counts.pending_flush)
      : createIdleHarvestRuntimeV2();
  if (safe.status !== "paused" || isAllowedPauseReason(safe.pause_reason)) return safe;
  const recovered = transitionHarvestRuntime(
    {
      ...safe,
      last_error: null
    },
    {
      status: safe.run_id ? "running" : "idle",
      phase: safe.run_id ? "opening_target" : "idle",
      pause_reason: null,
      last_error: null
    },
    {
      caller: "normalizeHarvestRuntimeV2",
      reason: "auto_recovered_unauthorized_pause",
      stack_or_location: "harvestRuntimeV2.normalize"
    }
  );
  return deriveRuntimeState(recovered, recovered.counts.pending_flush);
}

export function firstPendingTarget(runtime: HarvestRuntimeV2State): { aweme_id: string; index: number } | null {
  for (const awemeId of runtime.target_aweme_ids) {
    const target = runtime.target_status[awemeId];
    if (target?.status === "processing" || target?.status === "pending") return { aweme_id: awemeId, index: target.index };
  }
  return null;
}

export function updateTargetStatus(
  runtime: HarvestRuntimeV2State,
  awemeId: string,
  status: HarvestRuntimeV2TargetState,
  options?: { attemptsDelta?: number; lastError?: string | null; now?: Date }
): HarvestRuntimeV2State {
  const existing = runtime.target_status[awemeId];
  if (!existing) return runtime;
  const nextTargetStatus = {
    ...runtime.target_status,
    [awemeId]: {
      ...existing,
      status,
      attempts: existing.attempts + (options?.attemptsDelta ?? 0),
      last_error: options?.lastError ?? null
    }
  };
  return deriveRuntimeState(
    {
      ...runtime,
      target_status: nextTargetStatus,
      updated_at: (options?.now ?? new Date()).toISOString()
    },
    runtime.counts.pending_flush
  );
}

export function summarizeHarvestCounts(runtime: HarvestRuntimeV2State, pendingFlushCount: number): HarvestRuntimeV2State["counts"] {
  return deriveRuntimeStats(runtime, pendingFlushCount).counts;
}

export function appendRecentItem(
  runtime: HarvestRuntimeV2State,
  item: FullModalHarvestLastItemSummary,
  now = new Date()
): HarvestRuntimeV2State {
  const recentItems = [...runtime.recent_items, item].slice(-5);
  return deriveRuntimeState(
    {
      ...runtime,
      recent_items: recentItems,
      updated_at: now.toISOString()
    },
    runtime.counts.pending_flush
  );
}

export function pauseHarvestRuntimeV2(
  runtime: HarvestRuntimeV2State,
  pauseReason: Exclude<HarvestRuntimeV2PauseReason, null>,
  lastError: string | null,
  now = new Date(),
  caller = "pauseHarvestRuntimeV2"
): HarvestRuntimeV2State {
  return transitionHarvestRuntime(
    {
      ...runtime,
      last_error: lastError
    },
    {
      status: "paused",
      phase: "paused",
      pause_reason: pauseReason,
      last_error: lastError
    },
    {
      caller,
      reason: pauseReason,
      stack_or_location: caller
    },
    now
  );
}

export function failHarvestRuntimeV2(runtime: HarvestRuntimeV2State, lastError: string, now = new Date(), caller = "failHarvestRuntimeV2"): HarvestRuntimeV2State {
  return transitionHarvestRuntime(
    runtime,
    {
      status: "failed",
      phase: "failed",
      last_error: lastError,
      pause_reason: null
    },
    {
      caller,
      reason: lastError,
      stack_or_location: caller
    },
    now
  );
}

export function completeHarvestRuntimeV2(runtime: HarvestRuntimeV2State, now = new Date(), caller = "completeHarvestRuntimeV2"): HarvestRuntimeV2State {
  const failedCount = Object.values(runtime.target_status).filter((item) => item.status === "failed").length;
  return transitionHarvestRuntime(
    runtime,
    {
      status: failedCount > 0 ? "completed_with_warnings" : "completed",
      phase: "completed",
      pause_reason: null,
      last_error: failedCount > 0 ? `Harvest completed with warnings. Failed ${failedCount}.` : null
    },
    {
      caller,
      reason: failedCount > 0 ? "completed_with_warnings" : "completed",
      stack_or_location: caller
    },
    now
  );
}

export function runtimeV2ToProgress(runtime: HarvestRuntimeV2State, pendingItems: FullModalHarvestItemPayload[] = []): FullModalHarvestProgress {
  const normalized = normalizeHarvestRuntimeV2(deriveRuntimeState(runtime, pendingItems.length));
  const counts = summarizeHarvestCounts(normalized, pendingItems.length);
  const processedCount = counts.updated + counts.failed + counts.skipped;
  const failedTargets = Object.entries(normalized.target_status)
    .filter(([, item]) => item.status === "failed")
    .map(([awemeId, item]) => ({
      aweme_id: awemeId,
      index: item.index,
      status: "failed" as const,
      reason: item.last_error,
      attempts: item.attempts,
      updated_at: normalized.updated_at ?? new Date().toISOString()
    }));
  const elapsedSeconds =
    normalized.started_at == null ? null : Math.max(0, Math.round((Date.now() - new Date(normalized.started_at).getTime()) / 1000));
  const averageSecondsPerItem = processedCount > 0 && elapsedSeconds != null ? Math.round((elapsedSeconds / processedCount) * 10) / 10 : null;
  const etaSeconds =
    averageSecondsPerItem != null ? Math.max(0, Math.round((counts.target - processedCount) * averageSecondsPerItem)) : null;
  const currentPhase: NonNullable<FullModalHarvestProgress["phase"]> =
    normalized.phase === "resolving_plan" || normalized.phase === "opening_target" || normalized.phase === "advancing"
      ? "harvesting"
      : normalized.phase === "waiting_modal" || normalized.phase === "settling_modal"
        ? "waiting_modal_change"
        : normalized.phase === "extracting" || normalized.phase === "validating" || normalized.phase === "marking_updated"
          ? "extracting_metrics"
          : (normalized.phase as NonNullable<FullModalHarvestProgress["phase"]>);
  const currentState: NonNullable<FullModalHarvestProgress["current_state"]> =
    normalized.status === "running"
      ? "harvesting"
      : normalized.status === "paused"
        ? "paused"
        : normalized.status === "failed"
          ? "failed"
          : normalized.status === "completed_with_warnings"
            ? "completed_with_warnings"
            : normalized.status === "completed"
              ? "completed"
              : "stopped";
  const inferredItemStage: NonNullable<FullModalHarvestProgress["item_stage"]> =
    normalized.phase === "extracting"
      ? "extracting"
      : normalized.phase === "flushing"
        ? "flushing"
        : normalized.phase === "waiting_modal" || normalized.phase === "settling_modal"
          ? "navigating"
          : normalized.phase === "opening_target" || normalized.phase === "resolving_plan" || normalized.phase === "advancing"
            ? "navigating"
            : normalized.phase === "validating" || normalized.phase === "marking_updated"
              ? "committing"
              : "idle";
  return {
    running: normalized.status === "running",
    harvest_status:
      normalized.status === "completed_with_warnings"
        ? "completed_with_warnings"
        : normalized.status === "completed"
          ? "completed"
          : normalized.status === "failed"
            ? "failed"
            : normalized.status === "paused"
              ? "paused"
              : normalized.status === "running"
                ? "running"
                : "idle",
    harvest_loop_heartbeat_at: normalized.heartbeat_at,
    current_state: currentState,
    phase: currentPhase,
    target_count: counts.target,
    current_index: normalized.current_target_index,
    current_aweme_id: normalized.current_aweme_id,
    harvested_count: counts.updated,
    processed_count: processedCount,
    updated_count: counts.updated,
    skipped_count: counts.skipped,
    remaining_count: Math.max(0, counts.target - processedCount),
    pending_count: pendingItems.length,
    duplicate_count: counts.duplicates,
    failed_count: counts.failed,
    flushed_count: counts.flushed,
    flush_attempt_count: counts.flush_attempt_count ?? 0,
    ...(elapsedSeconds != null ? { elapsed_seconds: elapsedSeconds } : {}),
    average_seconds_per_item: averageSecondsPerItem,
    eta_seconds: etaSeconds,
    last_error: normalized.last_error,
    stopped_reason: normalized.pause_reason,
    can_resume: normalized.status === "paused" && isAllowedPauseReason(normalized.pause_reason),
    last_extracted_metrics: normalized.last_metrics,
    recent_items: normalized.recent_items,
    previous_aweme_id: normalized.previous_aweme_id,
    runtime_transition_log: normalized.state_transition_log ?? [],
    target_status_map: Object.fromEntries(
      Object.entries(normalized.target_status).map(([awemeId, status]) => [
        awemeId,
        {
          aweme_id: awemeId,
          index: status.index,
          status: status.status === "processing" ? "pending" : status.status,
          attempts: status.attempts,
          updated_at: normalized.updated_at ?? new Date().toISOString(),
          reason: status.last_error
        }
      ])
    ),
    failed_targets: failedTargets,
    item_stage: inferredItemStage,
    phase_elapsed_ms: null,
    extracted_not_committed_ms: null,
    last_commit_result: null,
    repair_extracted_not_committed_count: 0
  };
}

export function transitionEntriesForDisplay(runtime: HarvestRuntimeV2State, limit = 20): HarvestRuntimeV2TransitionLogEntry[] {
  return (runtime.state_transition_log ?? []).slice(-Math.max(1, limit));
}

function deriveRuntimeState(runtime: HarvestRuntimeV2State, pendingFlushCount: number): HarvestRuntimeV2State {
  const derived = deriveRuntimeStats(runtime, pendingFlushCount);
  let nextRuntime: HarvestRuntimeV2State = {
    ...runtime,
    current_target_index: derived.current_target_index,
    counts: derived.counts,
    state_transition_log: runtime.state_transition_log ?? []
  };
  if (derived.repaired_target_index) {
    nextRuntime = withTransitionLog(nextRuntime, {
      timestamp: nextRuntime.updated_at ?? new Date().toISOString(),
      from_status: nextRuntime.status,
      to_status: nextRuntime.status,
      from_phase: nextRuntime.phase,
      to_phase: nextRuntime.phase,
      reason: "repaired_target_index",
      caller: "deriveRuntimeState",
      stack_or_location: "harvestRuntimeV2.deriveRuntimeState",
      target_index: nextRuntime.current_target_index,
      aweme_id: nextRuntime.current_aweme_id
    });
  }
  return nextRuntime;
}

function deriveRuntimeStats(runtime: HarvestRuntimeV2State, pendingFlushCount: number): DerivedRuntimeStats {
  const statuses = Object.values(runtime.target_status);
  const updated = statuses.filter((item) => item.status === "updated").length;
  const failed = statuses.filter((item) => item.status === "failed").length;
  const skipped = statuses.filter((item) => item.status === "skipped").length;
  const processed_count = updated + failed + skipped;
  const target = runtime.target_aweme_ids.length;
  const pendingFlush = Math.max(0, pendingFlushCount);
  const flushedItems = Math.max(0, updated);
  const firstOpenTarget = runtime.target_aweme_ids
    .map((awemeId) => runtime.target_status[awemeId])
    .find((targetState) => targetState?.status === "processing" || targetState?.status === "pending");
  const derivedIndex = firstOpenTarget?.index ?? (target > 0 ? Math.min(target, processed_count + 1) : 0);
  return {
    counts: {
      target,
      updated,
      failed,
      skipped,
      pending_flush: pendingFlush,
      flushed: flushedItems,
      flush_attempt_count: runtime.counts.flush_attempt_count ?? 0,
      duplicates: runtime.counts.duplicates
    },
    processed_count,
    remaining_count: Math.max(0, target - processed_count),
    current_target_index: derivedIndex,
    repaired_target_index: runtime.current_target_index !== derivedIndex
  };
}

function withTransitionLog(runtime: HarvestRuntimeV2State, entry: HarvestRuntimeV2TransitionLogEntry): HarvestRuntimeV2State {
  return {
    ...runtime,
    state_transition_log: [...(runtime.state_transition_log ?? []), entry].slice(-HARVEST_RUNTIME_TRANSITION_LOG_LIMIT)
  };
}

function isAllowedPauseReason(reason: string | null | undefined): reason is Exclude<HarvestRuntimeV2PauseReason, null> {
  return typeof reason === "string" && (ALLOWED_HARVEST_PAUSE_REASONS as readonly string[]).includes(reason);
}
