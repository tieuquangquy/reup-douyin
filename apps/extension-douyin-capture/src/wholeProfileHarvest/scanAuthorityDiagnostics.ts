import {
  clearStaleRuntimeScanDiagnostics,
  overcollectionDiagnosticsTrusted,
  type ScannerControlPanelRenderContext
} from "./profileContext.js";
import { scanFinalizingTimedOut, scanProgressPhaseIsFinalizing } from "./scanPresentationPhase.js";
import type { WholeProfileHarvestState } from "./state.js";

const SCAN_AUTHORITY_CHANNEL = "scan_authority_diagnostics";

/** Fields owned by scan authority — safe to clear on profile scan reset. */
export const SCAN_SESSION_DIAGNOSTIC_KEYS = [
  "over_displayed_count",
  "over_displayed_extra_ids_exact",
  "over_displayed_extra_items_exact",
  "over_displayed_validation_status",
  "over_displayed_same_profile_validated",
  "over_displayed_itemized_reason_summary",
  "over_displayed_extra_source",
  "over_displayed_outside_profile_offending_aweme_ids",
  "count_semantics_status",
  "count_semantics_reason",
  "scan_health_verdict",
  "scan_health_verdict_reason",
  "final_verdict",
  "forensic_export_available",
  "forensic_export_scan_run_id",
  "accepted_target_ledger_present",
  "scan_finalization_result",
  "scan_finalization_stage",
  "scan_finalized_at",
  "scan_progress_discovered",
  "scan_progress_expected",
  "scan_progress_remaining",
  "scan_progress_phase_label",
  "scan_progress_pages",
  "scan_progress_requests",
  "scan_progress_updated_at",
  "scan_run_id"
] as const;

export type ScanAuthorityDiagnostics = Record<string, unknown>;

function diagnosticsRecordByChannel(
  value: unknown,
  channel = SCAN_AUTHORITY_CHANNEL
): ScanAuthorityDiagnostics {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  return typeof record.diagnostics_channel === "string" && record.diagnostics_channel === channel
    ? record
    : {};
}

/** Single read path for scan authority + runtime progress diagnostics. */
export function readScanAuthorityDiagnostics(state: WholeProfileHarvestState): ScanAuthorityDiagnostics {
  const profile = diagnosticsRecordByChannel(state.profile_scan.diagnostics);
  const verify = diagnosticsRecordByChannel(state.verify.diagnostics);
  const requestRuntime = state.debug.last_request_summary && typeof state.debug.last_request_summary === "object"
    && !Array.isArray(state.debug.last_request_summary)
    && (state.debug.last_request_summary as Record<string, unknown>).diagnostics_channel === "runtime_debug_diagnostics"
    ? state.debug.last_request_summary as Record<string, unknown>
    : {};
  const responseRuntime = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    && !Array.isArray(state.debug.last_response_summary)
    && (state.debug.last_response_summary as Record<string, unknown>).diagnostics_channel === "runtime_debug_diagnostics"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const authority = Object.keys(verify).length > 0 ? { ...profile, ...verify } : profile;
  return { ...requestRuntime, ...responseRuntime, ...authority };
}

/** Clear scan-session diagnostics from runtime summaries (reset / rescan chokepoint). */
export function clearScanSessionDiagnostics(summary: Record<string, unknown>): Record<string, unknown> {
  const cleared = clearStaleRuntimeScanDiagnostics(summary);
  for (const key of SCAN_SESSION_DIAGNOSTIC_KEYS) {
    cleared[key] = null;
  }
  return cleared;
}

export function scanAuthorityDiagnosticsTrusted(
  state: WholeProfileHarvestState,
  diagnostics: ScanAuthorityDiagnostics = readScanAuthorityDiagnostics(state)
): boolean {
  return overcollectionDiagnosticsTrusted(state, diagnostics);
}

