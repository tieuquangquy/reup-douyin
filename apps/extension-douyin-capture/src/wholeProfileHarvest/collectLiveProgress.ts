import type { WholeProfileHarvestState } from "./state.js";
import { isHybridNetworkCacheModeEnabledForCollect } from "./readiness.js";
import { staleLocalCollectedDisprovenByBackendEmpty } from "./profileContext.js";
import { resolveBackendCapturedCountFromState, resolveBackendPriorAlreadyForLiveCollect, resolveScannedTotalFromState } from "./backendCollectAuthority.js";
import type { ScannerControlPanelViewModel } from "./viewModel.js";

export type CollectLiveProgressPhase = "preparing" | "checking" | "saving" | "collecting";

export type CollectLiveProgressPresentation = {
  phase: CollectLiveProgressPhase;
  profileTotal: number;
  profileNumerator: number;
  profileTargetNumerator: number;
  profilePercent: number | null;
  profileIndeterminate: boolean;
  headerLabel: string;
  buttonLabel: string;
  description: string;
  priorAlready: number;
  savedTotal: number;
  checkedCount: number;
  readyCount: number;
  skippedCount: number;
  showBatchCard: boolean;
  batchAttempted: number;
  batchTotal: number;
  batchReady: number;
  batchNeedData: number;
  batchPercent: number | null;
  tilesAlreadyTarget: number;
  tiles: {
    alreadyCollectedCount: number;
    newCount: number;
    queueCount: number;
  };
};

function numericDiagnostic(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? Math.max(0, Math.round(parsed)) : null;
  }
  return null;
}

function resolveProfileTotal(state: WholeProfileHarvestState, _snapshot: WholeProfileHarvestState["post_scan_counter_snapshot"]): number {
  return resolveScannedTotalFromState(state);
}

function isHybridCollectionWorkflowActive(state: WholeProfileHarvestState): boolean {
  return (state.workflow.collection.status === "running" || state.workflow.collection.status === "opening_target")
    && state.workflow.active_task === "collect_videos";
}

export function computeProfileCollectPercent(collected: number, total: number): number | null {
  const safeTotal = Math.max(0, Math.round(total));
  if (safeTotal <= 0) return null;
  const safeCollected = Math.max(0, Math.min(Math.round(collected), safeTotal));
  if (safeCollected >= safeTotal) return 100;
  return Math.max(0, Math.min(99, Math.floor((safeCollected / safeTotal) * 100)));
}

function resolveHybridBatchPriorAlready(state: WholeProfileHarvestState): number | null {
  if (!isHybridNetworkCacheModeEnabledForCollect(state) || !isHybridCollectJobLive(state)) return null;
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const raw = numericDiagnostic(summary.hybrid_runner_batch_prior_already);
  if (raw == null) return null;
  const backend = resolveBackendPriorAlreadyForLiveCollect(state);
  return backend > 0 ? Math.min(raw, backend) : raw;
}

function resolveHybridBatchProgressCeiling(
  profileTotal: number,
  priorAlready: number,
  batchWindow: number
): number {
  if (profileTotal <= 0) return Math.max(0, priorAlready + Math.max(1, batchWindow));
  const profileRemaining = Math.max(0, profileTotal - priorAlready);
  const effectiveBatchWindow = Math.max(1, Math.min(batchWindow, profileRemaining));
  return Math.min(profileTotal, priorAlready + effectiveBatchWindow);
}

function resolveHybridBatchWindow(
  summary: Record<string, unknown>,
  selectedRaw: number | null,
  attempted: number,
  loopIndex: number,
  succeeded: number
): number {
  const actionable = numericDiagnostic(summary.hybrid_runner_batch_target_count)
    ?? numericDiagnostic(summary.hybrid_runner_actionable_count);
  if (actionable != null && actionable > 0) return actionable;
  if (selectedRaw != null) return Math.max(1, selectedRaw);
  return Math.max(attempted, loopIndex, succeeded, 1);
}

/**
 * Stable pre-batch captured baseline that survives job completion and post-run snapshot refresh.
 *
 * `hybrid_runner_batch_prior_already` only exists while the runner is live and is dropped from the
 * summary once the post-run refresh replaces it. `collect_job.pre_batch_backend_captured` is written
 * once at queue-filtering and never mutated for the batch, so it is the authoritative pre-batch floor
 * for computing live progress without double-counting a refreshed snapshot.
 */
