import type { WholeProfileHarvestState } from "./state.js";
import { resolveDisplayedProfileVideoLimit } from "./displayedProfileQueueCap.js";

export type BackendCollectAuthority = {
  /** Videos confirmed in Capture Inbox backend for this profile. */
  captured: number;
  scannedTotal: number;
  remaining: number;
  ready: number;
  duplicate: number;
  failed: number;
  incomplete: number;
};

function numericDiagnostic(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return Math.max(0, Math.round(value));
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return Math.max(0, Math.round(parsed));
  }
  return fallback;
}

/** Merge scan/count diagnostics from profile_scan, verify, and runtime debug summary. */
export function mergeScanAuthorityDiagnostics(state: WholeProfileHarvestState): Record<string, unknown> {
  const profileScan = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const verify = state.verify.diagnostics && typeof state.verify.diagnostics === "object"
    ? state.verify.diagnostics as Record<string, unknown>
    : {};
  const debug = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  return { ...verify, ...profileScan, ...debug };
}

/**
 * Monotonic profile-wide total for popup/collect progress.
 * Must include Douyin displayed count (e.g. 738) even when inbox/API persisted only 735.
 */
export function resolveScanProfileTotalAuthorityPeak(
  diagnostics: Record<string, unknown>,
  ...candidates: number[]
): number {
  const displayedProfileCount = numericDiagnostic(diagnostics.displayed_profile_count);
  const expectedProfileCount = numericDiagnostic(
    diagnostics.expected_profile_video_count
      ?? diagnostics.expected_count
      ?? diagnostics.profile_expected_count
  );
  const priorPeak = numericDiagnostic(diagnostics.scan_profile_total_authority_peak);
  const collectablePeak = numericDiagnostic(
    diagnostics.final_cumulative_collectable_count ?? diagnostics.collectable_count
  );
  const popupAuthority = numericDiagnostic(diagnostics.popup_counter_authority_total);
  const discovered = numericDiagnostic(diagnostics.scan_job_total_persisted ?? diagnostics.queue_total_persisted);
  const rawPeak = Math.max(
    priorPeak,
    displayedProfileCount,
    expectedProfileCount,
    collectablePeak,
    popupAuthority,
    discovered,
    ...candidates.map((value) => Math.max(0, Math.round(value)))
  );
  const displayedLimit = resolveDisplayedProfileVideoLimit(diagnostics);
  if (displayedLimit != null && displayedLimit > 0) {
    const overDisplayedCount = numericDiagnostic(diagnostics.over_displayed_count);
    const collectable = numericDiagnostic(
      diagnostics.final_cumulative_collectable_count ?? diagnostics.collectable_count
    );
    const apiDiscovered = numericDiagnostic(
      diagnostics.api_collectable_count ?? diagnostics.api_discovered_count_before_cap
    );
    const isOverDisplayed = overDisplayedCount > 0
      || (collectable != null && collectable > displayedLimit)
      || (apiDiscovered != null && apiDiscovered > displayedLimit);
    if (isOverDisplayed) {
      return Math.min(rawPeak, displayedLimit);
    }
  }
  return rawPeak;
}

/** Backend inbox count — never use harvest.updated or local floor here. */
export function resolveBackendCapturedCountFromState(state: WholeProfileHarvestState): number {
  const snap = state.post_scan_counter_snapshot;
  if (!snap) return 0;
  return Math.max(0, snap.backend_captured ?? 0, snap.already_collected ?? 0);
}

/** scanned_total authority minus backend captured (ignores stale queue.new). */
export function resolveHybridBackendAlignedGapFromState(
  state: WholeProfileHarvestState,
  backendCapturedOverride?: number
): number {
  const captured = backendCapturedOverride ?? resolveBackendCapturedCountFromState(state);
  return Math.max(0, resolveScannedTotalFromState(state) - captured);
}

