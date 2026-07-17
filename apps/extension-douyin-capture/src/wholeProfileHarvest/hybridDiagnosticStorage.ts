/**
 * Throttled hybrid-runner fossil writes. Unbounded chrome.storage.local writes
 * (probe steps + per-item loop updates) hit MAX_WRITE_OPERATIONS_PER_HOUR and
 * abort Start Collecting before the runner can start.
 */

export const HYBRID_RUNNER_FOSSIL_KEY = "hybrid_runner_fossil" as const;

/** Cleared when a new collect click is blocked before dispatch so fossils stay attributable. */
export const HYBRID_RUNNER_FOSSIL_STALE_SUMMARY_RESET: Record<string, null> = {
  hybrid_runner_write_ok_count: null,
  hybrid_runner_write_fail_count: null,
  hybrid_runner_per_item_count: null,
  hybrid_runner_per_item_summary: null,
  hybrid_runner_actionable_count: null,
  hybrid_runner_loop_phase: null,
  hybrid_runner_loop_index: null,
  hybrid_runner_loop_total: null,
  hybrid_runner_loop_succeeded_so_far: null,
  hybrid_runner_loop_failed_so_far: null,
  hybrid_runner_loop_pending_so_far: null,
  hybrid_runner_pre_skip_total: null,
  hybrid_runner_pre_skip_already_collected: null,
  hybrid_runner_pre_skip_pending: null,
  hybrid_runner_pre_skip_source: null,
  hybrid_runner_outcome: null,
  hybrid_runner_error: null,
  hybrid_runner_post_run_backend_captured: null,
  hybrid_runner_post_run_tile_already: null,
  hybrid_runner_post_run_tile_new: null,
  hybrid_post_run_backend_captured: null,
  hybrid_post_run_backend_new: null,
  hybrid_collection_done_override_applied: null,
  hybrid_collection_done_completed_at: null,
  hybrid_collection_done_outcome: null,
  hybrid_runner_lazy_detail_attempted_count: null,
  hybrid_runner_lazy_detail_recovered_count: null,
  hybrid_backend_gap_missing_ids: null,
  hybrid_exact_tail_gap_mode: null,
  hybrid_force_exact_tail_gap_collect: null,
  hybrid_tail_gap_live_remaining: null,
  hybrid_tail_gap_tab_ensured: null,
  hybrid_tail_gap_tab_navigated: null,
  hybrid_tail_gap_tab_created: null,
  hybrid_tail_gap_tab_resolve_initial: null,
  hybrid_tail_gap_content_script_ready: null
};

export function buildHybridRunnerFossilPreflightBlockedPatch(
  reason: string,
  extra: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    ...HYBRID_RUNNER_FOSSIL_STALE_SUMMARY_RESET,
    hybrid_runner_entry_hit: "blocked_before_dispatch",
    hybrid_runner_outcome: "blocked_before_dispatch",
    hybrid_runner_error: reason,
    hybrid_runner_probe_step: typeof extra.hybrid_runner_probe_step === "string"
      ? extra.hybrid_runner_probe_step
      : "start_collecting_preflight_blocked",
    ...extra
  };
}

const FOSSIL_PERSIST_INTERVAL_MS = 10_000;
const FOSSIL_MILESTONE_MARKERS = [
  "step_1",
  "step_2d",
  "step_5",
  "pre_skip_",
  "pre_skip_completed",
  "pre_skip_failed",
  "phase_4",
  "loop_complete",
  "loop_failed",
  "hybrid_runner_entry",
  "hybrid_runner_ack",
  "capture_session"
];

let fossilMemoryBuffer: Record<string, unknown> = {};
let persistedFossilSnapshot: Record<string, unknown> = {};
let lastFossilPersistMs = 0;
let storageWriteQuotaBlocked = false;
let lastHeartbeatPersistMs = 0;

export const HYBRID_HEARTBEAT_PERSIST_INTERVAL_MS = 4_000;

export function isChromeStorageWriteQuotaError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return message.includes("MAX_WRITE_OPERATIONS_PER_HOUR")
    || message.includes("MAX_WRITE_OPERATIONS_PER_MINUTE")
    || message.includes("QUOTA_BYTES");
}

export function isChromeStorageWriteQuotaBlocked(): boolean {
  return storageWriteQuotaBlocked;
}

export function resetHybridFossilDiagnosticBuffer(): void {
  fossilMemoryBuffer = {};
  lastFossilPersistMs = 0;
}

export function readHybridFossilMemoryBuffer(): Record<string, unknown> {
  return { ...fossilMemoryBuffer };
}

export function mergeHybridFossilSources(...sources: Array<Record<string, unknown> | null | undefined>): Record<string, unknown> {
  return Object.assign({}, ...sources.filter((source): source is Record<string, unknown> => Boolean(source)));
}