export function resolveFinalizingStagePresentation(
  diagnostics: ScanAuthorityDiagnostics,
  fallback: string
): { title: string; detail: string; stage: string | null } {
  const stage = typeof diagnostics.scan_finalization_stage === "string" && diagnostics.scan_finalization_stage.trim()
    ? diagnostics.scan_finalization_stage.trim()
    : null;
  switch (stage) {
    case "count_semantics":
      return { title: "Validating video counts", detail: "Checking API totals against the profile page count…", stage };
    case "classification":
      return { title: "Building collection queue", detail: "Classifying new, incomplete, and ready videos…", stage };
    case "inbox_sync":
      return { title: "Syncing Capture Inbox", detail: "Syncing scan results with Capture Inbox…", stage };
    case "complete":
      return { title: "Scan complete", detail: "Scan finished. Preparing next action…", stage };
    default:
      return { title: "Finalizing scan", detail: fallback, stage };
  }
}

export function finalizingElapsedSeconds(
  diagnostics: ScanAuthorityDiagnostics,
  state: WholeProfileHarvestState,
  nowMs = Date.now()
): number | null {
  const updatedAt = diagnostics.scan_finalized_at
    ?? diagnostics.scan_progress_updated_at
    ?? state.updated_at;
  const timestamp = Date.parse(String(updatedAt));
  if (!Number.isFinite(timestamp)) return null;
  return Math.max(0, Math.round((nowMs - timestamp) / 1000));
}

export type ScannerPresentationPhase =
  | "idle_scan_required"
  | "scan_in_progress"
  | "scan_finalizing"
  | "scan_finalizing_timeout"
  | "review_overcollection"
  | "scan_complete"
  | "collecting"
  | "paused"
  | "profile_context_gate";

export type ScannerPresentationAuthority = {
  phase: ScannerPresentationPhase;
  headerStatus: string;
  diagnosticsTrusted: boolean;
  finalizingStage: ReturnType<typeof resolveFinalizingStagePresentation> | null;
  finalizingElapsedSeconds: number | null;
};

export function deriveScannerPresentationAuthority(
  state: WholeProfileHarvestState,
  options: {
    renderContext?: ScannerControlPanelRenderContext;
    primaryActionKey: string;
    currentHeaderStatus: string;
    scanProgressActive: boolean;
    scanProgressAtFull: boolean;
    scanProgressPhaseLabel?: string | null;
    queueCount: number;
    newCount: number;
    nowMs?: number;
  }
): ScannerPresentationAuthority {
  const diagnostics = readScanAuthorityDiagnostics(state);
  const diagnosticsTrusted = scanAuthorityDiagnosticsTrusted(state, diagnostics);
  const nowMs = options.nowMs ?? Date.now();
  const workflowCollecting = state.workflow.collection.status === "running"
    || state.workflow.collection.status === "opening_target"
    || state.collect_job.state === "running"
    || state.collect_job.state === "starting";

  if (workflowCollecting) {
    return {
      phase: "collecting",
      headerStatus: options.currentHeaderStatus,
      diagnosticsTrusted,
      finalizingStage: null,
      finalizingElapsedSeconds: null
    };
  }

  const runnerCanonical = String(state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? (state.debug.last_response_summary as Record<string, unknown>).trace_ui_canonical_state ?? ""
    : "");
  if (runnerCanonical === "waiting_for_active_tab" || runnerCanonical === "paused_tab_inactive") {
    return {
      phase: "collecting",
      headerStatus: options.currentHeaderStatus,
      diagnosticsTrusted,
      finalizingStage: null,
      finalizingElapsedSeconds: null
    };
  }

  if (options.primaryActionKey === "review_overcollection" && diagnosticsTrusted) {
    const reviewTotal = Math.max(options.queueCount, options.newCount, state.harvest.queue.length, state.scan_job.total_persisted ?? 0);
    const headerStatus = options.currentHeaderStatus === "Scan required" || options.currentHeaderStatus === "Not scanned"
      ? (reviewTotal > 0 ? `${reviewTotal} ready · review needed` : "Scan needs review")
      : options.currentHeaderStatus;
    return {
      phase: "review_overcollection",
      headerStatus,
      diagnosticsTrusted,
      finalizingStage: null,
      finalizingElapsedSeconds: null
    };
  }

  if (options.scanProgressActive) {
    const phaseLabel = options.scanProgressPhaseLabel ?? String(diagnostics.scan_progress_phase_label ?? "");
    const explicitlyFinalizing = scanProgressPhaseIsFinalizing(phaseLabel)
      || diagnostics.scan_finalization_stage != null;
    if (options.scanProgressAtFull && explicitlyFinalizing) {
      const timedOut = scanFinalizingTimedOut(state, {
        scanProgressActive: true,
        scanProgressPhaseLabel: phaseLabel,
        scanProgressAtFull: true,
        nowMs
      });
      const elapsed = finalizingElapsedSeconds(diagnostics, state, nowMs);
      if (timedOut) {
        return {
          phase: "scan_finalizing_timeout",
          headerStatus: "Finalize timed out",
          diagnosticsTrusted,
          finalizingStage: null,
          finalizingElapsedSeconds: elapsed
        };
      }
      const stage = resolveFinalizingStagePresentation(
        diagnostics,
        "Finalizing scan and syncing with Capture Inbox…"
      );
      const elapsedSuffix = elapsed != null && elapsed > 0 ? ` (${elapsed}s)` : "";
      return {
        phase: "scan_finalizing",
        headerStatus: options.currentHeaderStatus,
        diagnosticsTrusted,
        finalizingStage: stage,
        finalizingElapsedSeconds: elapsed
      };
    }
    return {
      phase: "scan_in_progress",
      headerStatus: options.currentHeaderStatus,
      diagnosticsTrusted,
      finalizingStage: null,
      finalizingElapsedSeconds: null
    };
  }

  if (state.layer.profile_scan_ready || state.profile_scan.status === "success") {
    return {
      phase: "scan_complete",
      headerStatus: options.currentHeaderStatus,
      diagnosticsTrusted,
      finalizingStage: null,
      finalizingElapsedSeconds: null
    };
  }

  return {
    phase: "idle_scan_required",
    headerStatus: options.currentHeaderStatus,
    diagnosticsTrusted,
    finalizingStage: null,
    finalizingElapsedSeconds: null
  };
}