function resolveHybridStablePreBatchBaseline(state: WholeProfileHarvestState): number | null {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const fromSummary = numericDiagnostic(summary.hybrid_runner_batch_prior_already);
  const fromJob = typeof state.collect_job.pre_batch_backend_captured === "number"
    && Number.isFinite(state.collect_job.pre_batch_backend_captured)
    ? Math.max(0, state.collect_job.pre_batch_backend_captured)
    : null;
  if (fromSummary != null && fromJob != null) return Math.min(fromSummary, fromJob);
  return fromSummary ?? fromJob;
}

/**
 * Profile-wide captured count for live hybrid progress.
 *
 * Must never add batch succeeded_count on top of a snapshot/`already_collected` value that already
 * includes this batch's writes (production: batch 2 showed 738/738 when snapshot refreshed to 735 and
 * succeeded=235). Progress is `stablePreBatchBaseline + succeeded`, but the refreshed backend captured
 * count is authoritative when higher, so the two never stack. Without a stable pre-batch baseline the
 * backend count is the only safe truth (adding succeeded there would double-count).
 */
export function resolveHybridProfileCapturedNumerator(
  state: WholeProfileHarvestState,
  succeeded: number
): number {
  const backendCaptured = resolveBackendCapturedCountFromState(state);
  const stableBaseline = resolveHybridStablePreBatchBaseline(state);
  const attempted = typeof state.collect_job.attempted_count === "number" && Number.isFinite(state.collect_job.attempted_count)
    ? Math.max(0, state.collect_job.attempted_count)
    : 0;
  if (stableBaseline != null) {
    const fromWrites = stableBaseline + succeeded;
    if (isLiveHybridWriteProgressFrame(state)) {
      // During a live batch: progress tracks write_ok only. Optimistic local snapshot
      // reconcile (production: 728 while backend truth was 571) must not inflate the bar.
      // Continuation frames between generations may momentarily read succeeded/attempted as 0
      // while the API snapshot already includes this batch — honor that API floor only then.
      if (succeeded === 0 && attempted === 0 && backendCaptured > stableBaseline) {
        return backendCaptured;
      }
      // Job-start frames inherit stale succeeded_count from the prior collect_job until the
      // hybrid runner heartbeat arrives (production: batch-2 retry flashed 739/739 = 571+168).
      if (
        attempted === 0
        && succeeded > 0
        && (state.collect_job.state === "starting" || state.collect_job.current_step === "starting")
      ) {
        return stableBaseline;
      }
      return fromWrites;
    }
    return Math.max(fromWrites, backendCaptured);
  }
  // No stable pre-batch baseline (fresh batch-1 style, prior ≈ 0): treat backend captured as the
  // floor and count succeeded on top. This can't double-count — if the backend already includes
  // succeeded, backendCaptured >= succeeded so max() picks backendCaptured.
  return Math.max(backendCaptured, succeeded);
}

function resolvePriorAlready(state: WholeProfileHarvestState, suppressStaleLocal: boolean): number {
  if (suppressStaleLocal) return 0;
  const batchPriorAlready = resolveHybridBatchPriorAlready(state);
  if (batchPriorAlready != null) return batchPriorAlready;
  if (isHybridNetworkCacheModeEnabledForCollect(state) && isHybridCollectJobLive(state)) {
    return resolveBackendPriorAlreadyForLiveCollect(state);
  }
  const snap = state.post_scan_counter_snapshot;
  const scanDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const queueAlready = state.harvest.queue.filter((item) => {
    const status = String(item.status);
    return status === "already_collected" || status === "backend_verified" || status === "complete" || status === "extracted" || item.capture_status === "complete";
  }).length;
  const diagnosticAlready = numericDiagnostic(
    scanDiagnostics.post_scan_backend_captured_count
      ?? scanDiagnostics.profile_already_collected_count
      ?? (state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
        ? (state.debug.last_response_summary as Record<string, unknown>).hybrid_runner_post_run_tile_already
        : null)
  ) ?? 0;
  return Math.max(
    snap?.status === "applied" ? snap.already_collected : 0,
    queueAlready,
    state.classification.status === "success" ? state.classification.counts.complete : 0,
    diagnosticAlready
  );
}