/** Remaining collect gap from Capture Inbox profile-summary (totalCount beats stale local scanned_total). */
export function resolveCaptureInboxSummaryCollectGap(
  scannedTotalFromState: number,
  summary: { captured: number; totalCount: number; needsAction?: number; failed?: number }
): number {
  const captured = Math.max(0, Math.round(summary.captured));
  const totalAuthority = Math.max(
    Math.max(0, Math.round(scannedTotalFromState)),
    Math.max(0, Math.round(summary.totalCount)),
    captured
  );
  const incomplete = Math.max(0, Math.round(summary.needsAction ?? 0));
  const failed = Math.max(0, Math.round(summary.failed ?? 0));
  return Math.max(0, totalAuthority - captured - incomplete - failed);
}

function isScanFinalizedForTotalAuthority(
  state: WholeProfileHarvestState,
  diagnostics: Record<string, unknown>
): boolean {
  return state.scan_job.status === "completed"
    || state.scan_job.status === "failed"
    || typeof diagnostics.scan_finalization_result === "string"
    || state.profile_scan.status === "success";
}

function resolvePersistedQueueTotalAuthority(
  state: WholeProfileHarvestState,
  diagnostics: Record<string, unknown>
): number | null {
  const value = numericDiagnostic(
    diagnostics.queue_total_persisted
      ?? diagnostics.scan_job_total_persisted
      ?? diagnostics.profile_queue_total_count
      ?? state.scan_job.total_persisted
  );
  return value != null && value > 0 ? value : null;
}

/**
 * When scan finalized with a persisted queue smaller than a stale monotonic peak
 * (production: scan UI 3303 vs collect 3381), trust persisted unless under-display
 * semantics require the higher scan authority (production: inbox 735 vs displayed 738).
 */
export function shouldPreferScanAuthorityPeakOverPersistedQueue(
  state: WholeProfileHarvestState,
  diagnostics: Record<string, unknown>,
  peak: number,
  persistedQueue: number
): boolean {
  if (peak <= persistedQueue) return true;

  const countSemantics = String(diagnostics.count_semantics_status ?? "");
  const displayed = numericDiagnostic(diagnostics.displayed_profile_count);
  const collectable = numericDiagnostic(
    diagnostics.final_cumulative_collectable_count ?? diagnostics.collectable_count
  );
  const verified = Math.max(
    0,
    state.verify.verified_target_count ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.classification.status === "success" ? state.classification.total_candidates : 0
  );

  const underDisplayedSemantics = countSemantics === "completed_with_displayed_count_mismatch"
    || countSemantics === "completed_with_partial_secondary_recovery";
  const overDisplayedSemantics = countSemantics === "completed_with_api_over_displayed_count"
    || countSemantics === "overcollected_needs_validation";
  const overDisplayedCount = numericDiagnostic(diagnostics.over_displayed_count);

  if (overDisplayedSemantics || (overDisplayedCount > 0 && peak > persistedQueue)) {
    if (underDisplayedSemantics && displayed != null && displayed > persistedQueue && displayed >= peak) {
      return true;
    }
    if (verified > persistedQueue && verified >= peak) return true;
    if (collectable != null && collectable > persistedQueue && collectable >= peak) return true;
    return false;
  }

  if (displayed != null && displayed > persistedQueue && displayed >= peak) {
    return true;
  }
  if (verified > persistedQueue && verified >= peak) return true;
  if (collectable != null && collectable > persistedQueue && collectable >= peak) return true;

  return false;
}

