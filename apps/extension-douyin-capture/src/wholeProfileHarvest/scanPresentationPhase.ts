import { activeProfileRevisitPresentationActive } from "./activeProfilePresentation.js";
import {
  alignedPartialScanPersistedCount,
  alignedScanPersistedMeetsExpected,
  detectProfileContextMismatch,
  resolveScanJobExpectedCount,
  scanPersistedMeetsExpectedCount,
  scanQueueProvesSessionCompleteForPresentation,
  storedScanSessionAppliesToActiveTab,
  type ScannerControlPanelRenderContext
} from "./profileContext.js";
import { getDouyinScannerWorkflowReadiness, isDouyinCalibrationReady } from "./readiness.js";
import type { WholeProfileHarvestState } from "./state.js";

export type ScanPresentationPhase =
  | "scan_in_progress"
  | "scan_finalizing"
  | "scan_partial_failed"
  | "scan_complete"
  | "revisit_mismatch"
  | "calibrate_required"
  | "collect_ready"
  | "idle_scan_required";

export type ScanPresentationPhaseResolution = {
  phase: ScanPresentationPhase;
  partialPersisted: number;
  expectedCount: number | null;
  scanComplete: boolean;
  /** Keep persisted scan tiles visible; do not ghost-zero. */
  suppressGhostTiles: boolean;
  /** Do not overlay Rescan / partial-failed primary action. */
  suppressPartialRescanOverlay: boolean;
};

export function scanJobVisiblyActive(state: WholeProfileHarvestState): boolean {
  return state.phase !== "scan_finished"
    && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait");
}

export function scanProgressPhaseIsFinalizing(phaseLabel: string | null | undefined): boolean {
  const normalized = typeof phaseLabel === "string" ? phaseLabel.trim().toLowerCase() : "";
  return normalized === "finalizing scan" || normalized === "finalizing";
}

export function normalizeScanProgressPhaseLabel(
  phaseLabel: string | null | undefined,
  options?: { scanActive?: boolean; atFullProgress?: boolean }
): string {
  if (scanProgressPhaseIsFinalizing(phaseLabel)) return "Finalizing";
  if (typeof phaseLabel === "string" && phaseLabel.trim()) return phaseLabel.trim();
  if (options?.scanActive && options.atFullProgress) return "Finalizing";
  if (options?.scanActive) return "Scanning profile";
  return "Scan finalized";
}

export const SCAN_FINALIZING_STALE_MS = 120_000;

export function scanFinalizingTimedOut(
  state: WholeProfileHarvestState,
  options?: {
    scanProgressActive?: boolean;
    scanProgressPhaseLabel?: string | null;
    scanProgressAtFull?: boolean;
    nowMs?: number;
  }
): boolean {
  const scanActive = options?.scanProgressActive ?? scanJobVisiblyActive(state);
  const atFullProgress = options?.scanProgressAtFull === true;
  const finalizing = scanProgressPhaseIsFinalizing(options?.scanProgressPhaseLabel)
    || (scanActive && atFullProgress);
  if (!finalizing) return false;
  if (state.layer.profile_scan_ready) return false;
  const profileDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const updatedAt = profileDiagnostics.scan_finalized_at
    ?? profileDiagnostics.scan_progress_updated_at
    ?? summary.scan_progress_updated_at
    ?? state.updated_at;
  const hasFinalizeClock = profileDiagnostics.scan_finalized_at != null
    || profileDiagnostics.scan_progress_updated_at != null
    || summary.scan_progress_updated_at != null;
  if (!hasFinalizeClock && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait")) {
    return false;
  }
  const timestamp = Date.parse(String(updatedAt));
  if (!Number.isFinite(timestamp)) return false;
  return (options?.nowMs ?? Date.now()) - timestamp > SCAN_FINALIZING_STALE_MS;
}

/** Pagination ended with persisted rows but without a trusted expected count gate. */
function resolveScanFinalizationResult(state: WholeProfileHarvestState): string {
  const profileDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const verifyDiagnostics = state.verify.diagnostics && typeof state.verify.diagnostics === "object"
    ? state.verify.diagnostics as Record<string, unknown>
    : {};
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  return String(
    profileDiagnostics.scan_finalization_result
    ?? verifyDiagnostics.scan_finalization_result
    ?? summary.scan_finalization_result
    ?? ""
  ).trim();
}

function scanResumableBudgetExhaustedForPresentation(state: WholeProfileHarvestState): boolean {
  const profileDiagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const diagnostics = { ...summary, ...profileDiagnostics };
  return diagnostics.partial_scan_resumable === "yes"
    || diagnostics.continuation_available === "yes"
    || diagnostics.page_budget_exhausted === "yes"
    || diagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted"
    || diagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || diagnostics.final_gap_classification === "resumable_api_budget_exhausted";
}

/** Persisted rows exist but authoritative finalization says the scan did not finish. */
export function scanIncompleteUnderExpectedForPresentation(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  if (scanResumableBudgetExhaustedForPresentation(state)) return false;
  const expected = resolveScanJobExpectedCount(state);
  const persisted = alignedPartialScanPersistedCount(state, activeTabUrl);
  if (expected == null || !Number.isFinite(expected) || expected <= 0) return false;
  if (persisted <= 0 || persisted >= expected) return false;
  return resolveScanFinalizationResult(state) === "incomplete";
}