/** Last persisted fossil snapshot — sync read for popup render without awaiting storage. */
export function readCachedPersistedHybridRunnerFossil(): Record<string, unknown> {
  return { ...persistedFossilSnapshot };
}

export function readMergedHybridFossilForRender(): Record<string, unknown> {
  return mergeHybridFossilSources(readHybridFossilMemoryBuffer(), persistedFossilSnapshot);
}

export async function readPersistedHybridRunnerFossil(): Promise<Record<string, unknown>> {
  try {
    const chromeApi = (globalThis as {
      chrome?: { storage?: { local?: { get?: (keys: string | string[]) => Promise<Record<string, unknown>> } } };
    }).chrome;
    const get = chromeApi?.storage?.local?.get;
    if (typeof get !== "function") return readCachedPersistedHybridRunnerFossil();
    const raw = await get.call(chromeApi!.storage!.local!, HYBRID_RUNNER_FOSSIL_KEY);
    const fossil = raw?.[HYBRID_RUNNER_FOSSIL_KEY];
    persistedFossilSnapshot = fossil && typeof fossil === "object"
      ? { ...fossil as Record<string, unknown> }
      : {};
    return readCachedPersistedHybridRunnerFossil();
  } catch {
    return readCachedPersistedHybridRunnerFossil();
  }
}

export function shouldThrottleHybridHeartbeatPersist(nowMs = Date.now()): boolean {
  if (storageWriteQuotaBlocked) return true;
  return nowMs - lastHeartbeatPersistMs < HYBRID_HEARTBEAT_PERSIST_INTERVAL_MS;
}

export function markHybridHeartbeatPersisted(nowMs = Date.now()): void {
  lastHeartbeatPersistMs = nowMs;
}

export async function safeChromeStorageLocalSet(items: Record<string, unknown>): Promise<boolean> {
  if (storageWriteQuotaBlocked) return false;
  try {
    const chromeApi = (globalThis as { chrome?: { storage?: { local?: { set?: (items: Record<string, unknown>) => Promise<void> } } } }).chrome;
    const set = chromeApi?.storage?.local?.set;
    if (typeof set !== "function") return false;
    await set.call(chromeApi!.storage!.local!, items);
    return true;
  } catch (error) {
    if (isChromeStorageWriteQuotaError(error)) {
      storageWriteQuotaBlocked = true;
      console.warn("[HYBRID_STORAGE] chrome.storage.local write quota exceeded; throttling further writes until extension reload.");
      return false;
    }
    throw error;
  }
}

function isFossilMilestonePatch(patch: Record<string, unknown>, step: string | null): boolean {
  if (step && FOSSIL_MILESTONE_MARKERS.some((marker) => step.includes(marker))) return true;
  const outcome = typeof patch.hybrid_runner_outcome === "string" ? patch.hybrid_runner_outcome : "";
  if (outcome && !outcome.includes("pending") && !outcome.includes("acknowledged_proceeding")) return true;
  const phase = typeof patch.hybrid_runner_loop_phase === "string" ? patch.hybrid_runner_loop_phase : "";
  if (phase.includes("completed") || phase.includes("failed") || phase === "pre_skip_completed" || phase === "pre_skip_failed") {
    return true;
  }
  return false;
}

export async function mergeHybridRunnerFossil(
  patch: Record<string, unknown>,
  options: { force?: boolean } = {}
): Promise<void> {
  const step = typeof patch.hybrid_runner_probe_step === "string"
    ? patch.hybrid_runner_probe_step
    : typeof fossilMemoryBuffer.hybrid_runner_probe_step === "string"
      ? fossilMemoryBuffer.hybrid_runner_probe_step
      : null;
  fossilMemoryBuffer = {
    ...fossilMemoryBuffer,
    ...patch,
    ...(step ? { hybrid_runner_probe_step: step } : {}),
    written_at: new Date().toISOString()
  };

  const now = Date.now();
  const shouldPersist = options.force === true
    || isFossilMilestonePatch(patch, step)
    || now - lastFossilPersistMs >= FOSSIL_PERSIST_INTERVAL_MS;
  if (!shouldPersist) return;

  lastFossilPersistMs = now;
  persistedFossilSnapshot = { ...fossilMemoryBuffer };
  await safeChromeStorageLocalSet({ [HYBRID_RUNNER_FOSSIL_KEY]: fossilMemoryBuffer });
}

export async function markHybridRunnerProbeStep(
  step: string,
  extra: Record<string, unknown> = {},
  options: { force?: boolean } = {}
): Promise<void> {
  await mergeHybridRunnerFossil({ hybrid_runner_probe_step: step, ...extra }, options);
}