function isHybridCollectLiveStep(liveStep: string): boolean {
  return liveStep.includes("hybrid_loop") || liveStep === "hybrid_unattended_chain_continue";
}

export function shouldShowCollectBatchCard(state: WholeProfileHarvestState, profileTotal: number, batchTotal: number): boolean {
  // Whole-profile hybrid collect always uses profile-level progress only.
  if (isHybridNetworkCacheModeEnabledForCollect(state)) return false;
  if (profileTotal <= 0 || batchTotal <= 0) return false;
  if (batchTotal >= profileTotal) return false;
  return batchTotal < profileTotal;
}

function isHybridPreLoopMetricsRecoveryFrame(
  state: WholeProfileHarvestState,
  summary: Record<string, unknown>,
  succeeded: number,
  attempted: number
): boolean {
  if (succeeded > 0 || attempted > 0) return false;
  const loopPhase = String(summary.hybrid_runner_loop_phase ?? "");
  if (loopPhase === "metrics_miss_unrecoverable" || loopPhase.startsWith("hybrid_loop_")) return false;
  const probe = String(summary.hybrid_runner_probe_step ?? "");
  if (/^step_[67]/.test(probe)) return false;
  const step = String(state.collect_job.current_step ?? "");
  const jobLive = state.collect_job.state === "running"
    || state.collect_job.state === "starting"
    || state.collect_job.state === "running_tab_inactive";
  if (!jobLive) return false;
  return step.includes("hydrat")
    || step.startsWith("hybrid_runner_")
    || probe.startsWith("step_5")
    || loopPhase === "targets_selected"
    || loopPhase === "detail_hydration"
    || loopPhase === "profile_post_tail";
}

function isHybridCollectJobLive(state: WholeProfileHarvestState): boolean {
  return state.collect_job.state === "starting"
    || state.collect_job.state === "running"
    || state.collect_job.state === "running_tab_inactive";
}

/** True while hybrid collect job is live — local snapshot must not inflate progress numerator. */
function isLiveHybridWriteProgressFrame(state: WholeProfileHarvestState): boolean {
  if (!isHybridNetworkCacheModeEnabledForCollect(state)) return false;
  const harvestPausedForAuthOrSafety = state.harvest.status === "paused"
    || state.harvest.paused_reason === "backend_auth_required"
    || state.harvest.paused_reason === "douyin_login_required";
  const collectJobTerminal = state.collect_job.state === "completed"
    || state.collect_job.state === "failed"
    || state.collect_job.state === "stuck"
    || state.collect_job.state === "aborted_by_user_fix_stuck";
  if (harvestPausedForAuthOrSafety || collectJobTerminal) return false;
  return isHybridCollectJobLive(state) || isHybridCollectionWorkflowActive(state);
}