/** Single authority for profile video total across scan, collect progress, and popup tiles. */
export function resolveScannedTotalFromState(state: WholeProfileHarvestState): number {
  const snap = state.post_scan_counter_snapshot;
  const diagnostics = mergeScanAuthorityDiagnostics(state);
  const persistedTotal = numericDiagnostic(
    diagnostics.queue_total_persisted
      ?? diagnostics.profile_queue_total_count
      ?? diagnostics.scan_job_total_persisted
      ?? state.scan_job.total_persisted
  );
  const peak = resolveScanProfileTotalAuthorityPeak(
    diagnostics,
    snap?.status === "applied" ? snap.scanned_total ?? 0 : 0,
    persistedTotal,
    state.classification.status === "success" ? state.classification.total_candidates : 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0,
    state.verify.accepted_target_count ?? 0,
    state.profile_scan.target_details.length,
    state.verify.target_details.length,
    state.harvest.planned_total ?? 0,
    state.scan_job.expected_count ?? 0,
    state.scan_job.total_discovered
  );

  const persistedQueue = resolvePersistedQueueTotalAuthority(state, diagnostics);
  if (persistedQueue != null && isScanFinalizedForTotalAuthority(state, diagnostics) && peak > persistedQueue) {
    const devicePersisted = numericDiagnostic(
      diagnostics.queue_total_persisted
        ?? diagnostics.scan_job_total_persisted
        ?? state.scan_job.total_persisted
    );
    const authorityPeak = numericDiagnostic(diagnostics.scan_profile_total_authority_peak);
    const displayed = numericDiagnostic(diagnostics.displayed_profile_count);
    const countSemantics = String(diagnostics.count_semantics_status ?? "");
    const overDisplayedSemantics = countSemantics === "completed_with_api_over_displayed_count"
      || countSemantics === "overcollected_needs_validation";
    const overDisplayedCount = numericDiagnostic(diagnostics.over_displayed_count);
    const staleMonotonicInflation = authorityPeak > devicePersisted
      && authorityPeak >= peak
      && !(displayed > devicePersisted && displayed >= peak && !overDisplayedSemantics && overDisplayedCount <= 0);
    const displayedOverInflation = displayed > devicePersisted
      && displayed >= peak
      && (overDisplayedSemantics || overDisplayedCount > 0);
    const snapshotScanned = snap?.status === "applied" ? numericDiagnostic(snap.scanned_total) : 0;
    const snapshotLegitimatelyExceedsDeviceQueue = snapshotScanned > devicePersisted
      && snapshotScanned >= peak
      && !staleMonotonicInflation
      && !displayedOverInflation;
    if (snapshotLegitimatelyExceedsDeviceQueue) {
      return peak;
    }
    if (shouldPreferScanAuthorityPeakOverPersistedQueue(state, diagnostics, peak, persistedQueue)) {
      return peak;
    }
    if (staleMonotonicInflation || displayedOverInflation) {
      return persistedQueue;
    }
  }
  return peak;
}

export function resolveBackendCollectAuthorityFromState(state: WholeProfileHarvestState): BackendCollectAuthority {
  const snap = state.post_scan_counter_snapshot;
  const captured = resolveBackendCapturedCountFromState(state);
  const scannedTotal = resolveScannedTotalFromState(state);
  const ready = Math.max(0, snap?.backend_ready ?? captured);
  const duplicate = Math.max(0, snap?.backend_dup ?? 0);
  const failed = Math.max(0, snap?.backend_fail ?? 0);
  const incomplete = Math.max(0, snap?.incomplete ?? Math.max(0, captured - ready));
  const remaining = Math.max(0, scannedTotal - captured - incomplete - failed);
  return { captured, scannedTotal, remaining, ready, duplicate, failed, incomplete };
}

/** Cap local harvest.updated so live UI never exceeds backend truth. */
export function capHarvestUpdatedToBackendAuthority(
  localUpdated: number,
  authority: BackendCollectAuthority
): number {
  const safeLocal = Math.max(0, Math.round(localUpdated));
  if (authority.captured <= 0) return safeLocal;
  return Math.min(safeLocal, authority.captured);
}

/** Prior-already baseline for live collect progress (batch 2 must start at 500/734, not 734/734). */
export function resolveBackendPriorAlreadyForLiveCollect(state: WholeProfileHarvestState): number {
  return resolveBackendCapturedCountFromState(state);
}

/**
 * Operator skip must not trust inflated snapshot.queue when snapshot.new is lower.
 * Production: batch-2 resume can show queue=734 while new=237 after partial collect.
 */
export function resolveOperatorSkipQueueAuthority(state: WholeProfileHarvestState): number {
  const snapshot = state.post_scan_counter_snapshot;
  if (snapshot?.status === "applied") {
    const snapNew = Math.max(0, snapshot.new);
    const snapQueue = Math.max(0, snapshot.queue);
    const harvestPending = Math.max(0, state.harvest.pending);
    const snapshotAuthority = Math.min(snapNew, snapQueue);
    return harvestPending > 0 ? Math.min(snapshotAuthority, harvestPending) : snapshotAuthority;
  }
  return Math.max(0, state.harvest.pending);
}