export function applyScannerPresentationAuthority<T extends {
  headerStatus: string;
  primaryAction: { key: string; title: string; label: string; description: string };
  action: { key: string; title: string; buttonLabel: string; description: string };
  emptyState: string | null;
  emptyStateTone?: "neutral" | "warning" | "error" | "info" | "success";
  scanProgress?: { active: boolean; phaseLabel: string; detail: string } | null;
}>(
  viewModel: T,
  authority: ScannerPresentationAuthority
): T {
  const next = { ...viewModel } as T;
  if (authority.phase === "review_overcollection" || authority.phase === "scan_finalizing_timeout") {
    next.headerStatus = authority.headerStatus;
  }

  if (authority.phase === "scan_finalizing" && authority.finalizingStage && next.scanProgress?.active) {
    const elapsed = authority.finalizingElapsedSeconds;
    const elapsedSuffix = elapsed != null && elapsed > 0 ? ` · ${elapsed}s` : "";
    const detail = `${authority.finalizingStage.detail}${elapsedSuffix}`;
    next.scanProgress = {
      ...next.scanProgress,
      phaseLabel: authority.finalizingStage.title,
      detail
    };
    next.primaryAction = {
      ...next.primaryAction,
      title: authority.finalizingStage.title,
      label: "Finalizing...",
      description: detail
    };
    next.action = {
      ...next.action,
      title: authority.finalizingStage.title,
      buttonLabel: "Finalizing...",
      description: detail
    };
    next.emptyState = detail;
  }

  if (authority.phase === "scan_finalizing_timeout") {
    const timeoutMessage = "Finalizing took too long. Rescan the profile or copy the technical log from Advanced.";
    next.headerStatus = "Finalize timed out";
    next.emptyState = timeoutMessage;
    next.emptyStateTone = "warning";
    next.primaryAction = {
      ...next.primaryAction,
      key: "scan_profile",
      title: "Finalize timed out",
      label: "Rescan Profile",
      description: timeoutMessage
    };
    next.action = {
      ...next.action,
      key: "scan_profile",
      title: "Finalize timed out",
      buttonLabel: "Rescan Profile",
      description: timeoutMessage
    };
    if (next.scanProgress) {
      next.scanProgress = { ...next.scanProgress, active: false, phaseLabel: "Timed out" };
    }
  }

  return next;
}