export function buildCollectLiveProgressPresentation(state: WholeProfileHarvestState): CollectLiveProgressPresentation | null {
  const liveStep = String(state.collect_job.current_step ?? "");
  const attempted = typeof state.collect_job.attempted_count === "number" && Number.isFinite(state.collect_job.attempted_count)
    ? Math.max(0, state.collect_job.attempted_count)
    : 0;
  const succeeded = typeof state.collect_job.succeeded_count === "number" && Number.isFinite(state.collect_job.succeeded_count)
    ? Math.max(0, state.collect_job.succeeded_count)
    : 0;
  const skipped = typeof state.collect_job.skipped_count === "number" && Number.isFinite(state.collect_job.skipped_count)
    ? Math.max(0, state.collect_job.skipped_count)
    : 0;
  const selectedRaw = typeof state.collect_job.selected_count === "number" && state.collect_job.selected_count > 0
    ? state.collect_job.selected_count
    : typeof state.collect_job.batch_limit === "number" && state.collect_job.batch_limit > 0
      ? state.collect_job.batch_limit
      : null;
  const batchTotal = selectedRaw != null
    ? Math.max(selectedRaw, attempted, succeeded)
    : (attempted > 0 || succeeded > 0 ? Math.max(attempted, succeeded) : null);

  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const loopIndex = numericDiagnostic(summary.hybrid_runner_loop_index) ?? attempted;
  const snapshot = state.post_scan_counter_snapshot;
  const suppressStaleLocal = staleLocalCollectedDisprovenByBackendEmpty(state);
  const profileTotal = resolveProfileTotal(state, snapshot);
  const priorAlready = resolvePriorAlready(state, suppressStaleLocal);
  const batchPriorAlready = resolveHybridBatchPriorAlready(state);
  const stablePreBatchBaseline = resolveHybridStablePreBatchBaseline(state);
  const backendCaptured = resolveBackendCapturedCountFromState(state);
  const progressBaseline = stablePreBatchBaseline ?? batchPriorAlready ?? priorAlready;
  const hybridUnified = isHybridNetworkCacheModeEnabledForCollect(state)
    && (isHybridCollectLiveStep(liveStep) || isHybridCollectJobLive(state) || isHybridCollectionWorkflowActive(state));

  if (hybridUnified) {
    const savedTotal = resolveHybridProfileCapturedNumerator(state, succeeded);
    const checkedCount = Math.max(attempted, loopIndex);
    const batchWindow = resolveHybridBatchWindow(summary, selectedRaw, attempted, loopIndex, succeeded);
    const batchCeiling = resolveHybridBatchProgressCeiling(profileTotal, progressBaseline, batchWindow);
    const profileNumerator = Math.min(batchCeiling, savedTotal);
    const profileTargetNumerator = profileNumerator;
    const preLoopRecovery = isHybridPreLoopMetricsRecoveryFrame(state, summary, succeeded, attempted);
    const profileIndeterminate = !preLoopRecovery && profileTotal > 0
      && succeeded === 0
      && attempted === 0
      && profileNumerator <= progressBaseline
      && backendCaptured <= progressBaseline;
    const profilePercent = (profileIndeterminate || preLoopRecovery) || profileTotal <= 0
      ? null
      : computeProfileCollectPercent(profileNumerator, profileTotal);
    const headerLabel = preLoopRecovery
      ? "Recovering metrics…"
      : profileTotal > 0
        ? (profileIndeterminate ? "Preparing…" : `Collecting ${profileNumerator} / ${profileTotal}`)
        : "Collecting…";
    const description = preLoopRecovery
      ? `Fetching video details from Douyin… ${profileNumerator} / ${profileTotal} saved so far. Refresh the profile tab if this stalls.`
      : profileTotal > 0
        ? (profileIndeterminate
          ? `Starting collection… ${profileTotal} videos in profile.`
          : skipped > 0
            ? `Collecting videos ${profileNumerator} / ${profileTotal} · ${skipped} need data.`
            : `Collecting videos ${profileNumerator} / ${profileTotal}.`)
        : "Collecting videos…";
    const remaining = Math.max(0, profileTotal - savedTotal - skipped);
    const tiles = {
      alreadyCollectedCount: savedTotal,
      newCount: remaining,
      queueCount: remaining
    };
    const batchAttempted = Math.max(attempted, loopIndex, succeeded);
    const batchPercent = batchTotal != null && batchTotal > 0
      ? Math.max(0, Math.min(100, Math.round((batchAttempted / batchTotal) * 100)))
      : null;

    return {
      phase: preLoopRecovery ? "checking" : profileIndeterminate ? "preparing" : "collecting",
      profileTotal,
      profileNumerator,
      profileTargetNumerator,
      profilePercent,
      profileIndeterminate: preLoopRecovery ? true : profileIndeterminate,
      headerLabel,
      buttonLabel: headerLabel,
      description,
      priorAlready: progressBaseline,
      savedTotal,
      checkedCount: Math.max(checkedCount, attempted, loopIndex),
      readyCount: succeeded,
      skippedCount: skipped,
      showBatchCard: false,
      batchAttempted,
      batchTotal: batchTotal ?? Math.max(batchAttempted, 1),
      batchReady: succeeded,
      batchNeedData: skipped,
      batchPercent,
      tilesAlreadyTarget: savedTotal,
      tiles
    };
  }

  // Hybrid must never use the legacy checking path (false 735/735 while batch hydrates).
  if (isHybridNetworkCacheModeEnabledForCollect(state)) {
    const savedTotal = resolveHybridProfileCapturedNumerator(state, succeeded);
    const checkedCount = Math.max(attempted, loopIndex);
    const batchWindow = resolveHybridBatchWindow(summary, selectedRaw, attempted, loopIndex, succeeded);
    const batchCeiling = resolveHybridBatchProgressCeiling(profileTotal, progressBaseline, batchWindow);
    const profileNumerator = Math.min(batchCeiling, savedTotal);
    const profileIndeterminate = profileTotal > 0
      && succeeded === 0
      && attempted === 0
      && profileNumerator <= progressBaseline
      && backendCaptured <= progressBaseline;
    const profilePercent = profileIndeterminate || profileTotal <= 0
      ? null
      : computeProfileCollectPercent(profileNumerator, profileTotal);
    const postRunPending = state.collect_job.state === "completed"
      && summary.hybrid_runner_post_run_summary_status === "not_attempted";
    const headerLabel = postRunPending
      ? "Syncing with Capture Inbox…"
      : profileTotal > 0
        ? (profileIndeterminate ? "Preparing…" : `Collecting ${profileNumerator} / ${profileTotal}`)
        : "Collecting…";
    const description = postRunPending
      ? "Updating counts from Capture Inbox…"
      : profileTotal > 0
        ? (profileIndeterminate
          ? `Starting collection… ${profileTotal} videos in profile.`
          : skipped > 0
            ? `Collecting videos ${profileNumerator} / ${profileTotal} · ${skipped} need data.`
            : `Collecting videos ${profileNumerator} / ${profileTotal}.`)
        : "Collecting videos…";
    const remaining = Math.max(0, profileTotal - savedTotal - skipped);
    const batchAttempted = Math.max(attempted, loopIndex, succeeded);
    return {
      phase: postRunPending ? "saving" : profileIndeterminate ? "preparing" : "collecting",
      profileTotal,
      profileNumerator,
      profileTargetNumerator: profileNumerator,
      profilePercent,
      profileIndeterminate: postRunPending ? true : profileIndeterminate,
      headerLabel,
      buttonLabel: headerLabel,
      description,
      priorAlready: progressBaseline,
      savedTotal,
      checkedCount: Math.max(checkedCount, attempted, loopIndex),
      readyCount: succeeded,
      skippedCount: skipped,
      showBatchCard: false,
      batchAttempted,
      batchTotal: batchTotal ?? Math.max(batchAttempted, 1),
      batchReady: succeeded,
      batchNeedData: skipped,
      batchPercent: batchTotal != null && batchTotal > 0
        ? Math.max(0, Math.min(100, Math.round((batchAttempted / batchTotal) * 100)))
        : null,
      tilesAlreadyTarget: savedTotal,
      tiles: {
        alreadyCollectedCount: savedTotal,
        newCount: remaining,
        queueCount: remaining
      }
    };
  }

  const isSaving = liveStep.includes("flush");
  const isPreparing = !isSaving
    && attempted === 0
    && succeeded === 0
    && !liveStep.includes("hybrid_loop");
  const isChecking = !isPreparing && !isSaving;

  const checkedCount = Math.max(attempted, loopIndex);
  const savedTotal = isSaving ? priorAlready + succeeded : priorAlready;
  const hybridCumulativeChecking = false;
  const batchWindow = selectedRaw != null
    ? Math.max(1, selectedRaw)
    : Math.max(checkedCount, succeeded, 1);
  const hybridBatchCeiling = hybridCumulativeChecking
    ? resolveHybridBatchProgressCeiling(profileTotal, priorAlready, batchWindow)
    : profileTotal;
  const profileTargetNumerator = isSaving
    ? Math.min(hybridBatchCeiling, savedTotal)
    : isChecking
      ? (hybridCumulativeChecking
        ? Math.min(hybridBatchCeiling, priorAlready + checkedCount)
        : checkedCount)
      : 0;
  const profileNumerator = profileTargetNumerator;
  const profileIndeterminate = (isPreparing || (isChecking && checkedCount === 0)) && profileTotal > 0;
  const profilePercent = profileIndeterminate || profileTotal <= 0
    ? null
    : computeProfileCollectPercent(profileNumerator, profileTotal);

  const phase: CollectLiveProgressPhase = isSaving ? "saving" : isChecking ? "checking" : "preparing";
  const headerLabel = profileTotal > 0
    ? (profileIndeterminate
      ? (phase === "preparing" ? "Preparing…" : "Checking…")
      : phase === "saving"
        ? `Saving ${profileNumerator} / ${profileTotal}`
        : `Checking ${profileNumerator} / ${profileTotal}`)
    : phase === "saving"
      ? `Saving ${succeeded}`
      : phase === "checking"
        ? `Checking ${Math.max(attempted, succeeded)}`
        : "Preparing…";

  const description = profileTotal > 0
    ? (phase === "preparing"
      ? `Starting collection… ${profileTotal} videos in profile.`
      : phase === "saving"
        ? `Saving to Capture Inbox… ${profileNumerator} / ${profileTotal}.`
        : checkedCount > 0
          ? `Checking metadata ${profileNumerator} / ${profileTotal} · ${succeeded} ready to save · ${skipped} need data.`
          : `Starting collection… ${profileTotal} videos in profile.`)
    : phase === "saving"
      ? `Saving to Capture Inbox… ${succeeded} written this run.`
      : phase === "checking" && batchTotal != null
        ? `Checking this batch… ${Math.max(attempted, succeeded)} / ${batchTotal} · ${succeeded} ready · ${skipped} need data.`
        : "Starting collection…";

  const remaining = Math.max(0, profileTotal - savedTotal - skipped);
  const tilesAlreadyTarget = savedTotal;
  const tiles = phase === "preparing"
    ? {
      alreadyCollectedCount: priorAlready,
      newCount: Math.max(0, profileTotal - priorAlready - skipped),
      queueCount: Math.max(0, profileTotal - priorAlready - skipped)
    }
    : phase === "checking"
      ? {
        alreadyCollectedCount: priorAlready,
        newCount: Math.max(0, profileTotal - priorAlready - skipped),
        queueCount: Math.max(0, profileTotal - priorAlready - skipped)
      }
      : {
        alreadyCollectedCount: savedTotal,
        newCount: remaining,
        queueCount: remaining
      };

  const showBatchCard = batchTotal != null && shouldShowCollectBatchCard(state, profileTotal, batchTotal);
  const batchAttempted = Math.max(attempted, succeeded);
  const batchPercent = batchTotal != null && batchTotal > 0
    ? Math.max(0, Math.min(100, Math.round((batchAttempted / batchTotal) * 100)))
    : null;

  return {
    phase,
    profileTotal,
    profileNumerator,
    profileTargetNumerator,
    profilePercent,
    profileIndeterminate,
    headerLabel,
    buttonLabel: headerLabel,
    description,
    priorAlready,
    savedTotal,
    checkedCount,
    readyCount: succeeded,
    skippedCount: skipped,
    showBatchCard,
    batchAttempted,
    batchTotal: batchTotal ?? Math.max(batchAttempted, 1),
    batchReady: succeeded,
    batchNeedData: skipped,
    batchPercent,
    tilesAlreadyTarget,
    tiles
  };
}

