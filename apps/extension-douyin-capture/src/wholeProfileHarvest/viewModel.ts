import { collectCompletionOverridesActiveCollectRuntime, deriveAuthoritativeProfileCounters, deriveAuthoritativeRunnerLock, deriveReconciledPopupMetrics, isTerminalBatchContinuation, sanitizePopupViewState } from "./authoritativePopupState.js";
import { resolveScannedTotalFromState } from "./backendCollectAuthority.js";
import { isHybridCollectJobLiveForPresentation } from "./collectDisplaySmoothing.js";
import { buildScanProgressPresentationFields } from "./scanProgressPresentation.js";
import { collectQueueReadinessBlockReason, harvestQueueActionableCount, HYBRID_NETWORK_CACHE_MAX_BATCH_SIZE, postScanSnapshotCollectWorkCount } from "./controller.js";
import {
  activeProfileRevisitPresentationActive,
  buildActiveProfileScannerCounts
} from "./activeProfilePresentation.js";
import { evidenceHasHybridRequiredMetrics, evidenceIsHybridFlushReady } from "./hybridHydration.js";
import { buildProfileCollectContractFromState } from "./profileCollectContract.js";
import { filterQueueToDisplayedProfileCollectScope } from "./displayedProfileQueueCap.js";
import { profileIdentifierFromUrl } from "./profileTargetRepository.js";
import {
  buildHybridMetricsMissUi,
  hybridLastRunWasMetricsMiss,
  hybridSkippedUncollectableCount,
  shouldOfferHybridMetricsMissSkip
} from "./hybridMetricsMiss.js";
import {
  buildHybridTailGapClosedCompleteUi,
  buildHybridUnreachableTailGapUi,
  HYBRID_UNREACHABLE_TAIL_GAP_BLOCKED_REASON,
  isHybridTailGapAuthorityLocked,
  isHybridTailGapClosed,
  isHybridTailGapCollectBlocked,
  isHybridUnreachableTailGapOffer,
  resolveHybridTailGapClosedAlready,
  resolveHybridTailGapClosedCount,
  resolveUnreachableTailGapRemaining
} from "./hybridUnreachableTailGap.js";
import { buildRecentItemResults, buildRunSummary, getOperatorStatusMessage, normalizeScannerViewState, type RecentItemResult, type WholeProfileRunSummary } from "./hardening.js";
import {
  activeProfileInboxSummaryIsComplete,
  activeProfileInboxSummaryIsResumeEligible,
  alignedPartialScanPersistedCount,
  alignedScanPersistedMeetsExpected,
  deriveProfileContextViewModel,
  activeTabOnDouyinProfile,
  detectProfileContextMismatch,
  scanQueueProvesSessionCompleteForPresentation,
  storedScanSessionAppliesToActiveTab,
  collectPresentationSuppressed,
  clearStaleCollectBlockDiagnostics,
  deviceScanQueueCountFromSnapshot,
  orphanedPostCollectSnapshot,
  shouldGateScannerPanelForProfileContext,
  emptyTrustedInboxSummary,
  hybridPostCollectAuthorityActive,
  inboxSummaryHasReviewOnlyBacklog,
  inboxSummaryProvesBackendEmpty,
  shouldTrustSnapshotAlreadyCollected,
  staleLocalCollectedDisprovenByBackendEmpty,
  inboxSummaryScannerCounts,
  profileContextCollectableRemaining,
  profileContextHeaderStatus,
  profileContextInboxReviewCount,
  profileContextShouldShowActiveTiles,
  partialCollectTileCounts,
  persistedScanJobTotalsTrustedForStoredProfile,
  expectedCollectContinuationRemaining,
  hybridProfileCollectFullyComplete,
  type ProfileContextViewModel,
  type ScannerControlPanelRenderContext
} from "./profileContext.js";
import {
  parseAppBackendAuthStatus,
  type AppBackendAuthStatus
} from "./appBackendAuth.js";
import {
  buildOvercollectionReviewPresentation,
  getCanonicalCalibrationReady,
  getCanonicalScannerPrimaryAction,
  getActiveProfilePostScanBlockedReason,
  getDouyinScannerBusyState,
  getDouyinScannerWorkflowReadiness,
  getWholeProfileHarvestActionState,
  getWholeProfileHarvestReadiness,
  isCollectCalibrationSatisfied,
  isDouyinCalibrationReady,
  isHybridNetworkCacheModeEnabledForCollect,
  unresolvedOvercollectionReviewActive,
  type ScannerActionKey,
  type WholeProfileHarvestActionState,
  type WholeProfileHarvestReadiness
} from "./readiness.js";
import {
  applyScannerPresentationAuthority,
  deriveScannerPresentationAuthority,
  readScanAuthorityDiagnostics
} from "./scanAuthorityDiagnostics.js";
import { applyCollectLiveProgressToViewModel, buildCollectLiveProgressPresentation, computeProfileCollectPercent } from "./collectLiveProgress.js";
import { scanJobVisiblyActive } from "./scanPresentationPhase.js";
import {
  normalizeScanProgressPhaseLabel,
  resolveScanPresentationPhase,
  scanFinalizingTimedOut,
  scanIncompleteUnderExpectedForPresentation,
  scanPaginationExhaustedWithPersisted,
  scanPresentationPhaseAllowsPartialRescanOverlay,
  scanProgressPhaseIsFinalizing,
  scanSessionCompleteForPresentation
} from "./scanPresentationPhase.js";
import { resolveDisplayedProfileVideoLimit } from "./displayedProfileQueueCap.js";
import {
  applyLargeProfilePersistedScannerPanelTiles,
  resolveLargeProfileTileCounts,
  scanDiagnosticsLargeProfileMode,
  shouldApplyLargeProfilePersistedTileCounts
} from "./scannerPanelTiles.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY, type WholeProfileHarvestBatch, type WholeProfileHarvestMode, type WholeProfileHarvestQueueItem, type WholeProfileHarvestResult, type WholeProfileHarvestSpeed, type WholeProfileHarvestState } from "./state.js";

export type WholeProfileHarvestStepStatus = "todo" | "active" | "done" | "warning" | "failed" | "next" | "locked";
export type WholeProfileHarvestCardTone = "neutral" | "info" | "success" | "warning" | "error";

export type WholeProfileHarvestStepperItem = {
  key: "verify" | "dry_run" | "extract" | "flush";
  label: string;
  status: WholeProfileHarvestStepStatus;
  summary: string;
  action_label: string;
};

export type WholeProfileHarvestMetricRow = {
  label: string;
  value: string;
};

export type WholeProfileHarvestCardView = {
  key: "profile" | "dry_run" | "extraction" | "backend" | "safety";
  title: string;
  status: WholeProfileHarvestStepStatus;
  tone: WholeProfileHarvestCardTone;
  summary: string;
  metrics: WholeProfileHarvestMetricRow[];
  collapsed?: boolean;
};

export type WholeProfileBackendFlowStepKey = "session" | "payload" | "flush_one" | "flush_batch";

export type WholeProfileBackendFlowStepView = {
  key: WholeProfileBackendFlowStepKey;
  label: string;
  status: "todo" | "active" | "done" | "warning" | "failed";
  summary: string;
  enabled: boolean;
  disabled_reason: string | null;
  action_label: string;
};

export type WholeProfileBackendFlowViewModel = {
  steps: WholeProfileBackendFlowStepView[];
  next_backend_action: {
    key: string;
    label: string;
    reason: string;
    severity: "info" | "success" | "warning" | "error";
  };
  summary: {
    capture_session_id_short: string | null;
    payload_guard: "idle" | "passed" | "failed";
    one_item_flush: "idle" | "success" | "failed";
    batch_flush: "idle" | "running" | "completed" | "completed_with_warnings" | "failed" | "paused";
    flushed: number;
    failed: number;
    pending: number;
  };
  compact_guard_rows: WholeProfileHarvestMetricRow[];
  flush_result_rows: WholeProfileHarvestMetricRow[];
  details_rows: WholeProfileHarvestMetricRow[];
  capture_inbox_cta: string | null;
};

export type WholeProfileHarvestDetailsView = {
  profile_url: string;
  profile_url_short: string;
  phase: string;
  raw_status: string;
  technical_rows: WholeProfileHarvestMetricRow[];
  queue_preview_label: string;
};

export type WholeProfileHarvestQueuePreviewRow = {
  index: number;
  aweme_id: string;
  aweme_short: string;
  capture_status: string;
  queue_status: string;
  title_short: string;
  thumbnail_url: string | null;
  source_url: string | null;
  badge: string;
};

export type WholeProfileHarvestExtractionResultRow = {
  index: number;
  aweme_short: string;
  status: "extracted" | "failed" | "pending";
  duration_text: string;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  error_code: string | null;
};

export type WholeProfileHarvestBackendResultRow = {
  index: number;
  aweme_short: string;
  status: "flushed" | "failed" | "skipped_complete" | "pending";
  item_id_short: string | null;
  metadata_status: string;
  error_code: string | null;
};

export type WholeProfileHarvestRowGroup<T> = {
  total: number;
  visible_limit: number;
  remaining_count: number;
  rows: T[];
  full_rows: T[];
  empty_message: string;
};

export type WholeProfileHarvestQueueAndResultsViewModel = {
  queue_preview: WholeProfileHarvestRowGroup<WholeProfileHarvestQueuePreviewRow> & {
    subtitle: string;
  };
  extraction_results: WholeProfileHarvestRowGroup<WholeProfileHarvestExtractionResultRow>;
  backend_results: WholeProfileHarvestRowGroup<WholeProfileHarvestBackendResultRow> & {
    summary: string;
  };
};

export type WholeProfileHarvestOperatorActionKey =
  | "verify_profile"
  | "test_3_videos"
  | "dry_run_first"
  | "dry_run_last"
  | "dry_run_random"
  | "run_harvest"
  | "prepare_backend_session"
  | "build_payload_preview"
  | "flush_one_item"
  | "flush_batch"
  | "mode"
  | "batch"
  | "speed"
  | "unattended_safe_mode"
  | "resume"
  | "reset_harvest";

export type WholeProfileHarvestOperatorHelpView = {
  quick_start: string[];
  troubleshooting: string[];
  safety_tips: string[];
  action_help: Record<WholeProfileHarvestOperatorActionKey, string>;
  capture_inbox_cta: string | null;
};

export type WholeProfileHarvestProgressViewModel = {
  stepper: WholeProfileHarvestStepperItem[];
  next_action: {
    label: string;
    reason: string;
    severity: "info" | "success" | "warning" | "error";
  };
  cards: {
    profile: WholeProfileHarvestCardView;
    dry_run: WholeProfileHarvestCardView;
    extraction: WholeProfileHarvestCardView;
    backend: WholeProfileHarvestCardView;
    safety: WholeProfileHarvestCardView;
  };
  backend_flow: WholeProfileBackendFlowViewModel;
  lists: WholeProfileHarvestQueueAndResultsViewModel;
  details: WholeProfileHarvestDetailsView;
  operator_help: WholeProfileHarvestOperatorHelpView;
};

export type WholeProfileRunTabViewModel = {
  status_chips: Array<{
    label: string;
    value: string;
    tone: "success" | "info" | "warning" | "error" | "locked";
  }>;
  mini_stepper: Array<{
    key: "scan" | "test" | "extract" | "save";
    label: string;
    status: WholeProfileHarvestStepStatus;
  }>;
  primary_action: {
    key: string;
    label: string;
    enabled: boolean;
    tone: "primary" | "warning" | "danger";
    reason: string;
  } | null;
  secondary_actions: Array<{
    key: string;
    label: string;
    enabled: boolean;
  }>;
  settings: {
    mode: WholeProfileHarvestMode;
    batch: WholeProfileHarvestBatch;
    speed: WholeProfileHarvestSpeed;
    unattended_safe_mode: boolean;
    mode_label: string;
    batch_label: string;
    speed_label: string;
  };
  compact_metrics: {
    videos_found: number;
    tested: string;
    extracted: number;
    saved: number;
    pending: number;
  };
  save_next: {
    visible: boolean;
    label: string | null;
    reason: string | null;
  };
  alert: {
    tone: "warning" | "error" | "info";
    title: string;
    message: string;
    technical_hint?: string | null;
  } | null;
  workflow_hint: string | null;
  operator_status: {
    message: string;
    level: "info" | "warning" | "error" | "success";
    next_step: string;
  };
  run_summary: WholeProfileRunSummary;
  recent_item_results: RecentItemResult[];
  shortcuts: {
    results_visible: boolean;
    technical_visible: boolean;
  };
};

export type ScannerControlPanelViewModel = {
  videosFound: number;
  current_run_found_count: number;
  persisted_total_count: number | null;
  display_mode: "current_run_authority" | "persisted_history_authority";
  mixed_state_warning: string | null;
  profileScanned: boolean;
  scanDataVisible: boolean;
  headerStatus: string;
  /** Fraction + percent bar in the hero header during large-profile collect. */
  headerProgress: {
    collected: number;
    total: number;
    percent: number;
  } | null;
  /** Large-profile batch idle: Remaining + Next batch tiles instead of New/Queue. */
  statsTileMode: "default" | "large_profile_batch";
  statsLargeProfile: {
    remaining: number;
    nextBatchCap: number;
  } | null;
  emptyState: string | null;
  /** Visual tone for the hint row under the primary action. */
  emptyStateTone: "neutral" | "warning" | "success";
  /** Single-line stats when collection is complete or nearly complete. */
  statsCompact: {
    summary: string;
    percent: number | null;
  } | null;
  /** Card accent for the primary action block. */
  primaryActionCardTone: "default" | "success" | "warning";
  /** Hide modal-era Next-10 settings when Hybrid collect is active. */
  showCollectionSettings: boolean;
  scanProgress: {
    active: boolean;
    discovered: number;
    expected: number | null;
    /** Profile-fraction numerator capped at expected when API over-displays. */
    fractionDiscovered: number;
    overDisplayExtra: number | null;
    progressFractionLabel: string;
    pagesFetched: number;
    requestCount: number;
    phaseLabel: string;
    detail: string;
    percent: number | null;
  };
  /** Live Hybrid collect progress for profile-level bar + batch stats. */
  collectProgress: {
    active: boolean;
    profileAlready: number;
    profileTotal: number;
    profilePercent: number | null;
    profileTargetNumerator?: number;
    profileIndeterminate?: boolean;
    tilesAlreadyTarget?: number;
    priorAlreadyBaseline?: number;
    batchAttempted: number;
    batchTotal: number;
    batchReady: number;
    batchNeedData: number;
    batchPercent: number | null;
    phase: "preparing" | "checking" | "saving" | "collecting";
    showBatchCard?: boolean;
  } | null;
  /** Idle summary: how many discovered IDs have metrics vs need data. */
  metricsPlan: {
    discovered: number;
    metricsReady: number;
    metricsMissing: number;
    collected: number;
    skippedUncollectable: number;
  } | null;
  health: {
    profile: "Profile" | "No profile" | "This profile";
    api: "App OK" | "App login" | "App offline" | "API ready" | "API not checked" | "API offline";
    calibration: "Cal ready" | "Cal needed";
    safety: "Safe" | "Paused" | "Check";
  };
  counts: {
    newCount: number;
    incompleteCount: number;
    alreadyCollectedCount: number;
    queueCount: number;
    collectedCount: number;
    savedCount: number;
    failedCount: number;
  };
  primaryAction: {
    key: ScannerActionKey;
    label: string;
    title: string;
    description: string;
    enabled: boolean;
    disabledReason: string | null;
    /** Warning styling when the primary action finishes a profile via skip. */
    tone: "default" | "warning";
  };
  action: {
    key: ScannerActionKey;
    title: string;
    description: string;
    buttonLabel: string;
    enabled: boolean;
    disabledReason: string | null;
  };
  settings: {
    mode: string;
    batch: string;
    speed: string;
    summary: string;
  };
  /** Set when the active Douyin tab is a different profile than persisted harvest state. */
  profileContext: ProfileContextViewModel | null;
};

export type DouyinScannerMainViewModel = {
  header_status: string;
  current_run_found_count: number;
  persisted_total_count: number | null;
  display_mode: "current_run_authority" | "persisted_history_authority";
  mixed_state_warning: string | null;
  title: string;
  subtitle: string;
  status_chips: Array<{
    label: string;
    value: string;
    tone: "success" | "warning" | "danger" | "neutral";
  }>;
  stats_summary: {
    title: string;
    subtitle: string;
    metrics: WholeProfileHarvestMetricRow[];
  };
  primary_action: {
    key: string;
    label: string;
    enabled: boolean;
    reason: string;
  } | null;
  progress: {
    label: string;
    value: string;
    tone: "success" | "warning" | "danger" | "neutral";
    detail: string;
  };
  footer_actions: {
    open_capture_inbox: {
      visible: boolean;
      enabled: boolean;
      label: string;
    };
    pause_or_resume: {
      visible: boolean;
      enabled: boolean;
      label: string;
    };
    advanced: {
      visible: boolean;
      label: string;
    };
    reset: {
      enabled: boolean;
      label: string;
    };
  };
  alert: {
    tone: "warning" | "error" | "info";
    title: string;
    message: string;
  } | null;
};

export const PRODUCT_TERMS = {
  productName: "Douyin Profile Scanner",
  collect: "Collect",
  startCollecting: "Start Collecting",
  saveToCaptureInbox: "Save to Capture Inbox",
  openCaptureInbox: "Open Capture Inbox",
  dataCheck: "Data check",
  scanSession: "Scan session",
  alreadyCollected: "Already collected",
  needRetry: "Need retry",
  securityCheck: "Security check"
} as const;

function friendlyModeLabel(value: WholeProfileHarvestMode): string {
  if (value === "new_only") return "New only";
  if (value === "refresh_all") return "Refresh all";
  return "New + incomplete";
}

function friendlyBatchLabel(value: WholeProfileHarvestBatch): string {
  if (value === "next_5") return "Next 5";
  if (value === "next_20") return "Next 20";
  if (value === "all_remaining") return "All remaining";
  return "Next 10";
}

function friendlySpeedLabel(value: WholeProfileHarvestSpeed): string {
  if (value === "fast") return "Fast";
  if (value === "normal") return "Normal";
  return "Safe";
}

function firstPositiveNumber(values: number[]): number {
  return values.find((value) => Number.isFinite(value) && value > 0) ?? 0;
}

function diagnosticsRecordByChannel22C13B(value: unknown, channel: "scan_authority_diagnostics" | "runtime_debug_diagnostics"): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  const candidateChannel = typeof record.diagnostics_channel === "string" ? record.diagnostics_channel : null;
  return candidateChannel === channel ? record : {};
}

function scanAuthorityDiagnosticsRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  const profile = diagnosticsRecordByChannel22C13B(state.profile_scan.diagnostics, "scan_authority_diagnostics");
  const verify = diagnosticsRecordByChannel22C13B(state.verify.diagnostics, "scan_authority_diagnostics");
  return Object.keys(verify).length > 0 ? { ...profile, ...verify } : profile;
}

function scanRuntimeDiagnosticsRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  const requestRuntime = diagnosticsRecordByChannel22C13B(state.debug.last_request_summary, "runtime_debug_diagnostics");
  const responseRuntime = diagnosticsRecordByChannel22C13B(state.debug.last_response_summary, "runtime_debug_diagnostics");
  return { ...requestRuntime, ...responseRuntime };
}

function scanJobProgressActive22C14L(state: WholeProfileHarvestState): boolean {
  return state.phase !== "scan_finished" && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait");
}

function scanRuntimeProgressAvailable22C14L(runtime: Record<string, unknown>): boolean {
  return typeof runtime.scan_progress_discovered !== "undefined"
    || typeof runtime.scan_progress_update_seq !== "undefined"
    || typeof runtime.scan_progress_updated_at !== "undefined";
}

// Active progress snapshots are only valid while the matching scan run is actively scanning; final scan state must clear stale progress.
function scanRuntimeProgressActive22C14J(state: WholeProfileHarvestState, runtime: Record<string, unknown>): boolean {
  const runtimeRunId = typeof runtime.scan_run_id === "string" && runtime.scan_run_id.trim() ? runtime.scan_run_id.trim() : null;
  const matchingRun = runtimeRunId == null || runtimeRunId === state.run_id || runtimeRunId === state.scan_job.scan_job_id;
  const progressAvailable = scanRuntimeProgressAvailable22C14L(runtime);
  return matchingRun
    && state.phase !== "scan_finished"
    && progressAvailable
    && (state.workflow.scan.status === "running" || state.scan_job.status === "running" || state.scan_job.status === "retry_wait" || state.status === "verifying");
}

function scanDiagnosticsRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  const authority = scanAuthorityDiagnosticsRecord(state);
  const runtime = scanRuntimeDiagnosticsRecord(state);
  if (scanRuntimeProgressActive22C14J(state, runtime)) return { ...authority, ...runtime };
  const {
    scan_progress_discovered: _scanProgressDiscovered,
    scan_progress_expected: _scanProgressExpected,
    scan_progress_remaining: _scanProgressRemaining,
    scan_progress_pages: _scanProgressPages,
    scan_progress_requests: _scanProgressRequests,
    scan_progress_status_code: _scanProgressStatusCode,
    scan_progress_phase_label: _scanProgressPhaseLabel,
    ...runtimeWithoutProgress
  } = runtime;
  return { ...runtimeWithoutProgress, ...authority };
}

function getAuthoritativeScanStopReason(diagnostics: Record<string, unknown>): string {
  const authoritative = diagnostics.scan_stop_authoritative;
  if (typeof authoritative === "string" && authoritative.trim()) return authoritative.trim();
  const legacyDisplayOnly = diagnostics.scanStop ?? diagnostics.scan_stop ?? diagnostics.canonical_scanner_stop_reason;
  return typeof legacyDisplayOnly === "string" && legacyDisplayOnly.trim() ? legacyDisplayOnly.trim() : "none";
}

function expectedProfileVideoCount(state: WholeProfileHarvestState): number | null {
  if (scanProgressAuthorityActive(state) && scanRunDiagnosticsStale(state)) return null;
  const value = scanDiagnosticsRecord(state).expected_profile_video_count;
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : null;
  return numeric != null && Number.isFinite(numeric) && numeric > 0 ? Math.round(numeric) : null;
}

function scanAuthorityRunIdRaw(state: WholeProfileHarvestState): string {
  const raw = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? (state.profile_scan.diagnostics as Record<string, unknown>).scan_run_id
    : null;
  return typeof raw === "string" ? raw.trim() : "";
}

function scanRunDiagnosticsStale(state: WholeProfileHarvestState, diagnostics = scanDiagnosticsRecord(state)): boolean {
  const diagRunId = scanAuthorityRunIdRaw(state) || (typeof diagnostics.scan_run_id === "string" ? diagnostics.scan_run_id.trim() : "");
  const activeRunId = (typeof state.scan_job.scan_job_id === "string" ? state.scan_job.scan_job_id : state.run_id ?? "").trim();
  if (!activeRunId) return Boolean(diagRunId);
  if (!diagRunId) return false;
  return diagRunId !== activeRunId;
}

function scanRunDiagnosticsAligned(state: WholeProfileHarvestState, diagnostics = scanDiagnosticsRecord(state)): boolean {
  return !scanRunDiagnosticsStale(state, diagnostics);
}

function activeScanJobCountersTrusted(state: WholeProfileHarvestState, diagnostics = scanDiagnosticsRecord(state)): boolean {
  if (scanRunDiagnosticsStale(state, diagnostics)) return false;
  const jobId = typeof state.scan_job.scan_job_id === "string" ? state.scan_job.scan_job_id.trim() : "";
  if (!jobId) return false;
  return state.scan_job.status === "running" || state.scan_job.status === "retry_wait";
}

function scanProgressAuthorityActive(state: WholeProfileHarvestState): boolean {
  return scanJobProgressActive22C14L(state)
    || scanProfileWorkflowActive(state)
    || (state.status === "verifying" && state.workflow.active_task === "scan_profile");
}

function resolveScanProgressExpectedCount(state: WholeProfileHarvestState): number | null {
  const fromDiagnostics = expectedProfileVideoCount(state);
  const fromJob = state.scan_job.expected_count != null && state.scan_job.expected_count > 0 ? state.scan_job.expected_count : null;
  if (!scanProgressAuthorityActive(state)) return fromDiagnostics ?? fromJob;
  if (scanRunDiagnosticsStale(state)) return null;
  return fromDiagnostics ?? fromJob;
}

function numericDiagnosticValue(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(numeric) ? Math.round(numeric) : null;
}

function popupDiagnosticsRecord(state: WholeProfileHarvestState): Record<string, unknown> {
  const responseSummary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object" ? state.debug.last_response_summary as Record<string, unknown> : {};
  const requestSummary = state.debug.last_request_summary && typeof state.debug.last_request_summary === "object" ? state.debug.last_request_summary as Record<string, unknown> : {};
  return { ...requestSummary, ...responseSummary };
}

function popupStableCounterTotal(state: WholeProfileHarvestState): number | null {
  const diagnostics = popupDiagnosticsRecord(state);
  const value = numericDiagnosticValue(diagnostics.popup_counter_authority_total);
  return value != null && value >= 0 ? value : null;
}

function popupNearCompleteWarning(state: WholeProfileHarvestState, found = profileCountWithoutPopupWarning(state)): { applied: boolean; gapCount: number | null; threshold: number | null } {
  const diagnostics = scanDiagnosticsRecord(state);
  const expected = expectedProfileVideoCount(state) ?? state.scan_job.expected_count;
  const persistedFound = Math.max(
    state.scan_job.total_persisted,
    numericDiagnosticValue(diagnostics.scan_job_total_persisted) ?? 0,
    numericDiagnosticValue(diagnostics.queue_total_persisted) ?? 0
  );
  const authoritativeFound = state.scan_job.status === "completed" && persistedFound > 0
    ? Math.max(
      persistedFound,
      numericDiagnosticValue(diagnostics.scan_progress_discovered) ?? 0,
      state.scan_job.total_discovered
    )
    : Math.max(
      found,
      numericDiagnosticValue(diagnostics.scan_job_total_persisted) ?? 0,
      numericDiagnosticValue(diagnostics.scan_progress_discovered) ?? 0,
      state.scan_job.total_persisted,
      state.scan_job.total_discovered
    );
  if (expected == null || expected <= 0 || authoritativeFound >= expected) return { applied: false, gapCount: expected == null ? null : Math.max(0, expected - authoritativeFound), threshold: null };
  const gapCount = expected - authoritativeFound;
  const threshold = Math.max(5, Math.ceil(expected * 0.01));
  const activeSourceHardFailure = diagnostics.active_profile_post_fetch_response_status_code != null
    && diagnostics.active_profile_post_fetch_response_status_code !== 0
    && diagnostics.active_profile_post_fetch_response_status_code !== "0";
  const finalizationResult = String(diagnostics.scan_finalization_result ?? "");
  const terminalNearComplete = (finalizationResult === "completed_with_warning" || (finalizationResult === "" && state.scan_job.status === "completed")) && !activeSourceHardFailure;
  return {
    applied: terminalNearComplete && gapCount <= threshold,
    gapCount,
    threshold
  };
}

function scanProfileWorkflowActive(state: WholeProfileHarvestState): boolean {
  return state.workflow.scan.status === "running"
    && (state.workflow.active_task === "scan_profile" || state.workflow.action_lock === "scan_profile");
}

function scanProfileInFlight(state: WholeProfileHarvestState): boolean {
  return scanProfileWorkflowActive(state)
    || state.scan_job.status === "running"
    || state.scan_job.status === "retry_wait"
    || (state.status === "verifying" && state.workflow.active_task === "scan_profile")
    || activeScanProgress22C14G(state).active;
}

function resolveActiveTabUrlForPresentation(
  state: WholeProfileHarvestState,
  activeTabUrl?: string | null
): string | null {
  const tabUrl = activeTabUrl ?? state.page_context.current_url ?? state.safety.tab_health.current_url ?? null;
  return typeof tabUrl === "string" && tabUrl.trim() ? tabUrl.trim() : null;
}

function resolveScanPresentationForViewModel(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
) {
  return resolveScanPresentationPhase(state, renderContext, {
    scanProgressActive: viewModel.scanProgress.active,
    scanProgressPhaseLabel: viewModel.scanProgress.phaseLabel,
    scanProgressAtFull: scanProgressAtFullCapacity(viewModel.scanProgress)
  });
}

function partialAlignedScanPresentationActive(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined,
  viewModel?: ScannerControlPanelViewModel,
  renderContext: ScannerControlPanelRenderContext = {}
): boolean {
  if (viewModel) {
    return scanPresentationPhaseAllowsPartialRescanOverlay(
      resolveScanPresentationForViewModel(viewModel, state, renderContext)
    );
  }
  if (!storedScanSessionAppliesToActiveTab(state, activeTabUrl)) return false;
  if (alignedScanPersistedMeetsExpected(state, activeTabUrl)) return false;
  if (scanSessionCompleteForPresentation(state, activeTabUrl)) return false;
  return alignedPartialScanPersistedCount(state, activeTabUrl) > 0;
}

function scanBlocksCollectPresentation(state: WholeProfileHarvestState, activeTabUrl?: string | null): boolean {
  if (scanProfileInFlight(state)) return false;
  const tabUrl = resolveActiveTabUrlForPresentation(state, activeTabUrl);
  if (tabUrl && detectProfileContextMismatch(state, tabUrl)) return false;
  if (partialAlignedScanPresentationActive(state, tabUrl)) return false;
  const blockedReason = getActiveProfilePostScanBlockedReason(state);
  if (blockedReason == null) return false;
  const scanFailed = state.scan_job.status === "failed"
    || state.profile_scan.status === "failed"
    || state.workflow.scan.status === "failed"
    || state.verify.status === "failed";
  if (scanFailed) {
    if (
      alignedScanPersistedMeetsExpected(state, tabUrl)
      || scanPaginationExhaustedWithPersisted(state, tabUrl)
      || scanQueueProvesSessionCompleteForPresentation(state, tabUrl)
    ) {
      return false;
    }
    return true;
  }
  const workflow = getDouyinScannerWorkflowReadiness(state);
  if (workflow.profileScanReady) return false;
  return true;
}

function collectPreflightRecentlyBlockedReason(state: WholeProfileHarvestState): string | null {
  if (collectPresentationSuppressed(state)) return null;
  const tabUrl = resolveActiveTabUrlForPresentation(state);
  if (tabUrl && detectProfileContextMismatch(state, tabUrl)) return null;
  if (state.debug.last_action_clicked !== "start_collecting") return null;
  if (state.debug.last_action_result !== "blocked") return null;
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const fromSummary = typeof summary.start_collecting_blocked_reason === "string" ? summary.start_collecting_blocked_reason.trim() : "";
  if (fromSummary) return fromSummary;
  const workflowError = typeof state.workflow.collection.last_error === "string" ? state.workflow.collection.last_error.trim() : "";
  if (workflowError) return workflowError;
  const lastError = typeof state.last_error === "string" ? state.last_error.replace(/^Start Collecting failed:\s*/i, "").trim() : "";
  return lastError || null;
}

function forcedCollectFallbackPrimaryKey(state: WholeProfileHarvestState): ScannerActionKey {
  const workflow = getDouyinScannerWorkflowReadiness(state);
  if (!workflow.profileScanReady || !workflow.classificationReady) return "scan_profile";
  if (!workflow.calibrationReady) return "calibrate";
  return "start_collecting";
}

function buildForcedWorkflowPrimaryAction(
  state: WholeProfileHarvestState,
  fallbackKey: ScannerActionKey,
  counts?: ScannerControlPanelViewModel["counts"]
): ScannerControlPanelViewModel["primaryAction"] {
  if (fallbackKey === "calibrate") {
    return {
      key: "calibrate",
      title: "Calibrate 4 Points",
      label: "Calibrate 4 Points",
      description: "Click like, comment, favorite, and share once before collecting.",
      enabled: true,
      disabledReason: null,
      tone: "default"
    };
  }
  if (fallbackKey === "start_collecting" && counts) {
    const pres = deriveCollectRemainderPresentation(counts);
    return {
      key: "start_collecting",
      title: pres.title,
      label: pres.label,
      description: pres.description,
      enabled: true,
      disabledReason: null,
      tone: "default"
    };
  }
  const inFlight = scanProfileInFlight(state);
  return {
    key: "scan_profile",
    title: inFlight ? "Scanning profile" : "Scan Profile",
    label: inFlight ? "Scanning..." : "Scan Profile",
    description: inFlight
      ? "Scan in progress..."
      : "Scan this profile to discover videos and build a collection plan.",
    enabled: !inFlight,
    disabledReason: null,
    tone: "default"
  };
}

function isLargeProfileCollectPresentation(state: WholeProfileHarvestState, profileTotal: number): boolean {
  const diagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  if (diagnostics.large_profile_mode === "yes") return true;
  return profileTotal > 500;
}

/** Header fraction bar when profile scope is partially collected (any size). Live collect uses collectProgress. */
function shouldShowProfileFractionHeader(profileTotal: number, remaining: number): boolean {
  return remaining > 0 && profileTotal > 0;
}

function clearBatchHeaderChrome(viewModel: ScannerControlPanelViewModel, headerStatus: string): ScannerControlPanelViewModel {
  return {
    ...viewModel,
    headerStatus,
    headerProgress: null,
    statsTileMode: "default",
    statsLargeProfile: null
  };
}

function trustedInboxBlocksCollectContinuation(
  viewModel: ScannerControlPanelViewModel,
  renderContext: ScannerControlPanelRenderContext
): boolean {
  if (viewModel.primaryAction.key === "open_capture_inbox") return true;
  const summary = renderContext.active_profile_inbox_summary;
  if (!summary?.trusted) return false;
  if (activeProfileInboxSummaryIsComplete(summary)) return true;
  return summary.already_collected > 0 && profileContextCollectableRemaining(summary) === 0;
}

function buildHeaderProgressPresentation(collected: number, total: number): {
  headerProgress: NonNullable<ScannerControlPanelViewModel["headerProgress"]> | null;
  headerStatus: string;
} {
  const safeTotal = Math.max(0, Math.round(total));
  const safeCollected = Math.max(0, Math.min(Math.round(collected), safeTotal || Math.round(collected)));
  if (safeTotal <= 0) {
    return { headerProgress: null, headerStatus: safeCollected > 0 ? `${safeCollected} collected` : "0 ready" };
  }
  const percent = computeProfileCollectPercent(safeCollected, safeTotal) ?? 0;
  return {
    headerProgress: { collected: safeCollected, total: safeTotal, percent },
    headerStatus: `${safeCollected}/${safeTotal} (${percent}%)`
  };
}

function applyLargeProfileContinuationPresentation(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext,
  remaining: number
): ScannerControlPanelViewModel {
  if (isHybridTailGapClosed(state)) {
    return applyHybridTailGapClosedIfActive(viewModel, state);
  }
  if (isHybridUnreachableTailGapOffer(state)) {
    return applyUnreachableTailGapOfferIfActive(viewModel, state);
  }
  const already = Math.max(
    viewModel.counts.alreadyCollectedCount,
    renderContext.active_profile_inbox_summary?.already_collected ?? 0,
    state.target_status.complete,
    state.harvest.updated
  );
  const tiles = partialCollectTileCounts(remaining, already);
  const counts = {
    ...viewModel.counts,
    newCount: tiles.newCount,
    queueCount: tiles.queueCount,
    alreadyCollectedCount: already
  };
  const pres = deriveCollectRemainderPresentation(counts);
  const profileTotal = Math.max(resolveScannedTotalFromState(state), already);
  const largeProfileBatch = isLargeProfileCollectPresentation(state, profileTotal);
  const header = shouldShowProfileFractionHeader(profileTotal, remaining)
    ? buildHeaderProgressPresentation(already, profileTotal)
    : { headerProgress: null, headerStatus: pres.headerStatus };
  return {
    ...viewModel,
    profileScanned: true,
    scanDataVisible: true,
    headerStatus: header.headerStatus,
    headerProgress: header.headerProgress,
    statsTileMode: largeProfileBatch ? "large_profile_batch" : "default",
    statsLargeProfile: largeProfileBatch
      ? { remaining: Math.max(0, Math.round(remaining)), nextBatchCap: Math.min(500, Math.max(0, Math.round(remaining))) }
      : null,
    counts,
    emptyState: pres.emptyState,
    emptyStateTone: pres.remaining <= 5 ? "warning" : "neutral",
    statsCompact: pres.percent != null && remaining > 0
      ? { summary: pres.headerStatus, percent: pres.percent }
      : pres.percent === 100 && !largeProfileBatch
        ? { summary: pres.headerStatus, percent: pres.percent }
        : viewModel.statsCompact,
    primaryAction: {
      key: pres.primaryKey,
      label: pres.label,
      title: pres.title,
      description: pres.description,
      enabled: true,
      disabledReason: null,
      tone: "default"
    },
    action: {
      key: pres.primaryKey,
      title: pres.title,
      buttonLabel: pres.label,
      description: pres.description,
      enabled: true,
      disabledReason: null
    }
  };
}

function applyInboxSnapshotCounterAuthority(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext,
  counters: {
    newCount: number;
    incompleteCount: number;
    alreadyCollectedCount: number;
    failedCount: number;
    queueCount: number;
  }
): {
  newCount: number;
  incompleteCount: number;
  alreadyCollectedCount: number;
  failedCount: number;
  queueCount: number;
} {
  const snap = state.post_scan_counter_snapshot;
  const inbox = renderContext.active_profile_inbox_summary;
  const authoritativeAlready = Math.max(
    snap?.status === "applied" ? snap.already_collected : 0,
    inbox?.trusted ? inbox.already_collected : 0,
    counters.alreadyCollectedCount
  );
  if (authoritativeAlready <= 0) return counters;
  const inboxRemaining = inbox?.trusted ? profileContextCollectableRemaining(inbox) : null;
  const authoritativeNew = inboxRemaining != null
    ? inboxRemaining
    : Math.max(
      snap?.status === "applied" ? snap.new ?? 0 : 0,
      counters.newCount
    );
  const authoritativeQueue = Math.max(
    snap?.status === "applied" ? snap.queue ?? 0 : 0,
    inbox?.trusted ? profileContextCollectableRemaining(inbox) : 0,
    counters.queueCount
  );
  return {
    ...counters,
    alreadyCollectedCount: authoritativeAlready,
    newCount: authoritativeNew,
    queueCount: Math.min(counters.queueCount > 0 ? counters.queueCount : authoritativeQueue, Math.max(authoritativeNew, authoritativeQueue))
  };
}

function hybridPartialCollectContinuation(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): { already: number; remaining: number } | null {
  if (!isHybridNetworkCacheModeEnabledForCollect(state)) return null;
  const remaining = expectedCollectContinuationRemaining(state, renderContext);
  if (remaining <= 0) return null;
  const snap = state.post_scan_counter_snapshot;
  const inbox = renderContext.active_profile_inbox_summary;
  const already = Math.max(
    snap?.status === "applied" ? snap.already_collected : 0,
    inbox?.trusted ? inbox.already_collected : 0,
    state.harvest.updated,
    state.target_status.complete
  );
  if (already <= 0) return null;
  return { already, remaining };
}

function applyCollectQueueReadinessGate(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): ScannerControlPanelViewModel {
  if (collectPresentationSuppressed(state) || viewModel.scanProgress.active) return viewModel;
  if (viewModel.collectProgress?.active || isCollectJobVisiblyLive(state)) return viewModel;
  if (
    viewModel.profileContext != null
    && activeProfileRevisitPresentationActive(renderContext.active_profile_presentation)
  ) {
    return viewModel;
  }
  if (isHybridTailGapClosed(state)) {
    return applyHybridTailGapClosedIfActive(viewModel, state);
  }
  if (isHybridTailGapCollectBlocked(state)) {
    return applyUnreachableTailGapOfferIfActive(viewModel, state);
  }
  if (hybridProfileCollectFullyComplete(state, renderContext)) return viewModel;
  const presentationPhase = resolveScanPresentationForViewModel(viewModel, state, renderContext);
  if (presentationPhase.phase === "scan_partial_failed") return viewModel;
  const continuationTabUrl = renderContext.active_tab_url ?? state.page_context.current_url ?? null;
  if (scanBudgetContinuationAvailable(state) && !scanSessionCompleteForPresentation(state, continuationTabUrl)) return viewModel;
  // Unreachable tail-gap escape hatch must not be overwritten by "Collect N remaining".
  if (
    viewModel.primaryAction.key === "close_unreachable_tail_gap"
    || viewModel.primaryAction.key === "skip_hybrid_incomplete"
    || isHybridUnreachableTailGapOffer(state)
  ) {
    if (viewModel.primaryAction.key === "skip_hybrid_incomplete") {
      return viewModel;
    }
    return applyUnreachableTailGapOfferIfActive(viewModel, state);
  }
  const inboxBlocksContinuation = trustedInboxBlocksCollectContinuation(viewModel, renderContext);
  const continuationRemaining = expectedCollectContinuationRemaining(state, renderContext);
  const hybridPartial = hybridPartialCollectContinuation(state, renderContext);
  const staleOversizedHybridQueue = isHybridNetworkCacheModeEnabledForCollect(state)
    && continuationRemaining > 0
    && harvestQueueActionableCount(state) > Math.min(HYBRID_NETWORK_CACHE_MAX_BATCH_SIZE, continuationRemaining);
  if (
    isCollectCalibrationSatisfied(state)
    && !inboxBlocksContinuation
    && (
      hybridPartial != null
      || (continuationRemaining > 0 && (harvestQueueActionableCount(state) === 0 || staleOversizedHybridQueue))
    )
  ) {
    const remaining = hybridPartial?.remaining ?? continuationRemaining;
    return applyLargeProfileContinuationPresentation(viewModel, state, renderContext, remaining);
  }
  if (
    inboxBlocksContinuation
    && (viewModel.headerProgress != null || viewModel.statsTileMode === "large_profile_batch")
  ) {
    const summary = renderContext.active_profile_inbox_summary;
    const headerStatus = summary?.trusted
      ? profileContextHeaderStatus(summary)
      : `${viewModel.counts.alreadyCollectedCount} collected`;
    return clearBatchHeaderChrome(viewModel, headerStatus);
  }
  const blockReason = collectQueueReadinessBlockReason(state);
  const queueEmpty = harvestQueueActionableCount(state) === 0;
  const collectActionVisible = viewModel.primaryAction.key === "start_collecting" || viewModel.action.key === "start_collecting";
  const needsReroute = blockReason != null && collectActionVisible;
  if (needsReroute) {
    const fallbackKey = forcedCollectFallbackPrimaryKey(state);
    if (fallbackKey === "start_collecting") {
      const partialPersisted = alignedPartialScanPersistedCount(state, continuationTabUrl);
      const remaining = Math.max(
        viewModel.counts.newCount,
        viewModel.counts.queueCount,
        partialPersisted
      );
      if (remaining > 0) {
        return applyLargeProfileContinuationPresentation(viewModel, state, renderContext, remaining);
      }
    }
    const forced = buildForcedWorkflowPrimaryAction(state, fallbackKey, viewModel.counts);
    const workflow = getDouyinScannerWorkflowReadiness(state);
    return {
      ...viewModel,
      profileScanned: fallbackKey === "scan_profile" ? false : viewModel.profileScanned,
      primaryAction: forced,
      action: {
        key: forced.key,
        title: forced.title,
        description: forced.description,
        buttonLabel: forced.label,
        enabled: forced.enabled,
        disabledReason: forced.disabledReason
      },
      emptyState: null,
      emptyStateTone: "neutral",
      headerStatus: fallbackKey === "scan_profile" && !workflow.profileScanReady
        ? (viewModel.scanProgress.active ? viewModel.headerStatus : "Scan required")
        : viewModel.headerStatus,
      counts: queueEmpty && blockReason != null && !presentationPhase.suppressGhostTiles
        ? {
          ...viewModel.counts,
          newCount: 0,
          queueCount: 0
        }
        : viewModel.counts
    };
  }
  if (!blockReason && !collectActionVisible) return viewModel;
  const snapshotWork = postScanSnapshotCollectWorkCount(state);
  const tabUrl = resolveActiveTabUrlForPresentation(state);
  const profileStaleTiles = !persistedScanJobTotalsTrustedForStoredProfile(state)
    || (tabUrl ? detectProfileContextMismatch(state, tabUrl) : false)
    || scanRunDiagnosticsStale(state);
  const persistedGhostTiles = persistedScanJobTotalsTrustedForStoredProfile(state)
    && (state.scan_job.total_persisted ?? 0) > 0
    && state.harvest.queue.length === 0;
  const ghostTiles = queueEmpty
    && snapshotWork <= 0
    && blockReason != null
    && (viewModel.counts.newCount > 0 || viewModel.counts.queueCount > 0)
    && (profileStaleTiles || persistedGhostTiles);
  if (partialAlignedScanPresentationActive(state, renderContext.active_tab_url ?? null, viewModel, renderContext)) return viewModel;
  if (presentationPhase.suppressGhostTiles) return viewModel;
  if (!ghostTiles) return viewModel;
  return {
    ...viewModel,
    counts: {
      ...viewModel.counts,
      newCount: 0,
      queueCount: 0
    },
    headerStatus: viewModel.scanProgress.active ? viewModel.headerStatus : "Scan required",
    emptyState: null,
    emptyStateTone: "neutral" as const
  };
}

function applyCollectPreflightBlockedPresentation(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState
): ScannerControlPanelViewModel {
  if (collectPresentationSuppressed(state) || viewModel.scanProgress.active) return viewModel;
  if (viewModel.collectProgress?.active || isCollectJobVisiblyLive(state)) return viewModel;
  const reason = collectPreflightRecentlyBlockedReason(state);
  if (!reason) return viewModel;
  if (reason === HYBRID_UNREACHABLE_TAIL_GAP_BLOCKED_REASON || reason === "tail_gap_already_closed") {
    if (isHybridTailGapClosed(state)) {
      return applyHybridTailGapClosedIfActive(viewModel, state);
    }
    const remaining = resolveUnreachableTailGapRemaining(state);
    if (remaining > 0) {
      const next = { ...viewModel };
      applyHybridUnreachableTailGapAction(next, buildHybridUnreachableTailGapUi(remaining));
      return next;
    }
  }
  if (viewModel.primaryAction.key !== "start_collecting") return viewModel;
  return {
    ...viewModel,
    emptyState: reason,
    emptyStateTone: "warning"
  };
}

function applyBackendWipeCollectMessage(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState
): ScannerControlPanelViewModel {
  if (collectPresentationSuppressed(state) || viewModel.scanProgress.active) return viewModel;
  if (collectPreflightRecentlyBlockedReason(state)) return viewModel;
  const snap = state.post_scan_counter_snapshot;
  if (snap?.source !== "backend_empty_disproves_snapshot") return viewModel;
  if ((snap.already_collected ?? 0) > 0 || (snap.backend_captured ?? 0) > 0) return viewModel;
  const n = Math.max(viewModel.counts.newCount, viewModel.counts.queueCount, viewModel.videosFound);
  if (n <= 0) return viewModel;
  return {
    ...viewModel,
    emptyState: `Backend data was cleared — ${n} videos ready to collect again.`,
    emptyStateTone: "neutral"
  };
}

function headerStatusLooksLikeFraction(headerStatus: string): boolean {
  return /\d+\s*\/\s*\d+/.test(headerStatus);
}

export function isScannerCollectTerminalPresentation(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext,
  viewModel?: Pick<ScannerControlPanelViewModel, "primaryAction" | "statsCompact">
): boolean {
  const summary = renderContext.active_profile_inbox_summary;
  if (viewModel?.primaryAction.key === "open_capture_inbox") return true;
  if (state.phase === "profile_collection_complete") return true;
  if (hybridProfileCollectFullyComplete(state, renderContext)) return true;
  if (state.collect_job.state === "completed" && !isCollectJobVisiblyLive(state)) return true;
  if (summary?.trusted && activeProfileInboxSummaryIsComplete(summary)) return true;
  return expectedCollectContinuationRemaining(state, renderContext) <= 0
    && (
      viewModel?.statsCompact?.percent === 100
      || Boolean(summary?.trusted && (summary.already_collected ?? 0) > 0)
    );
}

function resolveTerminalCollectedCount(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): number {
  const summary = renderContext.active_profile_inbox_summary;
  return Math.max(
    summary?.trusted ? summary.already_collected : 0,
    viewModel.counts.alreadyCollectedCount,
    state.harvest.updated,
    state.target_status.complete
  );
}

function applyTerminalHeaderPresentation(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.scanProgress.active || isCollectJobVisiblyLive(state) || viewModel.collectProgress?.active) {
    return viewModel;
  }
  const activeTabUrl = renderContext.active_tab_url ?? state.page_context.current_url ?? null;
  const summary = renderContext.active_profile_inbox_summary;
  const continuationRemaining = expectedCollectContinuationRemaining(state, renderContext);
  const terminalComplete = isScannerCollectTerminalPresentation(state, renderContext, viewModel);
  if (terminalComplete) {
    const collected = resolveTerminalCollectedCount(viewModel, state, renderContext);
    const reviewCount = Math.max(
      viewModel.counts.incompleteCount,
      summary?.inbox_needs_review_count ?? 0
    );
    const collectLeft = Math.max(viewModel.counts.newCount, viewModel.counts.queueCount, viewModel.counts.failedCount);
    if (reviewCount > 0 && (collectLeft === 0 || reviewCount > collectLeft)) {
      const headerStatus = collectLeft > 0 && reviewCount > collectLeft
        ? `${collected} ready · ${reviewCount} need review · ${collectLeft} not in API`
        : reviewCount === 1
          ? `${collected} ready · 1 needs review`
          : `${collected} ready · ${reviewCount} need review`;
      return clearBatchHeaderChrome(viewModel, headerStatus);
    }
    const scanCompleteAuthorityTotal = Math.max(
      viewModel.videosFound,
      viewModel.headerProgress?.total ?? 0,
      resolveScannedTotalFromState(state)
    );
    if (
      scanSessionCompleteForPresentation(state, activeTabUrl)
      && headerStatusLooksLikeFraction(viewModel.headerStatus)
      && collected > 0
      && collected < scanCompleteAuthorityTotal
    ) {
      return viewModel;
    }
    return clearBatchHeaderChrome(viewModel, collected > 0 ? `${collected} collected` : viewModel.headerStatus);
  }
  if (viewModel.headerProgress != null && !shouldShowProfileFractionHeader(viewModel.headerProgress.total, continuationRemaining)) {
    const collected = resolveTerminalCollectedCount(viewModel, state, renderContext);
    const headerStatus = headerStatusLooksLikeFraction(viewModel.headerStatus) && collected > 0
      ? `${collected} collected`
      : viewModel.headerStatus;
    return clearBatchHeaderChrome(viewModel, headerStatus);
  }
  if (headerStatusLooksLikeFraction(viewModel.headerStatus) && continuationRemaining <= 0) {
    const collected = resolveTerminalCollectedCount(viewModel, state, renderContext);
    if (collected > 0) return clearBatchHeaderChrome(viewModel, `${collected} collected`);
  }
  return viewModel;
}

function applyPartialAlignedScanPresentation(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.scanProgress.active) return viewModel;
  const presentationPhase = resolveScanPresentationForViewModel(viewModel, state, renderContext);
  if (!scanPresentationPhaseAllowsPartialRescanOverlay(presentationPhase)) return viewModel;
  const partialPersisted = presentationPhase.partialPersisted;
  const expected = presentationPhase.expectedCount ?? state.scan_job.expected_count ?? null;
  const remaining = expected != null ? Math.max(0, expected - partialPersisted) : 0;
  const tiles = partialCollectTileCounts(partialPersisted, 0);
  const scanHint = "Scan didn't finish. Rescan profile to continue or retry.";
  return {
    ...viewModel,
    scanDataVisible: true,
    headerStatus: expected != null && remaining > 0
      ? `${partialPersisted} / ${expected} videos`
      : `${partialPersisted} videos`,
    counts: {
      ...viewModel.counts,
      newCount: Math.max(viewModel.counts.newCount, tiles.newCount),
      queueCount: Math.max(viewModel.counts.queueCount, tiles.queueCount)
    },
    emptyState: viewModel.emptyState ?? scanHint,
    emptyStateTone: viewModel.emptyState && viewModel.emptyStateTone !== "neutral"
      ? viewModel.emptyStateTone
      : "warning",
    primaryAction: {
      ...viewModel.primaryAction,
      key: "scan_profile",
      title: "Rescan profile",
      label: "Rescan profile",
      description: scanHint,
      enabled: true,
      disabledReason: null,
      tone: "default"
    },
    action: {
      ...viewModel.action,
      key: "scan_profile",
      title: "Rescan profile",
      buttonLabel: "Rescan profile",
      description: scanHint
    }
  };
}

function scanPresentationPhaseRestoresPersistedTiles(
  phase: ReturnType<typeof resolveScanPresentationForViewModel>["phase"]
): boolean {
  return phase === "revisit_mismatch"
    || phase === "calibrate_required"
    || phase === "scan_complete"
    || phase === "collect_ready";
}

function applyScanPresentationPhasePersistedTiles(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.collectProgress?.active) return viewModel;
  if (isHybridTailGapClosed(state)) return viewModel;
  const presentationPhase = resolveScanPresentationForViewModel(viewModel, state, renderContext);
  if (presentationPhase.phase === "scan_partial_failed") {
    return {
      ...viewModel,
      profileScanned: false,
      scanDataVisible: true
    };
  }
  if (
    !scanPresentationPhaseRestoresPersistedTiles(presentationPhase.phase)
    || !presentationPhase.suppressGhostTiles
    || presentationPhase.partialPersisted <= 0
    || harvestQueueActionableCount(state) > 0
  ) {
    return viewModel;
  }
  if (viewModel.counts.newCount > 0 || viewModel.counts.queueCount > 0) return viewModel;
  const tiles = partialCollectTileCounts(presentationPhase.partialPersisted, viewModel.counts.alreadyCollectedCount);
  return {
    ...viewModel,
    scanDataVisible: true,
    counts: {
      ...viewModel.counts,
      newCount: tiles.newCount,
      queueCount: tiles.queueCount
    }
  };
}

function enforceScanPersistedTilePresentation(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  return applyScanPresentationPhasePersistedTiles(viewModel, state, renderContext);
}

function finalizeScannerControlPanelViewModel(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  const gated = applyProfileContextGateToScannerPanel(viewModel, state, renderContext);
  const polished = applyScannerUxPolish(gated, state, renderContext);
  const withHealth = {
    ...polished,
    health: {
      ...polished.health,
      profile: scannerHealthProfileLabel(state, renderContext)
    }
  };
  const finalized = applyTerminalHeaderPresentation(
    applyAppBackendAuthScannerOverrides(
      applyCollectPreflightBlockedPresentation(
        applyCollectQueueReadinessGate(
          applyScanFailureCollectPresentationBlock(
            applyScanPresentationPhasePersistedTiles(
              applyPartialAlignedScanPresentation(
                applyBackendWipeCollectMessage(withHealth, state),
                state,
                renderContext
              ),
              state,
              renderContext
            ),
            state,
            renderContext
          ),
          state,
          renderContext
        ),
        state
      ),
      state,
      renderContext
    ),
    state,
    renderContext
  );
  const pipeline = enforceScanPersistedTilePresentation(
    applyWaitingForActiveTabPresentationContract(
      enforceScanPresentationPhaseContract(
        applyHybridTailGapClosedIfActive(
          applyUnreachableTailGapOfferIfActive(finalized, state),
          state
        ),
        state,
        renderContext
      ),
      state
    ),
    state,
    renderContext
  );
  return applyScannerPresentationAuthority(
    pipeline,
    deriveScannerPresentationAuthority(state, {
      renderContext,
      primaryActionKey: pipeline.primaryAction.key,
      currentHeaderStatus: pipeline.headerStatus,
      scanProgressActive: pipeline.scanProgress.active,
      scanProgressAtFull: scanProgressAtFullCapacity(pipeline.scanProgress),
      scanProgressPhaseLabel: pipeline.scanProgress.phaseLabel,
      queueCount: pipeline.counts.queueCount,
      newCount: pipeline.counts.newCount
    })
  );
}

function applyWaitingForActiveTabPresentationContract(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState
): ScannerControlPanelViewModel {
  const lock = deriveAuthoritativeRunnerLock(state);
  if (String(lock.diagnostics.trace_ui_canonical_state ?? "") !== "waiting_for_active_tab") return viewModel;
  return {
    ...viewModel,
    headerStatus: "Waiting for tab",
    headerProgress: null,
    statsCompact: null
  };
}

function enforceScanPresentationPhaseContract(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.scanProgress.active || viewModel.collectProgress?.active) return viewModel;
  const presentationPhase = resolveScanPresentationForViewModel(viewModel, state, renderContext);
  if (presentationPhase.phase !== "scan_partial_failed") return viewModel;
  const expected = presentationPhase.expectedCount;
  const partialPersisted = presentationPhase.partialPersisted;
  const missing = expected != null ? Math.max(0, expected - partialPersisted) : null;
  return {
    ...viewModel,
    profileScanned: false,
    scanDataVisible: true,
    headerProgress: null,
    statsCompact: null,
    metricsPlan: null,
    headerStatus: expected != null && partialPersisted > 0
      ? `${partialPersisted} / ${expected} videos`
      : viewModel.headerStatus,
    emptyState: expected != null && missing != null
      ? `Profile scan incomplete: expected ${expected}, found ${partialPersisted}, missing ${missing}.`
      : viewModel.emptyState
  };
}

function applyScanFailureCollectPresentationBlock(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): ScannerControlPanelViewModel {
  const activeTabUrl = resolveActiveTabUrlForPresentation(state, renderContext.active_tab_url ?? null);
  if (activeTabUrl && detectProfileContextMismatch(state, activeTabUrl)) return viewModel;
  if (shouldGateScannerPanelForProfileContext(state, renderContext.active_tab_url ?? null)) return viewModel;
  if (viewModel.profileContext != null) return viewModel;
  if (!scanBlocksCollectPresentation(state, activeTabUrl)) return viewModel;
  const partialPersisted = alignedPartialScanPersistedCount(state, activeTabUrl);
  if (partialPersisted > 0 && storedScanSessionAppliesToActiveTab(state, activeTabUrl)) {
    const expected = state.scan_job.expected_count ?? null;
    const remaining = expected != null ? Math.max(0, expected - partialPersisted) : 0;
    const tiles = partialCollectTileCounts(partialPersisted, 0);
    const scanHint = "Scan didn't finish. Rescan profile to continue or retry.";
    return {
      ...viewModel,
      profileScanned: false,
      scanDataVisible: true,
      headerStatus: expected != null && remaining > 0
        ? `${partialPersisted} / ${expected} scanned`
        : `${partialPersisted} scanned`,
      counts: {
        ...viewModel.counts,
        newCount: tiles.newCount,
        queueCount: tiles.queueCount
      },
      metricsPlan: null,
      statsCompact: null,
      emptyState: scanHint,
      emptyStateTone: "warning",
      primaryAction: {
        ...viewModel.primaryAction,
        key: "scan_profile",
        title: "Rescan profile",
        label: "Rescan profile",
        description: scanHint,
        enabled: true,
        disabledReason: null,
        tone: "default"
      },
      action: {
        ...viewModel.action,
        key: "scan_profile",
        title: "Rescan profile",
        buttonLabel: "Rescan profile",
        description: scanHint
      }
    };
  }
  const inFlight = scanProfileInFlight(state);
  const blockedReason = getActiveProfilePostScanBlockedReason(state) ?? "Scan Profile required before collecting.";
  const scanHint = String(blockedReason).toLowerCase().includes("failed")
    ? "Scan didn't finish. Scan Profile again to retry."
    : "Previous scan had an issue. Scan Profile again to refresh the collection plan.";
  return {
    ...viewModel,
    profileScanned: false,
    scanDataVisible: inFlight,
    headerStatus: inFlight ? "Scanning" : "Scan required",
    counts: inFlight ? viewModel.counts : {
      ...viewModel.counts,
      newCount: 0,
      incompleteCount: 0,
      alreadyCollectedCount: 0,
      queueCount: 0,
      collectedCount: 0,
      savedCount: 0,
      failedCount: 0
    },
    metricsPlan: null,
    statsCompact: null,
    emptyState: null,
    emptyStateTone: "warning",
    primaryAction: {
      ...viewModel.primaryAction,
      key: "scan_profile",
      title: inFlight ? "Scanning profile" : "Scan Profile",
      label: inFlight ? "Scanning..." : "Scan Profile",
      description: inFlight ? "Scan in progress..." : scanHint,
      enabled: !inFlight,
      disabledReason: null,
      tone: "default"
    },
    action: {
      ...viewModel.action,
      key: "scan_profile",
      title: inFlight ? "Scanning profile" : "Scan Profile",
      buttonLabel: inFlight ? "Scanning..." : "Scan Profile",
      description: inFlight ? "Scan in progress..." : scanHint
    }
  };
}

function formatActiveScanProgressHeader(scanProgress: NonNullable<ScannerControlPanelViewModel["scanProgress"]>): string {
  if (!scanProgress.active) return "Scanning";
  if (scanProgress.expected == null || scanProgress.expected <= 0) {
    return scanProgress.discovered > 0 ? `Scanning ${scanProgress.discovered}` : "Scanning";
  }
  const fraction = scanProgress.fractionDiscovered ?? Math.min(scanProgress.discovered, scanProgress.expected);
  if (scanProgressAtFullCapacity(scanProgress) && scanProgressPhaseIsFinalizing(scanProgress.phaseLabel)) {
    return `Finalizing ${fraction} / ${scanProgress.expected}`;
  }
  return `Scanning ${fraction} / ${scanProgress.expected}`;
}

function largeProfilePersistedQueueTotal(state: WholeProfileHarvestState, activeTabUrl?: string | null): number | null {
  if (scanBlocksCollectPresentation(state)) return null;
  const tabUrl = activeTabUrl ?? state.page_context.current_url ?? state.safety.tab_health.current_url ?? null;
  if (tabUrl && detectProfileContextMismatch(state, tabUrl)) return null;
  if (!persistedScanJobTotalsTrustedForStoredProfile(state)) return null;
  const diagnostics = scanDiagnosticsRecord(state);
  const visible = numericDiagnosticValue(diagnostics.queue_total_visible) ?? state.harvest.queue.length;
  const candidates = [diagnostics.queue_total_persisted, diagnostics.scan_job_total_persisted, diagnostics.profile_queue_total_count, state.scan_job.total_persisted];
  for (const value of candidates) {
    const numeric = numericDiagnosticValue(value);
    if (numeric != null && numeric > 0 && (diagnostics.large_profile_mode === "yes" || numeric >= visible)) return numeric;
  }
  return null;
}

function largeProfileVisibleQueueTotal(state: WholeProfileHarvestState): number | null {
  const diagnostics = scanDiagnosticsRecord(state);
  if (diagnostics.large_profile_mode !== "yes") return null;
  const value = diagnostics.queue_total_visible ?? state.harvest.queue_preview.length ?? state.harvest.queue.length;
  const numeric = numericDiagnosticValue(value);
  return numeric != null && numeric >= 0 ? numeric : null;
}

/** True when queue evidence has the Hybrid-required engagement + duration fields. */
function queueItemHasHybridMetrics(item: WholeProfileHarvestQueueItem): boolean {
  return evidenceHasHybridRequiredMetrics(
    item.profile_card_evidence && typeof item.profile_card_evidence === "object"
      ? item.profile_card_evidence
      : null
  );
}

function buildHybridMetricsPlan(state: WholeProfileHarvestState): ScannerControlPanelViewModel["metricsPlan"] {
  if (!isHybridNetworkCacheModeEnabledForCollect(state)) return null;
  const snapshot = state.post_scan_counter_snapshot;
  const diagnostics = scanDiagnosticsRecord(state);
  const contract = buildProfileCollectContractFromState(state);
  const discovered = contract.displayed_total > 0 ? contract.displayed_total : resolveScannedTotalFromState(state);
  if (discovered <= 0 && state.harvest.queue.length === 0) return null;
  const scopedQueue = filterQueueToDisplayedProfileCollectScope(state.harvest.queue, diagnostics);
  const actionable = scopedQueue.filter((item) => {
    const status = String(item.status);
    return status !== "already_collected" && status !== "backend_verified" && status !== "complete"
      && status !== "extracted" && status !== "skipped" && status !== "duplicate"
      && item.capture_status !== "complete" && item.capture_status !== "skipped";
  });
  const metricsReady = actionable.filter((item) => evidenceIsHybridFlushReady(item.profile_card_evidence)).length;
  const metricsMissing = Math.max(contract.pending_hydration, actionable.length - metricsReady);
  const collected = snapshot?.status === "applied"
    ? snapshot.already_collected
    : contract.captured;
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const skippedUncollectable = numericDiagnosticValue(summary.hybrid_runner_uncollectable_skipped_count) ?? state.harvest.queue.filter((item) => item.profile_card_evidence?.hybrid_uncollectable === true).length;
  return {
    discovered: Math.max(discovered, collected + actionable.length + skippedUncollectable),
    metricsReady,
    metricsMissing,
    collected,
    skippedUncollectable
  };
}

function applyHybridMetricsMissAction(
  viewModel: ScannerControlPanelViewModel,
  missUi: ReturnType<typeof buildHybridMetricsMissUi>
): void {
  viewModel.emptyState = missUi.retryHint;
  viewModel.emptyStateTone = "warning";
  viewModel.action = {
    key: "skip_hybrid_incomplete",
    title: missUi.title,
    description: missUi.description,
    buttonLabel: missUi.buttonLabel,
    enabled: true,
    disabledReason: null
  };
  viewModel.primaryAction = {
    key: "skip_hybrid_incomplete",
    label: missUi.buttonLabel,
    title: missUi.title,
    description: missUi.description,
    enabled: true,
    disabledReason: null,
    tone: "warning"
  };
}

function applyHybridUnreachableTailGapAction(
  viewModel: ScannerControlPanelViewModel,
  gapUi: ReturnType<typeof buildHybridUnreachableTailGapUi>
): void {
  viewModel.collectProgress = null;
  viewModel.emptyState = null;
  viewModel.emptyStateTone = "warning";
  viewModel.primaryActionCardTone = "warning";
  viewModel.action = {
    key: "close_unreachable_tail_gap",
    title: gapUi.title,
    description: gapUi.description,
    buttonLabel: gapUi.buttonLabel,
    enabled: true,
    disabledReason: null
  };
  viewModel.primaryAction = {
    key: "close_unreachable_tail_gap",
    label: gapUi.buttonLabel,
    title: gapUi.title,
    description: gapUi.description,
    enabled: true,
    disabledReason: null,
    tone: "warning"
  };
}

function applyHybridTailGapClosedAction(
  viewModel: ScannerControlPanelViewModel,
  completeUi: ReturnType<typeof buildHybridTailGapClosedCompleteUi>
): void {
  const already = completeUi.already;
  viewModel.collectProgress = null;
  viewModel.statsCompact = {
    summary: `${already} collected · ready for review`,
    percent: 100
  };
  viewModel.headerStatus = `${already} collected`;
  viewModel.headerProgress = null;
  viewModel.emptyState = completeUi.description;
  viewModel.emptyStateTone = "success";
  viewModel.primaryActionCardTone = "success";
  viewModel.counts.alreadyCollectedCount = already;
  viewModel.counts.newCount = 0;
  viewModel.counts.queueCount = 0;
  viewModel.counts.collectedCount = already;
  viewModel.counts.savedCount = already;
  viewModel.action = {
    key: "open_capture_inbox",
    title: completeUi.title,
    description: completeUi.description,
    buttonLabel: completeUi.buttonLabel,
    enabled: true,
    disabledReason: null
  };
  viewModel.primaryAction = {
    key: "open_capture_inbox",
    label: completeUi.buttonLabel,
    title: completeUi.title,
    description: completeUi.description,
    enabled: true,
    disabledReason: null,
    tone: "default"
  };
}

/** Pin complete UI after operator closed phantom tail gap (inbox API may still show phantom new_count). */
function applyHybridTailGapClosedIfActive(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState
): ScannerControlPanelViewModel {
  if (!isHybridTailGapClosed(state)) return viewModel;
  const next = { ...viewModel };
  applyHybridTailGapClosedAction(
    next,
    buildHybridTailGapClosedCompleteUi(
      resolveHybridTailGapClosedAlready(state),
      resolveHybridTailGapClosedCount(state)
    )
  );
  return next;
}

/** Pin Close presentation whenever unreachable-gap evidence is active (survives UX polish / continuation). */
function applyUnreachableTailGapOfferIfActive(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState
): ScannerControlPanelViewModel {
  if (!isHybridUnreachableTailGapOffer(state)) return viewModel;
  const next = { ...viewModel };
  applyHybridUnreachableTailGapAction(
    next,
    buildHybridUnreachableTailGapUi(resolveUnreachableTailGapRemaining(state))
  );
  return next;
}

function currentRunFoundCount22C14B(state: WholeProfileHarvestState): number {
  const diagnostics = scanDiagnosticsRecord(state);
  const explicit = numericDiagnosticValue(diagnostics.current_run_found_count ?? diagnostics.current_run_new_inserted_total ?? diagnostics.current_run_effective_progress_total);
  const persisted = largeProfilePersistedQueueTotal(state) ?? numericDiagnosticValue(diagnostics.persisted_total_count ?? diagnostics.scan_job_total_persisted) ?? state.scan_job.total_persisted;
  const failedOrRetrying = state.scan_job.status === "failed" || state.scan_job.status === "retry_wait" || state.profile_scan.status === "failed" || state.verify.status === "failed";
  if (failedOrRetrying && persisted > 0 && state.scan_job.page_count <= 1) return Math.max(0, explicit != null ? Math.min(explicit, state.profile_scan.accepted_target_count || state.verify.verified_target_count || 0) : 0);
  if (explicit != null && explicit >= 0) return explicit;
  return firstPositiveNumber([
    state.profile_scan.accepted_target_count,
    state.verify.verified_target_count,
    state.verify.accepted_target_count,
    state.profile_scan.targets.length,
    state.verify.targets.length,
    state.profile_scan.target_details.length,
    state.verify.target_details.length
  ]);
}

function activeScanProgress22C14G(state: WholeProfileHarvestState): ScannerControlPanelViewModel["scanProgress"] {
  const diagnostics = scanDiagnosticsRecord(state);
  const runtimeProgressAvailable = scanRuntimeProgressAvailable22C14L(diagnostics);
  const workflowScanActive = scanProfileWorkflowActive(state) || (state.status === "verifying" && state.workflow.active_task === "scan_profile");
  const active = scanJobProgressActive22C14L(state)
    || workflowScanActive
    || (state.phase !== "scan_finished" && state.workflow.scan.status === "running" && runtimeProgressAvailable);
  const alignedDiagnostics = scanRunDiagnosticsAligned(state, diagnostics);
  const jobCountersTrusted = activeScanJobCountersTrusted(state, diagnostics);
  const currentRunProgress = alignedDiagnostics
    ? numericDiagnosticValue(diagnostics.current_run_found_count ?? diagnostics.current_run_new_inserted_total ?? diagnostics.current_run_effective_progress_total)
    : null;
  const jobPersistedProgress = jobCountersTrusted ? Math.max(0, state.scan_job.total_persisted ?? 0) : 0;
  const fallbackProgress = !active || alignedDiagnostics || jobCountersTrusted
    ? numericDiagnosticValue(diagnostics.scan_progress_discovered)
      ?? Math.max(
        0,
        jobPersistedProgress,
        state.profile_scan.accepted_target_count ?? 0,
        state.verify.verified_target_count ?? 0
      )
    : 0;
  const staleRun = scanRunDiagnosticsStale(state, diagnostics);
  const discovered = staleRun && active
    ? Math.max(0, jobPersistedProgress)
    : Math.max(0, currentRunProgress ?? fallbackProgress);
  const expected = resolveScanProgressExpectedCount(state);
  const pagesFetched = !active || alignedDiagnostics || jobCountersTrusted
    ? Math.max(
      0,
      numericDiagnosticValue(diagnostics.scan_progress_pages ?? diagnostics.scan_job_pages_fetched ?? diagnostics.active_profile_post_fetch_page_count) ?? 0,
      jobCountersTrusted ? (state.scan_job.page_count ?? 0) : alignedDiagnostics ? (state.scan_job.page_count ?? 0) : 0
    )
    : 0;
  const requestCount = !active || alignedDiagnostics || jobCountersTrusted
    ? Math.max(
      0,
      numericDiagnosticValue(diagnostics.scan_progress_requests ?? diagnostics.scan_job_request_count ?? diagnostics.active_profile_post_fetch_request_count) ?? 0,
      jobCountersTrusted ? (state.scan_job.request_count ?? 0) : alignedDiagnostics ? (state.scan_job.request_count ?? 0) : 0
    )
    : 0;
  const rawPhase = typeof diagnostics.scan_progress_phase_label === "string"
    ? diagnostics.scan_progress_phase_label
    : null;
  const diagnosticExpected = numericDiagnosticValue(diagnostics.scan_progress_expected)
    ?? numericDiagnosticValue(diagnostics.expected_profile_video_count)
    ?? numericDiagnosticValue(diagnostics.api_pagination_expected);
  const diagnosticDiscovered = numericDiagnosticValue(diagnostics.scan_progress_discovered)
    ?? numericDiagnosticValue(diagnostics.current_run_found_count)
    ?? numericDiagnosticValue(diagnostics.scan_job_total_persisted);
  const atFullProgress = (expected != null && expected > 0 && discovered >= expected)
    || (diagnosticExpected != null && diagnosticExpected > 0 && diagnosticDiscovered != null && diagnosticDiscovered >= diagnosticExpected);
  const phaseLabel = state.scan_job.status === "retry_wait"
    ? "Retry wait"
    : normalizeScanProgressPhaseLabel(rawPhase, {
      scanActive: active,
      atFullProgress
    });
  const presentation = buildScanProgressPresentationFields({
    discovered,
    expected: expected != null && expected > 0 ? expected : null,
    phaseLabel
  });
  return {
    active,
    discovered: presentation.discovered,
    expected: presentation.expected,
    fractionDiscovered: presentation.fractionDiscovered,
    overDisplayExtra: presentation.overDisplayExtra,
    progressFractionLabel: presentation.progressFractionLabel,
    pagesFetched,
    requestCount,
    phaseLabel,
    detail: active && atFullProgress
      ? "All videos discovered. Finalizing scan and syncing with Capture Inbox..."
      : active && workflowScanActive && !runtimeProgressAvailable && discovered <= 0
        ? "Connecting to Douyin and preparing profile scan..."
        : active && pagesFetched === 0 && requestCount === 0
          ? "Waiting for first API pagination checkpoint..."
          : active
            ? "API pagination is running. Counts shown here are from the current scan run and exclude previously persisted repository history."
            : "Final scan counts are selected after scan finalization.",
    percent: presentation.percent
  };
}

function scanFinalized22C14G(state: WholeProfileHarvestState): boolean {
  const diagnostics = scanDiagnosticsRecord(state);
  return state.phase === "scan_finished"
    || state.status === "verified"
    || state.workflow.scan.status === "success"
    || state.workflow.scan.status === "failed"
    || state.scan_job.status === "completed"
    || state.scan_job.status === "failed"
    || typeof diagnostics.scan_finalization_result === "string"
    || typeof diagnostics.scan_finalized_at === "string";
}

function scanDisplayAuthority22C14B(state: WholeProfileHarvestState): {
  current_run_found_count: number;
  persisted_total_count: number | null;
  display_mode: "current_run_authority" | "persisted_history_authority";
  warning: string | null;
} {
  const diagnostics = scanDiagnosticsRecord(state);
  const progress = activeScanProgress22C14G(state);
  const finalized = scanFinalized22C14G(state) && !progress.active;
  // 22C-14G count authority intentionally separates active progress from finalized queue authority: while a scan lock is present, partial discoveries are progress only; persisted/post-scan totals become final display authority only after finalization.
  const currentRun = progress.active ? progress.discovered : currentRunFoundCount22C14B(state);
  const snapshotQueue = finalized && state.post_scan_counter_snapshot?.queue != null ? state.post_scan_counter_snapshot.queue : null;
  const persisted = finalized ? (largeProfilePersistedQueueTotal(state) ?? numericDiagnosticValue(diagnostics.persisted_total_count ?? diagnostics.scan_job_total_persisted) ?? snapshotQueue ?? (state.scan_job.total_persisted > 0 ? state.scan_job.total_persisted : null)) : null;
  const failedOrRetrying = state.scan_job.status === "failed" || state.scan_job.status === "retry_wait" || state.profile_scan.status === "failed" || state.verify.status === "failed";
  const mixed = !progress.active && failedOrRetrying && persisted != null && persisted > currentRun;
  return {
    current_run_found_count: currentRun,
    persisted_total_count: persisted,
    display_mode: mixed ? "persisted_history_authority" : "current_run_authority",
    warning: mixed ? "Current scan run failed/retrying; displayed total includes persisted history." : null
  };
}

function profileCountWithoutPopupWarning(state: WholeProfileHarvestState): number {
  if (scanIncompleteUnderExpectedForPresentation(state)) {
    return alignedPartialScanPersistedCount(state);
  }
  const authority = scanDisplayAuthority22C14B(state);
  if (authority.display_mode === "persisted_history_authority") {
    return Math.max(authority.current_run_found_count, authority.persisted_total_count ?? 0);
  }
  if (scanFinalized22C14G(state)) {
    const scanTotal = resolveScannedTotalFromState(state);
    if (scanTotal > 0) return scanTotal;
  }
  const largeProfileTotal = largeProfilePersistedQueueTotal(state);
  if (largeProfileTotal != null) return largeProfileTotal;
  return firstPositiveNumber([
    state.classification.total_candidates,
    state.profile_scan.accepted_target_count,
    state.verify.verified_target_count,
    state.verify.accepted_target_count,
    state.profile_scan.targets.length,
    state.verify.targets.length,
    state.profile_scan.target_details.length,
    state.verify.target_details.length,
    state.harvest.backend.batch_flush.queue_total,
    state.harvest.queue_preview.length,
    state.harvest.planned_total
  ]);
}

function profileCount(state: WholeProfileHarvestState): number {
  return profileCountWithoutPopupWarning(state);
}

function profileCountLabel(state: WholeProfileHarvestState, count = profileCount(state)): string {
  const expected = expectedProfileVideoCount(state);
  return expected != null ? `${count} / ${expected}` : String(count);
}

function profileScanDetected(state: WholeProfileHarvestState, videosFound = profileCount(state)): boolean {
  return state.layer.profile_scan_ready
    || state.profile_scan.status === "success"
    || state.verify.status === "success"
    || state.profile_scan.scan_rounds > 0
    || state.verify.scan_rounds > 0
    || state.profile_scan.targets.length > 0
    || state.verify.targets.length > 0
    || state.profile_scan.target_details.length > 0
    || state.verify.target_details.length > 0
    || videosFound > 0;
}

function profilePageDetected(state: WholeProfileHarvestState): boolean {
  return state.page_context.page_type === "profile"
    || state.safety.tab_health.page_type === "profile"
    || Boolean(state.profile_url)
    || Boolean(state.source_url)
    || Boolean(state.page_context.current_url?.includes("/user/"))
    || Boolean(state.safety.tab_health.current_url?.includes("/user/"));
}

function scannerHealthProfileLabel(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel["health"]["profile"] {
  if (activeTabOnDouyinProfile(renderContext.active_tab_url)) return "This profile";
  if (profilePageDetected(state)) return "Profile";
  return "No profile";
}

function calibrationReadyDetected(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): boolean {
  return readiness.calibration_ready || isDouyinCalibrationReady(state.calibration);
}

function scanApiPaginationAttempted22C14N(state: WholeProfileHarvestState, diagnostics = scanDiagnosticsRecord(state)): boolean {
  const requestCount = numericDiagnosticValue(diagnostics.api_pagination_request_count)
    ?? numericDiagnosticValue(diagnostics.scan_job_request_count)
    ?? (state.scan_job.request_count > 0 ? state.scan_job.request_count : null);
  const pageCount = numericDiagnosticValue(diagnostics.api_pagination_page_count)
    ?? numericDiagnosticValue(diagnostics.scan_job_pages_fetched)
    ?? (state.scan_job.page_count > 0 ? state.scan_job.page_count : null);
  return diagnostics.api_pagination_attempted === "yes" || (requestCount != null && requestCount > 0) || (pageCount != null && pageCount > 0);
}

function scannerAppBackendHealth(state: WholeProfileHarvestState, auth: AppBackendAuthStatus): ScannerControlPanelViewModel["health"]["api"] {
  if (!auth.loggedIn) return "App login";
  const backendFailed = state.harvest.backend.capture_session.status === "failed"
    || state.harvest.backend.one_item_flush.status === "failed"
    || state.harvest.backend.batch_flush.status === "failed";
  if (backendFailed) return "App offline";
  return "App OK";
}

function backendApiHealth(state: WholeProfileHarvestState): ScannerControlPanelViewModel["health"]["api"] {
  const backendFailed = state.harvest.backend.capture_session.status === "failed"
    || state.harvest.backend.one_item_flush.status === "failed"
    || state.harvest.backend.batch_flush.status === "failed";
  if (backendFailed) return "API offline";
  const backendReady = state.harvest.backend.capture_session.status === "ready"
    || state.harvest.backend.one_item_flush.status === "succeeded"
    || state.harvest.backend.batch_flush.status === "completed"
    || state.harvest.backend.batch_flush.status === "completed_with_warnings";
  if (backendReady || scanApiPaginationAttempted22C14N(state)) return "API ready";
  const errorMessage = typeof state.last_error === "string" ? state.last_error : state.last_error?.message ?? "";
  return errorMessage.includes("backend") || errorMessage.includes("timeout") ? "API offline" : "API not checked";
}

function extractedCount(state: WholeProfileHarvestState): number {
  return state.harvest.results.filter((result) => result.status === "extracted").length;
}

function savedCount(state: WholeProfileHarvestState): number {
  const verifiedQueueIds = new Set(state.harvest.queue.filter((item) => item.capture_inbox_item_id || ["extracted", "backend_verified", "saved"].includes(String(item.status))).map((item) => item.aweme_id));
  for (const result of state.harvest.results) {
    if (result.capture_inbox_item_id) verifiedQueueIds.add(result.aweme_id);
  }
  return verifiedQueueIds.size;
}

function deriveCollectionCountersFromQueue(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): {
  newCount: number;
  incompleteCount: number;
  alreadyCollectedCount: number;
  failedCount: number;
  queueCount: number;
} {
  if (state.harvest.queue.length === 0) {
    return applyInboxSnapshotCounterAuthority(state, renderContext, {
      newCount: state.classification.status === "success" ? state.classification.counts.new : state.target_status.new,
      incompleteCount: state.classification.status === "success" ? state.classification.counts.incomplete : state.target_status.incomplete,
      alreadyCollectedCount: state.classification.status === "success" ? state.classification.counts.complete : state.target_status.complete,
      failedCount: state.classification.status === "success" ? state.classification.counts.failed : state.target_status.failed,
      queueCount: state.classification.status === "success" ? state.classification.counts.collect : state.harvest.queue_preview.length || pendingCount(state)
    });
  }

  let newCount = 0;
  let incompleteCount = 0;
  let alreadyCollectedCount = 0;
  let failedCount = 0;
  let queueCount = 0;

  for (const item of state.harvest.queue) {
    const status = String(item.status);
    const captureStatus = item.capture_status;
    const isComplete = status === "backend_verified" || status === "complete" || status === "already_collected" || status === "extracted" || status === "saved" || captureStatus === "complete";
    const isFailed = status === "retry" || status === "failed_recoverable" || captureStatus === "failed";
    const isIncomplete = status === "incomplete" || status === "needs_metadata" || captureStatus === "incomplete";
    const isNew = !isComplete && !isFailed && !isIncomplete && (status === "new" || status === "pending");
    if (isNew) newCount += 1;
    if (isIncomplete) incompleteCount += 1;
    if (isFailed) failedCount += 1;
    if (isComplete) alreadyCollectedCount += 1;
    if (!isComplete && (status === "new" || status === "pending" || status === "processing" || status === "retry" || status === "incomplete" || status === "needs_metadata")) queueCount += 1;
  }

  return applyInboxSnapshotCounterAuthority(state, renderContext, {
    newCount,
    incompleteCount,
    alreadyCollectedCount,
    failedCount,
    queueCount
  });
}

function pendingCount(state: WholeProfileHarvestState): number {
  if (state.harvest.queue.length > 0) return state.harvest.queue.filter((item) => ["new", "pending", "processing", "retry", "incomplete", "needs_metadata"].includes(String(item.status)) && !["complete", "skipped"].includes(String(item.capture_status))).length;
  return state.harvest.queue_preview.length || Math.max(0, state.harvest.planned_total - savedCount(state) - state.harvest.failed);
}

function continuationBatchSize(state: WholeProfileHarvestState): number {
  return typeof state.harvest_options.batch_limit === "number"
    ? state.harvest_options.batch_limit
    : typeof state.harvest.batch_limit === "number"
      ? state.harvest.batch_limit
      : 10;
}

function batchContinuationButtonLabel(state: WholeProfileHarvestState): string {
  return `Continue Next ${continuationBatchSize(state)}`;
}

function batchContinuationMessage(state: WholeProfileHarvestState, saved: number, pending: number): string {
  return `Batch complete: ${saved} saved, ${pending} remaining. Click ${batchContinuationButtonLabel(state)} to process the next batch.`;
}

function scanBudgetContinuationAvailable(state: WholeProfileHarvestState): boolean {
  const diagnostics = scanDiagnosticsRecord(state);
  const autoContinuationLimitReached = diagnostics.auto_continuation_limit_reached === "yes"
    || diagnostics.continuation_reason === "auto_continuation_limit_reached"
    || diagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || diagnostics.final_exhaustion_mode === "manual_continuation";
  return autoContinuationLimitReached
    || diagnostics.continuation_available === "yes"
    || diagnostics.partial_scan_resumable === "yes"
    || diagnostics.page_budget_exhausted === "yes"
    || diagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || diagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted";
}

function scanBudgetContinuationMessage(state: WholeProfileHarvestState, videosFound: number, expectedCount: number | null): string {
  const diagnostics = scanDiagnosticsRecord(state);
  const pageBudgetLimit = numericDiagnosticValue(diagnostics.page_budget_limit);
  const remaining = expectedCount != null ? Math.max(expectedCount - videosFound, 0) : null;
  const replayDetected = diagnostics.continuation_replay_duplicate_pages_detected === "yes";
  const replayRecovered = diagnostics.continuation_resume_result === "replay_recovery_resumed";
  const resumedFromCheckpoint = diagnostics.continuation_resume_result === "resumed_from_saved_cursor";
  const autoContinuationBatchesRun = numericDiagnosticValue(diagnostics.auto_continuation_batches_run);
  const autoContinuationLimitReached = diagnostics.auto_continuation_limit_reached === "yes"
    || diagnostics.continuation_reason === "auto_continuation_limit_reached"
    || diagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || diagnostics.final_exhaustion_mode === "manual_continuation";
  const progressAuthority = numericDiagnosticValue(diagnostics.continuation_progress_total ?? diagnostics.current_run_new_inserted_total ?? diagnostics.current_run_found_count);
  const progressText = progressAuthority != null && progressAuthority >= 0
    ? ` Current run added ${progressAuthority} new videos; previously persisted history is tracked separately.`
    : " Current-run progress excludes previously persisted history.";
  const remainingText = remaining != null && remaining > 0
    ? ` ${remaining} more profile videos may remain.`
    : " More profile videos may remain.";
  const continuationText = replayDetected || replayRecovered
    ? " Duplicate replay was detected and the scan is ready to continue from the saved continuation cursor."
    : resumedFromCheckpoint
      ? " The next run will continue from the saved continuation cursor instead of replaying earlier pages."
      : autoContinuationLimitReached
        ? ` One click already processed ${autoContinuationBatchesRun ?? "multiple"} healthy pagination batch${autoContinuationBatchesRun === 1 ? "" : "es"}; Continue Scan will resume from the saved continuation cursor.`
        : " Continue Scan will fetch the remaining unseen pages.";
  return pageBudgetLimit != null
    ? `Large profile scan paused at page budget (${pageBudgetLimit} pages). ${videosFound} videos are currently persisted.${remainingText}${progressText}${continuationText}`
    : `Large profile scan paused before all profile pages were fetched. ${videosFound} videos are currently persisted.${remainingText}${progressText}${continuationText}`;
}

function batchContinuationAvailable(state: WholeProfileHarvestState, pending = pendingCount(state)): boolean {
  const responseSummary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const topFailure = responseSummary.top_failure ?? responseSummary.topFailure ?? null;
  const topFailureNone = topFailure == null || topFailure === "none";
  const failedCount = typeof responseSummary.failed_count === "number" ? responseSummary.failed_count : state.harvest.failed;
  const collectionIdle = state.workflow.collection.status !== "running"
    && state.workflow.collection.status !== "opening_target"
    && state.workflow.collection.status !== "pausing"
    && state.harvest.status !== "running"
    && state.status !== "harvesting";

  return state.phase === "batch_safe_mode_completed"
    && collectionIdle
    && pending > 0
    && (failedCount === 0 || topFailureNone);
}

export function getActionHelpText(
  actionKey: WholeProfileHarvestOperatorActionKey,
  actions: WholeProfileHarvestActionState,
  readiness: WholeProfileHarvestReadiness,
  state: WholeProfileHarvestState
): string {
  const actionMap: Partial<Record<WholeProfileHarvestOperatorActionKey, { disabledReason: string | null }>> = {
    verify_profile: actions.verifyProfile,
    test_3_videos: actions.dryRunRandom,
    dry_run_first: actions.dryRunFirst,
    dry_run_last: actions.dryRunLast,
    dry_run_random: actions.dryRunRandom,
    run_harvest: actions.runHarvest,
    prepare_backend_session: actions.prepareBackendSession,
    build_payload_preview: actions.buildPayloadPreview,
    flush_one_item: actions.flushOneItem,
    flush_batch: actions.flushBatch,
    resume: actions.resume,
    reset_harvest: actions.resetHarvest
  };
  const disabledReason = actionMap[actionKey]?.disabledReason ?? null;
  if (disabledReason) return disabledReason;

  if (actionKey === "verify_profile") return "Scan the current Douyin profile first to build a clean queue before testing or extracting.";
  if (actionKey === "test_3_videos") return readiness.profile_scan_ready
    ? "Recommended before extraction. Test 3 videos to confirm metrics load correctly."
    : "Scan Profile first, then test 3 videos before extraction.";
  if (actionKey === "dry_run_first") return "Use Test First 3 when you want a quick check near the top of the queue.";
  if (actionKey === "dry_run_last") return "Use Test Last 3 when you want a quick check near the end of the queue.";
  if (actionKey === "dry_run_random") return readiness.profile_scan_ready
    ? "Recommended before extraction. Test 3 videos to confirm metrics load correctly."
    : "Scan Profile first, then test 3 videos before extraction.";
  if (actionKey === "run_harvest") return readiness.dry_run_ready
    ? `Extract metrics for ${friendlyBatchLabel(state.harvest_options.batch)} without saving anything yet.`
    : "Run Test 3 Videos first, then extract the next batch of metrics.";
  if (actionKey === "prepare_backend_session") return "Create a scan session to prepare Capture Inbox before saving videos.";
  if (actionKey === "build_payload_preview") return "Run a data check on one extracted video before writing anything to Capture Inbox.";
  if (actionKey === "flush_one_item") return "Recommended first save step. Save 1 video to confirm Capture Inbox accepts the data.";
  if (actionKey === "flush_batch") return "Use Save to Capture Inbox after Save 1 Video succeeds and the data check passes.";
  if (actionKey === "mode") return `${friendlyModeLabel(state.harvest_options.mode)} controls which queued videos will be extracted next.`;
  if (actionKey === "batch") return `${friendlyBatchLabel(state.harvest_options.batch)} controls how many videos the next extraction or save run will process.`;
  if (actionKey === "speed") return `${friendlySpeedLabel(state.harvest_options.speed)} controls pacing. Safe is best when you want fewer security checks.`;
  if (actionKey === "unattended_safe_mode") return state.harvest_options.unattended_safe_mode
    ? "Unattended Safe Mode is on. Runs pause on security checks or repeated errors."
    : "Turn this on for smaller chunks and safer unattended runs.";
  if (actionKey === "resume") return readiness.resume_ready
    ? "Resume continues after a pause such as a solved security check or a temporary interruption."
    : "Resume becomes available after the run pauses.";
  return "Reset Harvest clears the current whole-profile run so you can scan the profile again from a clean state.";
}

function shortenUrl(value: string | null, max = 48): string {
  if (!value) return "none";
  if (value.length <= max) return value;
  return `${value.slice(0, max - 3)}...`;
}

function recentResultRows(results: WholeProfileHarvestResult[]): string[] {
  return results.slice(-5).map((result) => {
    if (result.status === "extracted") {
      return `#${result.index} EXTRACTED · ${result.duration_text ?? "—"} · Likes ${result.like_count ?? "—"} · Comments ${result.comment_count ?? "—"}`;
    }
    if (result.status === "skipped") return `#${result.index} SKIP · ${result.error_code ?? result.error ?? "already complete"}`;
    return `#${result.index} FAIL · ${result.error_code ?? result.error ?? "unknown"}`;
  });
}

function queuePreviewRows(state: WholeProfileHarvestState): { rows: string[]; more: number } {
  const preview = state.harvest.queue_preview.slice(0, 5).map((item) => `#${item.index + 1} ${item.aweme_id} · ${item.capture_status}`);
  return {
    rows: preview,
    more: Math.max(0, state.harvest.queue_preview.length - preview.length)
  };
}

function stepStatusTone(status: WholeProfileHarvestStepStatus): WholeProfileHarvestCardTone {
  if (status === "done") return "success";
  if (status === "active" || status === "next") return "info";
  if (status === "warning") return "warning";
  if (status === "failed") return "error";
  return "neutral";
}

function friendlyMode(value: string | null): string {
  if (!value) return "Missing";
  if (value === "new_and_incomplete") return "New + incomplete";
  if (value === "new_only") return "New only";
  if (value === "refresh_all") return "Refresh all";
  return value.replaceAll("_", " ");
}

function friendlyBatch(value: string | null): string {
  if (!value) return "Missing";
  if (value === "next_5") return "Next 5";
  if (value === "next_10") return "Next 10";
  if (value === "next_20") return "Next 20";
  if (value === "all_remaining") return "All remaining";
  return value;
}

function friendlySpeed(value: string | null): string {
  if (!value) return "Missing";
  if (value === "safe") return "Safe";
  if (value === "normal") return "Normal";
  if (value === "fast") return "Fast";
  return value;
}

function friendlyBooleanStatus(value: string): string {
  if (value === "yes") return "Ready";
  if (value === "no") return "Missing";
  return value;
}

function shortId(value: string | null, size = 8): string | null {
  if (!value) return null;
  return value.length <= size ? value : value.slice(0, size);
}

function shortAweme(value: string | null): string {
  if (!value) return "—";
  if (value.length <= 15) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

function shortText(value: string | null, max = 28): string {
  if (!value) return "—";
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1)}…`;
}

function queueStatusForAweme(state: WholeProfileHarvestState, awemeId: string): string {
  const queueItem = state.harvest.queue.find((item) => item.aweme_id === awemeId);
  const result = state.harvest.results.find((item) => item.aweme_id === awemeId);
  if (result?.capture_inbox_item_id) return "flushed";
  if (result?.status === "extracted") return "extracted";
  if (result?.status === "failed") return "failed";
  if (queueItem?.status) return queueItem.status;
  return "pending";
}

function queueBadge(status: string): string {
  if (status === "new") return "NEW";
  if (status === "incomplete") return "INCOMPLETE";
  if (status === "complete") return "COMPLETE";
  if (status === "failed") return "FAILED";
  if (status === "skipped") return "SKIPPED";
  return "UNKNOWN";
}

export function getHarvestQueueAndResultsViewModel(state: WholeProfileHarvestState): WholeProfileHarvestQueueAndResultsViewModel {
  const visibleLimit = 5;
  const queueFullRows: WholeProfileHarvestQueuePreviewRow[] = state.harvest.queue_preview.map((item) => ({
    index: item.index + 1,
    aweme_id: item.aweme_id,
    aweme_short: shortAweme(item.aweme_id),
    capture_status: item.capture_status,
    queue_status: queueStatusForAweme(state, item.aweme_id),
    title_short: shortText(item.title),
    thumbnail_url: item.thumbnail_url,
    source_url: item.source_url,
    badge: queueBadge(item.capture_status)
  }));
  const extractionFullRows: WholeProfileHarvestExtractionResultRow[] = state.harvest.results.map((result) => ({
    index: result.index,
    aweme_short: shortAweme(result.aweme_id),
    status: result.status === "skipped" ? "pending" : result.status,
    duration_text: result.duration_text ?? "—",
    like_count: result.like_count,
    comment_count: result.comment_count,
    favorite_count: result.favorite_count,
    share_count: result.share_count,
    error_code: result.error_code ?? result.error ?? null
  }));
  const backendFullRows: WholeProfileHarvestBackendResultRow[] = state.harvest.results
    .filter((result) => result.backend_called || result.capture_inbox_item_id || result.status === "skipped" || result.backend_status != null || result.backend_error_code != null)
    .map((result) => ({
      index: result.index,
      aweme_short: shortAweme(result.aweme_id),
      status: result.capture_inbox_item_id
        ? "flushed"
        : result.status === "skipped"
          ? "skipped_complete"
          : result.backend_error_code || result.backend_status != null
            ? "failed"
            : "pending",
      item_id_short: shortId(result.capture_inbox_item_id, 10),
      metadata_status: result.capture_inbox_item_id ? "ready" : result.status === "skipped" ? "complete" : result.backend_status != null ? String(result.backend_status) : "pending",
      error_code: result.backend_error_code ?? result.error_code ?? result.error ?? null
    }));

  const diagnostics = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {};
  const queueTotal = typeof diagnostics.queue_total_persisted === "number" ? diagnostics.queue_total_persisted : Math.max(state.harvest.planned_total, queueFullRows.length);
  const queueVisible = typeof diagnostics.queue_total_visible === "number" ? diagnostics.queue_total_visible : queueFullRows.length;
  const expectedTotal = typeof diagnostics.scan_total_expected === "number" ? diagnostics.scan_total_expected : null;
  const foundTotal = typeof diagnostics.scan_total_found === "number" ? diagnostics.scan_total_found : state.verify.verified_target_count;
  const windowOffset = typeof diagnostics.queue_window_offset === "number" ? diagnostics.queue_window_offset : 0;
  const remainingTotal = Math.max(0, queueTotal - windowOffset - queueVisible);
  const largeProfileNote = diagnostics.large_profile_mode === "yes" ? `Large profile mode: showing first ${queueVisible} queued items.` : null;
  const degradedStorageNote = diagnostics.large_profile_storage_degraded === "yes"
    ? `Storage degraded: ${String(diagnostics.large_profile_storage_backend ?? "local")} fallback; durable persistence not guaranteed${typeof diagnostics.large_profile_storage_degraded_reason === "string" ? ` (${diagnostics.large_profile_storage_degraded_reason})` : ""}.`
    : null;

  return {
    queue_preview: {
      total: queueTotal,
      visible_limit: visibleLimit,
      remaining_count: Math.max(remainingTotal, Math.max(0, queueFullRows.length - visibleLimit)),
      rows: queueFullRows.slice(0, visibleLimit),
      full_rows: queueFullRows,
      subtitle: queueFullRows.length
        ? `${expectedTotal == null ? `Found ${foundTotal}` : `Found ${foundTotal} / Expected ${expectedTotal}`} · Queue total ${queueTotal} · Preview window ${queueVisible}${remainingTotal > 0 ? ` · Remaining ${remainingTotal}` : ""}${largeProfileNote ? ` · ${largeProfileNote}` : ""}${degradedStorageNote ? ` · ${degradedStorageNote}` : ""} · Mode: ${state.harvest_options.mode.replaceAll("_", " ")}`
        : state.verify.verified_target_count > 0
          ? "No eligible targets. Complete videos are skipped in New + incomplete mode."
          : "No videos queued yet. Scan Profile first.",
      empty_message: state.harvest.queue_preview.length === 0
        ? state.verify.verified_target_count > 0
          ? "No eligible targets. Complete videos are skipped in New + incomplete mode."
          : "No videos queued yet. Scan Profile first."
        : ""
    },
    extraction_results: {
      total: extractionFullRows.length,
      visible_limit: visibleLimit,
      remaining_count: Math.max(0, extractionFullRows.length - visibleLimit),
      rows: extractionFullRows.slice(-visibleLimit),
      full_rows: extractionFullRows,
      empty_message: "No metrics extracted yet. Run Extract Next 10 after a successful test."
    },
    backend_results: {
      total: backendFullRows.length,
      visible_limit: visibleLimit,
      remaining_count: Math.max(0, backendFullRows.length - visibleLimit),
      rows: backendFullRows.slice(-visibleLimit),
      full_rows: backendFullRows,
      summary: `Flushed ${state.harvest.backend.batch_flush.succeeded} · Failed ${state.harvest.backend.batch_flush.failed} · Skipped complete ${state.harvest.backend.batch_flush.skipped}`,
      empty_message: "No saved videos yet."
    }
  };
}

function firstGuardPaths(state: WholeProfileHarvestState): string[] {
  return state.harvest.backend.payload_preview.guard?.offending_paths.slice(0, 3) ?? [];
}

function backendActionSeverity(state: WholeProfileHarvestState): "info" | "success" | "warning" | "error" {
  if (state.harvest.backend.batch_flush.status === "running") return "warning";
  if (state.harvest.backend.payload_preview.guard && !state.harvest.backend.payload_preview.guard.ok) return "error";
  if (state.harvest.backend.one_item_flush.status === "failed" || state.harvest.backend.batch_flush.status === "failed") return "error";
  if (state.harvest.backend.batch_flush.status === "completed") return "success";
  return "info";
}

export function getBackendFlushFlowViewModel(
  state: WholeProfileHarvestState,
  readiness: WholeProfileHarvestReadiness = getWholeProfileHarvestReadiness(state),
  actions: WholeProfileHarvestActionState = getWholeProfileHarvestActionState(state)
): WholeProfileBackendFlowViewModel {
  const captureSession = state.harvest.backend.capture_session;
  const payloadPreview = state.harvest.backend.payload_preview;
  const oneItemFlush = state.harvest.backend.one_item_flush;
  const batchFlush = state.harvest.backend.batch_flush;
  const payloadGuard = payloadPreview.guard;
  const sessionStepStatus: WholeProfileBackendFlowStepView["status"] =
    captureSession.status === "ready" && captureSession.session_id ? "done"
      : captureSession.status === "creating" ? "active"
        : captureSession.status === "failed" ? "failed"
          : "todo";
  const payloadStepStatus: WholeProfileBackendFlowStepView["status"] =
    payloadPreview.status === "ready" && payloadGuard?.ok === true ? "done"
      : payloadPreview.status === "failed" || payloadPreview.status === "guard_failed" || payloadGuard?.ok === false ? "failed"
        : payloadPreview.status === "ready" ? "done"
          : "todo";
  const oneItemStatus: WholeProfileBackendFlowStepView["status"] =
    oneItemFlush.status === "succeeded" && oneItemFlush.capture_inbox_item_id ? "done"
      : oneItemFlush.status === "running" ? "active"
        : oneItemFlush.status === "failed" ? "failed"
          : "todo";
  const batchStatus: WholeProfileBackendFlowStepView["status"] =
    batchFlush.status === "running" ? "active"
      : batchFlush.status === "completed" ? "done"
        : batchFlush.status === "completed_with_warnings" ? "warning"
          : batchFlush.status === "failed" ? "failed"
            : "todo";

  let next_backend_action: WholeProfileBackendFlowViewModel["next_backend_action"];
  if (!readiness.extraction_ready) {
    next_backend_action = {
      key: "run_extraction",
      label: "Extract metrics first",
      reason: "Extract metrics first before saving to Capture Inbox.",
      severity: "info"
    };
  } else if (!readiness.backend_session_ready) {
    next_backend_action = {
      key: "prepare_backend_session",
      label: "Create Scan Session",
      reason: "Create a scan session. This prepares Capture Inbox but does not save any video yet.",
      severity: "info"
    };
  } else if (payloadGuard && !payloadGuard.ok) {
    next_backend_action = {
      key: "payload_guard_failed",
      label: "Data check failed",
      reason: "Some unsafe or missing fields were found before saving. Open Advanced Details to review them.",
      severity: "error"
    };
  } else if (!readiness.payload_preview_ready) {
    next_backend_action = {
      key: "build_payload_preview",
      label: "Data check",
      reason: "Check one extracted video before writing anything to Capture Inbox.",
      severity: "info"
    };
  } else if (oneItemFlush.status !== "succeeded") {
    next_backend_action = {
      key: "flush_one_item",
      label: "Save 1 Video",
      reason: "Test Capture Inbox write with one video before saving the whole batch.",
      severity: "info"
    };
  } else if (batchFlush.status === "running") {
    next_backend_action = {
      key: "flush_batch_running",
      label: "Save to Capture Inbox is running",
      reason: "Saving is in progress. Do not close the Douyin tab.",
      severity: "warning"
    };
  } else if (batchFlush.status === "completed") {
    next_backend_action = {
      key: "batch_flush_completed",
      label: "Batch saved",
      reason: "Batch saved. Open Capture Inbox to review items.",
      severity: "success"
    };
  } else {
    next_backend_action = {
      key: "flush_batch",
      label: "Save to Capture Inbox",
      reason: "Save extracted videos sequentially with progress checkpoints.",
      severity: backendActionSeverity(state)
    };
  }

  const compact_guard_rows: WholeProfileHarvestMetricRow[] = [
    { label: "Data Check", value: payloadGuard == null ? "idle" : payloadGuard.ok ? "Data check passed" : "Data check failed" },
    { label: "Required fields", value: payloadPreview.status === "missing_result" ? "missing 1" : "ok" },
    { label: "Disallowed fields", value: payloadGuard?.ok === false ? String(payloadGuard.offending_paths.length) : "none" },
    { label: "Evidence version", value: "phase11a_production_stabilized_calibrated_harvest" },
    { label: "Commit policy", value: "finalized_only" },
    { label: "Selected aweme", value: payloadPreview.target_aweme_id ?? "none" },
    ...firstGuardPaths(state).map((path, index) => ({ label: `Offending ${index + 1}`, value: path }))
  ];

  const flush_result_rows: WholeProfileHarvestMetricRow[] = [
    { label: "Item created/updated", value: oneItemFlush.item_created_or_updated == null ? "unknown" : oneItemFlush.item_created_or_updated ? "yes" : "no" },
    { label: "Item id", value: shortId(oneItemFlush.capture_inbox_item_id) ?? "none" },
    { label: "Verify", value: oneItemFlush.verify_status },
    { label: "Aweme", value: payloadPreview.target_aweme_id ?? "none" },
    { label: "Save batch", value: batchFlush.status },
    { label: "Current item", value: batchFlush.current_aweme_id ? `${batchFlush.current_index + 1}/${batchFlush.queue_total}` : "none" },
    { label: "Flushed / Failed / Skipped / Pending", value: `${batchFlush.succeeded} / ${batchFlush.failed} / ${batchFlush.skipped} / ${batchFlush.pending}` },
    { label: "Last checkpoint", value: state.harvest.last_checkpoint_at ?? "none" },
    { label: "Last success", value: state.harvest.last_success_at ?? "none" },
    { label: "Top failure", value: state.harvest.failure_summary?.top_failure_reasons[0] ? `${state.harvest.failure_summary.top_failure_reasons[0].code} x ${state.harvest.failure_summary.top_failure_reasons[0].count}` : "none" }
  ];

  const steps: WholeProfileBackendFlowStepView[] = [
    {
      key: "session",
      label: "Scan session",
      status: sessionStepStatus,
      summary: captureSession.session_id ? `ready: ${shortId(captureSession.session_id)}` : captureSession.status === "failed" ? "failed" : captureSession.status === "creating" ? "creating" : "missing",
      enabled: actions.prepareBackendSession.enabled,
      disabled_reason: actions.prepareBackendSession.disabledReason,
      action_label: "Create Scan Session"
    },
    {
      key: "payload",
      label: "Save data",
      status: payloadStepStatus,
      summary: payloadGuard?.ok === true ? "Data check passed" : payloadGuard?.ok === false ? "Data check failed" : payloadPreview.status === "failed" ? "failed" : payloadPreview.status === "missing_result" ? "missing" : "missing",
      enabled: actions.buildPayloadPreview.enabled,
      disabled_reason: actions.buildPayloadPreview.disabledReason,
      action_label: "Data check"
    },
    {
      key: "flush_one",
      label: "Save 1 Video",
      status: oneItemStatus,
      summary: oneItemFlush.capture_inbox_item_id ? `item ${shortId(oneItemFlush.capture_inbox_item_id)}` : oneItemFlush.status === "failed" ? "failed" : "not run",
      enabled: actions.flushOneItem.enabled,
      disabled_reason: actions.flushOneItem.disabledReason,
      action_label: "Save 1 Video"
    },
    {
      key: "flush_batch",
      label: "Save to Capture Inbox",
      status: batchStatus,
      summary: state.harvest.flushed > 0 ? `${state.harvest.flushed} saved` : actions.flushBatch.enabled ? "ready" : batchFlush.status === "failed" ? "failed" : "not started",
      enabled: actions.flushBatch.enabled,
      disabled_reason: actions.flushBatch.disabledReason,
      action_label: "Save to Capture Inbox"
    }
  ];

  return {
    steps,
    next_backend_action,
    summary: {
      capture_session_id_short: shortId(captureSession.session_id),
      payload_guard: payloadGuard == null ? "idle" : payloadGuard.ok ? "passed" : "failed",
      one_item_flush: oneItemFlush.status === "succeeded" ? "success" : oneItemFlush.status === "failed" ? "failed" : "idle",
      batch_flush: batchFlush.status,
      flushed: batchFlush.succeeded || state.harvest.flushed,
      failed: batchFlush.failed,
      pending: batchFlush.pending || Math.max(0, state.harvest.pending)
    },
    compact_guard_rows,
    flush_result_rows,
    details_rows: [
      { label: "Session request", value: captureSession.request_summary ? "available in Details" : "none" },
      { label: "Session response", value: captureSession.response_summary ? "available in Details" : "none" },
      { label: "Payload preview JSON", value: payloadPreview.payload ? "available in Details" : "none" },
      { label: "Payload guard full", value: payloadGuard ? "available in Details" : "none" },
      { label: "Last flush request", value: oneItemFlush.request_summary || state.harvest.last_payload_summary ? "available in Details" : "none" },
      { label: "Last flush response", value: oneItemFlush.response_summary || state.harvest.last_backend_response ? "available in Details" : "none" }
    ],
    capture_inbox_cta: oneItemFlush.status === "succeeded"
      ? "1 video saved to Capture Inbox."
      : batchFlush.status === "completed"
        ? "Open /selection/capture-inbox to review collected videos."
        : null
  };
}

function verifyStep(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): WholeProfileHarvestStepperItem {
  let status: WholeProfileHarvestStepStatus = "todo";
  if (readiness.profile_scan_ready) status = "done";
  else if (state.status === "verifying" || /verify|scan/.test(state.phase)) status = "active";
  else if (state.profile_scan.status === "failed" || state.verify.status === "failed") status = "failed";
  const count = state.verify.verified_target_count || state.profile_scan.accepted_target_count;
  return {
    key: "verify",
    label: "Scan Profile",
    status,
    summary: readiness.profile_scan_ready ? `${profileCountLabel(state, count)} videos found` : status === "failed" && count > 0 ? `Incomplete: ${profileCountLabel(state, count)} videos` : status === "failed" ? "Scan failed" : "Not scanned",
    action_label: "Scan Profile"
  };
}

function dryRunStep(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): WholeProfileHarvestStepperItem {
  let status: WholeProfileHarvestStepStatus = "todo";
  if (readiness.dry_run_ready) status = state.dry_run.status === "completed_with_warnings" ? "warning" : "done";
  else if (state.status === "dry_running") status = "active";
  else if (state.dry_run.status === "failed") status = "failed";
  else if (readiness.profile_scan_ready && readiness.calibration_ready) status = "next";
  else if (readiness.profile_scan_ready) status = "locked";
  return {
    key: "dry_run",
    label: "Test",
    status,
    summary: state.dry_run.pass > 0 || state.dry_run.fail > 0 ? `${state.dry_run.pass} passed / ${state.dry_run.fail} failed` : readiness.profile_scan_ready ? "Not tested" : "Recommended",
    action_label: "Test 3 Videos"
  };
}

function extractionStep(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): WholeProfileHarvestStepperItem {
  const extracted = state.harvest.results.filter((result) => result.status === "extracted").length;
  let status: WholeProfileHarvestStepStatus = "todo";
  if (state.harvest.status === "running") status = "active";
  else if (extracted > 0 && state.harvest.failed > 0) status = "warning";
  else if (state.harvest.status === "failed") status = "failed";
  else if (extracted > 0 && (state.harvest.pending === 0 || state.harvest.status === "completed")) status = "done";
  else if (extracted > 0) status = "active";
  else if (readiness.extraction_ready) status = "next";
  else if (readiness.profile_scan_ready) status = "locked";
  return {
    key: "extract",
    label: "Extract",
    status,
    summary: extracted > 0 ? `${extracted} extracted / ${state.harvest.planned_total || state.harvest.queue_preview.length} planned` : readiness.dry_run_ready ? `0 / ${state.harvest.planned_total || state.harvest.queue_preview.length || 0}` : "Not extracted",
    action_label: "Extract Next 10"
  };
}

function flushStep(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): WholeProfileHarvestStepperItem {
  const batchStatus = state.harvest.backend.batch_flush.status;
  const oneItemStatus = state.harvest.backend.one_item_flush.status;
  let status: WholeProfileHarvestStepStatus = "todo";
  if (batchStatus === "running" || oneItemStatus === "running") status = "active";
  else if (batchStatus === "completed_with_warnings") status = "warning";
  else if (batchStatus === "failed" || oneItemStatus === "failed") status = "failed";
  else if (batchStatus === "completed" || (oneItemStatus === "succeeded" && !readiness.batch_flush_ready)) status = "done";
  else if (state.harvest.results.some((result) => result.status === "extracted")) status = "next";
  else if (readiness.profile_scan_ready) status = "locked";
  return {
    key: "flush",
    label: "Save",
    status,
    summary: state.harvest.flushed > 0
      ? `${state.harvest.flushed} saved`
      : readiness.extraction_ready
        ? readiness.backend_session_ready
          ? readiness.payload_preview_ready && readiness.payload_guard_passed
            ? "Ready to save"
            : "Save data check needed"
          : "Save session missing"
        : "Not saved",
    action_label: "Save to Capture Inbox"
  };
}

function actionSeverity(state: WholeProfileHarvestState, readiness: WholeProfileHarvestReadiness): "info" | "success" | "warning" | "error" {
  if (state.harvest.paused_reason === "captcha_detected") return "warning";
  if (state.last_error) return "error";
  if (readiness.next_recommended_action.code === "review_results" || readiness.next_recommended_action.code === "none") return "success";
  return "info";
}

export function getRunTabViewModel(
  state: WholeProfileHarvestState,
  readiness: WholeProfileHarvestReadiness,
  actionState: WholeProfileHarvestActionState
): WholeProfileRunTabViewModel {
  const normalizedView = normalizeScannerViewState(state);
  const viewState = normalizedView.state;
  const operatorStatus = getOperatorStatusMessage(viewState);
  const runSummary = buildRunSummary(viewState);
  const recentItemResults = buildRecentItemResults(viewState);
  const stepper = [
    verifyStep(viewState, readiness),
    dryRunStep(viewState, readiness),
    extractionStep(viewState, readiness),
    flushStep(viewState, readiness)
  ] as const;
  const videosFound = viewState.verify.verified_target_count || viewState.profile_scan.accepted_target_count;
  const extracted = viewState.harvest.results.filter((result) => result.status === "extracted").length;
  const saved = viewState.harvest.results.filter((result) => result.capture_inbox_item_id).length;
  const pending = viewState.harvest.queue_preview.length || Math.max(0, viewState.harvest.planned_total - viewState.harvest.updated - viewState.harvest.failed);
  const canonicalPrimaryAction = getCanonicalScannerPrimaryAction(viewState);
  const runTabPrimaryLabel = canonicalPrimaryAction.key === "start_collecting"
    ? `Extract ${friendlyBatchLabel(viewState.harvest_options.batch)}`
    : canonicalPrimaryAction.label;
  const primaryAction = {
    key: canonicalPrimaryAction.key,
    label: runTabPrimaryLabel,
    enabled: canonicalPrimaryAction.enabled,
    tone: canonicalPrimaryAction.key === "open_capture_inbox" ? "warning" : "primary",
    reason: canonicalPrimaryAction.description
  } satisfies NonNullable<WholeProfileRunTabViewModel["primary_action"]>;

  const runTabDiagnostics = (viewState.profile_scan.diagnostics && typeof viewState.profile_scan.diagnostics === "object"
    ? viewState.profile_scan.diagnostics
    : viewState.verify.diagnostics && typeof viewState.verify.diagnostics === "object"
      ? viewState.verify.diagnostics
      : {}) as Record<string, unknown>;
  const runTabVisibleProfileCount = typeof runTabDiagnostics.displayed_profile_count === "number"
    ? runTabDiagnostics.displayed_profile_count
    : typeof runTabDiagnostics.displayed_profile_count === "string" && runTabDiagnostics.displayed_profile_count.trim()
      ? Number(runTabDiagnostics.displayed_profile_count)
      : null;
  const runTabApiCollectableCount = typeof runTabDiagnostics.collectable_count === "number"
    ? runTabDiagnostics.collectable_count
    : typeof runTabDiagnostics.collectable_count === "string" && runTabDiagnostics.collectable_count.trim()
      ? Number(runTabDiagnostics.collectable_count)
      : null;
  const runTabAdditionalSameProfileVideos = typeof runTabDiagnostics.over_displayed_count === "number"
    ? runTabDiagnostics.over_displayed_count
    : typeof runTabDiagnostics.over_displayed_count === "string" && runTabDiagnostics.over_displayed_count.trim()
      ? Number(runTabDiagnostics.over_displayed_count)
      : null;

  let alert: WholeProfileRunTabViewModel["alert"] = null;
  if (unresolvedOvercollectionReviewActive(viewState, runTabDiagnostics) || canonicalPrimaryAction.key === "review_overcollection") {
    const reviewPresentation = buildOvercollectionReviewPresentation(runTabDiagnostics);
    alert = {
      tone: "warning",
      title: reviewPresentation.title,
      message: reviewPresentation.description,
      technical_hint: null
    };
  } else if (String(runTabDiagnostics.count_semantics_status ?? "") === "completed_with_api_over_displayed_count") {
    alert = {
      tone: "warning",
      title: "API returned additional same-profile videos",
      message: `API returned ${runTabAdditionalSameProfileVideos ?? "additional"} additional same-profile videos beyond visible profile count. Visible profile count: ${runTabVisibleProfileCount ?? "unknown"}. API collectable count: ${runTabApiCollectableCount ?? "unknown"}. Additional same-profile API videos: ${runTabAdditionalSameProfileVideos ?? "unknown"}.`,
      technical_hint: null
    };
  } else if (viewState.safety.safety_user_action_required || viewState.safety.captcha_detected) {
    alert = {
      tone: "warning",
      title: "Attention needed",
      message: operatorStatus.message,
      technical_hint: viewState.safety.safety_reason ?? operatorStatus.next_step
    };
  } else if (viewState.safety.safety_status === "stale" || viewState.safety.safety_status === "blocked") {
    alert = {
      tone: "warning",
      title: "Reconnect Douyin tab",
      message: operatorStatus.message,
      technical_hint: viewState.safety.safety_reason ?? operatorStatus.next_step
    };
  } else if (viewState.status === "paused" || viewState.harvest.status === "paused") {
    alert = {
      tone: "warning",
      title: "Paused safely",
      message: operatorStatus.message,
      technical_hint: operatorStatus.next_step
    };
  } else if (viewState.harvest.backend.batch_flush.status === "failed" || viewState.harvest.backend.one_item_flush.status === "failed") {
    alert = {
      tone: "error",
      title: "Save failed",
      message: operatorStatus.message,
      technical_hint: viewState.harvest.backend.batch_flush.last_error_message ?? operatorStatus.next_step
    };
  } else if (!isCollectCalibrationSatisfied(viewState) && viewState.calibration.status !== "calibrated" && viewState.calibration.point_count < 4) {
    alert = {
      tone: "info",
      title: "Calibration needed",
      message: "Click the four metric points before testing videos.",
      technical_hint: null
    };
  }

  return {
    status_chips: [
      { label: "Calibration", value: readiness.calibration_ready ? "Ready" : "Needed", tone: readiness.calibration_ready ? "success" : "locked" },
      { label: "Profile", value: readiness.profile_scan_ready ? "Scanned" : "Not scanned", tone: readiness.profile_scan_ready ? "success" : "locked" },
      {
        label: "Safety",
        value: state.safety.safety_status === "safe" ? "Normal" : alert ? (alert.title === "Reconnect Douyin tab" ? "Reconnect" : "Check") : state.safety.safety_status,
        tone: alert ? (alert.tone === "error" ? "error" : "warning") : "success"
      }
    ],
    mini_stepper: [
      { key: "scan", label: "Scan", status: stepper[0].status },
      { key: "test", label: "Test", status: stepper[1].status },
      { key: "extract", label: "Extract", status: stepper[2].status },
      { key: "save", label: "Save", status: stepper[3].status }
    ],
    primary_action: primaryAction,
    secondary_actions: [
      { key: "scan_profile", label: readiness.profile_scan_ready ? "Rescan" : "Scan Profile", enabled: actionState.verifyProfile.enabled },
      { key: "test_3_videos", label: "Test 3 Videos", enabled: actionState.dryRunRandom.enabled },
      { key: "reset", label: "Reset", enabled: actionState.resetHarvest.enabled }
    ],
    settings: {
      mode: viewState.harvest_options.mode,
      batch: viewState.harvest_options.batch,
      speed: viewState.harvest_options.speed,
      unattended_safe_mode: viewState.harvest_options.unattended_safe_mode,
      mode_label: friendlyModeLabel(viewState.harvest_options.mode),
      batch_label: friendlyBatchLabel(viewState.harvest_options.batch),
      speed_label: friendlySpeedLabel(viewState.harvest_options.speed)
    },
    compact_metrics: {
      videos_found: videosFound,
      tested: `${viewState.dry_run.pass}/${viewState.dry_run.fail}`,
      extracted,
      saved,
      pending
    },
    save_next: {
      visible: extracted > 0,
      label: extracted > 0 ? (readiness.next_recommended_action.code === "prepare_backend_session" || readiness.next_recommended_action.code === "build_payload_preview" || readiness.next_recommended_action.code === "flush_one_item" || readiness.next_recommended_action.code === "flush_batch" ? readiness.next_recommended_action.label : PRODUCT_TERMS.saveToCaptureInbox) : null,
      reason: extracted > 0 ? (readiness.next_recommended_action.code === "prepare_backend_session" || readiness.next_recommended_action.code === "build_payload_preview" || readiness.next_recommended_action.code === "flush_one_item" || readiness.next_recommended_action.code === "flush_batch" ? readiness.next_recommended_action.reason : "Saving unlocks after extraction has results.") : null
    },
    alert,
    workflow_hint: readiness.profile_scan_ready ? null : "Workflow: Scan -> Test -> Extract -> Save",
    operator_status: {
      message: operatorStatus.message,
      level: operatorStatus.level,
      next_step: operatorStatus.next_step
    },
    run_summary: runSummary,
    recent_item_results: recentItemResults,
    shortcuts: {
      results_visible: videosFound > 0 || viewState.harvest.results.length > 0,
      technical_visible: Boolean(viewState.last_error || alert || viewState.harvest.backend.payload_preview.guard?.ok === false || normalizedView.diagnostics.impossible_state_detected)
    }
  };
}

export type ActionDeckViewModel = {
  health: {
    tab: { label: string; value: string; tone: "success" | "warning" | "danger" | "neutral" };
    api: { label: string; value: string; tone: "success" | "warning" | "danger" | "neutral" };
    calibration: { label: string; value: string; tone: "success" | "warning" | "danger" | "neutral" };
    safety: { label: string; value: string; tone: "success" | "warning" | "danger" | "neutral" };
  };
  currentStep: {
    index: number;
    total: number;
    key: string;
    title: string;
    description: string;
    primaryActionKey: string;
    primaryActionLabel: string;
    primaryEnabled: boolean;
    disabledReason: string | null;
  };
  steps: Array<{ key: string; label: string; status: WholeProfileHarvestStepStatus }>;
  settings: {
    mode: WholeProfileHarvestMode;
    batch: WholeProfileHarvestBatch;
    speed: WholeProfileHarvestSpeed;
  };
  kpis: {
    videos: number;
    testedPass: number;
    testedFail: number;
    extracted: number;
    saved: number;
    pending: number;
  };
  alert: { tone: "warning" | "error" | "info"; title: string; message: string } | null;
};

export function getActionDeckViewModel(state: WholeProfileHarvestState): ActionDeckViewModel {
  const readiness = getWholeProfileHarvestReadiness(state);

  const stepper = [
    verifyStep(state, readiness),
    dryRunStep(state, readiness),
    extractionStep(state, readiness),
    flushStep(state, readiness)
  ] as const;

  const steps = [
    { key: "scan", label: "Scan", status: stepper[0].status },
    { key: "test", label: "Test", status: stepper[1].status },
    { key: "extract", label: "Extract", status: stepper[2].status },
    { key: "save", label: "Save", status: stepper[3].status }
  ];

  const currentStepIndex = steps.findIndex((s) => s.status === "next" || s.status === "active");
  const activeIndex = currentStepIndex >= 0 ? currentStepIndex : 0;

  const canonicalPrimaryAction = getCanonicalScannerPrimaryAction(state);
  const runnerLock = deriveAuthoritativeRunnerLock(state);
  const canonicalUiState = String(runnerLock.diagnostics.trace_ui_canonical_state ?? "idle");
  const waitingForActiveTab = canonicalUiState === "waiting_for_active_tab";
  const pausedTabInactive = canonicalUiState === "paused_tab_inactive";
  const paused = state.status === "paused" || state.harvest.status === "paused";

  const currentStepKey = canonicalPrimaryAction.key === "scan_profile" || canonicalPrimaryAction.key === "calibrate"
    ? "scan"
    : canonicalPrimaryAction.key === "start_collecting" || canonicalPrimaryAction.key === "pause" || canonicalPrimaryAction.key === "resume"
      ? "extract"
      : canonicalPrimaryAction.key === "open_capture_inbox"
        ? "save"
        : (steps[activeIndex]?.key ?? "scan");

  const currentStepTitle = steps.find((s) => s.key === currentStepKey)?.label ?? "Scan";

  const tabHealth = state.safety.tab_health.status === "content_script_missing" || state.safety.tab_health.status === "detector_failed"
    ? { label: "Tab" as const, value: "Check", tone: "warning" as const }
    : state.page_context.page_type === "profile"
      ? { label: "Tab" as const, value: "Profile", tone: "success" as const }
      : state.page_context.page_type === "modal"
        ? { label: "Tab" as const, value: "Modal", tone: "success" as const }
        : { label: "Tab" as const, value: "Other", tone: "neutral" as const };

  const scanDiagnostics = scanDiagnosticsRecord(state);
  const apiPaginationAttempted = scanApiPaginationAttempted22C14N(state, scanDiagnostics);
  const apiHealth = state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed"
    ? { label: "API" as const, value: "Error", tone: "danger" as const }
    : state.harvest.backend.capture_session.status === "ready" || apiPaginationAttempted
      ? { label: "API" as const, value: apiPaginationAttempted ? "Fetched" : "Ready", tone: "success" as const }
      : state.last_error && typeof state.last_error === "string" && (state.last_error.includes("backend") || state.last_error.includes("timeout"))
        ? { label: "API" as const, value: "Issue", tone: "warning" as const }
        : { label: "API" as const, value: "Idle", tone: "neutral" as const };

  const calibrationHealth = readiness.calibration_ready
    ? { label: "Calib" as const, value: "Ready", tone: "success" as const }
    : state.calibration.point_count > 0
      ? { label: "Calib" as const, value: `${state.calibration.point_count}/4`, tone: "warning" as const }
      : { label: "Calib" as const, value: "Needed", tone: "warning" as const };

  const safetyHealth = state.safety.captcha_detected
    ? { label: "Safety" as const, value: "Captcha", tone: "warning" as const }
    : state.safety.consecutive_errors > 0
      ? { label: "Safety" as const, value: "Caution", tone: "warning" as const }
      : paused || waitingForActiveTab || pausedTabInactive
        ? { label: "Safety" as const, value: "Paused", tone: "warning" as const }
        : { label: "Safety" as const, value: "Normal", tone: "success" as const };

  let alert: ActionDeckViewModel["alert"] = null;
  if (unresolvedOvercollectionReviewActive(state, scanDiagnostics) || canonicalPrimaryAction.key === "review_overcollection") {
    const reviewPresentation = buildOvercollectionReviewPresentation(scanDiagnosticsRecord(state));
    alert = { tone: "warning", title: reviewPresentation.title, message: reviewPresentation.description };
  } else if (String(scanDiagnosticsRecord(state).count_semantics_status ?? "") === "completed_with_api_over_displayed_count") {
    const diagnostics = scanDiagnosticsRecord(state);
    const visibleProfileCount = numericDiagnosticValue(diagnostics.displayed_profile_count);
    const apiCollectableCount = numericDiagnosticValue(diagnostics.collectable_count);
    const additionalSameProfileVideos = numericDiagnosticValue(diagnostics.over_displayed_count);
    alert = {
      tone: "warning",
      title: "API returned additional same-profile videos",
      message: `API returned ${additionalSameProfileVideos ?? "additional"} additional same-profile videos beyond visible profile count. Visible profile count: ${visibleProfileCount ?? "unknown"}. API collectable count: ${apiCollectableCount ?? "unknown"}. Additional same-profile API videos: ${additionalSameProfileVideos ?? "unknown"}.`
    };
  } else if (state.safety.captcha_detected) {
    alert = { tone: "warning", title: "Security check detected", message: "Solve it in the Douyin tab, then click Resume." };
  } else if (state.harvest.paused_reason === "backend_auth_required" || (state.harvest.paused_reason === "douyin_login_required" && state.harvest.pause_diagnostics && typeof state.harvest.pause_diagnostics === "object" && (state.harvest.pause_diagnostics as Record<string, unknown>).source === "hybrid_flush")) {
    alert = { tone: "warning", title: "Backend login required", message: state.harvest.pause_message ?? "Sign in to the app again in extension settings, then press Resume." };
  } else if (waitingForActiveTab) {
    alert = { tone: "warning", title: "Waiting for tab", message: state.harvest.pause_message ?? "Return to the Douyin tab to continue collecting." };
  } else if (pausedTabInactive || paused) {
    alert = { tone: "warning", title: "Collecting paused", message: state.harvest.pause_message ?? "Resume when the Douyin tab is ready again." };
  } else if (state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed") {
    alert = { tone: "error", title: "Save failed", message: "Open Advanced for save details before retrying." };
  } else if (!isCollectCalibrationSatisfied(state) && state.calibration.status !== "calibrated" && state.calibration.point_count < 4) {
    alert = { tone: "info", title: "Calibration needed", message: "Click the four metric points before testing videos." };
  }

  const videosFound = profileCount(state);
  const extracted = extractedCount(state);
  const saved = savedCount(state);
  const pending = pendingCount(state);

  return {
    health: { tab: tabHealth, api: apiHealth, calibration: calibrationHealth, safety: safetyHealth },
    currentStep: {
      index: activeIndex,
      total: 4,
      key: currentStepKey,
      title: currentStepTitle,
      description: canonicalPrimaryAction.description,
      primaryActionKey: canonicalPrimaryAction.key,
      primaryActionLabel: canonicalPrimaryAction.label,
      primaryEnabled: canonicalPrimaryAction.enabled,
      disabledReason: canonicalPrimaryAction.enabled ? null : canonicalPrimaryAction.disabledReason
    },
    steps,
    settings: {
      mode: state.harvest_options.mode,
      batch: state.harvest_options.batch,
      speed: state.harvest_options.speed
    },
    kpis: {
      videos: videosFound,
      testedPass: state.dry_run.pass,
      testedFail: state.dry_run.fail,
      extracted,
      saved,
      pending
    },
    alert
  };
}

const HYBRID_COLLECT_HEARTBEAT_STALE_MS = 30_000;

export function collectJobHeartbeatAgeMs(state: WholeProfileHarvestState, nowMs = Date.now()): number | null {
  const heartbeatAt = state.collect_job.heartbeat_at ?? state.collect_job.updated_at;
  const parsed = typeof heartbeatAt === "string" ? Date.parse(heartbeatAt) : Number.NaN;
  return Number.isFinite(parsed) ? Math.max(0, nowMs - parsed) : null;
}

export function isHybridLoopCollectStep(step: string): boolean {
  return step.startsWith("hybrid_loop_") || step.startsWith("hybrid_runner_");
}

export function hybridCollectRunnerLikelyStale(state: WholeProfileHarvestState, nowMs = Date.now()): boolean {
  const step = String(state.collect_job.current_step ?? "");
  if (!isHybridLoopCollectStep(step)) return false;
  if (["completed", "failed", "stuck", "aborted_by_user_fix_stuck"].includes(state.collect_job.state)) return false;
  const ageMs = collectJobHeartbeatAgeMs(state, nowMs);
  return ageMs === null || ageMs > HYBRID_COLLECT_HEARTBEAT_STALE_MS;
}

export function isCollectJobVisiblyLive(state: WholeProfileHarvestState, nowMs = Date.now()): boolean {
  if (isHybridTailGapAuthorityLocked(state)) return false;
  if (isHybridNetworkCacheModeEnabledForCollect(state)) {
    return isHybridCollectJobLiveForPresentation(state, nowMs);
  }
  const harvestPausedForAuthOrSafety = state.harvest.status === "paused"
    || state.harvest.paused_reason === "backend_auth_required"
    || state.harvest.paused_reason === "douyin_login_required";
  const collectJobTerminal = state.collect_job.state === "completed"
    || state.collect_job.state === "failed"
    || state.collect_job.state === "stuck"
    || state.collect_job.state === "aborted_by_user_fix_stuck";
  if (harvestPausedForAuthOrSafety || collectJobTerminal || hybridCollectRunnerLikelyStale(state, nowMs)) {
    return false;
  }
  const collectJobLive = state.collect_job.state === "running"
    || state.collect_job.state === "starting"
    || state.collect_job.state === "running_tab_inactive";
  const liveStep = String(state.collect_job.current_step ?? "");
  const liveAttempted = typeof state.collect_job.attempted_count === "number" && Number.isFinite(state.collect_job.attempted_count)
    ? Math.max(0, state.collect_job.attempted_count)
    : 0;
  const liveSucceeded = typeof state.collect_job.succeeded_count === "number" && Number.isFinite(state.collect_job.succeeded_count)
    ? Math.max(0, state.collect_job.succeeded_count)
    : 0;
  const collecting = (state.workflow.collection.status === "running" || state.workflow.collection.status === "opening_target")
    && state.workflow.active_task === "collect_videos";
  if (state.collect_job.state === "starting" && !harvestPausedForAuthOrSafety && !collectJobTerminal) {
    const startCollectBlocked = state.phase === "blocked"
      || state.debug.last_action_result === "blocked"
      || state.workflow.collection.status === "failed";
    if (startCollectBlocked) return false;
    return true;
  }
  return collecting || (collectJobLive && (liveAttempted > 0 || liveSucceeded > 0 || liveStep.startsWith("hybrid_loop_") || liveStep.startsWith("hybrid_runner_") || liveStep === "hybrid_unattended_chain_continue"));
}

function snapshotDisprovesLocalCollected(state: WholeProfileHarvestState): boolean {
  return staleLocalCollectedDisprovenByBackendEmpty(state);
}

function getScannerControlPanelViewModelUnreconciled(state: WholeProfileHarvestState): ScannerControlPanelViewModel {
  const readiness = getWholeProfileHarvestReadiness(state);
  const workflowReadiness = getDouyinScannerWorkflowReadiness(state);
  const canonicalPrimaryAction = getCanonicalScannerPrimaryAction(state);
  const runnerLock = deriveAuthoritativeRunnerLock(state);
  const nearCompleteAllowed = popupNearCompleteWarning(state).applied;
  const canonicalUiState = String(runnerLock.diagnostics.trace_ui_canonical_state ?? "idle");
  const scanAuthority = scanDisplayAuthority22C14B(state);
  const scanProgress = activeScanProgress22C14G(state);
  const largeProfilePersistedTotal = scanAuthority.display_mode === "persisted_history_authority" || scanProgress.active ? null : largeProfilePersistedQueueTotal(state);
  const videosFound = scanProgress.active
    ? scanProgress.discovered
    : scanAuthority.display_mode === "persisted_history_authority"
      ? scanAuthority.current_run_found_count
      : profileCount(state);
  const scanDiagnostics = scanDiagnosticsRecord(state);
  const countSemanticsStatus = String(scanDiagnostics.count_semantics_status ?? "");
  const countSemanticsDisplayedMismatch = countSemanticsStatus === "completed_with_displayed_count_mismatch" || countSemanticsStatus === "completed_with_partial_secondary_recovery";
  const countSemanticsOverDisplayedReady = countSemanticsStatus === "completed_with_api_over_displayed_count";
  const countSemanticsOverDisplayedNeedsValidation = countSemanticsStatus === "overcollected_needs_validation";
  const collectableCount = numericDiagnosticValue(scanDiagnostics.collectable_count) ?? videosFound;
  const finalCumulativeCollectableCount = numericDiagnosticValue(scanDiagnostics.final_cumulative_collectable_count) ?? collectableCount;
  const finalDisplayAuthority = String(scanDiagnostics.final_display_authority ?? "");
  const displayedProfileCount = numericDiagnosticValue(scanDiagnostics.displayed_profile_count) ?? expectedProfileVideoCount(state) ?? state.scan_job.expected_count;
  const unavailableOrUnlistedCount = numericDiagnosticValue(scanDiagnostics.unavailable_or_unlisted_count) ?? (displayedProfileCount == null ? null : Math.max(displayedProfileCount - finalCumulativeCollectableCount, 0));
  const overDisplayedCount = numericDiagnosticValue(scanDiagnostics.over_displayed_count) ?? (displayedProfileCount == null ? null : Math.max(finalCumulativeCollectableCount - displayedProfileCount, 0));
  const labeledCollectableCount = finalDisplayAuthority === "cumulative_persisted_count" ? finalCumulativeCollectableCount : collectableCount;
  const collectSnapshot = state.post_scan_counter_snapshot;
  const hybridCollectorCompleted = collectCompletionOverridesActiveCollectRuntime(state);
  const popupProfileVideoTotal = resolveScannedTotalFromState(state);
  const videosFoundLabel = collectSnapshot?.status === "applied" && (hybridCollectorCompleted || collectSnapshot.already_collected > 0)
    ? `${collectSnapshot.already_collected} / ${popupProfileVideoTotal}`
    : countSemanticsDisplayedMismatch || countSemanticsOverDisplayedReady
    ? String(popupProfileVideoTotal)
    : countSemanticsOverDisplayedNeedsValidation
      ? `${collectableCount} needs review`
      : scanProgress.expected != null
        ? `${videosFound} / ${scanProgress.expected}`
        : profileCountLabel(state, videosFound);
  const profileScanned = workflowReadiness.profileScanReady;
  const expectedCount = displayedProfileCount;
  const completedWithWarningReady = profileScanned && String(scanDiagnostics.scan_finalization_result ?? "") === "completed_with_warning";
  const expectedCountSemanticsMismatch = completedWithWarningReady && (countSemanticsDisplayedMismatch || String(scanDiagnostics.final_gap_reason ?? "") === "expected_count_semantics_mismatch");
  const scanBudgetContinuation = !scanProgress.active && scanBudgetContinuationAvailable(state);
  const scanIncomplete = scanIncompleteUnderExpectedForPresentation(state, state.page_context.current_url ?? null)
    || (!hybridCollectorCompleted && !scanBudgetContinuation && !scanProgress.active && expectedCount != null && videosFound > 0 && videosFound < expectedCount && !nearCompleteAllowed && !completedWithWarningReady);
  const warningMissingCount = completedWithWarningReady && expectedCount != null ? Math.max(expectedCount - labeledCollectableCount, 0) : null;
  const missingCount = scanIncomplete && expectedCount != null ? Math.max(expectedCount - videosFound, 0) : null;
  const scanDataVisible = profileScanned || profileScanDetected(state, videosFound);
  const calibrationReady = isCollectCalibrationSatisfied(state);
  const collectedCount = extractedCount(state);
  const saved = savedCount(state);
  const queueCounters = deriveCollectionCountersFromQueue(state);
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const popupMetricsAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
  const queueCount = popupMetricsAuthoritative ? popupMetrics.profile.queue_count : largeProfilePersistedTotal ?? queueCounters.queueCount;
  const newCountForEmptyState = popupMetricsAuthoritative ? popupMetrics.profile.new_count : queueCounters.newCount;
  const actionableCollectTiles = queueCount + newCountForEmptyState + queueCounters.incompleteCount + queueCounters.failedCount;
  const overcollectionReviewPresentation = canonicalPrimaryAction.key === "review_overcollection"
    ? buildOvercollectionReviewPresentation(scanDiagnostics)
    : null;
  const scannerBusy = getDouyinScannerBusyState(state);
  const running = scannerBusy.isBusy;
  const scanning = running && scannerBusy.busySource === "scan.status";
  const classifying = running && scannerBusy.busySource === "classification.status";
  const pausing = state.workflow.collection.status === "pausing" && (state.workflow.active_task === "collect_videos" || state.workflow.action_lock === "collect_videos");
  const waitingForActiveTab = canonicalUiState === "waiting_for_active_tab";
  const pausedTabInactive = canonicalUiState === "paused_tab_inactive";
  const collectActive = canonicalUiState === "running" || waitingForActiveTab || pausedTabInactive;
  const openingTarget = collectActive && state.workflow.collection.status === "opening_target";
  const collecting = collectActive && !openingTarget;
  const paused = !collectActive && state.harvest.resume_available === true && (state.workflow.collection.status === "paused" || (state.workflow.collection.status === "pausing" && !pausing && state.harvest.pause_requested === true));
  const liveCollecting = isCollectJobVisiblyLive(state);
  const livePresentation = liveCollecting && isHybridNetworkCacheModeEnabledForCollect(state)
    ? buildCollectLiveProgressPresentation(state)
    : null;
  const collectingHeader = livePresentation?.headerLabel ?? "Collecting";
  const headerStatus = scanProgress.active
    ? formatActiveScanProgressHeader(scanProgress)
    : scanning
    ? "Scanning"
    : classifying
      ? "Classifying"
      : pausing
        ? "Pausing..."
        : openingTarget
          ? "Opening first video"
          : waitingForActiveTab
            ? "Waiting for tab"
            : pausedTabInactive || paused
              ? "Paused"
              : livePresentation
                ? collectingHeader
                : profileScanned || scanIncomplete || nearCompleteAllowed
                  ? `${videosFoundLabel} videos`
                  : "Ready";
  const apiHealth = backendApiHealth(state);
  const safety: ScannerControlPanelViewModel["health"]["safety"] = pausing || paused || waitingForActiveTab || pausedTabInactive
    ? "Paused"
    : state.safety.captcha_detected || state.safety.consecutive_errors > 0
      ? "Check"
      : "Safe";

  const batchContinuation = canonicalPrimaryAction.key === "start_collecting" && batchContinuationAvailable(state, queueCount);
  const scanContinuation = canonicalPrimaryAction.key === "scan_profile" && scanBudgetContinuation;
  const continuationMessage = scanContinuation
    ? scanBudgetContinuationMessage(state, videosFound, expectedCount)
    : batchContinuation
      ? batchContinuationMessage(state, saved, queueCount)
      : null;
  const actionLabel = scanContinuation
    ? "Continue Scan"
    : batchContinuation
      ? batchContinuationButtonLabel(state)
      : canonicalPrimaryAction.label;
  const actionDescription = continuationMessage ?? canonicalPrimaryAction.description;
  const metricsPlan = buildHybridMetricsPlan(state);
  const metricsPlanMessage = !liveCollecting && metricsPlan
    ? (metricsPlan.skippedUncollectable > 0 && queueCount <= 0
      ? `${metricsPlan.collected} collected · ${metricsPlan.skippedUncollectable} skipped (no metrics)`
      : metricsPlan.collected === 0 && metricsPlan.discovered > 0 && !hybridLastRunWasMetricsMiss(state)
        ? `${metricsPlan.discovered} videos ready to collect (up to 500 per click).`
        : metricsPlan.collected > 0 && metricsPlan.discovered > metricsPlan.collected
          ? null
          : metricsPlan.metricsReady > 0 && metricsPlan.metricsMissing > 0 && queueCount > 0
            ? `${metricsPlan.collected} collected · ${metricsPlan.metricsReady} ready · ${metricsPlan.metricsMissing} need metrics`
            : null)
    : null;
  const collectProgress: ScannerControlPanelViewModel["collectProgress"] = livePresentation
    ? {
      active: true,
      profileAlready: livePresentation.profileNumerator,
      profileTotal: livePresentation.profileTotal,
      profilePercent: livePresentation.profilePercent,
      profileTargetNumerator: livePresentation.profileTargetNumerator,
      profileIndeterminate: livePresentation.profileIndeterminate,
      tilesAlreadyTarget: livePresentation.tilesAlreadyTarget,
      priorAlreadyBaseline: livePresentation.priorAlready,
      batchAttempted: livePresentation.batchAttempted,
      batchTotal: livePresentation.batchTotal,
      batchReady: livePresentation.readyCount,
      batchNeedData: livePresentation.skippedCount,
      batchPercent: livePresentation.batchPercent,
      phase: livePresentation.phase,
      showBatchCard: livePresentation.showBatchCard
    }
    : null;

  const action: ScannerControlPanelViewModel["action"] = scanProgress.active
    ? {
      key: "scan_profile",
      title: scanProgressPhaseIsFinalizing(scanProgress.phaseLabel) ? "Finalizing scan" : "Scanning Profile",
      description: scanProgressPhaseIsFinalizing(scanProgress.phaseLabel)
        ? scanProgress.detail
        : "Scanning the current profile and discovering video cards.",
      buttonLabel: scanProgressPhaseIsFinalizing(scanProgress.phaseLabel) ? "Finalizing..." : "Scanning...",
      enabled: false,
      disabledReason: null
    }
    : liveCollecting && livePresentation
    ? {
      key: "pause",
      title: "Collecting videos",
      description: livePresentation.description,
      buttonLabel: livePresentation.buttonLabel,
      enabled: false,
      disabledReason: null
    }
    : {
      key: unresolvedOvercollectionReviewActive(state, scanDiagnostics) ? "review_overcollection" : canonicalPrimaryAction.key,
      title: canonicalPrimaryAction.title,
      description: actionDescription,
      buttonLabel: actionLabel,
      enabled: canonicalPrimaryAction.enabled,
      disabledReason: canonicalPrimaryAction.disabledReason
    };

  const liveAlreadyCount = livePresentation
    ? livePresentation.tiles.alreadyCollectedCount
    : popupMetricsAuthoritative ? popupMetrics.profile.already_collected_count : queueCounters.alreadyCollectedCount;
  const liveNewCount = livePresentation
    ? livePresentation.tiles.newCount
    : popupMetricsAuthoritative ? popupMetrics.profile.new_count : largeProfilePersistedTotal ?? queueCounters.newCount;
  const liveQueueCount = livePresentation
    ? livePresentation.tiles.queueCount
    : queueCount;

  return {
    videosFound,
    current_run_found_count: scanAuthority.current_run_found_count,
    persisted_total_count: scanAuthority.persisted_total_count,
    display_mode: scanAuthority.display_mode,
    mixed_state_warning: scanAuthority.warning,
    profileScanned,
    scanDataVisible: scanDataVisible || scanProgress.active,
    headerStatus,
    headerProgress: null,
    statsTileMode: "default",
    statsLargeProfile: null,
    scanProgress,
    emptyState: livePresentation
      ? null
      : scanProgress.active
        ? (scanProgressAtFullCapacity(scanProgress)
          ? (scanProgress.overDisplayExtra != null
            ? `Finalizing scan… ${scanProgress.overDisplayExtra} videos beyond profile count are being validated.`
            : "Finalizing scan and syncing with Capture Inbox...")
          : "Scanning profile videos... Progress is still updating.")
        : continuationMessage ?? (scanDataVisible
      ? (metricsPlanMessage
          ?? (completedWithWarningReady
        ? countSemanticsOverDisplayedReady
          ? `API returned ${overDisplayedCount ?? "additional"} additional same-profile videos beyond visible profile count. Visible profile count: ${expectedCount ?? "unknown"}. API collectable count: ${labeledCollectableCount ?? "unknown"}. Additional same-profile API videos: ${overDisplayedCount ?? "unknown"}.`
          : expectedCountSemanticsMismatch
            ? `Scan completed: saved ${labeledCollectableCount} collectable videos. Douyin displays ${expectedCount ?? "unknown"}, but ${unavailableOrUnlistedCount ?? warningMissingCount ?? "some"} could not be found in the API or verified secondary sources. You can continue to the next step.`
            : `Scan completed with warning: saved ${videosFound} of expected ${expectedCount ?? "unknown"} videos. ${warningMissingCount ?? "Some"} items could not be confirmed after API pagination. You can continue to the next step.`
        : scanBudgetContinuation
          ? scanBudgetContinuationMessage(state, videosFound, expectedCount)
          : scanIncomplete
            ? (missingCount != null && missingCount > 0
              ? `Profile scan incomplete: expected ${expectedCount}, found ${videosFound}, missing ${missingCount}.`
              : `Profile scan incomplete: expected ${expectedCount}, found ${videosFound}.`)
            : videosFound === 0
              ? "No eligible videos found."
              : (overcollectionReviewPresentation?.emptyState
                ?? (actionableCollectTiles === 0 && state.classification.status === "success"
                  ? "No new or incomplete videos to collect."
                  : null))))
      : "Scan a profile to build the collection plan."),
    emptyStateTone: "neutral",
    statsCompact: null,
    primaryActionCardTone: "default",
    showCollectionSettings: !isHybridNetworkCacheModeEnabledForCollect(state),
    collectProgress,
    metricsPlan,
    health: {
      profile: profilePageDetected(state) ? "Profile" : "No profile",
      api: apiHealth,
      calibration: calibrationReady ? "Cal ready" : "Cal needed",
      safety
    },
    counts: {
      newCount: liveNewCount,
      incompleteCount: popupMetricsAuthoritative ? popupMetrics.profile.incomplete_count : queueCounters.incompleteCount,
      alreadyCollectedCount: liveAlreadyCount,
      queueCount: liveQueueCount,
      collectedCount,
      savedCount: saved,
      failedCount: popupMetricsAuthoritative ? popupMetrics.profile.need_retry_count : queueCounters.failedCount
    },
    primaryAction: {
      key: action.key,
      label: action.buttonLabel,
      title: action.title,
      description: action.description,
      enabled: action.enabled,
      disabledReason: action.disabledReason,
      tone: "default"
    },
    action,
    settings: {
      mode: friendlyModeLabel(state.harvest_options.mode),
      batch: friendlyBatchLabel(state.harvest_options.batch),
      speed: friendlySpeedLabel(state.harvest_options.speed),
      summary: `${friendlyModeLabel(state.harvest_options.mode)} · ${friendlyBatchLabel(state.harvest_options.batch)} · ${friendlySpeedLabel(state.harvest_options.speed)}`
    },
    profileContext: null
  };
}

function scanProgressAtFullCapacity(scanProgress: ScannerControlPanelViewModel["scanProgress"]): boolean {
  return scanProgress.active
    && scanProgress.expected != null
    && scanProgress.expected > 0
    && scanProgress.discovered >= scanProgress.expected;
}

function deriveCollectRemainderPresentation(counts: ScannerControlPanelViewModel["counts"]): {
  remaining: number;
  headerStatus: string;
  title: string;
  label: string;
  description: string;
  emptyState: string | null;
  percent: number | null;
  primaryKey: ScannerActionKey;
} {
  const already = counts.alreadyCollectedCount;
  const retry = counts.failedCount;
  const incomplete = counts.incompleteCount;
  const newCount = counts.newCount;
  const queue = counts.queueCount;
  const reviewOnly = incomplete > 0 && newCount === 0 && queue === 0 && retry === 0;
  const collectLeft = Math.max(queue, newCount, retry);
  const left = Math.max(collectLeft, incomplete, retry);
  const total = already + Math.max(collectLeft, incomplete);
  const percent = computeProfileCollectPercent(already, total);

  if (reviewOnly) {
    const description = incomplete === 1
      ? `${already} videos ready in Capture Inbox · 1 video needs review (already captured, not ready).`
      : `${already} videos ready in Capture Inbox · ${incomplete} videos need review (already captured, not ready).`;
    return {
      remaining: 0,
      headerStatus: incomplete === 1 ? `${already} collected · 1 needs review` : `${already} collected · ${incomplete} need review`,
      title: incomplete === 1 ? "Review 1 video in Capture Inbox" : `Review ${incomplete} videos in Capture Inbox`,
      label: "Open Capture Inbox",
      description,
      emptyState: null,
      percent,
      primaryKey: "open_capture_inbox"
    };
  }

  if (retry > 0 && retry >= incomplete && retry >= newCount) {
    return {
      remaining: retry,
      headerStatus: `${already} collected · ${retry} left`,
      title: retry === 1 ? "Retry failed video" : `Retry ${retry} failed videos`,
      label: retry === 1 ? "Retry 1 video" : `Retry ${retry} videos`,
      description: retry === 1
        ? "1 video failed during collection and needs retry."
        : `${retry} videos failed during collection and need retry.`,
      emptyState: retry === 1 ? "1 video needs retry." : `${retry} videos need retry.`,
      percent,
      primaryKey: "start_collecting"
    };
  }
  if (incomplete > 0 && incomplete >= collectLeft && incomplete > retry) {
    const reviewDominant = collectLeft === 0 || incomplete > collectLeft;
    const description = collectLeft > 0 && incomplete > collectLeft
      ? `${already} videos ready in Capture Inbox · ${incomplete} need metadata review · ${collectLeft} not collectable by API.`
      : incomplete === 1
        ? "1 video has incomplete metadata and may need review in Capture Inbox."
        : `${incomplete} videos have incomplete metadata and may need review in Capture Inbox.`;
    return {
      remaining: reviewDominant ? 0 : collectLeft,
      headerStatus: collectLeft > 0 && incomplete > collectLeft
        ? `${already} ready · ${incomplete} need review · ${collectLeft} not in API`
        : incomplete === 1
          ? `${already} ready · 1 needs review`
          : `${already} ready · ${incomplete} need review`,
      title: incomplete === 1 ? "Review 1 video in Capture Inbox" : `Review ${incomplete} videos in Capture Inbox`,
      label: reviewDominant ? "Open Capture Inbox" : (collectLeft === 1 ? "Collect 1 remaining" : `Collect ${collectLeft} remaining`),
      description,
      emptyState: reviewDominant
        ? (incomplete === 1 ? "1 video needs review in Capture Inbox." : `${incomplete} videos need review in Capture Inbox.`)
        : (collectLeft === 1 ? "1 video left to collect." : `${collectLeft} videos left to collect (up to 500 per click).`),
      percent,
      primaryKey: reviewDominant ? "open_capture_inbox" : "start_collecting"
    };
  }
  return {
    remaining: left,
    headerStatus: already > 0 ? `${already} collected · ${left} left` : `${left} ready`,
    title: already > 0
      ? (left === 1 ? "Collect last video" : "Continue collecting")
      : (left === 1 ? "Collect 1 video" : "Start Collecting"),
    label: already > 0
      ? (left > 500 ? "Collect next 500" : left === 1 ? "Collect 1 remaining" : `Collect ${left} remaining`)
      : (left > 500 ? "Collect next 500" : left === 1 ? "Collect 1 video" : "Start Collecting"),
    description: already > 0
      ? (left > 500
        ? `${already} already in Capture Inbox · ${left} left (about ${Math.ceil(left / 500)} batches).`
        : `${already} already in Capture Inbox · ${left} left to collect.`)
      : (left > 500
        ? `${left} videos ready to collect (up to 500 per batch).`
        : `${left} videos ready to collect (up to 500 per click).`),
    emptyState: already > 0
      ? (left > 500
        ? `${left} videos left — collecting in batches of up to 500.`
        : left === 1 ? "1 video left to collect." : `${left} videos left to collect.`)
      : (left > 500
        ? `${left} videos ready — up to 500 per batch.`
        : left === 1 ? "1 video ready to collect." : `${left} videos ready to collect (up to 500 per click).`),
    percent,
    primaryKey: "start_collecting"
  };
}

function emptyStateDuplicatesPrimaryDescription(viewModel: ScannerControlPanelViewModel): boolean {
  if (!viewModel.emptyState) return false;
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ");
  return normalize(viewModel.emptyState) === normalize(viewModel.primaryAction.description);
}

function applyAppBackendAuthScannerOverrides(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (renderContext.app_backend_logged_in === undefined) {
    return viewModel;
  }
  const loggedIn = renderContext.app_backend_logged_in === true;
  const auth: AppBackendAuthStatus = parseAppBackendAuthStatus({
    apiAuthToken: loggedIn ? "present" : "",
    apiAuthRequired: loggedIn ? false : true
  });
  const polished = { ...viewModel };
  polished.health = {
    ...polished.health,
    api: scannerAppBackendHealth(state, auth)
  };

  const needsSignInPrimary = !loggedIn && (
    polished.primaryAction.key === "start_collecting"
    || polished.primaryAction.key === "skip_hybrid_incomplete"
    || polished.primaryAction.key === "close_unreachable_tail_gap"
    || polished.primaryAction.key === "open_capture_inbox"
    || polished.primaryAction.key === "review_overcollection"
  );
  const discovered = Math.max(
    polished.counts.newCount,
    polished.counts.queueCount,
    polished.videosFound,
    resolveScannedTotalFromState(state),
    state.scan_job.total_persisted,
    state.post_scan_counter_snapshot?.scanned_total ?? 0
  );
  const signInMessage = polished.profileScanned && discovered > 0
    ? `${discovered} videos scanned on this device · not in Capture Inbox yet. Sign in to save them.`
    : "Sign in to the Web Dashboard before collecting videos.";

  const authPaused = state.harvest.paused_reason === "backend_auth_required";
  const checkedWithoutSave = !loggedIn
    && polished.profileScanned
    && polished.counts.alreadyCollectedCount === 0
    && polished.counts.queueCount > 0
    && polished.collectProgress?.active !== true
    && (authPaused || (typeof state.last_error === "object" && state.last_error?.code === "backend_auth_required"));

  const staleBackendCompleteWhileLoggedOut = !loggedIn && polished.profileScanned && !checkedWithoutSave && (
    needsSignInPrimary
    || polished.counts.alreadyCollectedCount > 0
    || polished.statsCompact != null
    || polished.primaryActionCardTone === "success"
  );

  if (staleBackendCompleteWhileLoggedOut) {
    polished.headerStatus = discovered > 0 ? `${discovered} / ${discovered} videos` : polished.headerStatus;
    polished.counts = {
      ...polished.counts,
      alreadyCollectedCount: 0,
      collectedCount: 0,
      savedCount: 0,
      newCount: discovered,
      queueCount: discovered
    };
    polished.statsCompact = null;
    polished.metricsPlan = null;
    polished.primaryActionCardTone = "warning";
    polished.primaryAction = {
      key: "sign_in_to_app",
      label: "Sign in to app",
      title: "Sign in to save videos",
      description: signInMessage,
      enabled: true,
      disabledReason: null,
      tone: "default"
    };
    polished.action = {
      key: "sign_in_to_app",
      title: polished.primaryAction.title,
      description: signInMessage,
      buttonLabel: "Sign in to app",
      enabled: true,
      disabledReason: null
    };
    polished.emptyState = signInMessage;
    polished.emptyStateTone = "warning";
  }

  if (checkedWithoutSave) {
    const n = polished.counts.queueCount;
    const pauseMessage = `Checked ${n} videos on this device · 0 saved. Sign in to the app, then press Resume or Start Collecting.`;
    polished.headerStatus = `0 saved · ${n} waiting`;
    polished.emptyState = pauseMessage;
    polished.emptyStateTone = "warning";
    polished.statsCompact = null;
    polished.collectProgress = null;
    polished.primaryAction = {
      key: authPaused ? "resume" : "sign_in_to_app",
      label: authPaused ? "Resume" : "Sign in to app",
      title: authPaused ? "Resume after sign in" : "Sign in to save videos",
      description: pauseMessage,
      enabled: true,
      disabledReason: null,
      tone: "default"
    };
    polished.action = {
      key: polished.primaryAction.key,
      title: polished.primaryAction.title,
      description: pauseMessage,
      buttonLabel: polished.primaryAction.label,
      enabled: true,
      disabledReason: null
    };
  }

  if (!loggedIn && !polished.profileScanned && !checkedWithoutSave) {
    if (polished.primaryAction.key === "scan_profile") {
      const scanSignInHint = "Scan this Douyin profile locally. Sign in to the Web Dashboard before saving to Capture Inbox.";
      polished.primaryAction = {
        ...polished.primaryAction,
        description: scanSignInHint
      };
      polished.action = {
        ...polished.action,
        description: scanSignInHint
      };
    }
  }

  if (!loggedIn && polished.collectProgress?.active) {
    const n = Math.max(polished.counts.queueCount, polished.videosFound, discovered);
    const pauseMessage = n > 0
      ? `Collect paused · ${n} videos on this device · not saved. Sign in to the app, then press Resume.`
      : "Sign in to the Web Dashboard before collecting videos.";
    polished.collectProgress = null;
    polished.headerStatus = n > 0 ? `0 saved · ${n} waiting` : polished.headerStatus;
    polished.statsCompact = null;
    polished.primaryActionCardTone = "warning";
    polished.primaryAction = {
      key: authPaused ? "resume" : "sign_in_to_app",
      label: authPaused ? "Resume" : "Sign in to app",
      title: authPaused ? "Resume after sign in" : "Sign in to save videos",
      description: pauseMessage,
      enabled: true,
      disabledReason: null,
      tone: "default"
    };
    polished.action = {
      key: polished.primaryAction.key,
      title: polished.primaryAction.title,
      description: pauseMessage,
      buttonLabel: polished.primaryAction.label,
      enabled: true,
      disabledReason: null
    };
    polished.emptyState = pauseMessage;
    polished.emptyStateTone = "warning";
  }

  if (polished.collectProgress?.active && polished.collectProgress.profileIndeterminate && polished.collectProgress.profileTotal <= 0) {
    polished.collectProgress = {
      ...polished.collectProgress,
      profilePercent: null
    };
  }

  if (emptyStateDuplicatesPrimaryDescription(polished)) {
    polished.emptyState = null;
  }

  return polished;
}

function applyScannerUxPolish(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.scanProgress.active) {
    const atFullProgress = scanProgressAtFullCapacity(viewModel.scanProgress);
    if (atFullProgress && scanFinalizingTimedOut(state, {
      scanProgressActive: true,
      scanProgressPhaseLabel: viewModel.scanProgress.phaseLabel,
      scanProgressAtFull: true
    })) {
      const timeoutMessage = "Finalizing took too long. Rescan the profile or copy the technical log from Advanced.";
      return {
        ...viewModel,
        scanProgress: { ...viewModel.scanProgress, active: false, phaseLabel: "Timed out" },
        headerStatus: "Finalize timed out",
        emptyState: timeoutMessage,
        emptyStateTone: "warning",
        primaryAction: {
          ...viewModel.primaryAction,
          key: "scan_profile",
          title: "Finalize timed out",
          label: "Rescan Profile",
          description: timeoutMessage
        },
        action: {
          ...viewModel.action,
          key: "scan_profile",
          title: "Finalize timed out",
          buttonLabel: "Rescan Profile",
          description: timeoutMessage
        }
      };
    }
    if (!atFullProgress) return viewModel;
    if (!scanProgressPhaseIsFinalizing(viewModel.scanProgress.phaseLabel)) return viewModel;
    const headerStatus = formatActiveScanProgressHeader(viewModel.scanProgress);
    const detail = viewModel.scanProgress.detail;
    const finalizingScanProgress = {
      ...viewModel.scanProgress,
      phaseLabel: "Finalizing"
    };
    return {
      ...viewModel,
      headerStatus,
      scanProgress: finalizingScanProgress,
      emptyState: "Finalizing scan and syncing with Capture Inbox...",
      emptyStateTone: "neutral",
      primaryAction: {
        ...viewModel.primaryAction,
        title: "Finalizing scan",
        label: "Finalizing...",
        description: detail
      },
      action: {
        ...viewModel.action,
        title: "Finalizing scan",
        buttonLabel: "Finalizing...",
        description: detail
      }
    };
  }

  if (viewModel.collectProgress?.active) {
    return {
      ...viewModel,
      emptyState: null,
      statsCompact: null
    };
  }

  let polished = { ...viewModel };

  const activeTabUrl = renderContext.active_tab_url
    ?? state.page_context.current_url
    ?? state.safety.tab_health.current_url
    ?? null;
  if (orphanedPostCollectSnapshot(state)) {
    return {
      ...polished,
      profileScanned: false,
      scanDataVisible: false,
      headerStatus: activeTabOnDouyinProfile(activeTabUrl) ? "Not scanned" : "No profile tab",
      emptyState: "Previous collection data was incomplete. Open a Douyin profile and scan again.",
      emptyStateTone: "warning",
      statsCompact: null,
      primaryActionCardTone: "default",
      counts: {
        newCount: 0,
        incompleteCount: 0,
        alreadyCollectedCount: 0,
        queueCount: 0,
        collectedCount: 0,
        savedCount: 0,
        failedCount: 0
      },
      primaryAction: {
        key: "scan_profile",
        label: activeTabOnDouyinProfile(activeTabUrl) ? "Scan this profile" : "Scan Profile",
        title: activeTabOnDouyinProfile(activeTabUrl) ? "Scan this profile" : "Open a profile tab",
        description: "Navigate to a Douyin creator profile page, then scan to build a collection plan.",
        enabled: activeTabOnDouyinProfile(activeTabUrl),
        disabledReason: activeTabOnDouyinProfile(activeTabUrl) ? null : "Open a Douyin profile tab first.",
        tone: "default"
      },
      action: {
        key: "scan_profile",
        title: activeTabOnDouyinProfile(activeTabUrl) ? "Scan this profile" : "Open a profile tab",
        description: "Navigate to a Douyin creator profile page, then scan to build a collection plan.",
        buttonLabel: activeTabOnDouyinProfile(activeTabUrl) ? "Scan this profile" : "Scan Profile",
        enabled: activeTabOnDouyinProfile(activeTabUrl),
        disabledReason: activeTabOnDouyinProfile(activeTabUrl) ? null : "Open a Douyin profile tab first."
      }
    };
  }

  if (shouldGateScannerPanelForProfileContext(state, renderContext.active_tab_url ?? null)) {
    return polished;
  }

  const batchContinuationPending = isTerminalBatchContinuation(
    state,
    deriveAuthoritativeProfileCounters(state).pending_count
  );

  if (
    polished.primaryAction.key === "open_capture_inbox"
    && polished.counts.alreadyCollectedCount > 0
    && polished.counts.queueCount === 0
    && polished.counts.newCount === 0
    && polished.counts.failedCount === 0
    && polished.counts.incompleteCount === 0
  ) {
    const collected = polished.counts.alreadyCollectedCount;
    polished = clearBatchHeaderChrome({
      ...polished,
      emptyState: null,
      emptyStateTone: "success",
      statsCompact: { summary: `${collected} collected · ready for review`, percent: 100 },
      primaryActionCardTone: "success"
    }, `${collected} collected`);
  } else if (
    !isHybridUnreachableTailGapOffer(state)
    && !batchContinuationPending
    && !polished.collectProgress?.active
    && polished.primaryAction.key === "start_collecting"
    && polished.profileScanned
    && (
      polished.counts.alreadyCollectedCount > 0
      || (state.post_scan_counter_snapshot?.status === "applied" && (state.post_scan_counter_snapshot.already_collected ?? 0) > 0)
      || (renderContext.active_profile_inbox_summary?.trusted && (renderContext.active_profile_inbox_summary.already_collected ?? 0) > 0)
    )
    && (polished.counts.newCount > 0 || polished.counts.queueCount > 0 || polished.counts.failedCount > 0)
  ) {
    const authoritativeAlready = Math.max(
      polished.counts.alreadyCollectedCount,
      state.post_scan_counter_snapshot?.status === "applied" ? state.post_scan_counter_snapshot.already_collected : 0,
      renderContext.active_profile_inbox_summary?.trusted ? renderContext.active_profile_inbox_summary.already_collected : 0
    );
    const pres = deriveCollectRemainderPresentation({
      ...polished.counts,
      alreadyCollectedCount: authoritativeAlready
    });
    if (pres.remaining > 0) {
      polished = {
        ...polished,
        headerStatus: pres.headerStatus,
        emptyState: pres.emptyState,
        emptyStateTone: pres.remaining <= 5 ? "warning" : "neutral",
        statsCompact: pres.percent != null && pres.percent >= 90
          ? { summary: pres.headerStatus, percent: pres.percent }
          : null,
        primaryAction: {
          ...polished.primaryAction,
          key: pres.primaryKey,
          title: pres.title,
          label: pres.label,
          description: pres.description
        },
        action: {
          ...polished.action,
          key: pres.primaryKey,
          title: pres.title,
          buttonLabel: pres.label,
          description: pres.description
        }
      };
    }
  } else if (
    !isHybridUnreachableTailGapOffer(state)
    && polished.counts.incompleteCount > 0
    && polished.counts.newCount === 0
    && polished.counts.queueCount === 0
    && polished.counts.failedCount === 0
    && polished.counts.alreadyCollectedCount > 0
  ) {
    const pres = deriveCollectRemainderPresentation(polished.counts);
    polished = {
      ...polished,
      headerStatus: pres.headerStatus,
      emptyState: pres.emptyState,
      emptyStateTone: "warning",
      statsCompact: pres.percent != null && pres.percent >= 90
        ? { summary: pres.headerStatus, percent: pres.percent }
        : polished.statsCompact,
      primaryActionCardTone: "success",
      primaryAction: {
        ...polished.primaryAction,
        key: pres.primaryKey,
        title: pres.title,
        label: pres.label,
        description: pres.description
      },
      action: {
        ...polished.action,
        key: pres.primaryKey,
        title: pres.title,
        buttonLabel: pres.label,
        description: pres.description
      }
    };
  }

  if (emptyStateDuplicatesPrimaryDescription(polished)) {
    polished = { ...polished, emptyState: null };
  }

  return applyHybridTailGapClosedIfActive(applyUnreachableTailGapOfferIfActive(polished, state), state);
}

function applyTrustedBackendInboxToScannerPanel(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  if (viewModel.collectProgress?.active) return viewModel;
  if (isHybridTailGapClosed(state)) {
    return applyHybridTailGapClosedIfActive(viewModel, state);
  }
  // Operator escape hatch for phantom tail gap / metrics-miss skip must not be overwritten by inbox tiles.
  if (
    viewModel.primaryAction.key === "close_unreachable_tail_gap"
    || viewModel.primaryAction.key === "skip_hybrid_incomplete"
    || isHybridUnreachableTailGapOffer(state)
  ) {
    if (viewModel.primaryAction.key === "skip_hybrid_incomplete") {
      return viewModel;
    }
    return applyUnreachableTailGapOfferIfActive(viewModel, state);
  }

  const summary = renderContext.active_profile_inbox_summary;
  if (!summary?.trusted) return viewModel;

  if (viewModel.scanProgress.active) {
    const discovered = viewModel.scanProgress.discovered;
    const backendCoversScan = summary.captured_total >= Math.max(discovered, 1) && summary.already_collected > 0;
    if (!backendCoversScan && !activeProfileInboxSummaryIsComplete(summary)) return viewModel;
  } else if (deriveProfileContextViewModel(state, renderContext)) {
    return viewModel;
  }

  const localAlready = viewModel.counts.alreadyCollectedCount;
  const localCollectable = viewModel.counts.newCount + viewModel.counts.queueCount + viewModel.counts.failedCount;
  const backendCollectable = profileContextCollectableRemaining(summary);
  const backendReview = profileContextInboxReviewCount(summary);
  const backendComplete = activeProfileInboxSummaryIsComplete(summary);
  const backendProvesEmpty = inboxSummaryProvesBackendEmpty(summary);
  const localShowsBackendComplete = viewModel.counts.alreadyCollectedCount > 0
    || viewModel.primaryAction.key === "open_capture_inbox"
    || backendComplete;

  if (backendProvesEmpty && localShowsBackendComplete && !hybridPostCollectAuthorityActive(state)) {
    const scanCollectable = Math.max(
      state.harvest.pending,
      state.harvest.queue.filter((item) => {
        const status = String(item.status);
        return status === "pending" || status === "new" || status === "retry" || item.capture_status === "new";
      }).length,
      state.scan_job.total_persisted,
      state.post_scan_counter_snapshot?.scanned_total ?? 0,
      viewModel.counts.newCount,
      viewModel.counts.queueCount
    );
    const pres = deriveCollectRemainderPresentation({
      newCount: scanCollectable,
      incompleteCount: 0,
      alreadyCollectedCount: 0,
      queueCount: scanCollectable,
      collectedCount: 0,
      savedCount: 0,
      failedCount: viewModel.counts.failedCount
    });
    return {
      ...viewModel,
      profileScanned: true,
      scanDataVisible: true,
      headerStatus: pres.headerStatus,
      counts: {
        newCount: scanCollectable,
        incompleteCount: 0,
        alreadyCollectedCount: 0,
        queueCount: scanCollectable,
        collectedCount: 0,
        savedCount: 0,
        failedCount: viewModel.counts.failedCount
      },
      metricsPlan: null,
      emptyState: pres.emptyState,
      emptyStateTone: pres.remaining <= 5 ? "warning" : "neutral",
      statsCompact: null,
      primaryActionCardTone: "default",
      primaryAction: {
        key: pres.primaryKey,
        label: pres.label,
        title: pres.title,
        description: pres.description,
        enabled: true,
        disabledReason: null,
        tone: "default"
      },
      action: {
        key: pres.primaryKey,
        title: pres.title,
        buttonLabel: pres.label,
        description: pres.description,
        enabled: true,
        disabledReason: null
      }
    };
  }

  const backendAhead = summary.already_collected > localAlready;
  const localStaleVsBackend = backendAhead && backendCollectable < localCollectable;

  if (!backendComplete && !localStaleVsBackend && backendCollectable <= 0 && backendReview <= 0) return viewModel;

  const counts = inboxSummaryScannerCounts(summary);

  if (backendComplete || inboxSummaryHasReviewOnlyBacklog(summary)) {
    const localNeverSavedThisRun = viewModel.counts.alreadyCollectedCount === 0
      && viewModel.counts.savedCount === 0
      && viewModel.primaryAction.key !== "open_capture_inbox";
    if (localNeverSavedThisRun && (
      viewModel.primaryAction.key === "start_collecting"
      || viewModel.primaryAction.key === "review_overcollection"
      || viewModel.primaryAction.key === "calibrate"
    )) {
      return viewModel;
    }
    const review = backendReview;
    const collected = summary.already_collected;
    const description = review > 0
      ? (review === 1
        ? `${collected} videos ready in Capture Inbox · 1 video needs review (already captured, not ready for collect).`
        : `${collected} videos ready in Capture Inbox · ${review} videos need review.`)
      : `${collected} videos from this profile are in Capture Inbox and ready for review.`;
    const title = review > 0
      ? (review === 1 ? "Review 1 video in Capture Inbox" : "Collection complete · review needed")
      : "Collection complete";
    return clearBatchHeaderChrome({
      ...viewModel,
      profileScanned: true,
      scanDataVisible: true,
      counts,
      metricsPlan: null,
      emptyState: null,
      emptyStateTone: review > 0 ? "warning" : "success",
      statsCompact: {
        summary: profileContextHeaderStatus(summary) + (review > 0 ? "" : " · ready for review"),
        percent: review > 0 && collected + review > 0
          ? Math.floor((collected / (collected + review)) * 100)
          : 100
      },
      primaryActionCardTone: "success",
      primaryAction: {
        key: "open_capture_inbox",
        label: "Open Capture Inbox",
        title,
        description,
        enabled: true,
        disabledReason: null,
        tone: "default"
      },
      action: {
        key: "open_capture_inbox",
        title,
        description,
        buttonLabel: "Open Capture Inbox",
        enabled: true,
        disabledReason: null
      }
    }, profileContextHeaderStatus(summary));
  }

  const pres = deriveCollectRemainderPresentation(counts);
  return {
    ...viewModel,
    profileScanned: true,
    scanDataVisible: true,
    headerStatus: pres.headerStatus,
    counts,
    metricsPlan: null,
    emptyState: pres.emptyState,
    emptyStateTone: pres.remaining <= 5 ? "warning" : "neutral",
    statsCompact: pres.percent != null && pres.percent >= 90
      ? { summary: pres.headerStatus, percent: pres.percent }
      : null,
    primaryAction: {
      key: pres.primaryKey,
      label: pres.label,
      title: pres.title,
      description: pres.description,
      enabled: true,
      disabledReason: null,
      tone: "default"
    },
    action: {
      key: pres.primaryKey,
      title: pres.title,
      buttonLabel: pres.label,
      description: pres.description,
      enabled: true,
      disabledReason: null
    }
  };
}

function applyProfileContextGateToScannerPanel(
  viewModel: ScannerControlPanelViewModel,
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext
): ScannerControlPanelViewModel {
  const activeTabUrl = renderContext.active_tab_url
    ?? state.page_context.current_url
    ?? state.safety.tab_health.current_url
    ?? null;
  const gateActiveTabUrl = renderContext.active_tab_url ?? null;
  const profileContextGate = shouldGateScannerPanelForProfileContext(state, gateActiveTabUrl);
  const liveCollecting = viewModel.collectProgress?.active === true;
  const scanning = viewModel.scanProgress.active;
  const jobVisiblyLive = isCollectJobVisiblyLive(state);
  // Live collect UI must not be replaced by the profile-context placeholder panel.
  if (jobVisiblyLive && liveCollecting) return viewModel;
  // Stale collect progress from a previous profile must not block the mismatch gate.
  if (!profileContextGate && (liveCollecting || scanning)) return viewModel;

  const collectionRunning = jobVisiblyLive || (!profileContextGate && (viewModel.primaryAction.key === "pause" || liveCollecting));
  const profileContext = deriveProfileContextViewModel(state, renderContext, {
    collectionRunning
  });
  if (!profileContext) return viewModel;

  const summary = profileContext.active_inbox_summary;
  const resumeEligible = activeProfileInboxSummaryIsResumeEligible(summary);

  let primaryKey: ScannerActionKey;
  let primaryTitle: string;
  let primaryLabel: string;
  let primaryDescription: string;
  let primaryEnabled: boolean;
  let emptyState: string | null;
  let headerStatus: string;

  if (profileContext.collection_running_on_stored_profile) {
    primaryKey = "pause";
    primaryTitle = "Collecting on previous profile";
    primaryLabel = "Return to previous tab";
    primaryDescription = "Return to the Douyin tab where collection is running, or reset to work on this profile.";
    primaryEnabled = false;
    emptyState = null;
    headerStatus = "Profile switch";
  } else if (!profileContext.active_tab_on_profile) {
    primaryKey = "scan_profile";
    primaryTitle = "Open a profile tab";
    primaryLabel = "Scan Profile";
    primaryDescription = "Navigate to a Douyin creator profile page, then scan to build a collection plan.";
    primaryEnabled = false;
    emptyState = null;
    headerStatus = "No profile tab";
  } else {
    const profileMismatch = detectProfileContextMismatch(state, activeTabUrl);
    const revisit = activeProfileRevisitPresentationActive(renderContext.active_profile_presentation)
      ? renderContext.active_profile_presentation
      : null;
    const inboxComplete = summary != null && activeProfileInboxSummaryIsComplete(summary);
    const revisitInboxComplete = revisit != null
      && revisit.already_collected > 0
      && revisit.new_count + revisit.queue_count <= 0;
    if (inboxComplete || revisitInboxComplete) {
      const collected = revisit?.already_collected ?? summary?.already_collected ?? 0;
      primaryKey = "open_capture_inbox";
      primaryTitle = revisit?.primary_title ?? "Collection complete";
      primaryLabel = revisit?.primary_label ?? "Open Capture Inbox";
      primaryDescription = revisit?.primary_description
        ?? `${collected} videos are ready in Capture Inbox for this creator.`;
      primaryEnabled = true;
      emptyState = null;
      headerStatus = revisit?.header_status ?? profileContextHeaderStatus(summary!);
    } else {
      primaryKey = "scan_profile";
      primaryTitle = revisit?.primary_title ?? (profileMismatch ? "Scan this profile" : "Scan this profile");
      primaryLabel = revisit?.primary_label ?? (profileMismatch ? "Scan this profile" : "Scan this profile");
      primaryDescription = revisit?.primary_description ?? (profileMismatch
        ? "Different creator than your last session. Scan this profile to discover videos and build a collection plan."
        : resumeEligible && summary && summary.queue_count > 0
          ? `After scan, Capture Inbox shows ${summary.already_collected} ready and ${summary.queue_count} needing action for this creator.`
          : "Discover videos on this profile and build a collection plan.");
      primaryEnabled = true;
      emptyState = null;
      headerStatus = revisit?.header_status ?? "Not scanned";
    }
  }

  const revisit = activeProfileRevisitPresentationActive(renderContext.active_profile_presentation)
    ? renderContext.active_profile_presentation
    : null;
  const showActiveTabTiles = revisit != null
    || profileContextShouldShowActiveTiles(
      profileContext.active_tab_on_profile,
      summary,
      false
    );

  const counts = revisit
    ? buildActiveProfileScannerCounts(revisit)
    : showActiveTabTiles && summary
    ? {
      newCount: summary.new_count,
      incompleteCount: summary.incomplete_count,
      alreadyCollectedCount: summary.already_collected,
      queueCount: summary.queue_count,
      collectedCount: summary.already_collected,
      savedCount: summary.already_collected,
      failedCount: summary.need_retry_count
    }
    : {
      newCount: 0,
      incompleteCount: 0,
      alreadyCollectedCount: 0,
      queueCount: 0,
      collectedCount: 0,
      savedCount: 0,
      failedCount: 0
    };

  return {
    ...viewModel,
    profileScanned: false,
    scanDataVisible: showActiveTabTiles || revisit != null,
    headerStatus,
    emptyState,
    emptyStateTone: "neutral",
    counts,
    metricsPlan: null,
    collectProgress: null,
    statsCompact: revisit && revisit.already_collected > 0
      ? { summary: revisit.header_status, percent: revisit.scanned_total > 0 ? Math.min(100, Math.round((revisit.already_collected / revisit.scanned_total) * 100)) : null }
      : null,
    health: {
      ...viewModel.health,
      profile: profileContext.active_tab_on_profile ? "This profile" : viewModel.health.profile,
      calibration: (summary != null && activeProfileInboxSummaryIsComplete(summary))
        || (revisit != null && revisit.already_collected > 0 && revisit.new_count + revisit.queue_count <= 0)
        ? "Cal ready"
        : viewModel.health.calibration
    },
    primaryAction: {
      key: primaryKey,
      label: primaryLabel,
      title: primaryTitle,
      description: primaryDescription,
      enabled: primaryEnabled,
      disabledReason: primaryEnabled ? null : primaryDescription,
      tone: "default"
    },
    action: {
      key: primaryKey,
      title: primaryTitle,
      description: primaryDescription,
      buttonLabel: primaryLabel,
      enabled: primaryEnabled,
      disabledReason: primaryEnabled ? null : primaryDescription
    },
    profileContext
  };
}

export function getScannerControlPanelViewModel(
  state: WholeProfileHarvestState,
  renderContext: ScannerControlPanelRenderContext = {}
): ScannerControlPanelViewModel {
  let viewModel = sanitizePopupViewState(getScannerControlPanelViewModelUnreconciled(state), state);
  const gateActiveTabUrl = renderContext.active_tab_url ?? null;
  const profileContextGate = shouldGateScannerPanelForProfileContext(state, gateActiveTabUrl);
  const revisitPresentation = renderContext.active_profile_presentation;
  const revisitWithData = activeProfileRevisitPresentationActive(revisitPresentation);
  const repositoryEvidence = (renderContext.active_profile_repository_snapshot?.total_targets ?? 0) > 0
    || (revisitPresentation?.scanned_total ?? 0) > 0;
  const alignedPersistedComplete = scanSessionCompleteForPresentation(state, gateActiveTabUrl)
    && alignedPartialScanPersistedCount(state, gateActiveTabUrl) > 0;
  const liveCollectingEarly = isCollectJobVisiblyLive(state);
  if (profileContextGate && !liveCollectingEarly && !viewModel.scanProgress.active && !revisitWithData && !repositoryEvidence && !alignedPersistedComplete) {
    return finalizeScannerControlPanelViewModel({
      ...viewModel,
      profileScanned: false,
      scanDataVisible: false,
      metricsPlan: null,
      statsCompact: null,
      collectProgress: null
    }, state, renderContext);
  }
  const partialScanTiles = partialAlignedScanPresentationActive(state, gateActiveTabUrl, viewModel, renderContext);
  const presentationBlocked = scanBlocksCollectPresentation(state, gateActiveTabUrl) && !viewModel.scanProgress.active && !liveCollectingEarly && !partialScanTiles;
  if (presentationBlocked) {
    viewModel = {
      ...viewModel,
      profileScanned: false,
      scanDataVisible: false,
      metricsPlan: null,
      statsCompact: null
    };
    return finalizeScannerControlPanelViewModel(viewModel, state, renderContext);
  }
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const snapshot = state.post_scan_counter_snapshot;
  const liveCollecting = isCollectJobVisiblyLive(state);
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const hybridProfileCollectComplete = hybridProfileCollectFullyComplete(state, renderContext)
    || isHybridTailGapClosed(state)
    || (!liveCollecting
      && state.collect_job.state === "completed"
      && isHybridNetworkCacheModeEnabledForCollect(state)
      && (summary.hybrid_collector_completed === "yes" || summary.hybrid_collection_done_override_applied === "yes")
      && snapshot?.status === "applied"
      && (snapshot.already_collected ?? 0) > 0
      && snapshot.new <= 0
      && snapshot.queue <= 0);
  // After Hybrid collect, post_scan_counter_snapshot is the tile authority
  // (synced from Capture Inbox card + durable floor). Never let large-profile
  // persisted queue totals overwrite New/Queue back to ~full profile size
  // (production: Already=21 correct-ish, New forced to 117/128).
  // While a run is in progress, collectLiveProgress owns tiles — skip snapshot reconcile.
  // After hybrid profile collect completes, skip interim device-queue tiles (end flash).
  if (snapshot?.status === "applied" && !liveCollecting && !hybridProfileCollectComplete) {
    const trustAlready = shouldTrustSnapshotAlreadyCollected(state, renderContext);
    const popupTilesAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
    const scanAuthorityRemaining = Math.max(
      popupMetrics.profile.new_count,
      popupMetrics.profile.queue_count,
      Math.max(0, resolveScannedTotalFromState(state) - (trustAlready ? snapshot.already_collected : 0))
    );
    if (trustAlready) {
      viewModel.counts.alreadyCollectedCount = Math.max(snapshot.already_collected, viewModel.counts.alreadyCollectedCount);
      viewModel.counts.newCount = popupTilesAuthoritative
        ? popupMetrics.profile.new_count
        : Math.max(snapshot.new, scanAuthorityRemaining);
      viewModel.counts.queueCount = popupTilesAuthoritative
        ? popupMetrics.profile.queue_count
        : Math.max(snapshot.queue, scanAuthorityRemaining);
    } else {
      const deviceQueue = deviceScanQueueCountFromSnapshot(state, snapshot);
      const reconciledQueue = Math.max(deviceQueue, scanAuthorityRemaining);
      viewModel.counts.alreadyCollectedCount = 0;
      viewModel.counts.collectedCount = 0;
      viewModel.counts.savedCount = 0;
      viewModel.counts.newCount = reconciledQueue;
      viewModel.counts.queueCount = reconciledQueue;
    }
    const profileVideoTotal = resolveScannedTotalFromState(state);
    if (profileVideoTotal > 0 && viewModel.profileScanned && !viewModel.collectProgress?.active) {
      viewModel.headerStatus = `${profileVideoTotal} videos`;
      viewModel.videosFound = profileVideoTotal;
    }
  }
  if (hybridProfileCollectComplete && snapshot) {
    const postRunAlready = isHybridTailGapClosed(state)
      ? resolveHybridTailGapClosedAlready(state)
      : typeof summary.hybrid_runner_post_run_tile_already === "number" && Number.isFinite(summary.hybrid_runner_post_run_tile_already)
      ? Math.max(0, Math.round(summary.hybrid_runner_post_run_tile_already))
      : snapshot.already_collected;
    viewModel.counts.alreadyCollectedCount = postRunAlready;
    viewModel.counts.newCount = 0;
    viewModel.counts.queueCount = 0;
    viewModel.counts.collectedCount = postRunAlready;
    viewModel.counts.savedCount = postRunAlready;
    viewModel.collectProgress = null;
    viewModel.statsCompact = {
      summary: `${postRunAlready} collected · ready for review`,
      percent: 100
    };
    viewModel.headerStatus = `${postRunAlready} collected`;
    viewModel.primaryActionCardTone = "success";
    viewModel.emptyState = null;
    viewModel.emptyStateTone = "success";
  }
  // Keep live progress labels even if sanitizePopupViewState forced a generic
  // "Collecting videos..." lock label (operators need batch progress on large profiles).
  // Three-phase hybrid collect UI applies only to whole-profile hybrid runs.
  if (liveCollecting && isHybridNetworkCacheModeEnabledForCollect(state)) {
    const presentation = buildCollectLiveProgressPresentation(state);
    if (presentation) {
      viewModel = applyCollectLiveProgressToViewModel(viewModel, presentation);
    }
  } else {
    viewModel.collectProgress = null;
    viewModel.metricsPlan = buildHybridMetricsPlan(state);
    viewModel.showCollectionSettings = !isHybridNetworkCacheModeEnabledForCollect(state);
    const queueCount = viewModel.counts.queueCount;
    const skippedUncollectable = viewModel.metricsPlan?.skippedUncollectable ?? hybridSkippedUncollectableCount(state);
    const collected = viewModel.metricsPlan?.collected
      ?? (snapshot?.status === "applied" ? snapshot.already_collected : viewModel.counts.alreadyCollectedCount);

    if (skippedUncollectable > 0 && queueCount <= 0) {
      const doneMessage = `Collection finished. ${skippedUncollectable} video(s) skipped (no metrics). Open Capture Inbox to review ${collected} collected videos.`;
      viewModel.emptyState = doneMessage;
      viewModel.emptyStateTone = "success";
      viewModel.action = {
        key: "open_capture_inbox",
        title: "Open Capture Inbox",
        description: doneMessage,
        buttonLabel: "Open Capture Inbox",
        enabled: true,
        disabledReason: null
      };
      viewModel.primaryAction = {
        key: "open_capture_inbox",
        label: "Open Capture Inbox",
        title: "Open Capture Inbox",
        description: doneMessage,
        enabled: true,
        disabledReason: null,
        tone: "default"
      };
    } else if (isHybridUnreachableTailGapOffer(state)) {
      applyHybridUnreachableTailGapAction(
        viewModel,
        buildHybridUnreachableTailGapUi(resolveUnreachableTailGapRemaining(state))
      );
    } else if (shouldOfferHybridMetricsMissSkip(state, queueCount)) {
      const contract = buildProfileCollectContractFromState(state);
      applyHybridMetricsMissAction(
        viewModel,
        buildHybridMetricsMissUi(
          queueCount,
          contract.incomplete_count > 0 ? contract.incomplete_count : null
        )
      );
    } else if (viewModel.metricsPlan && viewModel.profileScanned && !scanBlocksCollectPresentation(state)) {
      const plan = viewModel.metricsPlan;
      if (viewModel.emptyState == null && plan.collected === 0 && plan.discovered > 0) {
        const displayed = numericDiagnosticValue(scanDiagnosticsRecord(state).displayed_profile_count);
        const overDisplayed = numericDiagnosticValue(scanDiagnosticsRecord(state).over_displayed_count);
        viewModel.emptyState = displayed != null && overDisplayed != null && overDisplayed > 0 && plan.discovered > displayed
          ? `${plan.discovered} collectable videos (Douyin shows ${displayed} on profile).`
          : `${plan.discovered} videos ready to collect (up to 500 per click).`;
        viewModel.emptyStateTone = "neutral";
      } else if (viewModel.emptyState == null && plan.metricsMissing > 0 && plan.metricsReady > 0 && viewModel.counts.queueCount > 0) {
        viewModel.emptyState = `${plan.collected} collected · ${plan.metricsReady} ready · ${plan.metricsMissing} need metrics`;
        viewModel.emptyStateTone = "neutral";
      }
    }
  }
  if (snapshot?.status === "applied") {
    const popupMetricsAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
    const largeProfilePersistedTotal = activeScanProgress22C14G(state).active ? null : largeProfilePersistedQueueTotal(state, gateActiveTabUrl);
    const persistedTotalHasNewerAuthority = popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_newer_persisted_total === "yes";
    applyLargeProfilePersistedScannerPanelTiles(viewModel, {
      largeProfilePersistedTotal,
      presentationBlocked,
      largeProfileMode: scanDiagnosticsLargeProfileMode(state),
      popupMetricsAuthoritative,
      persistedTotalHasNewerAuthority,
      displayedProfileCollectLimit: resolveDisplayedProfileVideoLimit(scanDiagnosticsRecord(state))
    });
    viewModel = applyTrustedBackendInboxToScannerPanel(viewModel, state, renderContext);
    return finalizeScannerControlPanelViewModel(viewModel, state, renderContext);
  }
  const popupMetricsAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
  const largeProfilePersistedTotal = activeScanProgress22C14G(state).active ? null : largeProfilePersistedQueueTotal(state, gateActiveTabUrl);
  const persistedTotalHasNewerAuthority = popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_newer_persisted_total === "yes";
  applyLargeProfilePersistedScannerPanelTiles(viewModel, {
    largeProfilePersistedTotal,
    presentationBlocked,
    largeProfileMode: scanDiagnosticsLargeProfileMode(state),
    popupMetricsAuthoritative,
    persistedTotalHasNewerAuthority,
    displayedProfileCollectLimit: resolveDisplayedProfileVideoLimit(scanDiagnosticsRecord(state))
  });
  viewModel = applyTrustedBackendInboxToScannerPanel(viewModel, state, renderContext);
  return finalizeScannerControlPanelViewModel(viewModel, state, renderContext);
}

function getDouyinScannerMainViewModelUnreconciled(state: WholeProfileHarvestState): DouyinScannerMainViewModel {
  const readiness = getWholeProfileHarvestReadiness(state);
  const workflowReadiness = getDouyinScannerWorkflowReadiness(state);
  const actionState = getWholeProfileHarvestActionState(state);
  const canonicalPrimaryAction = getCanonicalScannerPrimaryAction(state);
  const runnerLock = deriveAuthoritativeRunnerLock(state);
  const canonicalUiState = String(runnerLock.diagnostics.trace_ui_canonical_state ?? "idle");
  const scanAuthority = scanDisplayAuthority22C14B(state);
  const scanProgress = activeScanProgress22C14G(state);
  const largeProfilePersistedTotal = scanAuthority.display_mode === "persisted_history_authority" || scanProgress.active ? null : largeProfilePersistedQueueTotal(state);
  const videosFound = scanProgress.active
    ? scanProgress.discovered
    : scanAuthority.display_mode === "persisted_history_authority"
      ? scanAuthority.current_run_found_count
      : profileCount(state);
  const scanDiagnostics = scanDiagnosticsRecord(state);
  const countSemanticsStatus = String(scanDiagnostics.count_semantics_status ?? "");
  const countSemanticsDisplayedMismatch = countSemanticsStatus === "completed_with_displayed_count_mismatch" || countSemanticsStatus === "completed_with_partial_secondary_recovery";
  const countSemanticsOverDisplayedReady = countSemanticsStatus === "completed_with_api_over_displayed_count";
  const countSemanticsOverDisplayedNeedsValidation = countSemanticsStatus === "overcollected_needs_validation";
  const collectableCount = numericDiagnosticValue(scanDiagnostics.collectable_count) ?? videosFound;
  const finalCumulativeCollectableCount = numericDiagnosticValue(scanDiagnostics.final_cumulative_collectable_count) ?? collectableCount;
  const finalDisplayAuthority = String(scanDiagnostics.final_display_authority ?? "");
  const displayedProfileCount = numericDiagnosticValue(scanDiagnostics.displayed_profile_count) ?? expectedProfileVideoCount(state) ?? state.scan_job.expected_count;
  const unavailableOrUnlistedCount = numericDiagnosticValue(scanDiagnostics.unavailable_or_unlisted_count) ?? (displayedProfileCount == null ? null : Math.max(displayedProfileCount - finalCumulativeCollectableCount, 0));
  const overDisplayedCount = numericDiagnosticValue(scanDiagnostics.over_displayed_count) ?? (displayedProfileCount == null ? null : Math.max(finalCumulativeCollectableCount - displayedProfileCount, 0));
  const labeledCollectableCount = finalDisplayAuthority === "cumulative_persisted_count" ? finalCumulativeCollectableCount : collectableCount;
  const popupProfileVideoTotal = resolveScannedTotalFromState(state);
  const videosFoundLabel = countSemanticsOverDisplayedReady
    ? `${labeledCollectableCount ?? collectableCount ?? popupProfileVideoTotal} collectable`
    : countSemanticsDisplayedMismatch
    ? String(popupProfileVideoTotal)
    : countSemanticsOverDisplayedNeedsValidation
      ? `${collectableCount} needs review`
      : scanProgress.expected != null
        ? `${videosFound} / ${scanProgress.expected}`
        : profileCountLabel(state, videosFound);
  const nearCompleteWarning = scanProgress.active ? { applied: false, gapCount: null, threshold: null } : popupNearCompleteWarning(state, videosFound);
  const nearCompleteAllowed = nearCompleteWarning.applied;
  const expectedCount = displayedProfileCount;
  const profileScanned = workflowReadiness.profileScanReady;
  const completedWithWarningReady = profileScanned && String(scanDiagnostics.scan_finalization_result ?? "") === "completed_with_warning";
  const expectedCountSemanticsMismatch = completedWithWarningReady && (countSemanticsDisplayedMismatch || String(scanDiagnostics.final_gap_reason ?? "") === "expected_count_semantics_mismatch");
  const scanBudgetContinuation = !scanProgress.active && scanBudgetContinuationAvailable(state);
  const hybridCollectorCompleted = collectCompletionOverridesActiveCollectRuntime(state);
  const scanIncomplete = scanIncompleteUnderExpectedForPresentation(state, state.page_context.current_url ?? null)
    || (!hybridCollectorCompleted && !scanBudgetContinuation && !scanProgress.active && expectedCount != null && videosFound > 0 && videosFound < expectedCount && !nearCompleteWarning.applied && !completedWithWarningReady);
  const calibrationReady = isCollectCalibrationSatisfied(state);
  const extracted = extractedCount(state);
  const saved = savedCount(state);
  const pending = pendingCount(state);
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const popupMetricsAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
  const collectActiveForProfileTiles = state.workflow.collection.status === "running"
    || state.workflow.active_task === "collect_videos"
    || isCollectJobVisiblyLive(state);
  const profileTileAlready = popupMetricsAuthoritative ? popupMetrics.profile.already_collected_count : state.target_status.complete;
  const largeProfileTiles = largeProfilePersistedTotal != null
    ? resolveLargeProfileTileCounts(
      largeProfilePersistedTotal,
      profileTileAlready,
      scanDiagnosticsLargeProfileMode(state)
    )
    : null;
  const profileTileQueueCount = !collectActiveForProfileTiles && largeProfileTiles != null
    ? largeProfileTiles.queueCount
    : (popupMetricsAuthoritative ? popupMetrics.profile.queue_count : state.harvest.queue_preview.length || pending);
  const profileTileNewCount = !collectActiveForProfileTiles && largeProfileTiles != null
    ? largeProfileTiles.newCount
    : (popupMetricsAuthoritative ? popupMetrics.profile.new_count : state.target_status.new);
  const scannerBusy = getDouyinScannerBusyState(state);
  const running = scannerBusy.isBusy;
  const scanning = running && scannerBusy.busySource === "scan.status";
  const classifying = running && scannerBusy.busySource === "classification.status";
  const pausing = state.workflow.collection.status === "pausing" && (state.workflow.active_task === "collect_videos" || state.workflow.action_lock === "collect_videos");
  const waitingForActiveTab = canonicalUiState === "waiting_for_active_tab";
  const pausedTabInactive = canonicalUiState === "paused_tab_inactive";
  const runtimeVisibleStatusSource = String(runnerLock.diagnostics.trace_progress_visible_status_source ?? "legacy_state");
  const runtimeVisiblePhaseSource = String(runnerLock.diagnostics.trace_progress_visible_phase_source ?? "legacy_state");
  const runtimeVisibleStatusCommitted = String(runnerLock.diagnostics.trace_progress_runtime_status_committed ?? canonicalUiState);
  const runtimeVisiblePhaseCommitted = String(runnerLock.diagnostics.trace_progress_runtime_phase_committed ?? canonicalUiState);
  const runtimeActiveBatchRequired = runnerLock.diagnostics.trace_progress_active_batch_runtime_required === "yes";
  const collectActive = canonicalPrimaryAction.key === "pause" || canonicalUiState === "running" || waitingForActiveTab || pausedTabInactive;
  const openingTarget = runtimeActiveBatchRequired
    ? runtimeVisiblePhaseCommitted === "opening_target"
    : collectActive && state.workflow.collection.status === "opening_target";
  const collecting = runtimeActiveBatchRequired
    ? runtimeVisibleStatusCommitted === "collecting" || runtimeVisiblePhaseCommitted === "running"
    : collectActive && !openingTarget;
  const paused = !collectActive && state.harvest.resume_available === true && (state.workflow.collection.status === "paused" || (state.workflow.collection.status === "pausing" && !pausing && state.harvest.pause_requested === true));
  const activeScanHeader = formatActiveScanProgressHeader(scanProgress);
  const headerStatus = scanProgress.active
    ? activeScanHeader
    : scanning
    ? "Scanning"
    : classifying
      ? "Classifying"
      : pausing
        ? "Pausing..."
        : runtimeActiveBatchRequired && runtimeVisiblePhaseCommitted === "opening_target"
          ? "Opening first video"
          : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "waiting_for_active_tab"
            ? "Waiting for tab"
            : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "paused_tab_inactive"
              ? "Paused"
              : openingTarget
                ? "Opening first video"
                : waitingForActiveTab
                  ? "Waiting for tab"
                  : pausedTabInactive || paused
                    ? "Paused"
                    : collecting
                      ? "Collecting"
                      : profileScanned || nearCompleteAllowed
                        ? `${videosFoundLabel} videos`
                        : scanIncomplete
                          ? `${videosFoundLabel} videos`
                          : "Ready";
  const profileLabel = state.profile_url ? shortenUrl(state.profile_url, 36) : "Open a Douyin profile to start scanning.";

  const tabHealth = state.safety.tab_health.status === "content_script_missing" || state.safety.tab_health.status === "detector_failed"
    ? { label: "Tab", value: "Check", tone: "warning" as const }
    : profilePageDetected(state)
      ? { label: "Tab", value: "Profile", tone: "success" as const }
      : state.page_context.page_type === "modal"
        ? { label: "Tab", value: "Modal", tone: "success" as const }
        : { label: "Tab", value: "Other", tone: "neutral" as const };

  const apiPaginationAttempted = scanApiPaginationAttempted22C14N(state, scanDiagnostics);
  const apiHealth = state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed"
    ? { label: "API", value: "Error", tone: "danger" as const }
    : state.harvest.backend.capture_session.status === "ready" || apiPaginationAttempted
      ? { label: "API", value: apiPaginationAttempted ? "Collectable" : "Ready", tone: "success" as const }
      : state.last_error && typeof state.last_error === "string" && (state.last_error.includes("backend") || state.last_error.includes("timeout"))
        ? { label: "API", value: "Issue", tone: "warning" as const }
        : { label: "API", value: "Idle", tone: "neutral" as const };

  const calibrationHealth = calibrationReady
    ? { label: "Calib", value: "Ready", tone: "success" as const }
    : state.calibration.point_count > 0
      ? { label: "Calib", value: `${state.calibration.point_count}/4`, tone: "warning" as const }
      : { label: "Calib", value: "Needed", tone: "warning" as const };

  const safetyHealth = state.safety.captcha_detected
    ? { label: "Safety", value: "Captcha", tone: "warning" as const }
    : state.safety.consecutive_errors > 0
      ? { label: "Safety", value: "Caution", tone: "warning" as const }
      : pausing
        ? { label: "Safety", value: "Pausing", tone: "warning" as const }
        : paused || waitingForActiveTab || pausedTabInactive
          ? { label: "Safety", value: "Paused", tone: "warning" as const }
          : { label: "Safety", value: "Normal", tone: "success" as const };

  const primaryCode = unresolvedOvercollectionReviewActive(state, scanDiagnostics)
    ? "review_overcollection"
    : canonicalPrimaryAction.key;
  const reviewOvercollectionAction = primaryCode === "review_overcollection";
  const responseSummary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};

  let alert: DouyinScannerMainViewModel["alert"] = null;
  if (reviewOvercollectionAction) {
    const reviewPresentation = buildOvercollectionReviewPresentation(scanDiagnostics);
    alert = { tone: "warning", title: reviewPresentation.title, message: reviewPresentation.description };
  } else if (state.safety.captcha_detected) {
    alert = { tone: "warning", title: PRODUCT_TERMS.securityCheck, message: "Solve it in the Douyin tab, then click Resume." };
  } else if (pausing) {
    alert = { tone: "warning", title: "Pausing collection", message: state.harvest.pause_message ?? "Pause requested. Stopping after the current video." };
  } else if (state.harvest.paused_reason === "backend_auth_required" || (state.harvest.paused_reason === "douyin_login_required" && state.harvest.pause_diagnostics && typeof state.harvest.pause_diagnostics === "object" && (state.harvest.pause_diagnostics as Record<string, unknown>).source === "hybrid_flush")) {
    alert = { tone: "warning", title: "Backend login required", message: state.harvest.pause_message ?? "Sign in to the app again in extension settings, then press Resume." };
  } else if (waitingForActiveTab) {
    alert = { tone: "warning", title: "Waiting for tab", message: state.harvest.pause_message ?? "Return to the Douyin tab to continue collecting." };
  } else if (pausedTabInactive || paused) {
    alert = { tone: "warning", title: "Collecting paused", message: state.harvest.pause_message ?? "Resume when the Douyin tab is ready again." };
  } else if (state.collect_job.state === "failed" && state.collect_job.last_error) {
    alert = { tone: "error", title: "Collect failed", message: state.collect_job.last_error };
  } else if (state.harvest.status === "failed" && state.last_error) {
    const errText = typeof state.last_error === "string" ? state.last_error : state.last_error.message;
    alert = { tone: "error", title: "Collect failed", message: errText };
  } else if (typeof responseSummary.hybrid_runner_outcome === "string" && responseSummary.hybrid_runner_outcome === "phase_4_4d_loop_all_failed") {
    const flushError = typeof responseSummary.hybrid_runner_backend_write_error_message === "string"
      ? responseSummary.hybrid_runner_backend_write_error_message
      : "Backend write failed. Open Advanced → Hybrid Runtime Test Log for details.";
    alert = { tone: "error", title: "Could not save to Capture Inbox", message: flushError };
  } else if (state.workflow.collection.status === "failed" && state.workflow.collection.last_error) {
    alert = { tone: "error", title: "Start Collecting blocked", message: `Start Collecting blocked:\n${state.workflow.collection.last_error}` };
  } else if (scanProgress.active) {
    alert = { tone: "info", title: "Scanning profile videos", message: scanProgress.detail };
  } else if (countSemanticsOverDisplayedNeedsValidation) {
    alert = { tone: "warning", title: "Scan needs review", message: "Scan needs review: API returned more videos than the profile displayed count. Retry Scan Profile or preserve diagnostics for same-profile validation review." };
  } else if (nearCompleteWarning.applied || (profileScanned && String(scanDiagnostics.scan_finalization_result ?? "") === "completed_with_warning")) {
    const warningMissing = nearCompleteWarning.gapCount
      ?? (expectedCount == null ? null : Math.max(expectedCount - videosFound, 0));
    const warningFoundCount = nearCompleteWarning.gapCount != null && expectedCount != null
      ? Math.max(0, expectedCount - nearCompleteWarning.gapCount)
      : videosFound;
    alert = countSemanticsOverDisplayedReady
      ? { tone: "warning", title: "API returned additional same-profile videos", message: `API returned ${overDisplayedCount ?? "additional"} additional same-profile videos beyond visible profile count. Visible profile count: ${expectedCount ?? "unknown"}. API collectable count: ${labeledCollectableCount ?? "unknown"}. Additional same-profile API videos: ${overDisplayedCount ?? "unknown"}.` }
      : expectedCountSemanticsMismatch
        ? { tone: "warning", title: "Scan completed with warning", message: `Scan completed: saved ${collectableCount} collectable videos. Douyin displays ${expectedCount ?? "unknown"}, but ${unavailableOrUnlistedCount ?? warningMissing ?? "some"} could not be found in the API or verified secondary sources.` }
        : { tone: "warning", title: "Scan completed with warning", message: `Scan completed with warning: found ${warningFoundCount} of ${expectedCount}. ${warningMissing ?? "Some"} videos may be unavailable, hidden, deleted, filtered, or not returned by Douyin. You can continue with the available videos or rescan.` };
  } else if (scanAuthority.warning) {
    alert = { tone: state.scan_job.status === "failed" ? "error" : "warning", title: "Current scan run unresolved", message: scanAuthority.warning };
  } else if (scanBudgetContinuation) {
    alert = { tone: "info", title: "Continue Scan", message: scanBudgetContinuationMessage(state, videosFound, expectedCount) };
  } else if (scanIncomplete) {
    const activeFailure = scanDiagnostics.scan_completeness_dom_only_fallback === "yes" || scanDiagnostics.scan_completeness_ready_blocked === "yes";
    const reason = typeof scanDiagnostics.scan_completeness_gate_reason === "string" ? scanDiagnostics.scan_completeness_gate_reason : "expected count was not reached";
    const completenessFound = numericDiagnosticValue(scanDiagnostics.scan_completeness_found_count) ?? videosFound;
    alert = { tone: activeFailure ? "error" : "warning", title: "Profile scan incomplete", message: activeFailure ? `Profile scan incomplete: active profile API failed; found ${completenessFound} of expected ${expectedCount} from page fallback. Retry Scan Profile. (${reason})` : `Profile scan incomplete: expected ${expectedCount}, collected ${videosFound}.` };
  } else if (state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed") {
    alert = { tone: "error", title: "Save failed", message: "Open Advanced for save details before retrying." };
  } else if (!isCollectCalibrationSatisfied(state) && state.calibration.status !== "calibrated" && state.calibration.point_count < 4) {
    alert = { tone: "info", title: "Calibration needed", message: "Click the four metric points before testing videos." };
  }

  const openCaptureInboxVisible = saved > 0 || state.harvest.backend.one_item_flush.status === "succeeded" || state.harvest.backend.batch_flush.status === "completed" || state.harvest.backend.batch_flush.status === "completed_with_warnings";
  const pauseOrResumeVisible = running || pausing || paused || waitingForActiveTab || pausedTabInactive || state.harvest.resume_available || actionState.resume.visible || actionState.stop.visible;
  const pauseOrResumeEnabled = pausing ? false : paused || waitingForActiveTab || pausedTabInactive ? actionState.resume.enabled : actionState.stop.enabled;
  const pauseOrResumeLabel = pausing ? "Pausing..." : paused || waitingForActiveTab || pausedTabInactive ? "Resume" : "Pause";

  const continuationPending = largeProfilePersistedTotal ?? (popupMetricsAuthoritative ? popupMetrics.profile.queue_count : pending);
  const batchContinuation = primaryCode === "start_collecting" && batchContinuationAvailable(state, continuationPending);
  const scanContinuation = primaryCode === "scan_profile" && scanBudgetContinuation;
  const continuationMessage = scanContinuation
    ? scanBudgetContinuationMessage(state, videosFound, expectedCount)
    : batchContinuation
      ? batchContinuationMessage(state, saved, continuationPending)
      : null;
  const primaryLabel = unresolvedOvercollectionReviewActive(state, scanDiagnostics)
    ? "Review Overcollection"
    : scanContinuation
    ? "Continue Scan"
    : batchContinuation
      ? batchContinuationButtonLabel(state)
      : canonicalPrimaryAction.label;
  const primaryReason = unresolvedOvercollectionReviewActive(state, scanDiagnostics)
    ? "Over-display exact-item validation is required before collecting."
    : continuationMessage ?? canonicalPrimaryAction.disabledReason ?? canonicalPrimaryAction.description;
  const runtimeProgressDiagnostics = {
    trace_progress_active_batch_runtime_required: runnerLock.diagnostics.trace_progress_active_batch_runtime_required,
    trace_progress_visible_status_source: runtimeVisibleStatusSource,
    trace_progress_visible_phase_source: runtimeVisiblePhaseSource,
    trace_progress_runtime_status_committed: runtimeVisibleStatusCommitted,
    trace_progress_runtime_phase_committed: runtimeVisiblePhaseCommitted
  };
  const activeBatchProcessed = typeof responseSummary.batch_processed_count === "number" ? responseSummary.batch_processed_count : state.harvest.updated;
  const activeBatchSelected = typeof responseSummary.batch_selected_count === "number" ? responseSummary.batch_selected_count : Math.max(activeBatchProcessed, pending + activeBatchProcessed, 1);
  const activeBatchSuccess = typeof responseSummary.batch_success_count === "number" ? responseSummary.batch_success_count : saved;
  const activeBatchProgressDetail = `Collecting batch: ${activeBatchProcessed}/${activeBatchSelected} processed, ${activeBatchSuccess} saved.`;

  let progressTone: DouyinScannerMainViewModel["progress"]["tone"] = "neutral";
  let progressValue = scanProgress.active && scanProgress.expected != null ? `${scanProgress.discovered}/${scanProgress.expected}` : `${state.harvest.updated}/${Math.max(state.harvest.planned_total, state.harvest.updated, videosFound)}`;
  let progressLabel = scanProgress.active
    ? "Scanning profile videos"
    : scanning
      ? "Scanning"
      : classifying
        ? "Classifying"
      : pausing
        ? "Pausing..."
        : runtimeActiveBatchRequired && runtimeVisiblePhaseCommitted === "opening_target"
          ? "Opening video"
          : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "waiting_for_active_tab"
            ? "Waiting for tab"
            : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "paused_tab_inactive"
              ? "Paused"
              : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "collecting"
                ? "Collecting"
                : openingTarget
                  ? "Opening video"
                  : waitingForActiveTab
                    ? "Waiting for tab"
                    : pausedTabInactive || paused
                      ? "Paused"
                      : collecting
                        ? "Collecting"
                        : extracted > 0
                          ? "Collected"
                          : videosFound > 0
                            ? "Scanned"
                            : "Idle";
  let progressDetail = continuationMessage ?? (pausing
    ? (state.harvest.pause_message ?? "Pause requested. Stopping after the current video.")
    : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "waiting_for_active_tab"
      ? (state.harvest.pause_message ?? "Return to the Douyin tab to continue collecting.")
      : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "paused_tab_inactive"
        ? (state.harvest.pause_message ?? "Resume when ready.")
        : waitingForActiveTab
          ? (state.harvest.pause_message ?? "Return to the Douyin tab to continue collecting.")
          : pausedTabInactive
            ? (state.harvest.pause_message ?? "Resume when ready.")
            : scanProgress.active
              ? `${scanProgress.detail} Pages fetched: ${scanProgress.pagesFetched}; requests: ${scanProgress.requestCount}.`
              : scanning
                ? "Scanning the current profile and discovering video cards."
                : classifying
                  ? "Classifying scanned videos and building the collection queue."
                : runtimeActiveBatchRequired && runtimeVisiblePhaseCommitted === "opening_target"
                  ? "Opening first video."
                  : runtimeActiveBatchRequired && runtimeVisibleStatusCommitted === "collecting"
                    ? activeBatchProgressDetail
                    : openingTarget
                      ? "Opening first video."
                      : collecting
                        ? activeBatchProgressDetail
                        : extracted > 0
                          ? `${extracted} collected, ${saved} saved to Capture Inbox.`
                          : videosFound > 0
                            ? scanBudgetContinuation
                              ? scanBudgetContinuationMessage(state, videosFound, expectedCount)
                              : countSemanticsOverDisplayedReady
                                ? `API returned ${overDisplayedCount ?? "additional"} additional same-profile videos beyond visible profile count. Visible profile count: ${expectedCount ?? "unknown"}. API collectable count: ${collectableCount ?? "unknown"}. Additional same-profile API videos: ${overDisplayedCount ?? "unknown"}.`
                                : countSemanticsOverDisplayedNeedsValidation
                                  ? "Scan needs review: API returned more videos than the profile displayed count. Retry Scan Profile or preserve diagnostics."
                                  : countSemanticsDisplayedMismatch
                                    ? `${collectableCount} collectable videos scanned. Douyin displays ${expectedCount ?? "unknown"}; ${unavailableOrUnlistedCount ?? "some"} were not listable by API after verification.`
                                    : `${videosFoundLabel} profile videos scanned. ${largeProfilePersistedTotal ?? popupMetrics.profile.queue_count} queued for collecting.`
                            : "Scan the current profile to prepare your first collection run.");

  if (state.harvest.backend.batch_flush.status === "failed" || state.harvest.backend.one_item_flush.status === "failed") progressTone = "danger";
  else if (pausing || paused || waitingForActiveTab || pausedTabInactive || state.safety.captcha_detected || state.safety.consecutive_errors > 0) progressTone = "warning";
  else if (running || collectActive || extracted > 0 || saved > 0) progressTone = "success";

  return {
    header_status: headerStatus,
    current_run_found_count: scanAuthority.current_run_found_count,
    persisted_total_count: scanAuthority.persisted_total_count,
    display_mode: scanAuthority.display_mode,
    mixed_state_warning: scanAuthority.warning,
    title: PRODUCT_TERMS.productName,
    subtitle: "Scan profile videos, collect metadata, then review in Capture Inbox.",
    status_chips: [tabHealth, apiHealth, calibrationHealth, safetyHealth],
    stats_summary: {
      title: "Compact scan stats",
      subtitle: `${profileLabel} · ${friendlyModeLabel(state.harvest_options.mode)} · ${friendlyBatchLabel(state.harvest_options.batch)} · ${friendlySpeedLabel(state.harvest_options.speed)}`,
      metrics: [
        { label: "Found this run", value: String(scanAuthority.current_run_found_count) },
        { label: "Persisted total", value: scanAuthority.persisted_total_count == null ? "none" : String(scanAuthority.persisted_total_count) },
        { label: "Videos found", value: videosFoundLabel },
        { label: "New", value: String(profileTileNewCount) },
        { label: "Queued", value: String(profileTileQueueCount) },
        { label: "Planned", value: String(state.harvest.planned_total) },
        { label: "Collected", value: String(extracted) },
        { label: "Saved", value: String(saved) }
      ]
    },
    primary_action: primaryCode === "open_capture_inbox"
      ? null
      : {
        key: primaryCode,
        label: primaryLabel,
        enabled: unresolvedOvercollectionReviewActive(state, scanDiagnostics) ? true : canonicalPrimaryAction.enabled,
        reason: primaryReason
      },
    progress: {
      label: progressLabel,
      value: progressValue,
      tone: progressTone,
      detail: progressDetail
    },
    footer_actions: {
      open_capture_inbox: {
        visible: openCaptureInboxVisible,
        enabled: openCaptureInboxVisible,
        label: PRODUCT_TERMS.openCaptureInbox
      },
      pause_or_resume: {
        visible: pauseOrResumeVisible,
        enabled: pauseOrResumeEnabled,
        label: pauseOrResumeLabel
      },
      advanced: {
        visible: true,
        label: "Advanced"
      },
      reset: {
        enabled: workflowReadiness.canReset,
        label: "Reset"
      }
    },
    alert
  };
}

export function getDouyinScannerMainViewModel(state: WholeProfileHarvestState): DouyinScannerMainViewModel {
  const viewModel = sanitizePopupViewState(getDouyinScannerMainViewModelUnreconciled(state), state);
  const authority = scanDisplayAuthority22C14B(state);
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const popupMetricsAuthoritative = popupMetrics.diagnostics.popup_metrics_profile_tiles_authority !== "scan_queue";
  const largeProfilePersistedTotal = authority.display_mode === "persisted_history_authority" || activeScanProgress22C14G(state).active ? null : largeProfilePersistedQueueTotal(state);
  const persistedTotalHasNewerAuthority = popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_newer_persisted_total === "yes";
  const collectActiveForProfileTiles = state.workflow.collection.status === "running"
    || state.workflow.active_task === "collect_videos"
    || isCollectJobVisiblyLive(state);
  viewModel.current_run_found_count = authority.current_run_found_count;
  viewModel.persisted_total_count = authority.persisted_total_count;
  viewModel.display_mode = authority.display_mode;
  viewModel.mixed_state_warning = authority.warning;
  if (shouldApplyLargeProfilePersistedTileCounts({
    largeProfilePersistedTotal,
    presentationBlocked: collectActiveForProfileTiles || scanBlocksCollectPresentation(state),
    largeProfileMode: scanDiagnosticsLargeProfileMode(state),
    popupMetricsAuthoritative,
    persistedTotalHasNewerAuthority,
    displayedProfileCollectLimit: resolveDisplayedProfileVideoLimit(scanDiagnosticsRecord(state))
  })) {
    const tiles = resolveLargeProfileTileCounts(
      largeProfilePersistedTotal!,
      popupMetrics.profile.already_collected_count,
      scanDiagnosticsLargeProfileMode(state)
    );
    for (const metric of viewModel.stats_summary.metrics) {
      if (metric.label === "New") metric.value = String(tiles.newCount);
      if (metric.label === "Queued") metric.value = String(tiles.queueCount);
    }
  }
  return viewModel;
}

function getWholeProfileHarvestProgressViewModelUnreconciled(state: WholeProfileHarvestState): WholeProfileHarvestProgressViewModel {
  const readiness = getWholeProfileHarvestReadiness(state);
  const actions = getWholeProfileHarvestActionState(state);
  const stepper: [
    WholeProfileHarvestStepperItem,
    WholeProfileHarvestStepperItem,
    WholeProfileHarvestStepperItem,
    WholeProfileHarvestStepperItem
  ] = [
    verifyStep(state, readiness),
    dryRunStep(state, readiness),
    extractionStep(state, readiness),
    flushStep(state, readiness)
  ];
  const lists = getHarvestQueueAndResultsViewModel(state);
  const targetCounts = state.target_status;
  const batchFlush = state.harvest.backend.batch_flush;
  const oneItemFlush = state.harvest.backend.one_item_flush;
  const payloadPreview = state.harvest.backend.payload_preview;
  const backendFlow = getBackendFlushFlowViewModel(state, readiness, actions);
  const authoritativeCounters = deriveAuthoritativeProfileCounters(state);
  const popupMetrics = deriveReconciledPopupMetrics(state);
  const largeProfilePersistedTotal = largeProfilePersistedQueueTotal(state);
  const largeProfileVisibleTotal = largeProfileVisibleQueueTotal(state);
  const scannerBusy = getDouyinScannerBusyState(state);
  const scannerWorkflowReadiness = getDouyinScannerWorkflowReadiness(state);
  const canonicalPrimaryAction = getCanonicalScannerPrimaryAction(state);
  const canonicalCalibration = getCanonicalCalibrationReady(state);
  const resetRequestSummary = state.debug.last_request_summary as Record<string, unknown> | null;
  const resetResponseSummary = state.debug.last_response_summary as Record<string, unknown> | null;
  const resumeDiagnostics = state.harvest.pause_diagnostics && typeof state.harvest.pause_diagnostics === "object" ? state.harvest.pause_diagnostics as Record<string, unknown> : {};
  const resumeDiagnosticValue = (key: string): string => {
    const value = resumeDiagnostics[key];
    return typeof value === "string" || typeof value === "number" ? String(value) : "none";
  };
  const scanDiagnostics = scanDiagnosticsRecord(state);
  const profileDomProbe = scanDiagnostics.profile_dom_probe && typeof scanDiagnostics.profile_dom_probe === "object"
    ? scanDiagnostics.profile_dom_probe as Record<string, unknown>
    : {};
  const scanActionTrace = scanDiagnostics.scan_profile_action_trace && typeof scanDiagnostics.scan_profile_action_trace === "object"
    ? scanDiagnostics.scan_profile_action_trace as Record<string, unknown>
    : {};
  const scanDiagnosticValue = (key: string): string => {
    const value = scanDiagnostics[key];
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "none";
  };
  const runtimeBuildIdValue = (key: "extension_runtime_build_id" | "background_runtime_build_id" | "popup_runtime_build_id" | "content_script_runtime_build_id"): string => scanDiagnosticValue(key);
  const runtimeBuildIdConsistentValue = (): string => {
    const extension = runtimeBuildIdValue("extension_runtime_build_id");
    const required = [runtimeBuildIdValue("background_runtime_build_id"), runtimeBuildIdValue("content_script_runtime_build_id")];
    if (extension === "none" || required.some((value) => value === "none")) return "no + missing_runtime_id";
    const popup = runtimeBuildIdValue("popup_runtime_build_id");
    if (popup !== "none" && popup !== extension) return "no";
    return required.every((value) => value === extension) ? "yes" : "no";
  };
  const profileDomProbeStatus = (): string => {
    const explicit = scanDiagnosticValue("profile_dom_probe_status");
    const message = scanDiagnosticValue("profile_dom_probe_message") !== "none" ? scanDiagnosticValue("profile_dom_probe_message") : scanDiagnosticValue("dom_probe_message_result");
    if (message === "ok" && scanDiagnosticValue("profile_dom_probe_completed_at") !== "none") return "completed";
    if (explicit !== "none") return explicit;
    if (["failed", "timeout", "error"].some((value) => message.toLowerCase().includes(value))) return message.toLowerCase().includes("timeout") ? "timeout" : "failed";
    return scanDiagnosticValue("profile_dom_probe_started_at") !== "none" ? "started" : "not_attempted";
  };
  const profileScanCount = (key: string, fallback: string): string => {
    const authoritative = authoritativeCounters.diagnostics[key];
    if (typeof authoritative === "string" || typeof authoritative === "number" || typeof authoritative === "boolean") return String(authoritative);
    return scanDiagnosticValue(key) !== "none" ? scanDiagnosticValue(key) : fallback;
  };
  const profileDomProbeDiagnosticValue = (key: string): string => {
    const value = profileDomProbe[key];
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "none";
  };
  const scanDiagnosticArrayValue = (key: string): string => {
    const value = scanDiagnostics[key];
    if (Array.isArray(value)) return value.length ? value.join(", ") : "[]";
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "none";
  };
  const scanDiagnosticNumberValue = (key: string): number | null => {
    const value = scanDiagnostics[key];
    const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
    return Number.isFinite(numeric) ? numeric : null;
  };
  const scanActionTraceValue = (key: string): string => {
    const value = scanActionTrace[key];
    return typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? String(value) : "none";
  };
  const profileScanIncompleteReasonValue = (): string => {
    const reason = profileScanCount("profile_scan_incomplete_reason", "none");
    if (reason !== "none") return reason;
    const incomplete = profileScanCount("profile_scan_incomplete", "none");
    if (incomplete === "no") return "no + scan_complete";
    if (incomplete === "yes") return "unknown";
    const finalization = scanDiagnosticValue("scan_finalization_result");
    if (finalization === "success") return "no + scan_complete";
    return "unknown";
  };
  const profileScanSourceLedgerValue = (): string => {
    const keys = ["profile_scan_stop_reason_source_ledger", "profile_scan_source_ledger", "scan_source_ledger"];
    for (const key of keys) {
      const value = scanDiagnostics[key];
      if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
      if (value && typeof value === "object" && !Array.isArray(value)) {
        const ledger = value as Record<string, unknown>;
        const requestedProfileUrl = typeof ledger.requested_profile_url === "string" ? ledger.requested_profile_url : "unknown";
        const networkCount = typeof ledger.network_profile_post_count === "number" ? ledger.network_profile_post_count : Number(ledger.network_profile_post_count ?? Number.NaN);
        const passiveNetworkCount = typeof ledger.network_profile_post_passive_count === "number" ? ledger.network_profile_post_passive_count : Number(ledger.network_profile_post_passive_count ?? Number.NaN);
        const activeNetworkCount = typeof ledger.network_profile_post_active_count === "number" ? ledger.network_profile_post_active_count : Number(ledger.network_profile_post_active_count ?? Number.NaN);
        const activeOnlyNetworkCount = typeof ledger.network_profile_post_active_only_count === "number" ? ledger.network_profile_post_active_only_count : Number(ledger.network_profile_post_active_only_count ?? Number.NaN);
        const domCount = typeof ledger.dom_profile_scoped_target_count === "number" ? ledger.dom_profile_scoped_target_count : Number(ledger.dom_profile_scoped_target_count ?? Number.NaN);
        const domSupplementCount = typeof ledger.dom_profile_scoped_supplement_count === "number" ? ledger.dom_profile_scoped_supplement_count : Number(ledger.dom_profile_scoped_supplement_count ?? Number.NaN);
        const domRejectedCount = typeof ledger.dom_profile_scoped_rejected_count === "number" ? ledger.dom_profile_scoped_rejected_count : Number(ledger.dom_profile_scoped_rejected_count ?? Number.NaN);
        const mergedCount = typeof ledger.merged_target_count === "number" ? ledger.merged_target_count : Number(ledger.merged_target_count ?? Number.NaN);
        const currentVideoSupplemented = ledger.current_video_supplemented === true ? "yes" : ledger.current_video_supplemented === false ? "no" : "unknown";
        const segments = [
          `requested=${requestedProfileUrl}`,
          `network_post=${Number.isFinite(networkCount) ? String(networkCount) : "unknown"}`,
          `dom_scoped=${Number.isFinite(domCount) ? String(domCount) : "unknown"}`,
          `dom_supplement=${Number.isFinite(domSupplementCount) ? String(domSupplementCount) : "unknown"}`,
          `dom_rejected=${Number.isFinite(domRejectedCount) ? String(domRejectedCount) : "unknown"}`,
          `current_video_supplemented=${currentVideoSupplemented}`,
          `merged=${Number.isFinite(mergedCount) ? String(mergedCount) : "unknown"}`
        ];
        if (Number.isFinite(passiveNetworkCount)) segments.push(`network_post_passive=${String(passiveNetworkCount)}`);
        if (Number.isFinite(activeNetworkCount)) segments.push(`network_post_active=${String(activeNetworkCount)}`);
        if (Number.isFinite(activeOnlyNetworkCount)) segments.push(`network_post_active_only=${String(activeOnlyNetworkCount)}`);
        return segments.join("; ");
      }
    }
    return "unknown";
  };
  const networkCollectionStopReasonValue = (): string => {
    const effective = scanDiagnosticValue("network_collection_stop_reason_effective");
    if (effective !== "none") return effective;
    const reason = scanDiagnosticValue("network_collection_stop_reason");
    if (reason !== "none") return reason;
    if (scanDiagnosticValue("network_post_exhausted_evidence_gate_passed_22C12B") === "no") return "no + exhaustion_evidence_not_strong";
    const networkProbeBatchesSeen = scanDiagnosticNumberValue("network_probe_batches_seen") ?? 0;
    const networkProfilePostUniqueCount = scanDiagnosticNumberValue("network_profile_post_unique_count") ?? 0;
    if (networkProbeBatchesSeen > 0 || networkProfilePostUniqueCount > 0) return "no + reason_not_reported";
    return "unknown";
  };
  const authoritativeStopReason = getAuthoritativeScanStopReason(scanDiagnostics);
  const activeProfilePostDiagnostics = (() => {
    const nested = scanDiagnostics.active_profile_post && typeof scanDiagnostics.active_profile_post === "object" && !Array.isArray(scanDiagnostics.active_profile_post)
      ? scanDiagnostics.active_profile_post as Record<string, unknown>
      : {};
    const text = (...values: unknown[]): string | null => {
      for (const value of values) {
        if (typeof value === "string" && value.trim()) return value.trim();
      }
      return null;
    };
    const yesNoUnknown = (value: unknown, fallback: "yes" | "no" | "unknown" = "unknown"): "yes" | "no" | "unknown" => {
      if (value === true || value === "true" || value === "yes" || value === 1) return "yes";
      if (value === false || value === "false" || value === "no" || value === 0) return "no";
      return fallback;
    };
    const trueFalseUnknown = (value: unknown): "true" | "false" | "unknown" => {
      if (value === true || value === "true" || value === "yes" || value === 1) return "true";
      if (value === false || value === "false" || value === "no" || value === 0) return "false";
      return "unknown";
    };
    const numberText = (...values: unknown[]): string => {
      for (const value of values) {
        const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
        if (Number.isFinite(numeric)) return String(Math.max(0, Math.round(numeric)));
      }
      return "0";
    };
    const numberOrText = (...values: unknown[]): string | null => {
      for (const value of values) {
        if (typeof value === "number" && Number.isFinite(value)) return String(Math.round(value));
        if (typeof value === "string" && value.trim()) return value.trim();
      }
      return null;
    };
    const compactJson = (value: unknown): string | null => {
      try {
        const serialized = JSON.stringify(value);
        if (!serialized || serialized === "{}" || serialized === "[]") return null;
        return serialized.length > 240 ? `${serialized.slice(0, 240)}…` : serialized;
      } catch {
        return null;
      }
    };
    const arrayText = (...values: unknown[]): string => {
      for (const value of values) {
        if (Array.isArray(value)) {
          const normalized = value
            .map((entry) => {
              if (typeof entry === "string") return entry.trim();
              if (typeof entry === "number" || typeof entry === "boolean") return String(entry);
              return compactJson(entry);
            })
            .filter((entry): entry is string => Boolean(entry));
          if (normalized.length > 0) return normalized.slice(0, 8).join(" | ");
        }
        const serialized = compactJson(value);
        if (serialized) return serialized;
      }
      return "none";
    };
    const notAttemptedReason = text(
      scanDiagnostics.active_profile_post_fetch_not_attempted_reason,
      scanDiagnostics.minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B,
      nested.not_attempted_reason
    ) ?? "none";
    const stopReason = text(
      scanDiagnostics.active_profile_post_fetch_stop_reason,
      scanDiagnostics.minimal_scan_active_profile_post_fetch_stop_reason_22C12B,
      nested.stop_reason
    ) ?? (notAttemptedReason !== "none" ? notAttemptedReason : "none");
    return {
      enabled: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_enabled
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_enabled_22C12B
          ?? nested.enabled
      ),
      attempted: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_attempted
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_attempted_22C12B
          ?? scanDiagnostics.api_pagination_attempted
          ?? nested.attempted,
        notAttemptedReason !== "none" ? "no" : "unknown"
      ),
      effectiveAttempted: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_effective_attempted
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_effective_attempted_22C13B
          ?? nested.effective_attempted
      ),
      effectiveAttemptReason: text(
        scanDiagnostics.expected_count_finalization_gate_active_profile_post_effective_attempt_reason_22C13B,
        scanDiagnostics.active_profile_post_fetch_effective_attempt_reason,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B,
        nested.effective_attempt_reason
      ) ?? "none",
      stopReason,
      notAttemptedReason,
      targetCount: numberText(
        scanDiagnostics.active_profile_post_fetch_target_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_target_count_22C12B,
        scanDiagnostics.api_pagination_total_persisted_targets,
        scanDiagnostics.api_pagination_total_accepted_targets,
        nested.target_count
      ),
      hasMoreState: trueFalseUnknown(
        scanDiagnostics.active_profile_post_fetch_has_more_state
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_has_more_state_22C12B
          ?? scanDiagnostics.api_pagination_final_has_more
          ?? scanDiagnostics.api_pagination_has_more_final
          ?? nested.has_more_state
      ),
      onlyAwemeCount: numberText(
        scanDiagnostics.active_profile_post_only_aweme_count,
        scanDiagnostics.minimal_scan_active_profile_post_only_aweme_count_22C12B,
        nested.only_aweme_count
      ),
      requestCount: numberText(
        scanDiagnostics.active_profile_post_fetch_request_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_request_count_22C12B,
        scanDiagnostics.api_pagination_request_count,
        scanDiagnostics.scan_job_request_count,
        nested.request_count
      ),
      batchCount: numberText(
        scanDiagnostics.active_profile_post_fetch_batch_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_batch_count_22C12B,
        nested.batch_count
      ),
      pageCount: numberText(
        scanDiagnostics.active_profile_post_fetch_page_count,
        scanDiagnostics.api_pagination_page_count,
        scanDiagnostics.scan_job_pages_fetched,
        nested.page_count
      ),
      pageCap: numberText(
        scanDiagnostics.active_profile_post_fetch_page_cap,
        nested.page_cap
      ),
      pageCapHitCount: numberText(
        scanDiagnostics.active_profile_post_fetch_page_cap_hit_count,
        nested.page_cap_hit_count
      ),
      pageCapHitWhileHasMoreCount: numberText(
        scanDiagnostics.active_profile_post_fetch_page_cap_hit_while_has_more_count,
        nested.page_cap_hit_while_has_more_count
      ),
      runtimeTimeoutMs: numberText(
        scanDiagnostics.active_profile_post_fetch_runtime_timeout_ms,
        nested.runtime_timeout_ms
      ),
      runtimeTimeoutHit: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_runtime_timeout_hit
          ?? nested.runtime_timeout_hit
      ),
      continuationPolicy: text(
        scanDiagnostics.active_profile_post_fetch_continuation_policy,
        nested.continuation_policy
      ) ?? "none",
      fallbackCycleEligible: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_eligible
          ?? nested.fallback_cycle_eligible
      ),
      fallbackCycleAttempted: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_attempted
          ?? nested.fallback_cycle_attempted
      ),
      fallbackCycleStopReason: text(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_stop_reason,
        nested.fallback_cycle_stop_reason
      ) ?? "none",
      fallbackCycleHasMoreState: trueFalseUnknown(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_has_more_state
          ?? nested.fallback_cycle_has_more_state
      ),
      fallbackCycleRequestCount: numberText(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_request_count,
        nested.fallback_cycle_request_count
      ),
      fallbackCycleBatchCount: numberText(
        scanDiagnostics.active_profile_post_fetch_fallback_cycle_batch_count,
        nested.fallback_cycle_batch_count
      ),
      error: text(
        scanDiagnostics.active_profile_post_fetch_error,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_error_22C12B,
        nested.error
      ) ?? "none",
      responseShape: text(
        scanDiagnostics.active_profile_post_fetch_response_shape,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_shape_22C12B,
        nested.response_shape
      ) ?? "unknown",
      endpointVariantAttemptCount: numberText(
        scanDiagnostics.active_profile_post_fetch_endpoint_variant_attempt_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B,
        nested.endpoint_variant_attempt_count
      ),
      endpointVariantSuccess: text(
        scanDiagnostics.active_profile_post_fetch_endpoint_variant_success,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B,
        nested.endpoint_variant_success
      ) ?? "none",
      endpointAttemptSamples: arrayText(
        scanDiagnostics.active_profile_post_fetch_endpoint_attempt_samples,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B,
        nested.endpoint_attempt_samples
      ),
      parserRoute: text(
        scanDiagnostics.active_profile_post_fetch_parser_route,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_route_22C12B,
        nested.parser_route
      ) ?? "none",
      parserRoutesTried: arrayText(
        scanDiagnostics.active_profile_post_fetch_parser_routes_tried,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B,
        nested.parser_routes_tried
      ),
      parserDirectRoutesTried: arrayText(
        scanDiagnostics.active_profile_post_fetch_parser_direct_routes_tried,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B,
        nested.parser_direct_routes_tried
      ),
      parserDirectMatchCount: numberText(
        scanDiagnostics.active_profile_post_fetch_parser_direct_match_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B,
        nested.parser_direct_match_count
      ),
      parserFallbackAttempted: yesNoUnknown(
        scanDiagnostics.active_profile_post_fetch_parser_fallback_attempted
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B
          ?? nested.parser_fallback_attempted
      ),
      parserFallbackMatchCount: numberText(
        scanDiagnostics.active_profile_post_fetch_parser_fallback_match_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B,
        nested.parser_fallback_match_count
      ),
      parserFallbackCandidateCount: numberText(
        scanDiagnostics.active_profile_post_fetch_parser_fallback_candidate_count,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B,
        nested.parser_fallback_candidate_count
      ),
      parserFallbackVisitedNodes: numberText(
        scanDiagnostics.active_profile_post_fetch_parser_fallback_visited_nodes,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B,
        nested.parser_fallback_visited_nodes
      ),
      templateFound: yesNoUnknown(
        scanDiagnostics.active_profile_post_template_found
          ?? scanDiagnostics.minimal_scan_active_profile_post_template_found_22C13B
          ?? nested.template_found
      ),
      templateSource: text(
        scanDiagnostics.active_profile_post_template_source,
        scanDiagnostics.minimal_scan_active_profile_post_template_source_22C13B,
        nested.template_source
      ) ?? "none",
      templateEndpointPath: text(
        scanDiagnostics.active_profile_post_template_endpoint_path,
        scanDiagnostics.minimal_scan_active_profile_post_template_endpoint_path_22C13B,
        nested.template_endpoint_path
      ) ?? "none",
      templateQueryKeys: arrayText(
        scanDiagnostics.active_profile_post_template_query_keys,
        scanDiagnostics.minimal_scan_active_profile_post_template_query_keys_22C13B,
        nested.template_query_keys
      ),
      templateRequiredQueryKeys: arrayText(
        scanDiagnostics.active_profile_post_template_required_query_keys,
        scanDiagnostics.minimal_scan_active_profile_post_template_required_query_keys_22C13B,
        nested.template_required_query_keys
      ),
      templateRequiredQueryKeysAvailable: yesNoUnknown(
        scanDiagnostics.active_profile_post_template_required_query_keys_available
          ?? scanDiagnostics.minimal_scan_active_profile_post_template_required_query_keys_available_22C13B
          ?? nested.template_required_query_keys_available
      ),
      templateMissingRequiredQueryKeys: arrayText(
        scanDiagnostics.active_profile_post_template_missing_required_query_keys,
        scanDiagnostics.minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B,
        nested.template_missing_required_query_keys
      ),
      templateSecretKeysPresent: yesNoUnknown(
        scanDiagnostics.active_profile_post_template_secret_keys_present
          ?? scanDiagnostics.minimal_scan_active_profile_post_template_secret_keys_present_22C13B
          ?? nested.template_secret_keys_present
      ),
      templateSecretQueryKeys: arrayText(
        scanDiagnostics.active_profile_post_template_secret_query_keys,
        scanDiagnostics.minimal_scan_active_profile_post_template_secret_query_keys_22C13B,
        nested.template_secret_query_keys
      ),
      templateWarmupAttempted: yesNoUnknown(
        scanDiagnostics.active_profile_post_template_warmup_attempted
          ?? scanDiagnostics.minimal_scan_active_profile_post_template_warmup_attempted_22C13B
          ?? nested.template_warmup_attempted
      ),
      templateWarmupAttemptCount: numberText(
        scanDiagnostics.active_profile_post_template_warmup_attempt_count,
        scanDiagnostics.minimal_scan_active_profile_post_template_warmup_attempt_count_22C13B,
        nested.template_warmup_attempt_count
      ),
      templateWarmupAppliedTemplate: yesNoUnknown(
        scanDiagnostics.active_profile_post_template_warmup_applied_template
          ?? scanDiagnostics.minimal_scan_active_profile_post_template_warmup_applied_template_22C13B
          ?? nested.template_warmup_applied_template
      ),
      templateWarmupStopReason: text(
        scanDiagnostics.active_profile_post_template_warmup_stop_reason,
        scanDiagnostics.minimal_scan_active_profile_post_template_warmup_stop_reason_22C13B,
        nested.template_warmup_stop_reason
      ) ?? "none",
      expectedCountFinalizationGatePolicy: text(
        scanDiagnostics.expected_count_finalization_gate_policy_22C13B,
        scanDiagnostics.minimal_scan_expected_count_finalization_gate_policy_22C13B
      ) ?? "none",
      expectedCountFinalizationGateActiveProfilePostMeaningfulAttempt: yesNoUnknown(
        scanDiagnostics.expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B
          ?? scanDiagnostics.minimal_scan_expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B
      ),
      expectedCountFinalizationGateDomOnlyConvergenceDetected: yesNoUnknown(
        scanDiagnostics.minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B
      ),
      expectedCountFinalizationGateDomOnlyConvergenceAllowed: yesNoUnknown(
        scanDiagnostics.minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B
      ),
      responseStatusCode: numberOrText(
        scanDiagnostics.active_profile_post_fetch_response_status_code,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_status_code_22C13B,
        nested.response_status_code
      ) ?? "none",
      responseStatusMsg: text(
        scanDiagnostics.active_profile_post_fetch_response_status_msg,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_status_msg_22C13B,
        nested.response_status_msg
      ) ?? "none",
      responseTopLevelKeys: arrayText(
        scanDiagnostics.active_profile_post_fetch_response_top_level_keys,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B,
        nested.response_top_level_keys
      ),
      responseDataKeys: arrayText(
        scanDiagnostics.active_profile_post_fetch_response_data_keys,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_data_keys_22C13B,
        nested.response_data_keys
      ),
      responseResultKeys: arrayText(
        scanDiagnostics.active_profile_post_fetch_response_result_keys,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_response_result_keys_22C13B,
        nested.response_result_keys
      ),
      parserPathCounts: compactJson(
        scanDiagnostics.active_profile_post_fetch_parser_path_counts
          ?? scanDiagnostics.minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B
          ?? nested.parser_path_counts
      ) ?? "none",
      listSampleKeys: arrayText(
        scanDiagnostics.active_profile_post_fetch_list_sample_keys,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B,
        nested.list_sample_keys
      ),
      rejectReasons: arrayText(
        scanDiagnostics.active_profile_post_fetch_reject_reasons,
        scanDiagnostics.minimal_scan_active_profile_post_fetch_reject_reasons_22C13B,
        nested.reject_reasons
      )
    };
  })();
  const traceValue = (value: unknown): string | number | boolean | null => typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? value : null;
  const traceString = (value: unknown): string | null => typeof value === "string" && value.trim() ? value : null;
  const traceProfileUrl = traceString(scanDiagnostics.profile_url) ?? traceString(scanDiagnostics.tab_url) ?? state.profile_url ?? state.page_context.current_url;
  const traceProfileIdentifier = traceString(scanDiagnostics.post_scan_backend_reconciliation_profile_identifier) ?? traceString(state.post_scan_counter_snapshot?.profile_identifier) ?? traceString(traceProfileUrl?.match(/\/user\/([^/?#]+)/i)?.[1]);
  const traceBackendCalled = scanDiagnostics.post_scan_backend_reconciliation_status != null || scanDiagnostics.post_scan_backend_profile_response_status != null || scanDiagnostics.post_scan_backend_captured_count != null;
  const traceRawShapeKeys = Array.isArray(scanDiagnostics.post_scan_backend_summary_raw_shape_keys)
    ? scanDiagnostics.post_scan_backend_summary_raw_shape_keys.join(", ")
    : traceValue(scanDiagnostics.post_scan_backend_summary_raw_shape_keys);
  const traceCounterAuthorityBlocked = scanDiagnostics.backend_reconciliation_skipped_for_incomplete_scan === "yes"
    || scanDiagnostics.post_scan_snapshot_skipped_for_incomplete_scan === "yes"
    || scanDiagnostics.counter_authority_blocked_for_incomplete_scan === "yes"
    || scanDiagnostics.legacy_dom_written_as_diagnostic_only === "yes";
  const scanUsableByReadiness = scannerWorkflowReadiness.profileScanReady === true || state.layer.profile_scan_ready === true;
  const traceScanReady = scanUsableByReadiness && state.status === "verified" && state.profile_scan.status === "success" && state.verify.status === "success";
  const traceScanUsable = traceScanReady && !traceCounterAuthorityBlocked ? "yes" : "no";
  const traceScanCompleted = traceScanUsable;
  const traceScanIncomplete = traceScanCompleted !== "yes";
  const postScanCounterPipelineTrace = {
    scan_result: {
      trace_scan_completed: traceScanCompleted,
      trace_scan_usable: traceScanUsable,
      trace_scan_profile_url: traceProfileUrl ?? null,
      trace_scan_profile_identifier: traceProfileIdentifier,
      trace_scan_total_count: popupMetrics.profile.profile_total_count,
      trace_scan_queue_count: state.harvest.queue.length,
      trace_scan_completed_at: state.profile_scan.status === "success" ? scanDiagnosticValue("scan_finalized_at") !== "none" ? scanDiagnosticValue("scan_finalized_at") : state.verify.completed_at : null
    },
    backend_summary_request: {
      trace_backend_summary_called: traceScanIncomplete && scanDiagnostics.backend_reconciliation_skipped_for_incomplete_scan === "yes" ? "no" : traceBackendCalled ? "yes" : "no",
      trace_backend_summary_call_location: traceBackendCalled ? "post_scan_reconcileProfileQueueWithBackend" : "none",
      trace_backend_summary_endpoint: traceBackendCalled ? "/douyin-extension/capture-inbox/profile-items" : "none",
      trace_backend_summary_request_profile_identifier: traceProfileIdentifier,
      trace_backend_summary_request_profile_url: traceProfileUrl ?? null,
      trace_backend_summary_request_after_scan: traceBackendCalled ? "yes" : "no",
      trace_backend_summary_called_at: traceValue(scanDiagnostics.post_scan_backend_summary_called_at) ?? traceValue(scanDiagnostics.scan_finalized_at),
      trace_backend_summary_error: traceValue(scanDiagnostics.post_scan_counter_fallback_reason) ?? traceValue(scanDiagnostics.post_scan_backend_reconciliation_error)
    },
    backend_summary_response: {
      trace_backend_summary_status: traceValue(scanDiagnostics.post_scan_backend_reconciliation_status),
      trace_backend_summary_http_status: traceValue(scanDiagnostics.post_scan_backend_profile_response_status),
      trace_backend_summary_response_profile_identifier: traceValue(scanDiagnostics.post_scan_backend_reconciliation_profile_identifier),
      trace_backend_summary_captured: traceValue(scanDiagnostics.post_scan_backend_captured_count),
      trace_backend_summary_ready: traceValue(scanDiagnostics.post_scan_backend_ready_count),
      trace_backend_summary_dup: traceValue(scanDiagnostics.post_scan_backend_duplicate_count),
      trace_backend_summary_fail: traceValue(scanDiagnostics.post_scan_backend_failed_count),
      trace_backend_summary_raw_shape_keys: traceRawShapeKeys,
      trace_backend_summary_used_capture_inbox_card_source: scanDiagnostics.post_scan_counter_snapshot_source === "capture_inbox_profile_card_counts" || state.post_scan_counter_snapshot?.source === "backend_capture_inbox_profile_summary" ? "yes" : "no"
    },
    snapshot_state: {
      trace_counter_snapshot_exists: traceCounterAuthorityBlocked ? "no" : state.post_scan_counter_snapshot ? "yes" : "no",
      trace_counter_snapshot_source: state.post_scan_counter_snapshot?.source ?? null,
      trace_counter_snapshot_status: state.post_scan_counter_snapshot?.status ?? null,
      trace_counter_snapshot_scanned_total: state.post_scan_counter_snapshot?.scanned_total ?? null,
      trace_counter_snapshot_backend_captured: state.post_scan_counter_snapshot?.backend_captured ?? null,
      trace_counter_snapshot_backend_ready: state.post_scan_counter_snapshot?.backend_ready ?? null,
      trace_counter_snapshot_backend_dup: state.post_scan_counter_snapshot?.backend_dup ?? null,
      trace_counter_snapshot_backend_fail: state.post_scan_counter_snapshot?.backend_fail ?? null,
      trace_counter_snapshot_new: state.post_scan_counter_snapshot?.new ?? null,
      trace_counter_snapshot_incomplete: state.post_scan_counter_snapshot?.incomplete ?? null,
      trace_counter_snapshot_need_retry: state.post_scan_counter_snapshot?.need_retry ?? null,
      trace_counter_snapshot_already_collected: state.post_scan_counter_snapshot?.already_collected ?? null,
      trace_counter_snapshot_queue: state.post_scan_counter_snapshot?.queue ?? null,
      trace_counter_snapshot_stored_at: state.post_scan_counter_snapshot?.applied_at ?? null,
      trace_counter_snapshot_storage_key: WHOLE_PROFILE_HARVEST_STATE_KEY
    },
    final_popup_render_input: {
      trace_popup_tiles_render_source: String(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority),
      trace_popup_tiles_render_object_new: popupMetrics.profile.new_count,
      trace_popup_tiles_render_object_incomplete: popupMetrics.profile.incomplete_count,
      trace_popup_tiles_render_object_need_retry: popupMetrics.profile.need_retry_count,
      trace_popup_tiles_render_object_already_collected: popupMetrics.profile.already_collected_count,
      trace_popup_tiles_render_object_queue: popupMetrics.profile.queue_count,
      trace_popup_tiles_render_used_snapshot: traceCounterAuthorityBlocked ? "no" : popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "post_scan_counter_snapshot" ? "yes" : "no",
      trace_popup_tiles_render_ignored_raw_scan_queue: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "post_scan_counter_snapshot" && state.harvest.queue.length !== popupMetrics.profile.queue_count ? "yes" : "no",
      trace_popup_tiles_render_ignored_raw_pending: popupMetrics.diagnostics.popup_metrics_raw_pending_ignored_for_profile_tiles === true ? "yes" : "no",
      trace_popup_tiles_render_ignored_legacy_counters: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "post_scan_counter_snapshot" ? "yes" : "no",
      trace_popup_tiles_rendered_at: new Date().toISOString()
    }
  };
  const collectRequestDiagnostics = state.debug.last_request_summary && typeof state.debug.last_request_summary === "object" ? state.debug.last_request_summary as Record<string, unknown> : {};
  const collectResponseDiagnostics = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object" ? state.debug.last_response_summary as Record<string, unknown> : {};
  const activeCollectRuntime = state.active_collect_runtime;
  const activeCollectRuntimeSummary = activeCollectRuntime.trace.summary && typeof activeCollectRuntime.trace.summary === "object" ? activeCollectRuntime.trace.summary as Record<string, unknown> : {};
  const activeCollectRuntimeQueueFiltering = activeCollectRuntime.trace.queue_filtering && typeof activeCollectRuntime.trace.queue_filtering === "object" ? activeCollectRuntime.trace.queue_filtering as Record<string, unknown> : {};
  const activeCollectRuntimePerItemWrites = activeCollectRuntime.trace.per_item_backend_writes && typeof activeCollectRuntime.trace.per_item_backend_writes === "object" ? activeCollectRuntime.trace.per_item_backend_writes as Record<string, unknown> : {};
  const activeCollectRuntimeTiming = activeCollectRuntime.trace.timing && typeof activeCollectRuntime.trace.timing === "object" ? activeCollectRuntime.trace.timing as Record<string, unknown> : {};
  const activeCollectRuntimeActive = !collectCompletionOverridesActiveCollectRuntime(state) && activeCollectRuntime.job_id !== null && (activeCollectRuntime.canonical_state === "starting" || activeCollectRuntime.canonical_state === "running" || activeCollectRuntime.canonical_state === "waiting_for_active_tab" || activeCollectRuntime.canonical_state === "paused_tab_inactive" || activeCollectRuntime.canonical_state === "recoverable_stuck" || activeCollectRuntime.canonical_state === "start_failed_recoverable");
  const collectionDisplayStatus = activeCollectRuntimeActive ? activeCollectRuntime.canonical_state : state.workflow.collection.status;
  const collectDiagnosticsBase: Record<string, unknown> = {
    ...collectRequestDiagnostics,
    ...collectResponseDiagnostics
  };
  const activeCollectRuntimeOverlay: Record<string, unknown> = activeCollectRuntimeActive
    ? {
      ...activeCollectRuntimeSummary,
      trace_canonical_collect_state: activeCollectRuntime.canonical_state,
      trace_collect_job_popup_render_state: activeCollectRuntime.canonical_state,
      trace_collect_job_id: activeCollectRuntime.job_id,
      trace_collect_job_current_step: activeCollectRuntime.current_step,
      trace_collect_job_current_aweme_id: activeCollectRuntime.current_aweme_id,
      trace_collect_job_current_item_index: activeCollectRuntime.current_item_index,
      trace_collect_job_batch_limit: activeCollectRuntime.batch_limit,
      trace_collect_job_selected_count: activeCollectRuntime.selected_count,
      trace_collect_job_attempted_count: activeCollectRuntime.attempted_count,
      trace_collect_job_succeeded_count: activeCollectRuntime.succeeded_count,
      trace_collect_job_failed_count: activeCollectRuntime.failed_count,
      trace_collect_job_skipped_count: activeCollectRuntime.skipped_count,
      trace_collect_pre_batch_backend_captured: activeCollectRuntime.pre_batch_backend_captured,
      trace_collect_pre_batch_backend_ready: activeCollectRuntime.pre_batch_backend_ready,
      trace_collect_pre_batch_backend_dup: activeCollectRuntime.pre_batch_backend_dup,
      trace_collect_pre_batch_backend_fail: activeCollectRuntime.pre_batch_backend_fail,
      trace_collect_pre_batch_new: activeCollectRuntime.pre_batch_new,
      trace_collect_pre_batch_queue: activeCollectRuntime.pre_batch_queue,
      trace_collect_popup_already_collected: activeCollectRuntime.latest_progress_captured,
      trace_collect_popup_queue: activeCollectRuntime.latest_progress_queue,
      trace_collect_popup_new: activeCollectRuntime.latest_progress_new,
      trace_collect_job_heartbeat_at: activeCollectRuntime.heartbeat_at,
      trace_collect_job_lock_owner: activeCollectRuntime.lock_owner,
      trace_collect_job_lock_expires_at: activeCollectRuntime.lock_expires_at,
      trace_collect_runtime_generation: activeCollectRuntime.runtime_generation,
      trace_collect_runtime_render_generation: activeCollectRuntime.render_generation,
      trace_collect_runtime_last_update_source: activeCollectRuntime.last_update_source,
      queue_filtering: activeCollectRuntimeQueueFiltering,
      batch_item_loop_entered: activeCollectRuntimePerItemWrites.batch_item_loop_entered,
      batch_item_loop_selected_count: activeCollectRuntimePerItemWrites.batch_item_loop_selected_count,
      batch_item_loop_attempted_count: activeCollectRuntimePerItemWrites.batch_item_loop_attempted_count,
      batch_item_loop_returned_count: activeCollectRuntimePerItemWrites.batch_item_loop_returned_count,
      batch_item_loop_result_appended_count: activeCollectRuntimePerItemWrites.batch_item_loop_result_appended_count,
      batch_item_loop_exit_reason: activeCollectRuntimePerItemWrites.batch_item_loop_exit_reason,
      batch_item_loop_last_stage: activeCollectRuntimePerItemWrites.batch_item_loop_last_stage,
      batch_item_loop_current_aweme_id: activeCollectRuntimePerItemWrites.batch_item_loop_current_aweme_id,
      batch_item_loop_current_index: activeCollectRuntimePerItemWrites.batch_item_loop_current_index,
      recent_batch_item_results: Array.isArray(activeCollectRuntimePerItemWrites.recent_batch_item_results) ? activeCollectRuntimePerItemWrites.recent_batch_item_results : [],
      trace_collect_batch_timing_total_ms: activeCollectRuntimeTiming.trace_collect_batch_timing_total_ms,
      trace_collect_batch_timing_avg_item_ms: activeCollectRuntimeTiming.trace_collect_batch_timing_avg_item_ms,
      trace_collect_batch_timing_item_count: activeCollectRuntimeTiming.trace_collect_batch_timing_item_count,
      trace_collect_batch_timing_recent_items: activeCollectRuntimeTiming.trace_collect_batch_timing_recent_items
    }
    : {};
  const collectDiagnostics: Record<string, unknown> = {
    ...collectDiagnosticsBase,
    ...activeCollectRuntimeOverlay
  };
  const collectInitialSnapshot = state.post_scan_counter_snapshot;
  const collectItemResults = Array.isArray(collectDiagnostics.recent_batch_item_results) ? collectDiagnostics.recent_batch_item_results : [];
  const collectJob = state.collect_job;
  const collectJobHeartbeatAt = typeof collectJob.heartbeat_at === "string" ? Date.parse(collectJob.heartbeat_at) : Number.NaN;
  const collectJobUpdatedAt = typeof collectJob.updated_at === "string" ? Date.parse(collectJob.updated_at) : Number.NaN;
  const collectJobReferenceAt = Number.isFinite(collectJobHeartbeatAt) ? collectJobHeartbeatAt : Number.isFinite(collectJobUpdatedAt) ? collectJobUpdatedAt : null;
  const collectJobHeartbeatAgeMs = collectJobReferenceAt === null ? null : Math.max(0, Date.now() - collectJobReferenceAt);
  const collectJobLockExpiresAt = typeof collectJob.lock_expires_at === "string" ? Date.parse(collectJob.lock_expires_at) : Number.NaN;
  const collectJobActive = collectJob.state === "starting" || collectJob.state === "running" || collectJob.state === "running_tab_inactive" || collectJob.state === "waiting_for_active_tab" || collectJob.state === "paused_tab_inactive" || collectJob.state === "recovering";
  const collectJobRawLockExpired = Number.isFinite(collectJobLockExpiresAt) ? collectJobLockExpiresAt <= Date.now() : false;
  const collectJobMayBeAlive = collectDiagnostics.trace_collect_job_may_be_alive === "yes" || collectDiagnostics.trace_collect_stale_check_may_be_alive === "yes" || collectDiagnostics.trace_collect_runtime_authoritative === "yes";
  const collectJobFreshLiveHeartbeat = collectJobActive && collectJobHeartbeatAgeMs !== null && collectJobHeartbeatAgeMs <= 30_000 && collectJobMayBeAlive;
  const collectJobLockExpired = collectJobRawLockExpired && !collectJobFreshLiveHeartbeat;
  const persistentCollectJobTrace = {
    trace_collect_job_id: collectJob.job_id,
    trace_collect_job_state: collectJob.state,
    trace_collect_job_created: collectJob.started_at ? "yes" : "no",
    trace_collect_job_loaded_on_popup_open: collectDiagnostics.trace_collect_job_loaded_on_popup_open === true || collectDiagnostics.trace_collect_job_loaded_on_popup_open === "yes" ? "yes" : "unknown",
    trace_collect_job_storage_key: traceString(collectDiagnostics.trace_collect_job_storage_key) ?? "douyinWholeProfileHarvest",
    trace_collect_job_profile_identifier: collectJob.profile_identifier,
    trace_collect_job_normalized_profile_identifier: collectJob.normalized_profile_identifier,
    trace_collect_job_started_at: collectJob.started_at,
    trace_collect_job_updated_at: collectJob.updated_at,
    trace_collect_job_heartbeat_at: collectJob.heartbeat_at,
    trace_collect_job_heartbeat_age_ms: traceValue(collectDiagnostics.trace_collect_job_heartbeat_age_ms) ?? collectJobHeartbeatAgeMs,
    trace_collect_job_heartbeat_stale: collectDiagnostics.trace_collect_job_heartbeat_stale === true ? "yes" : collectDiagnostics.trace_collect_job_heartbeat_stale === false ? "no" : collectJobActive && (collectJobHeartbeatAgeMs === null || collectJobHeartbeatAgeMs > 30_000) ? "yes" : "no",
    trace_collect_job_heartbeat_threshold_ms: traceValue(collectDiagnostics.trace_collect_job_heartbeat_threshold_ms) ?? 30_000,
    trace_collect_job_current_step: collectJob.current_step,
    trace_collect_job_current_aweme_id: collectJob.current_aweme_id,
    trace_collect_job_current_item_index: collectJob.current_item_index,
    trace_collect_job_batch_limit: collectJob.batch_limit,
    trace_collect_job_selected_count: collectJob.selected_count,
    trace_collect_job_attempted_count: collectJob.attempted_count,
    trace_collect_job_succeeded_count: collectJob.succeeded_count,
    trace_collect_job_failed_count: collectJob.failed_count,
    trace_collect_job_skipped_count: collectJob.skipped_count,
    trace_collect_job_pre_batch_backend_captured: collectJob.pre_batch_backend_captured,
    trace_collect_job_post_batch_backend_captured: collectJob.post_batch_backend_captured,
    trace_collect_job_batch_delta_captured: collectJob.batch_delta_captured,
    trace_collect_job_lock_owner: collectJob.lock_owner,
    trace_collect_job_lock_acquired_at: collectJob.lock_acquired_at,
    trace_collect_job_lock_expires_at: collectJob.lock_expires_at,
    trace_collect_job_lock_expired: collectJobLockExpired,
    trace_collect_job_lock_expired_raw: collectJobRawLockExpired,
    trace_collect_job_lock_expired_suppressed: collectJobRawLockExpired && !collectJobLockExpired ? "yes" : "no",
    trace_collect_job_lock_expired_suppressed_reason: collectJobRawLockExpired && !collectJobLockExpired ? "fresh_live_heartbeat_progress" : null,
    trace_collect_job_lock_released: collectJob.lock_released,
    trace_collect_job_recoverable: collectJob.recoverable,
    trace_collect_job_stale_reason: collectJob.stale_reason,
    trace_collect_job_popup_render_state: collectDiagnostics.trace_collect_job_popup_render_state ?? (collectJobActive ? collectJob.state === "waiting_for_active_tab" || collectJob.state === "running_tab_inactive" || collectJob.state === "paused_tab_inactive" ? collectJob.state : "running" : collectJob.state),
    trace_collect_job_soft_stale: collectDiagnostics.trace_collect_job_soft_stale ?? "unknown",
    trace_collect_job_hard_stale: collectDiagnostics.trace_collect_job_hard_stale ?? "unknown",
    trace_collect_job_may_be_alive: collectDiagnostics.trace_collect_job_may_be_alive ?? "unknown",
    trace_collect_job_tab_inactive_state: collectDiagnostics.trace_collect_job_tab_inactive_state ?? null,
    trace_collect_job_non_destructive_stale_check: collectDiagnostics.trace_collect_job_non_destructive_stale_check ?? "unknown",
    trace_collect_job_action_blocked_reason: collectDiagnostics.trace_collect_job_action_blocked_reason ?? null,
    trace_collect_job_recovery_available: collectDiagnostics.trace_collect_job_recovery_available === true || collectJob.recoverable || collectJobLockExpired,
    trace_collect_job_stale_lock_cleared: collectDiagnostics.trace_collect_job_stale_lock_cleared === true ? "yes" : collectDiagnostics.trace_collect_job_stale_lock_cleared === false ? "no" : "unknown",
    trace_collect_job_final_state: collectDiagnostics.trace_collect_job_state_at_finish ?? collectJob.state
  };
  const postCollectPipelineTrace = {
    collect_job: persistentCollectJobTrace,
    batch_start: {
      trace_collect_popup_route_hit: collectDiagnostics.start_collecting_popup_route_hit === true ? "yes" : "no",
      trace_collect_popup_dispatch_target: traceString(collectDiagnostics.start_collecting_popup_dispatch_target) ?? traceString(collectDiagnostics.last_primary_action_dispatch_target),
      trace_collect_controller_entry_hit: collectDiagnostics.start_collecting_controller_entry_hit === true || collectDiagnostics.start_collecting_stage != null ? "yes" : "no",
      trace_collect_batch_runner_entry_hit: collectDiagnostics.collect_batch_runner_entry_hit === true || collectDiagnostics.batch_runner_called === true ? "yes" : "no",
      trace_collect_started: collectDiagnostics.collect_batch_runner_entry_hit === true || collectDiagnostics.batch_runner_called === true ? "yes" : "no",
      trace_collect_controller_exit_before_batch_runner: collectDiagnostics.start_collecting_controller_exit_before_batch_runner === true ? "yes" : "no",
      trace_collect_controller_exit_stage: collectDiagnostics.start_collecting_controller_exit_before_batch_runner === true ? traceString(collectDiagnostics.start_collecting_controller_exit_stage) : null,
      trace_collect_controller_exit_reason: collectDiagnostics.start_collecting_controller_exit_before_batch_runner === true ? traceString(collectDiagnostics.start_collecting_controller_exit_reason) ?? traceString(collectDiagnostics.start_collecting_blocked_reason) ?? traceString(collectDiagnostics.start_collecting_error) : null,
      trace_collect_preflight_result: traceString(collectDiagnostics.start_collecting_preflight_result),
      trace_collect_blocked_reason: traceString(collectDiagnostics.start_collecting_blocked_reason),
      trace_collect_runtime_open_direct_modal_present: collectDiagnostics.runtime_open_direct_modal_present === true ? "yes" : collectDiagnostics.runtime_open_direct_modal_present === false ? "no" : "unknown",
      trace_collect_runtime_extract_modal_metrics_present: collectDiagnostics.runtime_extract_modal_metrics_present === true ? "yes" : collectDiagnostics.runtime_extract_modal_metrics_present === false ? "no" : "unknown",
      trace_collect_started_at: traceValue(collectDiagnostics.collect_batch_runner_entered_at) ?? traceValue(collectDiagnostics.start_collecting_clicked_at) ?? traceValue(state.workflow.collection.started_at),
      trace_collect_profile_identifier: traceProfileIdentifier,
      trace_collect_initial_backend_captured: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_captured) ?? traceValue(collectDiagnostics.collect_initial_backend_captured) ?? collectInitialSnapshot?.backend_captured ?? null,
      trace_collect_initial_backend_ready: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_ready) ?? traceValue(collectDiagnostics.collect_initial_backend_ready) ?? collectInitialSnapshot?.backend_ready ?? null,
      trace_collect_initial_backend_dup: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_dup) ?? traceValue(collectDiagnostics.collect_initial_backend_dup) ?? collectInitialSnapshot?.backend_dup ?? null,
      trace_collect_initial_backend_fail: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_fail) ?? traceValue(collectDiagnostics.collect_initial_backend_fail) ?? collectInitialSnapshot?.backend_fail ?? null,
      trace_collect_initial_new: traceValue(collectDiagnostics.trace_collect_pre_batch_new) ?? traceValue(collectDiagnostics.collect_initial_new) ?? collectInitialSnapshot?.new ?? popupMetrics.profile.new_count,
      trace_collect_initial_queue: traceValue(collectDiagnostics.trace_collect_pre_batch_queue) ?? traceValue(collectDiagnostics.collect_initial_queue) ?? collectInitialSnapshot?.queue ?? popupMetrics.profile.queue_count,
      trace_collect_pre_batch_backend_captured: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_captured),
      trace_collect_pre_batch_backend_ready: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_ready),
      trace_collect_pre_batch_backend_dup: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_dup),
      trace_collect_pre_batch_backend_fail: traceValue(collectDiagnostics.trace_collect_pre_batch_backend_fail),
      trace_collect_pre_batch_new: traceValue(collectDiagnostics.trace_collect_pre_batch_new),
      trace_collect_pre_batch_queue: traceValue(collectDiagnostics.trace_collect_pre_batch_queue),
      trace_collect_post_batch_backend_captured: traceValue(collectDiagnostics.trace_collect_post_batch_backend_captured),
      trace_collect_post_batch_backend_ready: traceValue(collectDiagnostics.trace_collect_post_batch_backend_ready),
      trace_collect_post_batch_backend_dup: traceValue(collectDiagnostics.trace_collect_post_batch_backend_dup),
      trace_collect_post_batch_backend_fail: traceValue(collectDiagnostics.trace_collect_post_batch_backend_fail),
      trace_collect_post_batch_new: traceValue(collectDiagnostics.trace_collect_post_batch_new),
      trace_collect_post_batch_queue: traceValue(collectDiagnostics.trace_collect_post_batch_queue),
      trace_collect_batch_delta_captured: traceValue(collectDiagnostics.trace_collect_batch_delta_captured),
      trace_collect_batch_delta_queue: traceValue(collectDiagnostics.trace_collect_batch_delta_queue),
      trace_collect_selected_count: traceValue(collectDiagnostics.batch_selected_count),
      trace_collect_batch_limit: traceValue(collectDiagnostics.effective_batch_limit) ?? traceValue(collectDiagnostics.requested_batch_limit),
      trace_collect_start_index: traceValue(collectDiagnostics.batch_target_queue_index) ?? traceValue(collectDiagnostics.start_collecting_start_index) ?? state.harvest.resume_from_index ?? state.harvest.current_index,
      trace_collect_selected_aweme_ids_first_10: Array.isArray(collectDiagnostics.batch_selected_aweme_ids) ? collectDiagnostics.batch_selected_aweme_ids.slice(0, 10) : [],
      trace_collect_job_id: collectJob.job_id,
      trace_collect_job_state_at_start: traceString(collectDiagnostics.trace_collect_job_state_at_start) ?? collectJob.state,
      trace_collect_job_heartbeat_updates_count: collectJob.heartbeat_updates_count
    },
    queue_filtering: {
      trace_collect_queue_filtering_endpoint: traceString((collectDiagnostics.queue_filtering as Record<string, unknown> | undefined)?.queue_filtering_endpoint) ?? "/douyin-extension/capture-inbox/profile-items",
      trace_collect_queue_filtering_status: traceString((collectDiagnostics.queue_filtering as Record<string, unknown> | undefined)?.queue_filtering_backend_summary_status),
      backend_captured_aweme_id_count: traceValue(collectDiagnostics.backend_captured_aweme_id_count),
      trace_collect_backend_captured_count_source: traceString(collectDiagnostics.trace_collect_backend_captured_count_source),
      trace_collect_backend_captured_id_set_source: traceString(collectDiagnostics.trace_collect_backend_captured_id_set_source),
      trace_collect_backend_counts_and_ids_same_response: collectDiagnostics.trace_collect_backend_counts_and_ids_same_response === true ? "yes" : collectDiagnostics.trace_collect_backend_counts_and_ids_same_response === false ? "no" : "unknown",
      trace_collect_backend_captured_aweme_id_count_expected: traceValue(collectDiagnostics.trace_collect_backend_captured_aweme_id_count_expected) ?? traceValue(collectDiagnostics.queue_filtering_backend_captured_aweme_id_count_expected),
      trace_collect_backend_captured_aweme_id_count_actual: traceValue(collectDiagnostics.trace_collect_backend_captured_aweme_id_count_actual) ?? traceValue(collectDiagnostics.queue_filtering_backend_captured_aweme_id_count_actual),
      trace_collect_backend_captured_id_set_stale: collectDiagnostics.trace_collect_backend_captured_id_set_stale === true ? "yes" : collectDiagnostics.trace_collect_backend_captured_id_set_stale === false ? "no" : "unknown",
      trace_collect_backend_captured_id_set_stale_reason: traceString(collectDiagnostics.trace_collect_backend_captured_id_set_stale_reason),
      trace_collect_selection_blocked: collectDiagnostics.trace_collect_selection_blocked === true ? "yes" : collectDiagnostics.trace_collect_selection_blocked === false ? "no" : "unknown",
      trace_collect_selection_block_reason: traceString(collectDiagnostics.trace_collect_selection_block_reason),
      filtered_collectable_count: traceValue(collectDiagnostics.filtered_collectable_count),
      skipped_already_captured_count: traceValue(collectDiagnostics.skipped_already_captured_count),
      selected_ids_already_captured_count: traceValue(collectDiagnostics.selected_ids_already_captured_count),
      selected_ids_already_captured_first_10: Array.isArray(collectDiagnostics.selected_ids_already_captured_first_10) ? collectDiagnostics.selected_ids_already_captured_first_10.slice(0, 10) : [],
      was_in_backend_captured_set_before_collect: collectDiagnostics.was_in_backend_captured_set_before_collect === true ? "yes" : collectDiagnostics.was_in_backend_captured_set_before_collect === false ? "no" : "unknown",
      backend_captured_id_set_available: collectDiagnostics.backend_captured_id_set_available === true ? "yes" : collectDiagnostics.backend_captured_id_set_available === false ? "no" : "unknown",
      backend_captured_id_set_incomplete: collectDiagnostics.backend_captured_id_set_incomplete === true ? "yes" : collectDiagnostics.backend_captured_id_set_incomplete === false ? "no" : "unknown",
      selection_blocked: collectDiagnostics.backend_captured_id_set_selection_blocked === true ? "yes" : collectDiagnostics.backend_captured_id_set_selection_blocked === false ? "no" : "unknown",
      selection_block_reason: traceString(collectDiagnostics.backend_captured_id_set_selection_block_reason),
      used_for_selection: (collectDiagnostics.queue_filtering as Record<string, unknown> | undefined)?.queue_filtering_used_for_selection === true ? "yes" : (collectDiagnostics.queue_filtering as Record<string, unknown> | undefined)?.queue_filtering_used_for_selection === false ? "no" : "unknown"
    },
    per_item_backend_writes: {
      trace_collect_item_loop_entered: collectDiagnostics.batch_item_loop_entered === true ? "yes" : "no",
      trace_collect_item_loop_selected_count: traceValue(collectDiagnostics.batch_item_loop_selected_count),
      trace_collect_item_loop_attempted_count: traceValue(collectDiagnostics.batch_item_loop_attempted_count),
      trace_collect_item_loop_returned_count: traceValue(collectDiagnostics.batch_item_loop_returned_count),
      trace_collect_item_loop_result_appended_count: traceValue(collectDiagnostics.batch_item_loop_result_appended_count),
      trace_collect_item_loop_exit_reason: traceString(collectDiagnostics.batch_item_loop_exit_reason),
      trace_collect_item_loop_last_stage: traceString(collectDiagnostics.batch_item_loop_last_stage),
      trace_collect_item_loop_current_aweme_id: traceString(collectDiagnostics.batch_item_loop_current_aweme_id),
      trace_collect_item_loop_current_index: traceValue(collectDiagnostics.batch_item_loop_current_index),
      trace_collect_item_runner_call_started: collectDiagnostics.batch_item_runner_call_started === true ? "yes" : "no",
      trace_collect_item_runner_call_returned: collectDiagnostics.batch_item_runner_call_returned === true ? "yes" : "no",
      trace_collect_item_results: collectItemResults.map((item) => {
        const record = item && typeof item === "object" ? item as Record<string, unknown> : {};
        return {
          index: typeof record.index === "number" ? record.index : null,
          aweme_id: typeof record.aweme_id === "string" ? record.aweme_id : "",
          selected_from_queue: record.selected_from_queue === true,
          skipped_reason: typeof record.skipped_reason === "string" ? record.skipped_reason : null,
          modal_open_result: record.modal_open_result === "success" || record.modal_open_result === "failed" || record.modal_open_result === "skipped" ? record.modal_open_result : "skipped",
          extraction_result: record.extraction_result === "success" || record.extraction_result === "failed" || record.extraction_result === "skipped" ? record.extraction_result : "skipped",
          backend_write_attempted: record.backend_write_attempted === true || record.backend_called === true,
          backend_http_status: typeof record.backend_http_status === "number" ? record.backend_http_status : null,
          backend_success: typeof record.backend_success === "boolean" ? record.backend_success : null,
          backend_item_created_or_updated: typeof record.backend_item_created_or_updated === "boolean" ? record.backend_item_created_or_updated : null,
          backend_duplicate: typeof record.backend_duplicate === "boolean" ? record.backend_duplicate : null,
          backend_capture_inbox_item_id: typeof record.backend_capture_inbox_item_id === "string" ? record.backend_capture_inbox_item_id : null,
          backend_error_code: typeof record.backend_error_code === "string" ? record.backend_error_code : null,
          was_in_backend_captured_set_before_collect: record.was_in_backend_captured_set_before_collect === true ? "yes" : record.was_in_backend_captured_set_before_collect === false ? "no" : "unknown",
          expected_backend_operation: typeof record.expected_backend_operation === "string" ? record.expected_backend_operation : null,
          backend_operation_result: typeof record.backend_operation_result === "string" ? record.backend_operation_result : null,
          backend_profile_capture_delta_effect: typeof record.backend_profile_capture_delta_effect === "string" ? record.backend_profile_capture_delta_effect : null,
          backend_summary_missing_this_id_before_collect: record.backend_summary_missing_this_id_before_collect === true ? "yes" : record.backend_summary_missing_this_id_before_collect === false ? "no" : "unknown",
          backend_match_diagnostics: record.backend_match_diagnostics && typeof record.backend_match_diagnostics === "object" ? record.backend_match_diagnostics : null,
          final_status: record.final_status === "saved_verified" || record.final_status === "duplicate" || record.final_status === "updated" || record.final_status === "failed" || record.final_status === "skipped" ? record.final_status : "skipped"
        };
      })
    },
    post_batch_summary_refresh: {
      trace_collect_backend_summary_called_after_batch: collectDiagnostics.post_collect_backend_summary_called === true ? "yes" : "no",
      trace_collect_backend_summary_endpoint: collectDiagnostics.post_collect_backend_summary_called === true ? "/douyin-extension/capture-inbox/profile-items" : "none",
      trace_collect_backend_summary_http_status: traceValue(collectDiagnostics.post_collect_backend_summary_http_status),
      trace_collect_backend_summary_captured: traceValue(collectDiagnostics.post_collect_backend_captured_count),
      trace_collect_backend_summary_ready: traceValue(collectDiagnostics.post_collect_backend_ready_count),
      trace_collect_backend_summary_dup: traceValue(collectDiagnostics.trace_collect_post_batch_backend_dup),
      trace_collect_backend_summary_fail: traceValue(collectDiagnostics.trace_collect_post_batch_backend_fail),
      trace_collect_post_batch_new: traceValue(collectDiagnostics.trace_collect_post_batch_new),
      trace_collect_post_batch_queue: traceValue(collectDiagnostics.trace_collect_post_batch_queue),
      trace_collect_batch_delta_captured: traceValue(collectDiagnostics.trace_collect_batch_delta_captured),
      trace_collect_batch_delta_queue: traceValue(collectDiagnostics.trace_collect_batch_delta_queue),
      trace_collect_counter_snapshot_refreshed: collectDiagnostics.post_collect_counter_snapshot_refreshed === true ? "yes" : "no",
      trace_collect_job_state_at_finish: traceString(collectDiagnostics.trace_collect_job_state_at_finish) ?? collectJob.state,
      trace_collect_job_heartbeat_updates_count: collectJob.heartbeat_updates_count,
      trace_collect_job_lock_released: collectJob.lock_released,
      trace_collect_job_failed_with_error: traceString(collectDiagnostics.trace_collect_job_failed_with_error) ?? collectJob.last_error,
      trace_collect_job_recoverable_after_error: collectDiagnostics.trace_collect_job_recoverable_after_error === true || collectJob.recoverable
    },
    final_popup_render_input: {
      trace_collect_popup_tiles_render_source: String(popupMetrics.diagnostics.popup_metrics_profile_tiles_authority),
      trace_collect_popup_new: popupMetrics.profile.new_count,
      trace_collect_popup_incomplete: popupMetrics.profile.incomplete_count,
      trace_collect_popup_need_retry: popupMetrics.profile.need_retry_count,
      trace_collect_popup_already_collected: popupMetrics.profile.already_collected_count,
      trace_collect_popup_queue: popupMetrics.profile.queue_count,
      trace_collect_backend_card_popup_agree: collectDiagnostics.post_collect_backend_captured_count === popupMetrics.profile.already_collected_count ? "yes" : "unknown",
      trace_collect_counter_authority: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority,
      trace_collect_counter_monotonic_guard_applied: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" || popupMetrics.diagnostics.popup_metrics_collect_job_progress_available === "yes" ? "yes" : "no",
      trace_counter_active_runtime_monotonic_guard_required: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" ? "yes" : "no",
      trace_counter_active_runtime_monotonic_guard_applied: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" ? "yes" : "no",
      trace_counter_active_runtime_monotonic_guard_missing_detected: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" && popupMetrics.diagnostics.popup_metrics_collect_job_progress_available !== "yes" ? "yes" : "no",
      trace_counter_active_runtime_monotonic_guard_missing_fixed: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" && popupMetrics.diagnostics.popup_metrics_collect_job_progress_available !== "yes" ? "yes" : "no",
      trace_counter_tiles_same_runtime_snapshot: popupMetrics.diagnostics.popup_metrics_profile_tiles_authority === "active_collect_runtime" ? "yes" : "unknown",
      trace_collect_post_scan_snapshot_ignored_for_active_collect_job: popupMetrics.diagnostics.popup_metrics_post_scan_snapshot_ignored_for_active_collect_job ?? "no"
    }
  };
  const scanInProgress = activeScanProgress22C14G(state).active;
  const scanProgressDiscovered = scanInProgress ? (scanDiagnosticValue("scan_progress_discovered") !== "none" ? scanDiagnosticValue("scan_progress_discovered") : String(state.scan_job.total_discovered)) : "none";
  const scanProgressExpected = scanInProgress ? (scanDiagnosticValue("scan_progress_expected") !== "none" ? scanDiagnosticValue("scan_progress_expected") : state.scan_job.expected_count == null ? "unknown" : String(state.scan_job.expected_count)) : "none";
  const scanProgressRemaining = scanInProgress ? (scanDiagnosticValue("scan_progress_remaining") !== "none" ? scanDiagnosticValue("scan_progress_remaining") : state.scan_job.remaining_estimate == null ? "unknown" : String(state.scan_job.remaining_estimate)) : "none";
  const scanProgressPages = scanInProgress ? (scanDiagnosticValue("scan_progress_pages") !== "none" ? scanDiagnosticValue("scan_progress_pages") : String(state.scan_job.page_count)) : "none";
  const scanProgressRequests = scanInProgress ? (scanDiagnosticValue("scan_progress_requests") !== "none" ? scanDiagnosticValue("scan_progress_requests") : String(state.scan_job.request_count)) : "none";
  const scanProgressStatusCode = scanInProgress ? (scanDiagnosticValue("scan_progress_status_code") !== "none" ? scanDiagnosticValue("scan_progress_status_code") : state.scan_job.last_status_code == null ? "none" : String(state.scan_job.last_status_code)) : "none";
  const scanProgressPhaseLabel = scanInProgress ? (scanDiagnosticValue("scan_progress_phase_label") !== "none" ? scanDiagnosticValue("scan_progress_phase_label") : state.scan_job.status === "retry_wait" ? "Retry wait" : "Scanning profile") : "Not scanning";
  const profileCard: WholeProfileHarvestCardView = {
    key: "profile",
    title: scanInProgress ? "Scan progress" : "Profile",
    status: stepper[0].status,
    tone: stepStatusTone(stepper[0].status),
    summary: scanInProgress ? scanProgressPhaseLabel : stepper[0].status === "done" ? "Scanned" : stepper[0].summary,
    metrics: scanInProgress ? [
      { label: "Discovered so far", value: scanProgressDiscovered },
      { label: "Expected", value: scanProgressExpected },
      { label: "Remaining estimate", value: scanProgressRemaining },
      { label: "Pages / requests", value: `${scanProgressPages} / ${scanProgressRequests}` },
      { label: "Last status code", value: scanProgressStatusCode }
    ] : [
      { label: "Videos found", value: String(authoritativeCounters.applied ? popupMetrics.profile.profile_total_count : state.verify.verified_target_count || state.profile_scan.accepted_target_count) },
      { label: "Ready to process", value: String(authoritativeCounters.applied ? popupMetrics.profile.queue_count : targetCounts.new + targetCounts.incomplete + targetCounts.unknown) },
      { label: "Complete skipped", value: String(authoritativeCounters.applied ? popupMetrics.profile.already_collected_count : targetCounts.complete) }
    ]
  };
  const dryRunCard: WholeProfileHarvestCardView = {
    key: "dry_run",
    title: "Test",
    status: stepper[1].status,
    tone: stepStatusTone(stepper[1].status),
    summary: stepper[1].status === "done" ? "Test passed" : stepper[1].summary,
    metrics: [
      { label: "Sample", value: state.dry_run.mode === "random" ? "Random 3" : state.dry_run.mode === "first" ? "First 3" : state.dry_run.mode === "last" ? "Last 3" : "Missing" },
      { label: "Result", value: `${state.dry_run.pass} passed, ${state.dry_run.fail} failed` }
    ]
  };
  const extractionCard: WholeProfileHarvestCardView = {
    key: "extraction",
    title: "Extract",
    status: stepper[2].status,
    tone: stepStatusTone(stepper[2].status),
    summary: stepper[2].status === "done" || stepper[2].status === "active" ? "Extract Metrics" : stepper[2].summary,
    metrics: [
      { label: "Batch", value: friendlyBatch(state.harvest_options.batch) },
      { label: "Extracted", value: `${state.harvest.updated}` },
      { label: "Failed", value: `${state.harvest.failed}` }
    ]
  };
  const backendCard: WholeProfileHarvestCardView = {
    key: "backend",
    title: "Save",
    status: stepper[3].status,
    tone: stepStatusTone(stepper[3].status),
    summary: backendFlow.next_backend_action.reason,
    metrics: [
      { label: "Save session", value: backendFlow.summary.capture_session_id_short ? `Ready: ${backendFlow.summary.capture_session_id_short}` : friendlyBooleanStatus(state.harvest.backend.capture_session.status === "ready" ? "yes" : "no") },
      { label: "Data check", value: backendFlow.summary.payload_guard === "passed" ? "Passed" : backendFlow.summary.payload_guard === "failed" ? "Failed" : "Missing" },
      { label: "Saved", value: `${backendFlow.summary.flushed}` },
      { label: "Failed", value: `${backendFlow.summary.failed}` }
    ]
  };
  const safetyNormal = !state.safety.captcha_detected && state.safety.consecutive_errors === 0 && state.safety.tab_health.status !== "content_script_missing" && state.safety.tab_health.status !== "detector_failed";
  const safetyCard: WholeProfileHarvestCardView = {
    key: "safety",
    title: "Safety",
    status: state.safety.captcha_detected ? "warning" : safetyNormal ? "done" : "warning",
    tone: state.safety.captcha_detected ? "warning" : safetyNormal ? "success" : "warning",
    summary: state.safety.captcha_detected ? "Security check detected" : "Normal",
    collapsed: safetyNormal,
    metrics: [
      { label: "Security check", value: state.safety.captcha_detected ? (state.safety.captcha_reason ?? "detected") : "None" },
      { label: "Errors", value: `${state.safety.consecutive_errors} / ${state.safety.max_consecutive_errors}` },
      { label: "Last delay", value: state.safety.last_delay_ms === null ? "none" : `${(state.safety.last_delay_ms / 1000).toFixed(1)}s` }
    ]
  };

  return {
    stepper,
    next_action: {
      label: canonicalPrimaryAction.label,
      reason: canonicalPrimaryAction.description,
      severity: actionSeverity(state, readiness)
    },
    cards: {
      profile: profileCard,
      dry_run: dryRunCard,
      extraction: extractionCard,
      backend: backendCard,
      safety: safetyCard
    },
    backend_flow: backendFlow,
    lists,
    details: {
      profile_url: state.profile_url ?? "none",
      profile_url_short: shortenUrl(state.profile_url),
      phase: state.phase,
      raw_status: state.status,
      technical_rows: [
        { label: "Scan progress panel", value: scanInProgress ? "active" : "inactive" },
        { label: "scan_progress_discovered", value: scanProgressDiscovered },
        { label: "scan_progress_expected", value: scanProgressExpected },
        { label: "scan_progress_remaining", value: scanProgressRemaining },
        { label: "scan_progress_pages", value: scanProgressPages },
        { label: "scan_progress_requests", value: scanProgressRequests },
        { label: "scan_progress_status_code", value: scanProgressStatusCode },
        { label: "scan_progress_phase_label", value: scanProgressPhaseLabel },
        { label: "Scan job status", value: state.scan_job.status },
        { label: "Pages fetched", value: String(state.scan_job.page_count) },
        { label: "Request count", value: String(state.scan_job.request_count) },
        { label: "Has more", value: state.scan_job.has_more_state == null ? "unknown" : String(state.scan_job.has_more_state) },
        { label: "Persisted total", value: String(largeProfilePersistedTotal ?? state.scan_job.total_persisted) },
        { label: "Expected", value: state.scan_job.expected_count == null ? "unknown" : String(state.scan_job.expected_count) },
        { label: "Remaining estimate", value: state.scan_job.remaining_estimate == null ? "unknown" : String(state.scan_job.remaining_estimate) },
        { label: "Last status code", value: state.scan_job.last_status_code == null ? "none" : String(state.scan_job.last_status_code) },
        { label: "Last error", value: state.scan_job.last_error ?? "none" },
        { label: "popup_counter_authority_selected", value: String(popupDiagnosticsRecord(state).popup_counter_authority_selected ?? "none") },
        { label: "popup_counter_authority_previous", value: String(popupDiagnosticsRecord(state).popup_counter_authority_previous ?? "none") },
        { label: "popup_counter_authority_switch_blocked_stale", value: String(popupDiagnosticsRecord(state).popup_counter_authority_switch_blocked_stale ?? "no") },
        { label: "popup_counter_authority_reason", value: String(popupDiagnosticsRecord(state).popup_counter_authority_reason ?? "none") },
        { label: "popup_counter_state_version", value: String(popupDiagnosticsRecord(state).popup_counter_state_version ?? state.updated_at ?? "none") },
        { label: "popup_active_scan_run_id", value: String(popupDiagnosticsRecord(state).popup_active_scan_run_id ?? "none") },
        { label: "popup_render_scan_run_id", value: String(popupDiagnosticsRecord(state).popup_render_scan_run_id ?? state.scan_job.scan_job_id ?? state.run_id ?? "none") },
        { label: "popup_render_dropped_stale_run_update", value: String(popupDiagnosticsRecord(state).popup_render_dropped_stale_run_update ?? "no") },
        { label: "popup_render_profile_switch_detected", value: String(popupDiagnosticsRecord(state).popup_render_profile_switch_detected ?? "no") },
        { label: "popup_progress_active_rendered", value: String(popupDiagnosticsRecord(state).popup_progress_active_rendered ?? "unknown") },
        { label: "popup_progress_render_source", value: String(popupDiagnosticsRecord(state).popup_progress_render_source ?? "none") },
        { label: "popup_progress_render_run_id", value: String(popupDiagnosticsRecord(state).popup_progress_render_run_id ?? "none") },
        { label: "popup_progress_render_discovered", value: String(popupDiagnosticsRecord(state).popup_progress_render_discovered ?? "none") },
        { label: "popup_progress_render_expected", value: String(popupDiagnosticsRecord(state).popup_progress_render_expected ?? "none") },
        { label: "popup_progress_render_pages", value: String(popupDiagnosticsRecord(state).popup_progress_render_pages ?? "none") },
        { label: "popup_progress_render_requests", value: String(popupDiagnosticsRecord(state).popup_progress_render_requests ?? "none") },
        { label: "popup_progress_cleared_after_terminal", value: String(popupDiagnosticsRecord(state).popup_progress_cleared_after_terminal ?? "no") },
        { label: "popup_progress_stale_ignored_reason", value: String(popupDiagnosticsRecord(state).popup_progress_stale_ignored_reason ?? "none") },
        { label: scanInProgress ? "Queue total snapshot" : "Queue total", value: String(largeProfilePersistedTotal ?? state.scan_job.total_persisted ?? numericDiagnosticValue(scanDiagnosticsRecord(state).queue_total_persisted) ?? state.harvest.queue.length) },
        { label: scanInProgress ? "Preview window snapshot" : "Preview window", value: String(largeProfileVisibleTotal ?? state.harvest.queue_preview.length) },
        { label: scanInProgress ? "Displaying first N preview items" : "Displaying first N items", value: String(state.harvest.queue_preview.length) },
        { label: "popup_near_complete_warning_applied", value: popupNearCompleteWarning(state).applied ? "yes" : "no" },
        { label: "popup_near_complete_gap_count", value: popupNearCompleteWarning(state).gapCount == null ? "unknown" : String(popupNearCompleteWarning(state).gapCount) },
        { label: "popup_near_complete_threshold_used", value: popupNearCompleteWarning(state).threshold == null ? "none" : String(popupNearCompleteWarning(state).threshold) },
        { label: "Profile scan ready", value: readiness.profile_scan_ready ? "yes" : "no" },
        { label: "Calibration ready", value: readiness.calibration_ready ? "yes" : "no" },
        { label: "Canonical calibration ready", value: canonicalCalibration.ready ? "yes" : "no" },
        { label: "Canonical calibration source", value: canonicalCalibration.source },
        { label: "Canonical calibration canonical_ready", value: canonicalCalibration.canonicalReady ? "yes" : "no" },
        { label: "Canonical calibration legacy_ready", value: canonicalCalibration.legacyReady ? "yes" : "no" },
        { label: "Canonical calibration conflict", value: canonicalCalibration.conflict ? "yes" : "no" },
        { label: "Dry-run ready", value: readiness.dry_run_ready ? "yes" : "no" },
        { label: "Extraction ready", value: readiness.extraction_ready ? "yes" : "no" },
        { label: "Backend session ready", value: readiness.backend_session_ready ? "yes" : "no" },
        { label: "Payload preview ready", value: readiness.payload_preview_ready ? "yes" : "no" },
        { label: "Payload guard passed", value: readiness.payload_guard_passed ? "yes" : "no" },
        { label: "Scanner busy", value: scannerBusy.isBusy ? (scannerBusy.busyLabel ?? "busy") : scannerBusy.isStale ? `stale: ${scannerBusy.busySource ?? "unknown"}` : "no" },
        { label: "Primary action key", value: canonicalPrimaryAction.key },
        { label: "Primary action title", value: canonicalPrimaryAction.title },
        { label: "Primary action label", value: canonicalPrimaryAction.label },
        { label: "Primary action source", value: canonicalPrimaryAction.source },
        { label: "Primary action selector version", value: canonicalPrimaryAction.selectorVersion },
        { label: "Primary action trace selected", value: canonicalPrimaryAction.decisionTrace.selectedAction },
        { label: "Primary action trace reason", value: canonicalPrimaryAction.decisionTrace.reason },
        { label: "Primary action trace profileScanReady", value: canonicalPrimaryAction.decisionTrace.profileScanReady ? "yes" : "no" },
        { label: "Primary action trace canonicalCalibrationReady", value: canonicalPrimaryAction.decisionTrace.canonicalCalibrationReady ? "yes" : "no" },
        { label: "Primary action trace extractionReady", value: canonicalPrimaryAction.decisionTrace.extractionReady ? "yes" : "no" },
        { label: "Primary action trace backendSessionReady", value: canonicalPrimaryAction.decisionTrace.backendSessionReady ? "yes" : "no" },
        { label: "Scanner next action", value: scannerWorkflowReadiness.nextActionKey },
        { label: "Scanner active task", value: state.workflow.active_task ?? "none" },
        { label: "Scanner action lock", value: state.workflow.action_lock ?? "none" },
        { label: "Last scanner action", value: state.debug.last_action_clicked ?? "none" },
        { label: "Last scanner result", value: state.debug.last_action_result ?? "none" },
        { label: "Last scanner error", value: state.debug.last_action_error ?? state.workflow.collection.last_error ?? "none" },
        { label: "Resume requested at", value: resumeDiagnosticValue("resume_requested_at") },
        { label: "Resume started at", value: resumeDiagnosticValue("resume_started_at") },
        { label: "Resume acknowledged at", value: resumeDiagnosticValue("resume_acknowledged_at") },
        { label: "Resume result", value: resumeDiagnosticValue("resume_result") },
        { label: "Resume error", value: resumeDiagnosticValue("resume_error") },
        { label: "Resume from index", value: resumeDiagnosticValue("resume_from_index") },
        { label: "Resume from aweme", value: resumeDiagnosticValue("resume_from_aweme") },
        { label: "Resume pending count", value: resumeDiagnosticValue("resume_pending_count") },
        { label: "Resume skipped completed count", value: resumeDiagnosticValue("resume_skipped_completed_count") },
        { label: "Resume session id", value: resumeDiagnosticValue("resume_session_id") },
        { label: "Resume runner target", value: resumeDiagnosticValue("resume_runner_target") },
        { label: "Pause requested", value: state.harvest.pause_requested ? "yes" : "no" },
        { label: "Pause requested at", value: state.harvest.pause_requested_at ?? "none" },
        { label: "Pause acknowledged at", value: state.harvest.pause_acknowledged_at ?? "none" },
        { label: "Pause reason", value: state.harvest.pause_reason ?? state.harvest.paused_reason ?? "none" },
        { label: "Collection status", value: collectionDisplayStatus },
        { label: "Active task", value: state.workflow.active_task ?? "none" },
        { label: "Action lock", value: state.workflow.action_lock ?? "none" },
        { label: "Current index", value: String(state.harvest.current_index) },
        { label: "Current aweme", value: state.harvest.current_aweme_id ?? "none" },
        { label: "Active runner remaining count", value: String(popupMetrics.active_runner.active_runner_remaining_count) },
        { label: "Raw pending count", value: String(popupMetrics.diagnostics.popup_metrics_raw_pending_count) },
        { label: "Pending count", value: String(pendingCount(state)) },
        { label: "Saved count", value: String(savedCount(state)) },
        { label: "Failed count", value: String(state.harvest.failed) },
        { label: "Skipped count", value: String(state.harvest.skipped) },
        { label: "Scanner runtime version", value: typeof resetResponseSummary?.scanner_runtime_version === "string" ? resetResponseSummary.scanner_runtime_version : typeof resetRequestSummary?.scanner_runtime_version === "string" ? resetRequestSummary.scanner_runtime_version : "22C-9Z-3" },
        { label: "State machine version", value: typeof resetResponseSummary?.state_machine_version === "string" ? resetResponseSummary.state_machine_version : typeof resetRequestSummary?.state_machine_version === "string" ? resetRequestSummary.state_machine_version : "22C-9Z-3" },
        { label: "Primary action decision trace", value: `${canonicalPrimaryAction.decisionTrace.selector_version}:${canonicalPrimaryAction.decisionTrace.selected_action}:${canonicalPrimaryAction.decisionTrace.reason}` },
        { label: "Profile scan state summary", value: `${state.profile_scan.status};ready=${scannerWorkflowReadiness.profileScanReady ? "yes" : "no"};rounds=${state.profile_scan.scan_rounds};discovered=${profileScanCount("profile_discovered_count", String(state.profile_scan.raw_candidate_count))};queued=${profileScanCount("profile_queue_total_count", String(state.harvest.queue.length))};pending=${profileScanCount("profile_batch_pending_count", String(pendingCount(state)))};limit=${profileScanCount("profile_batch_mode", `${state.harvest_options.batch}_${state.harvest_options.speed}`)}` },
        { label: "Calibration state summary", value: `${canonicalCalibration.ready ? "ready" : "missing"};source=${canonicalCalibration.source};points=${state.calibration.point_count}` },
        { label: "Collection state summary", value: `${collectionDisplayStatus};queue=${state.harvest.queue.length};pending=${pendingCount(state)}` },
        { label: "Backend session state summary", value: `${state.harvest.backend.capture_session.status};session=${state.capture_session_id ?? state.harvest.backend.capture_session.session_id ?? "none"}` },
        { label: "Reset state summary", value: typeof resetResponseSummary?.reset_mode === "string" ? `${resetResponseSummary.reset_mode}:${resetResponseSummary.reset_result ?? "unknown"}` : "none" },
        { label: "Storage state audit", value: state.debug.legacy_state_summary && typeof state.debug.legacy_state_summary === "object" && (state.debug.legacy_state_summary as Record<string, unknown>).storage_state_audit ? "legacy_quarantined" : "none" },
        { label: "Extension build timestamp", value: scanDiagnosticValue("extension_build_timestamp") !== "none" ? scanDiagnosticValue("extension_build_timestamp") : typeof resetResponseSummary?.extension_build_timestamp === "string" ? resetResponseSummary.extension_build_timestamp : typeof resetRequestSummary?.extension_build_timestamp === "string" ? resetRequestSummary.extension_build_timestamp : "none" },
        { label: "Extension runtime build id", value: runtimeBuildIdValue("extension_runtime_build_id") },
        { label: "Background runtime build id", value: runtimeBuildIdValue("background_runtime_build_id") },
        { label: "Popup runtime build id", value: runtimeBuildIdValue("popup_runtime_build_id") },
        { label: "Content script runtime build id", value: runtimeBuildIdValue("content_script_runtime_build_id") },
        { label: "Runtime build id consistent", value: runtimeBuildIdConsistentValue() },
        { label: "Scan controller version", value: typeof resetResponseSummary?.scan_controller_version === "string" ? resetResponseSummary.scan_controller_version : typeof resetRequestSummary?.scan_controller_version === "string" ? resetRequestSummary.scan_controller_version : "22C-9Z-3-scan-controller" },
        { label: "Reset controller version", value: typeof resetResponseSummary?.reset_controller_version === "string" ? resetResponseSummary.reset_controller_version : typeof resetRequestSummary?.reset_controller_version === "string" ? resetRequestSummary.reset_controller_version : "22C-12F-reset-controller" },
        { label: "Reset result", value: typeof resetResponseSummary?.reset_result === "string" ? resetResponseSummary.reset_result : "none" },
        { label: "Reset at", value: typeof resetResponseSummary?.reset_at === "string" ? resetResponseSummary.reset_at : "none" },
        { label: "Reset storage write", value: typeof resetResponseSummary?.reset_storage_write_status === "string" ? resetResponseSummary.reset_storage_write_status : "none" },
        { label: "Reset cleared profile scan state", value: resetResponseSummary?.reset_cleared_profile_scan_state === "yes" ? "yes" : resetResponseSummary?.reset_cleared_profile_scan_state === "no" ? "no" : "none" },
        { label: "Reset kept calibration", value: resetRequestSummary?.reset_kept_calibration === true ? "yes" : "none" },
        { label: "Reset kept settings", value: resetRequestSummary?.reset_kept_settings === true ? "yes" : "none" },
        { label: "Reset queue count", value: typeof resetResponseSummary?.queueCount === "number" ? String(resetResponseSummary.queueCount) : "none" },
        { label: "Reset background cancel", value: typeof resetRequestSummary?.reset_background_cancel_status === "string" ? resetRequestSummary.reset_background_cancel_status : "none" },
        { label: "One-item flush", value: oneItemFlush.status },
        { label: "Batch flush", value: batchFlush.status },
        { label: "Scan rounds", value: String(state.verify.scan_rounds) },
        { label: "Scan stop", value: authoritativeStopReason },
        { label: "Profile DOM probe status", value: profileDomProbeStatus() },
        { label: "Scan action trace version", value: scanDiagnosticValue("scan_action_trace_version") !== "none" ? scanDiagnosticValue("scan_action_trace_version") : scanActionTraceValue("traceVersion") },
        { label: "Popup route hit", value: scanDiagnosticValue("popup_route_hit") !== "none" ? scanDiagnosticValue("popup_route_hit") : scanActionTraceValue("popupHandlerName") === "none" ? "none" : "yes" },
        { label: "Background route hit", value: scanDiagnosticValue("background_route_hit") !== "none" ? scanDiagnosticValue("background_route_hit") : scanActionTraceValue("backgroundHandlerName") },
        { label: "Controller route hit", value: scanDiagnosticValue("controller_route_hit") !== "none" ? scanDiagnosticValue("controller_route_hit") : scanActionTraceValue("controllerName") === "none" ? "none" : "yes" },
        { label: "Scan run id", value: scanDiagnosticValue("scan_run_id") },
        { label: "Scan watchdog fired", value: scanDiagnosticValue("scan_watchdog_fired") },
        { label: "Scan watchdog stage", value: scanDiagnosticValue("scan_watchdog_stage") },
        { label: "Tab resolved", value: scanDiagnosticValue("tab_resolve_result") !== "none" ? scanDiagnosticValue("tab_resolve_result") : scanActionTraceValue("tabResolveResult") },
        { label: "Tab resolve strategy", value: scanDiagnosticValue("tab_resolve_strategy") },
        { label: "Tab URL", value: scanDiagnosticValue("tab_url") },
        { label: "Content script ensure status", value: scanDiagnosticValue("content_script_ensure_status") !== "none" ? scanDiagnosticValue("content_script_ensure_status") : state.page_context.content_script_status ?? "none" },
        { label: "Content script ping", value: scanDiagnosticValue("content_script_ping_result") !== "none" ? scanDiagnosticValue("content_script_ping_result") : scanActionTraceValue("contentPingResult") },
        { label: "Content injection", value: scanDiagnosticValue("content_injection_result") !== "none" ? scanDiagnosticValue("content_injection_result") : scanActionTraceValue("contentInjectionResult") },
        { label: "Scan finalization result", value: scanDiagnosticValue("scan_finalization_result") },
        { label: "Scan completeness gate result", value: scanDiagnosticValue("scan_completeness_gate_result") },
        { label: "Scan completeness gate reason", value: scanDiagnosticValue("scan_completeness_gate_reason") },
        { label: "Scan completeness ready blocked", value: scanDiagnosticValue("scan_completeness_ready_blocked") },
        { label: "Scan completeness DOM-only fallback", value: scanDiagnosticValue("scan_completeness_dom_only_fallback") },
        { label: "Scan finalized at", value: scanDiagnosticValue("scan_finalized_at") },
        { label: "Profile expected video count", value: profileScanCount("expected_profile_video_count", "unknown") },
        { label: "Profile found video count", value: String(profileCount(state)) },
        { label: "Profile missing video count", value: profileScanCount("missing_profile_video_count", "unknown") },
        { label: "Profile scan incomplete reason", value: profileScanIncompleteReasonValue() },
        { label: "Profile scan source ledger", value: profileScanSourceLedgerValue() },
        { label: "Profile DOM probe message", value: scanDiagnosticValue("profile_dom_probe_message") !== "none" ? scanDiagnosticValue("profile_dom_probe_message") : scanDiagnosticValue("dom_probe_message_result") },
        { label: "Profile DOM probe started at", value: scanDiagnosticValue("profile_dom_probe_started_at") },
        { label: "Profile DOM probe completed at", value: scanDiagnosticValue("profile_dom_probe_completed_at") },
        { label: "Profile DOM probe fallback attempted", value: scanDiagnosticValue("dom_probe_fallback_execute_script_attempted") },
        { label: "Profile DOM probe fallback result", value: scanDiagnosticValue("dom_probe_fallback_execute_script_result") },
        { label: "Specific scan error", value: scanDiagnosticValue("specific_scan_error") },
        { label: "Scan failure stage", value: scanDiagnosticValue("scan_failure_stage") },
        { label: "Raw scan error", value: scanDiagnosticValue("raw_scan_error") },
        { label: "Raw scan error safe", value: scanDiagnosticValue("raw_scan_error_stack_safe") },
        { label: "Profile grid ready", value: scanDiagnosticValue("profile_grid_ready") !== "none" ? scanDiagnosticValue("profile_grid_ready") : scanDiagnosticValue("scan_grid_ready") },
        { label: "Profile grid selector", value: profileDomProbeDiagnosticValue("profileGridSelector") },
        { label: "Video anchor count", value: scanDiagnosticValue("video_anchor_count") !== "none" ? scanDiagnosticValue("video_anchor_count") : scanDiagnosticValue("video_link_count") },
        { label: "Aweme id count", value: scanDiagnosticValue("aweme_id_count") !== "none" ? scanDiagnosticValue("aweme_id_count") : profileDomProbeDiagnosticValue("awemeIdCount") },
        { label: "Grid card candidate count", value: scanDiagnosticValue("grid_card_candidate_count") },
        { label: "Scroll container found", value: scanDiagnosticValue("scroll_container_found") !== "none" ? scanDiagnosticValue("scroll_container_found") : profileDomProbeDiagnosticValue("scrollContainerFound") },
        { label: "Network probe version", value: scanDiagnosticValue("network_probe_version") },
        { label: "Network probe installed", value: scanDiagnosticValue("network_probe_installed") },
        { label: "Network probe content listener ready", value: scanDiagnosticValue("network_probe_content_listener_ready") },
        { label: "Network probe page script injection attempted", value: scanDiagnosticValue("network_probe_page_script_injection_attempted") },
        { label: "Network probe page script injected", value: scanDiagnosticValue("network_probe_page_script_injected") },
        { label: "Network probe bridge ready", value: scanDiagnosticValue("network_probe_bridge_ready") !== "none" ? scanDiagnosticValue("network_probe_bridge_ready") : scanDiagnosticValue("network_probe_page_bridge_ready") },
        { label: "Network probe page ready at", value: scanDiagnosticValue("network_probe_page_ready_at") },
        { label: "Network probe batches seen", value: scanDiagnosticValue("network_probe_batches_seen") },
        { label: "Network probe unique aweme count", value: scanDiagnosticValue("network_probe_unique_aweme_count") },
        { label: "Network probe endpoint count", value: scanDiagnosticValue("network_probe_endpoint_count") !== "none" ? scanDiagnosticValue("network_probe_endpoint_count") : scanDiagnosticValue("network_probe_candidate_endpoint_count") },
        { label: "Network probe endpoint samples", value: scanDiagnosticArrayValue("network_probe_endpoint_samples") !== "none" ? scanDiagnosticArrayValue("network_probe_endpoint_samples") : scanDiagnosticValue("network_probe_endpoint_samples_display") },
        { label: "Network probe first 10 aweme ids", value: scanDiagnosticArrayValue("network_probe_first_10_aweme_ids") !== "none" ? scanDiagnosticArrayValue("network_probe_first_10_aweme_ids") : scanDiagnosticValue("network_probe_first_10_aweme_ids_display") },
        { label: "Network probe last 10 aweme ids", value: scanDiagnosticArrayValue("network_probe_last_10_aweme_ids") !== "none" ? scanDiagnosticArrayValue("network_probe_last_10_aweme_ids") : scanDiagnosticValue("network_probe_last_10_aweme_ids_display") },
        { label: "Network probe last batch at", value: scanDiagnosticValue("network_probe_last_batch_at") },
        { label: "Network probe last error", value: scanDiagnosticValue("network_probe_last_error") },
        { label: "Network probe live status query", value: scanDiagnosticValue("network_probe_live_status_query") },
        { label: "Network probe live status error", value: scanDiagnosticValue("network_probe_live_status_error") },
        { label: "Network profile post unique count", value: scanDiagnosticValue("network_profile_post_unique_count") },
        { label: "Network favorite unique count", value: scanDiagnosticValue("network_favorite_unique_count") },
        { label: "Network favorite excluded count", value: scanDiagnosticValue("network_favorite_excluded_count") !== "none" ? scanDiagnosticValue("network_favorite_excluded_count") : scanDiagnosticValue("network_excluded_favorite_count") },
        { label: "Network other aweme unique count", value: scanDiagnosticValue("network_other_aweme_unique_count") },
        { label: "Network other excluded count", value: scanDiagnosticValue("network_excluded_other_count") },
        { label: "Network collection stop reason", value: networkCollectionStopReasonValue() },
        { label: "Expected-count finalization gate policy", value: activeProfilePostDiagnostics.expectedCountFinalizationGatePolicy },
        { label: "Expected-count gate meaningful active fetch", value: activeProfilePostDiagnostics.expectedCountFinalizationGateActiveProfilePostMeaningfulAttempt },
        { label: "Expected-count gate active fetch reason", value: activeProfilePostDiagnostics.effectiveAttemptReason },
        { label: "Expected-count gate DOM-only convergence detected", value: activeProfilePostDiagnostics.expectedCountFinalizationGateDomOnlyConvergenceDetected },
        { label: "Expected-count gate DOM-only convergence allowed", value: activeProfilePostDiagnostics.expectedCountFinalizationGateDomOnlyConvergenceAllowed },
        { label: "Active profile-post fetch enabled", value: activeProfilePostDiagnostics.enabled },
        { label: "Active profile-post fetch attempted", value: activeProfilePostDiagnostics.attempted },
        { label: "Active profile-post fetch effective attempted", value: activeProfilePostDiagnostics.effectiveAttempted },
        { label: "Active profile-post fetch effective attempt reason", value: activeProfilePostDiagnostics.effectiveAttemptReason },
        { label: "Active profile-post fetch stop reason", value: activeProfilePostDiagnostics.stopReason },
        { label: "Active profile-post fetch not-attempted reason", value: activeProfilePostDiagnostics.notAttemptedReason },
        { label: "Active profile-post fetch target count", value: activeProfilePostDiagnostics.targetCount },
        { label: "Active profile-post fetch has-more state", value: activeProfilePostDiagnostics.hasMoreState },
        { label: "Active profile-post active-only aweme count", value: activeProfilePostDiagnostics.onlyAwemeCount },
        { label: "Active profile-post fetch request count", value: activeProfilePostDiagnostics.requestCount },
        { label: "Active profile-post fetch batch count", value: activeProfilePostDiagnostics.batchCount },
        { label: "Active profile-post fetch page count", value: activeProfilePostDiagnostics.pageCount },
        { label: "api_pagination_raw_items_total", value: scanDiagnosticValue("api_pagination_raw_items_total") === "none" ? "unknown" : scanDiagnosticValue("api_pagination_raw_items_total") },
        { label: "api_pagination_raw_aweme_ids_total", value: scanDiagnosticValue("api_pagination_raw_aweme_ids_total") === "none" ? "unknown" : scanDiagnosticValue("api_pagination_raw_aweme_ids_total") },
        { label: "api_pagination_accepted_targets_total", value: scanDiagnosticValue("api_pagination_accepted_targets_total") === "none" ? "unknown" : scanDiagnosticValue("api_pagination_accepted_targets_total") },
        { label: "api_pagination_persisted_targets_total", value: scanDiagnosticValue("api_pagination_persisted_targets_total") === "none" ? "unknown" : scanDiagnosticValue("api_pagination_persisted_targets_total") },
        { label: "api_pagination_repository_write_total_after", value: scanDiagnosticValue("api_pagination_repository_write_total_after") === "none" ? "unknown" : scanDiagnosticValue("api_pagination_repository_write_total_after") },
        { label: "api_pagination_per_page_raw_counts", value: scanDiagnosticArrayValue("api_pagination_per_page_raw_counts") === "none" ? "[]" : scanDiagnosticArrayValue("api_pagination_per_page_raw_counts") },
        { label: "api_pagination_per_page_accepted_counts", value: scanDiagnosticArrayValue("api_pagination_per_page_accepted_counts") === "none" ? "[]" : scanDiagnosticArrayValue("api_pagination_per_page_accepted_counts") },
        { label: "api_pagination_per_page_persisted_totals", value: scanDiagnosticArrayValue("api_pagination_per_page_persisted_totals") === "none" ? "[]" : scanDiagnosticArrayValue("api_pagination_per_page_persisted_totals") },
        { label: "final_gap_reason", value: scanDiagnosticValue("final_gap_reason") },
        { label: "final_gap_classification", value: scanDiagnosticValue("final_gap_classification") },
        { label: "Scan job status", value: state.scan_job.status },
        { label: "Scan job id", value: state.scan_job.scan_job_id ?? "none" },
        { label: "Scan job profile", value: state.scan_job.profile_identifier ?? "none" },
        { label: "Scan job pages fetched", value: String(state.scan_job.page_count) },
        { label: "Scan job request count", value: String(state.scan_job.request_count) },
        { label: "Scan job has-more state", value: state.scan_job.has_more_state == null ? "unknown" : String(state.scan_job.has_more_state) },
        { label: "Scan job cursor", value: state.scan_job.cursor == null ? "none" : String(state.scan_job.cursor) },
        { label: "Scan job last HTTP status", value: state.scan_job.last_http_status == null ? "none" : String(state.scan_job.last_http_status) },
        { label: "Scan job last status code", value: state.scan_job.last_status_code == null ? "none" : String(state.scan_job.last_status_code) },
        { label: "Scan job consecutive no-new pages", value: String(state.scan_job.consecutive_no_new_pages) },
        { label: "Scan job discovered total", value: String(state.scan_job.total_discovered) },
        { label: "Scan job persisted total", value: String(state.scan_job.total_persisted) },
        { label: "Scan job expected count", value: state.scan_job.expected_count == null ? "unknown" : String(state.scan_job.expected_count) },
        { label: "Scan job remaining estimate", value: state.scan_job.remaining_estimate == null ? "unknown" : String(state.scan_job.remaining_estimate) },
        { label: "Scan job next retry at", value: state.scan_job.next_retry_at ?? "none" },
        { label: "Scan job retry count", value: String(state.scan_job.retry_count) },
        { label: "Scan job resume source", value: state.scan_job.resume_source ?? "none" },
        { label: "Scan job last error", value: state.scan_job.last_error ?? "none" },
        { label: "Active profile-post fetch page cap", value: activeProfilePostDiagnostics.pageCap },
        { label: "Active profile-post fetch page cap hit count", value: activeProfilePostDiagnostics.pageCapHitCount },
        { label: "Active profile-post fetch page cap hit while has-more count", value: activeProfilePostDiagnostics.pageCapHitWhileHasMoreCount },
        { label: "Active profile-post fetch runtime timeout ms", value: activeProfilePostDiagnostics.runtimeTimeoutMs },
        { label: "Active profile-post fetch runtime timeout hit", value: activeProfilePostDiagnostics.runtimeTimeoutHit },
        { label: "Active profile-post fetch continuation policy", value: activeProfilePostDiagnostics.continuationPolicy },
        { label: "Active profile-post fallback-cycle eligible", value: activeProfilePostDiagnostics.fallbackCycleEligible },
        { label: "Active profile-post fallback-cycle attempted", value: activeProfilePostDiagnostics.fallbackCycleAttempted },
        { label: "Active profile-post fallback-cycle stop reason", value: activeProfilePostDiagnostics.fallbackCycleStopReason },
        { label: "Active profile-post fallback-cycle has-more state", value: activeProfilePostDiagnostics.fallbackCycleHasMoreState },
        { label: "Active profile-post fallback-cycle request count", value: activeProfilePostDiagnostics.fallbackCycleRequestCount },
        { label: "Active profile-post fallback-cycle batch count", value: activeProfilePostDiagnostics.fallbackCycleBatchCount },
        { label: "Active profile-post fetch endpoint variant attempts", value: activeProfilePostDiagnostics.endpointVariantAttemptCount },
        { label: "Active profile-post fetch endpoint variant success", value: activeProfilePostDiagnostics.endpointVariantSuccess },
        { label: "Active profile-post fetch endpoint attempt samples", value: activeProfilePostDiagnostics.endpointAttemptSamples },
        { label: "Active profile-post fetch parser route", value: activeProfilePostDiagnostics.parserRoute },
        { label: "Active profile-post fetch parser routes tried", value: activeProfilePostDiagnostics.parserRoutesTried },
        { label: "Active profile-post fetch parser direct routes tried", value: activeProfilePostDiagnostics.parserDirectRoutesTried },
        { label: "Active profile-post fetch parser direct match count", value: activeProfilePostDiagnostics.parserDirectMatchCount },
        { label: "Active profile-post fetch parser fallback attempted", value: activeProfilePostDiagnostics.parserFallbackAttempted },
        { label: "Active profile-post fetch parser fallback match count", value: activeProfilePostDiagnostics.parserFallbackMatchCount },
        { label: "Active profile-post fetch parser fallback candidate count", value: activeProfilePostDiagnostics.parserFallbackCandidateCount },
        { label: "Active profile-post fetch parser fallback visited nodes", value: activeProfilePostDiagnostics.parserFallbackVisitedNodes },
        { label: "Active profile-post fetch error", value: activeProfilePostDiagnostics.error },
        { label: "Active profile-post fetch response shape", value: activeProfilePostDiagnostics.responseShape },
        { label: "Active profile-post template found", value: activeProfilePostDiagnostics.templateFound },
        { label: "Active profile-post template source", value: activeProfilePostDiagnostics.templateSource },
        { label: "Active profile-post template endpoint path", value: activeProfilePostDiagnostics.templateEndpointPath },
        { label: "Active profile-post template query keys", value: activeProfilePostDiagnostics.templateQueryKeys },
        { label: "Active profile-post template required query keys", value: activeProfilePostDiagnostics.templateRequiredQueryKeys },
        { label: "Active profile-post template required query keys available", value: activeProfilePostDiagnostics.templateRequiredQueryKeysAvailable },
        { label: "Active profile-post template missing required query keys", value: activeProfilePostDiagnostics.templateMissingRequiredQueryKeys },
        { label: "Active profile-post template secret keys present", value: activeProfilePostDiagnostics.templateSecretKeysPresent },
        { label: "Active profile-post template secret query keys", value: activeProfilePostDiagnostics.templateSecretQueryKeys },
        { label: "Active profile-post template warm-up attempted", value: activeProfilePostDiagnostics.templateWarmupAttempted },
        { label: "Active profile-post template warm-up attempt count", value: activeProfilePostDiagnostics.templateWarmupAttemptCount },
        { label: "Active profile-post template warm-up applied template", value: activeProfilePostDiagnostics.templateWarmupAppliedTemplate },
        { label: "Active profile-post template warm-up stop reason", value: activeProfilePostDiagnostics.templateWarmupStopReason },
        { label: "Active profile-post fetch response status code", value: activeProfilePostDiagnostics.responseStatusCode },
        { label: "Active profile-post fetch response status message", value: activeProfilePostDiagnostics.responseStatusMsg },
        { label: "Active profile-post fetch response top-level keys", value: activeProfilePostDiagnostics.responseTopLevelKeys },
        { label: "Active profile-post fetch response data keys", value: activeProfilePostDiagnostics.responseDataKeys },
        { label: "Active profile-post fetch response result keys", value: activeProfilePostDiagnostics.responseResultKeys },
        { label: "Active profile-post fetch parser path counts", value: activeProfilePostDiagnostics.parserPathCounts },
        { label: "Active profile-post fetch list sample keys", value: activeProfilePostDiagnostics.listSampleKeys },
        { label: "Active profile-post fetch reject reasons", value: activeProfilePostDiagnostics.rejectReasons },
        { label: "Profile discovered count", value: profileScanCount("profile_discovered_count", scanDiagnosticValue("aweme_id_count")) },
        { label: "Profile normalized count", value: profileScanCount("profile_normalized_count", String(state.profile_scan.raw_candidate_count)) },
        { label: "Profile duplicate count", value: profileScanCount("profile_duplicate_count", scanDiagnosticValue("profile_candidate_duplicate_count")) },
        { label: "Profile invalid count", value: profileScanCount("profile_invalid_count", scanDiagnosticValue("profile_candidate_invalid_count")) },
        { label: "Profile already collected count", value: String(popupMetrics.profile.already_collected_count) },
        { label: "Profile eligible count", value: String(popupMetrics.profile.eligible_count) },
        { label: "Profile queue total count", value: String(popupMetrics.profile.profile_total_count) },
        { label: "Profile batch limit", value: profileScanCount("profile_batch_limit", String(state.harvest_options.batch_limit ?? state.harvest.batch_limit)) },
        { label: "Profile batch pending count", value: profileScanCount("profile_batch_pending_count", String(pendingCount(state))) },
        { label: "Profile batch mode", value: profileScanCount("profile_batch_mode", `${state.harvest_options.batch}_${state.harvest_options.speed}`) },
        { label: "Profile queue limit reason", value: profileScanCount("profile_queue_limit_reason", "none") },
        { label: "Scan fallback used", value: scanDiagnosticValue("scan_fallback_used") },
        { label: "Scan fallback reason", value: scanDiagnosticValue("scan_fallback_reason") },
        { label: "Scan queue builder used", value: scanDiagnosticValue("scan_queue_builder_used") },
        { label: "Scan no-round reason", value: scanDiagnosticValue("scan_no_round_reason") },
        { label: "Legacy route invoked", value: scanDiagnosticValue("legacy_route_invoked") !== "none" ? scanDiagnosticValue("legacy_route_invoked") : scanDiagnosticValue("legacy_scan_profile_route_invoked") },
        { label: "Legacy route delegated", value: scanDiagnosticValue("legacy_route_delegated") !== "none" ? scanDiagnosticValue("legacy_route_delegated") : scanDiagnosticValue("legacy_scan_profile_delegated_to_canonical") },
        { label: "Backend reconciliation counter source", value: String(authoritativeCounters.diagnostics.backend_reconciliation_counter_source) },
        { label: "Backend reconciliation applied", value: String(authoritativeCounters.diagnostics.backend_reconciliation_applied_to_profile_counters) },
        { label: "Backend reconciliation matched count", value: String(authoritativeCounters.diagnostics.backend_reconciliation_matched_count) },
        { label: "Profile counter authority", value: String(authoritativeCounters.diagnostics.profile_counter_authority) },
        { label: "Popup metrics reconciler ran", value: String(popupMetrics.diagnostics.popup_metrics_reconciler_ran) },
        { label: "Popup metrics profile total source", value: String(popupMetrics.diagnostics.popup_metrics_profile_total_source) },
        { label: "Popup metrics already collected source", value: String(popupMetrics.diagnostics.popup_metrics_already_collected_source) },
        { label: "Popup metrics new count", value: String(popupMetrics.diagnostics.popup_metrics_new_count) },
        { label: "Popup metrics eligible count", value: String(popupMetrics.diagnostics.popup_metrics_eligible_count) },
        { label: "Popup metrics queue count", value: String(popupMetrics.diagnostics.popup_metrics_queue_count) },
        { label: "Popup metrics active runner remaining count", value: String(popupMetrics.diagnostics.popup_metrics_active_runner_remaining_count) },
        { label: "Popup metrics raw pending count", value: String(popupMetrics.diagnostics.popup_metrics_raw_pending_count) },
        { label: "Popup metrics raw batch pending count", value: String(popupMetrics.diagnostics.popup_metrics_raw_batch_pending_count) },
        { label: "Popup metrics profile tiles authority", value: String(largeProfilePersistedTotal != null ? "queue_total_persisted" : popupMetrics.diagnostics.popup_metrics_profile_tiles_authority) },
        ...(largeProfilePersistedTotal != null ? [
          { label: "Queue counter authority", value: String(popupDiagnosticsRecord(state).popup_counter_authority_selected ?? "queue_total_persisted") }
        ] : []),
        { label: "Popup metrics raw pending ignored for profile tiles", value: String(popupMetrics.diagnostics.popup_metrics_raw_pending_ignored_for_profile_tiles) },
        { label: "POST_SCAN_COUNTER_PIPELINE_TRACE", value: JSON.stringify(postScanCounterPipelineTrace) },
        { label: "PERSISTENT_COLLECT_JOB_TRACE", value: JSON.stringify(persistentCollectJobTrace) },
        { label: "POST_COLLECT_PIPELINE_TRACE", value: JSON.stringify(postCollectPipelineTrace) },
        { label: "Current batch saved count ignored", value: String(authoritativeCounters.diagnostics.current_batch_saved_count_ignored_for_already_collected) }
      ],
      queue_preview_label: scanInProgress ? `Queue preview/state snapshot: ${state.harvest.queue_preview.length} visible during scan` : `Queue preview: ${state.harvest.queue_preview.length} planned`
    },
    operator_help: {
      quick_start: [
        "Scan Profile to build a clean queue from the current Douyin profile.",
        "Test 3 Videos before a larger extraction run.",
        `Extract ${friendlyBatchLabel(state.harvest_options.batch)} to read metrics without saving yet.`,
        "Create a scan session, run a data check, then start with Save 1 Video."
      ],
      troubleshooting: [
        "If buttons are disabled, follow the Next step card from top to bottom.",
        "If a security check appears, solve it in the Douyin tab, then click Resume.",
        "If Extract Next 10 cannot start, run Test 3 Videos first and keep the profile tab ready.",
        "If Save to Capture Inbox is disabled, create a scan session and run a data check first."
      ],
      safety_tips: [
        "Use Next 10 and Safe for the most stable operator workflow.",
        "Start with Save 1 Video before Save to Capture Inbox on a new profile.",
        "Do not close the Douyin tab while extraction or saving is running.",
        "Reset Harvest if the queue no longer matches the current profile page."
      ],
      action_help: {
        verify_profile: getActionHelpText("verify_profile", actions, readiness, state),
        test_3_videos: getActionHelpText("test_3_videos", actions, readiness, state),
        dry_run_first: getActionHelpText("dry_run_first", actions, readiness, state),
        dry_run_last: getActionHelpText("dry_run_last", actions, readiness, state),
        dry_run_random: getActionHelpText("dry_run_random", actions, readiness, state),
        run_harvest: getActionHelpText("run_harvest", actions, readiness, state),
        prepare_backend_session: getActionHelpText("prepare_backend_session", actions, readiness, state),
        build_payload_preview: getActionHelpText("build_payload_preview", actions, readiness, state),
        flush_one_item: getActionHelpText("flush_one_item", actions, readiness, state),
        flush_batch: getActionHelpText("flush_batch", actions, readiness, state),
        mode: getActionHelpText("mode", actions, readiness, state),
        batch: getActionHelpText("batch", actions, readiness, state),
        speed: getActionHelpText("speed", actions, readiness, state),
        unattended_safe_mode: getActionHelpText("unattended_safe_mode", actions, readiness, state),
        resume: getActionHelpText("resume", actions, readiness, state),
        reset_harvest: getActionHelpText("reset_harvest", actions, readiness, state)
      },
      capture_inbox_cta: backendFlow.capture_inbox_cta
    }
  };
}

export function getWholeProfileHarvestProgressViewModel(state: WholeProfileHarvestState): WholeProfileHarvestProgressViewModel {
  return sanitizePopupViewState(getWholeProfileHarvestProgressViewModelUnreconciled(state), state);
}