export function scanPaginationExhaustedWithPersisted(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  if (state.scan_job.has_more_state !== false) return false;
  const expected = resolveScanJobExpectedCount(state);
  const persisted = alignedPartialScanPersistedCount(state, activeTabUrl);
  if (persisted <= 0) return false;
  if (expected != null && persisted < expected) return false;
  return state.phase === "scan_finished"
    || state.scan_job.status === "completed"
    || state.scan_job.status === "failed";
}

export function scanSessionCompleteForPresentation(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): boolean {
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  if (scanQueueProvesSessionCompleteForPresentation(state, activeTabUrl)) return true;
  if (scanIncompleteUnderExpectedForPresentation(state, activeTabUrl)) return false;
  if (alignedScanPersistedMeetsExpected(state, activeTabUrl)) return true;
  if (state.layer.profile_scan_ready) return true;
  if (scanPaginationExhaustedWithPersisted(state, activeTabUrl)) return true;
  const finalization = resolveScanFinalizationResult(state);
  if (
    finalization !== "incomplete"
    && state.profile_scan.status === "success"
    && state.verify.status === "success"
    && (state.profile_scan.accepted_target_count > 0 || state.verify.verified_target_count > 0)
  ) {
    return true;
  }
  return false;
}

function resolveActiveTabUrl(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): string | null {
  const tabUrl = renderContext.active_tab_url
    ?? state.page_context.current_url
    ?? state.safety.tab_health.current_url
    ?? null;
  return typeof tabUrl === "string" && tabUrl.trim() ? tabUrl.trim() : null;
}

export function resolveScanPresentationPhase(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {},
  options?: {
    scanProgressActive?: boolean;
    scanProgressPhaseLabel?: string | null;
    scanProgressAtFull?: boolean;
  }
): ScanPresentationPhaseResolution {
  const activeTabUrl = resolveActiveTabUrl(state, renderContext);
  const expectedCount = resolveScanJobExpectedCount(state);
  const partialPersisted = alignedPartialScanPersistedCount(state, activeTabUrl);
  const revisitActive = activeProfileRevisitPresentationActive(renderContext.active_profile_presentation);
  const scanActive = options?.scanProgressActive ?? scanJobVisiblyActive(state);
  const atFullProgress = options?.scanProgressAtFull === true;
  const finalizing = scanProgressPhaseIsFinalizing(options?.scanProgressPhaseLabel)
    || (scanActive && atFullProgress);

  if (scanActive) {
    const phase: ScanPresentationPhase = finalizing ? "scan_finalizing" : "scan_in_progress";
    return {
      phase,
      partialPersisted,
      expectedCount,
      scanComplete: false,
      suppressGhostTiles: true,
      suppressPartialRescanOverlay: true
    };
  }

  if (revisitActive) {
    return {
      phase: "revisit_mismatch",
      partialPersisted,
      expectedCount,
      scanComplete: false,
      suppressGhostTiles: true,
      suppressPartialRescanOverlay: true
    };
  }

  const tabMismatch = activeTabUrl ? detectProfileContextMismatch(state, activeTabUrl) : false;
  if (tabMismatch) {
    return {
      phase: "idle_scan_required",
      partialPersisted: 0,
      expectedCount,
      scanComplete: false,
      suppressGhostTiles: false,
      suppressPartialRescanOverlay: true
    };
  }

  const scanComplete = scanSessionCompleteForPresentation(state, activeTabUrl);
  if (scanComplete) {
    const calibrationReady = isDouyinCalibrationReady(state.calibration)
      || getDouyinScannerWorkflowReadiness(state).calibrationReady;
    const workflow = getDouyinScannerWorkflowReadiness(state);
    const collectReady = calibrationReady && workflow.collectQueueReady && workflow.canStartCollecting;
    const phase: ScanPresentationPhase = collectReady
      ? "collect_ready"
      : !calibrationReady
        ? "calibrate_required"
        : "scan_complete";
    return {
      phase,
      partialPersisted,
      expectedCount,
      scanComplete: true,
      suppressGhostTiles: true,
      suppressPartialRescanOverlay: true
    };
  }

  if (partialPersisted > 0 && storedScanSessionAppliesToActiveTab(state, activeTabUrl) && !scanResumableBudgetExhaustedForPresentation(state)) {
    return {
      phase: "scan_partial_failed",
      partialPersisted,
      expectedCount,
      scanComplete: false,
      suppressGhostTiles: true,
      suppressPartialRescanOverlay: false
    };
  }

  return {
    phase: "idle_scan_required",
    partialPersisted,
    expectedCount,
    scanComplete: false,
    suppressGhostTiles: false,
    suppressPartialRescanOverlay: true
  };
}

export function scanPresentationPhaseAllowsPartialRescanOverlay(
  resolution: ScanPresentationPhaseResolution
): boolean {
  return resolution.phase === "scan_partial_failed" && !resolution.suppressPartialRescanOverlay;
}