export function applyCollectLiveProgressToViewModel(
  viewModel: ScannerControlPanelViewModel,
  presentation: CollectLiveProgressPresentation
): ScannerControlPanelViewModel {
  const next: ScannerControlPanelViewModel = {
    ...viewModel,
    headerProgress: null,
    headerStatus: presentation.headerLabel,
    emptyState: null,
    counts: {
      ...viewModel.counts,
      alreadyCollectedCount: presentation.tiles.alreadyCollectedCount,
      newCount: presentation.tiles.newCount,
      queueCount: presentation.tiles.queueCount
    },
    collectProgress: {
      active: true,
      profileAlready: presentation.profileNumerator,
      profileTotal: presentation.profileTotal,
      profilePercent: presentation.profilePercent,
      profileTargetNumerator: presentation.profileTargetNumerator,
      profileIndeterminate: presentation.profileIndeterminate,
      tilesAlreadyTarget: presentation.tilesAlreadyTarget,
      priorAlreadyBaseline: presentation.priorAlready,
      batchAttempted: presentation.batchAttempted,
      batchTotal: presentation.batchTotal,
      batchReady: presentation.batchReady,
      batchNeedData: presentation.batchNeedData,
      batchPercent: presentation.batchPercent,
      phase: presentation.phase,
      showBatchCard: presentation.showBatchCard
    }
  };
  if (next.action) {
    next.action = {
      ...next.action,
      title: "Collecting videos",
      buttonLabel: presentation.buttonLabel,
      description: presentation.description,
      enabled: false
    };
  }
  if (next.primaryAction) {
    next.primaryAction = {
      ...next.primaryAction,
      title: "Collecting videos",
      label: presentation.buttonLabel,
      description: presentation.description,
      enabled: false,
      tone: "default"
    };
  }
  return next;
}
