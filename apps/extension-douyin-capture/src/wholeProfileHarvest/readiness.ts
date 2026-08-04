import { collectCompletionOverridesActiveCollectRuntime, deriveAuthoritativeRunnerLock, sanitizeCanonicalPrimaryAction } from "./authoritativePopupState.js";
import { isHybridTailGapClosed, isHybridUnreachableTailGapOffer } from "./hybridUnreachableTailGap.js";
import { countQueueItemsWithHybridMetrics } from "./hybridHydration.js";
import { scanPaginationExhaustedWithPersisted } from "./scanPresentationPhase.js";
import { resolveScannerWorkflowPhase, type ScannerWorkflowPhase } from "./scannerWorkflowPhase.js";
import type { ScannerPresentationPhase } from "./scanAuthorityDiagnostics.js";
import { collectPresentationSuppressed, detectProfileContextMismatch, overcollectionDiagnosticsTrusted, persistedScanJobTotalsTrustedForStoredProfile, resolveScanJobExpectedCount, scanPersistedMeetsExpectedCount, scanSessionTrustedForStoredProfile } from "./profileContext.js";
import type { WholeProfileHarvestCalibration, WholeProfileHarvestState } from "./state.js";

export type WholeProfileHarvestRecommendedActionCode =
  | "verify_profile"
  | "calibrate_4_points"
  | "test_3_videos"
  | "run_extraction"
  | "prepare_backend_session"
  | "build_payload_preview"
  | "flush_one_item"
  | "flush_batch"
  | "resume"
  | "solve_captcha_then_resume"
  | "review_results"
  | "none";

export type WholeProfileHarvestRecommendedAction = {
  code: WholeProfileHarvestRecommendedActionCode;
  label: string;
  reason: string;
};

export type WholeProfileHarvestReadiness = {
  calibration_ready: boolean;
  profile_scan_ready: boolean;
  dry_run_ready: boolean;
  extraction_ready: boolean;
  backend_session_ready: boolean;
  payload_preview_ready: boolean;
  payload_guard_passed: boolean;
  one_item_flush_ready: boolean;
  batch_flush_ready: boolean;
  resume_ready: boolean;
  stop_ready: boolean;
  next_recommended_action: WholeProfileHarvestRecommendedAction;
};

export type ScannerActionKey =
  | "scan_profile"
  | "review_overcollection"
  | "calibrate"
  | "start_collecting"
  | "skip_hybrid_incomplete"
  | "close_unreachable_tail_gap"
  | "pause"
  | "resume"
  | "open_capture_inbox"
  | "sign_in_to_app"
  | "switch_to_active_profile"
  | "none";

export type DouyinScannerWorkflowActionKey = Exclude<ScannerActionKey, "none" | "switch_to_active_profile">;

export type DouyinScannerWorkflowReadiness = {
  calibrationReady: boolean;
  profileScanReady: boolean;
  classificationReady: boolean;
  collectQueueReady: boolean;
  collecting: boolean;
  collectionRunnerActive: boolean;
  primaryActionLockedReason: "collection_running" | null;
  paused: boolean;
  busy: boolean;
  canScanProfile: boolean;
  canStartCollecting: boolean;
  canReset: boolean;
  nextActionKey: DouyinScannerWorkflowActionKey;
  disabledReason: string | null;
  hybridMetricsBlockedReason: string | null;
};

export type CanonicalCalibrationReady = {
  ready: boolean;
  source: "canonical" | "legacy" | "missing";
  canonicalReady: boolean;
  legacyReady: boolean;
  conflict: boolean;
};

export type CanonicalScannerPrimaryActionDecisionTrace = {
  selectorVersion: "22C-11B";
  selector_version: "22C-11B";
  profileScanReady: boolean;
  profile_scan_ready: boolean;
  canonicalCalibrationReady: boolean;
  canonical_calibration_ready: boolean;
  extractionReady: boolean;
  extraction_ready: boolean;
  backendSessionReady: boolean;
  backend_session_ready: boolean;
  collection_status: string;
  collection_runner_active: boolean;
  primary_action_locked_reason: "collection_running" | null;
  queue_count: number;
  pending_count: number;
  scanner_busy: boolean;
  selectedAction: DouyinScannerWorkflowActionKey;
  selected_action: DouyinScannerWorkflowActionKey;
  reason: string;
  workflow_phase: ScannerWorkflowPhase;
  presentation_phase: ScannerPresentationPhase;
  diagnostics_trusted: boolean;
};

export type CanonicalScannerPrimaryAction = {
  key: DouyinScannerWorkflowActionKey;
  title: string;
  label: string;
  description: string;
  enabled: boolean;
  disabledReason: string | null;
  source: "getCanonicalScannerPrimaryAction";
  selectorVersion: "22C-11B";
  calibration: CanonicalCalibrationReady;
  decisionTrace: CanonicalScannerPrimaryActionDecisionTrace;
};

export type WholeProfileHarvestActionControl = {
  enabled: boolean;
  visible: boolean;
  disabledReason: string | null;
  label?: string;
};

export type WholeProfileHarvestActionState = {
  verifyProfile: WholeProfileHarvestActionControl;
  dryRunFirst: WholeProfileHarvestActionControl;
  dryRunLast: WholeProfileHarvestActionControl;
  dryRunRandom: WholeProfileHarvestActionControl;
  runHarvest: WholeProfileHarvestActionControl;
  prepareBackendSession: WholeProfileHarvestActionControl;
  buildPayloadPreview: WholeProfileHarvestActionControl;
  flushOneItem: WholeProfileHarvestActionControl;
  flushBatch: WholeProfileHarvestActionControl;
  stop: WholeProfileHarvestActionControl;
  resume: WholeProfileHarvestActionControl;
  resetHarvest: WholeProfileHarvestActionControl;
};

function extractedResults(state: WholeProfileHarvestState) {
  return state.harvest.results.filter((result) => result.status === "extracted");
}

function flushableExtractedResults(state: WholeProfileHarvestState) {
  return extractedResults(state).filter((result) => !result.capture_inbox_item_id);
}

function oneItemFlushSucceeded(state: WholeProfileHarvestState): boolean {
  return state.harvest.backend.one_item_flush.status === "succeeded"
    && typeof state.harvest.backend.one_item_flush.capture_inbox_item_id === "string"
    && state.harvest.backend.one_item_flush.capture_inbox_item_id.length > 0;
}

function hasFourCanonicalCalibrationPoints(calibration: WholeProfileHarvestCalibration | (Partial<WholeProfileHarvestCalibration> & Record<string, unknown>)): boolean {
  const points = (calibration as { points?: Record<string, unknown> }).points;
  if (!points || typeof points !== "object") return false;
  const canonical = ["like", "comment", "favorite", "share"];
  if (canonical.every((key) => points[key] != null)) return true;
  const legacy = ["like_count", "comment_count", "favorite_count", "share_count"];
  return legacy.every((key) => points[key] != null);
}

type CalibrationReadyInput = {
  calibration: WholeProfileHarvestCalibration | (Partial<WholeProfileHarvestCalibration> & Record<string, unknown>) | null | undefined;
};

export function getCanonicalCalibrationReady(state: CalibrationReadyInput): CanonicalCalibrationReady {
  const calibration = state.calibration;
  if (!calibration || typeof calibration !== "object") {
    return { ready: false, source: "missing", canonicalReady: false, legacyReady: false, conflict: false };
  }

  const canonicalReady = calibration.status === "calibrated"
    && (calibration as { ready?: unknown }).ready === true
    && typeof calibration.point_count === "number"
    && calibration.point_count >= 4
    && hasFourCanonicalCalibrationPoints(calibration);
  const legacyReady = (calibration as { calibrationStatus?: unknown }).calibrationStatus === "calibrated"
    && typeof calibration.point_count === "number"
    && calibration.point_count >= 4
    && hasFourCanonicalCalibrationPoints(calibration);

  if (canonicalReady) {
    return {
      ready: true,
      source: "canonical",
      canonicalReady,
      legacyReady,
      conflict: canonicalReady !== legacyReady
    };
  }

  if (legacyReady) {
    return {
      ready: true,
      source: "legacy",
      canonicalReady,
      legacyReady,
      conflict: false
    };
  }

  return {
    ready: false,
    source: "missing",
    canonicalReady,
    legacyReady,
    conflict: canonicalReady !== legacyReady
  };
}

export function isDouyinCalibrationReady(calibration: WholeProfileHarvestCalibration | (Partial<WholeProfileHarvestCalibration> & Record<string, unknown>) | null | undefined): boolean {
  return getCanonicalCalibrationReady({ calibration }).ready;
}

export function isWholeProfileCalibrationReady(state: WholeProfileHarvestState): boolean {
  return getCanonicalCalibrationReady(state).ready;
}

function readHybridNetworkCacheModeFlagFromSummary(summary: unknown): "enabled" | "disabled" | null {
  if (!summary || typeof summary !== "object" || Array.isArray(summary)) return null;
  const flag = (summary as Record<string, unknown>).hybrid_network_cache_mode_flag;
  if (flag === "enabled" || flag === true) return "enabled";
  if (flag === "disabled" || flag === false) return "disabled";
  return null;
}

/** Read the operator hybrid collect flag from either debug summary mirror. */
export function readHybridNetworkCacheModeFlagFromState(state: WholeProfileHarvestState): "enabled" | "disabled" | null {
  return readHybridNetworkCacheModeFlagFromSummary(state.debug.last_response_summary)
    ?? readHybridNetworkCacheModeFlagFromSummary(state.debug.last_request_summary);
}

/**
 * Hybrid network-cache collect does not open modals or read the 4 calibrated
 * DOM points. When the operator flag is mirrored into state diagnostics,
 * calibration is not required for Start Collecting / primary-action routing.
 */
export function isHybridNetworkCacheModeEnabledForCollect(state: WholeProfileHarvestState): boolean {
  return readHybridNetworkCacheModeFlagFromState(state) === "enabled";
}

export type PreserveOperatorCollectPrerequisitesOptions = {
  /** Authoritative operator toggle from chrome.storage when diagnostics mirrors are stale. */
  hybridNetworkCacheModeEnabled?: boolean;
};

/**
 * Scan finalize writes fresh runtime diagnostics that omit operator prerequisites.
 * Preserve hybrid collect mode across those wholesale summary replacements.
 */
export function preserveOperatorCollectPrerequisitesInDiagnostics(
  priorState: WholeProfileHarvestState,
  diagnostics: Record<string, unknown>,
  options: PreserveOperatorCollectPrerequisitesOptions = {}
): Record<string, unknown> {
  const nextFlag = readHybridNetworkCacheModeFlagFromSummary(diagnostics);
  if (nextFlag === "enabled") return diagnostics;
  const fromState = readHybridNetworkCacheModeFlagFromState(priorState);
  const fromStorage = options.hybridNetworkCacheModeEnabled === true
    ? "enabled"
    : options.hybridNetworkCacheModeEnabled === false
      ? "disabled"
      : null;
  const preservedHybrid = fromState === "enabled" || fromStorage === "enabled"
    ? "enabled"
    : fromState ?? fromStorage;
  if (!preservedHybrid) return diagnostics;
  return { ...diagnostics, hybrid_network_cache_mode_flag: preservedHybrid };
}

function mergeHybridNetworkCacheModeFlagIntoSummary(
  summary: unknown,
  flagValue: "enabled" | "disabled"
): Record<string, unknown> {
  const base = summary && typeof summary === "object" && !Array.isArray(summary)
    ? summary as Record<string, unknown>
    : {};
  return { ...base, hybrid_network_cache_mode_flag: flagValue };
}

/** Mirror the chrome.storage hybrid flag into harvest diagnostics for sync readiness. */
export function applyHybridNetworkCacheModeFlagToState(
  state: WholeProfileHarvestState,
  enabled: boolean
): WholeProfileHarvestState {
  const flagValue = enabled ? "enabled" : "disabled";
  if (readHybridNetworkCacheModeFlagFromState(state) === flagValue) return state;
  return {
    ...state,
    debug: {
      ...state.debug,
      last_response_summary: mergeHybridNetworkCacheModeFlagIntoSummary(state.debug.last_response_summary, flagValue),
      last_request_summary: mergeHybridNetworkCacheModeFlagIntoSummary(state.debug.last_request_summary, flagValue)
    }
  };
}

/** True when 4-point calibration is satisfied OR Hybrid collect makes it unnecessary. */
export function isCollectCalibrationSatisfied(state: WholeProfileHarvestState): boolean {
  if (isHybridNetworkCacheModeEnabledForCollect(state)) return true;
  if (isWholeProfileCalibrationReady(state)) return true;
  if (state.layer.dry_run_ready && state.dry_run.status === "success" && (state.dry_run.pass ?? 0) >= 3) {
    return true;
  }
  return false;
}

const SCANNER_BUSY_STALE_MS = 2 * 60 * 1000;
const SCANNER_BUSY_STALE_MESSAGE = "Previous scan was interrupted. Please scan again.";
const SCANNER_BUSY_WAIT_MESSAGE = "Wait for the current step to finish.";

export type ScannerBusyState = {
  isBusy: boolean;
  busyReason: string | null;
  busySource: string | null;
  busyLabel: string | null;
  disabledLabel: string | null;
  isStale: boolean;
};

type ScannerBusyCandidate = {
  source: string;
  status: unknown;
  started_at?: string | null;
  updated_at?: string | null;
};

function timestampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function candidateIsStale(candidate: ScannerBusyCandidate, nowMs: number): boolean {
  const latest = timestampMs(candidate.updated_at) ?? timestampMs(candidate.started_at);
  if (latest === null) return true;
  return nowMs - latest > SCANNER_BUSY_STALE_MS;
}

export function getDouyinScannerBusyState(state: WholeProfileHarvestState, nowMs = Date.now()): ScannerBusyState {
  const collectionCompletionOverridden = collectCompletionOverridesActiveCollectRuntime(state);
  const candidates: ScannerBusyCandidate[] = [
    { source: "scan.status", status: state.workflow.scan.status, started_at: state.workflow.scan.started_at, updated_at: state.workflow.scan.updated_at },
    { source: "classification.status", status: state.workflow.classification.status, started_at: state.workflow.classification.started_at, updated_at: state.workflow.classification.updated_at },
    ...(collectionCompletionOverridden ? [] : [{ source: "collection.status", status: state.workflow.collection.status, started_at: state.workflow.collection.started_at, updated_at: state.workflow.collection.updated_at }])
  ];

  const running = candidates.find((candidate) => candidate.status === "running" || candidate.status === "pausing");
  if (!running) return { isBusy: false, busyReason: null, busySource: null, busyLabel: null, disabledLabel: null, isStale: false };
  const labels = running.source === "scan.status"
    ? { busyLabel: "Scanning Profile", disabledLabel: "Scanning..." }
    : running.source === "classification.status"
      ? { busyLabel: "Classifying Videos", disabledLabel: "Classifying..." }
      : { busyLabel: running.status === "pausing" ? "Pausing Collection" : "Collecting Videos", disabledLabel: running.status === "pausing" ? "Pausing..." : "Pause" };
  if (candidateIsStale(running, nowMs)) return { isBusy: false, busyReason: SCANNER_BUSY_STALE_MESSAGE, busySource: running.source, ...labels, isStale: true };
  return { isBusy: true, busyReason: SCANNER_BUSY_WAIT_MESSAGE, busySource: running.source, ...labels, isStale: false };
}

export function getScannerBusyState(state: WholeProfileHarvestState, nowMs = Date.now()): ScannerBusyState {
  return getDouyinScannerBusyState(state, nowMs);
}

function isBusy(state: WholeProfileHarvestState): boolean {
  return getScannerBusyState(state).isBusy;
}

function isPaused(state: WholeProfileHarvestState): boolean {
  return state.harvest.resume_available === true
    && (
      state.workflow.collection.status === "paused"
      || (
        state.workflow.collection.status === "pausing"
        && state.harvest.pause_requested === true
        && state.workflow.active_task == null
        && state.workflow.action_lock == null
      )
    );
}

function isPausing(state: WholeProfileHarvestState): boolean {
  return state.workflow.collection.status === "pausing"
    && (state.workflow.active_task === "collect_videos" || state.workflow.action_lock === "collect_videos");
}

function validDouyinProfileUrl22C11B(value: unknown): boolean {
  return typeof value === "string" && /(^https?:\/\/)?([^/]+\.)?douyin\.com\/user\//i.test(value);
}

function diagnosticsRecordByChannel22C13B(value: unknown, channel: "scan_authority_diagnostics" | "runtime_debug_diagnostics"): Record<string, unknown> {
  if (!value || typeof value !== "object") return {};
  const record = value as Record<string, unknown>;
  const candidateChannel = typeof record.diagnostics_channel === "string" ? record.diagnostics_channel : null;
  return candidateChannel === channel ? record : {};
}

function mergedScanDiagnostics22C13B(state: WholeProfileHarvestState): Record<string, unknown> {
  const profile = diagnosticsRecordByChannel22C13B(state.profile_scan.diagnostics, "scan_authority_diagnostics");
  const verify = diagnosticsRecordByChannel22C13B(state.verify.diagnostics, "scan_authority_diagnostics");
  const requestRuntime = diagnosticsRecordByChannel22C13B(state.debug.last_request_summary, "runtime_debug_diagnostics");
  const responseRuntime = diagnosticsRecordByChannel22C13B(state.debug.last_response_summary, "runtime_debug_diagnostics");
  const authority = Object.keys(verify).length > 0 ? { ...profile, ...verify } : profile;
  return { ...requestRuntime, ...responseRuntime, ...authority };
}

function countSemanticsNumberArrayLength22C14Q(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

function countSemanticsNonEmptyString22C14Q(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function overDisplayedItemValue22C14Q(item: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (item[key] != null) return item[key];
  }
  return null;
}

/** Normalize forensic-export extra items to the canonical itemized-proof shape. */
export function normalizeOverDisplayedExtraItem22C14Q(raw: Record<string, unknown>): Record<string, unknown> {
  return {
    ...raw,
    raw_index: overDisplayedItemValue22C14Q(raw, "raw_index", "raw_index_in_page", "raw_index_found"),
    source_endpoint: overDisplayedItemValue22C14Q(raw, "source_endpoint", "source_url", "endpoint_path", "request_url_path"),
    source_cursor: overDisplayedItemValue22C14Q(raw, "source_cursor", "cursor", "page_marker", "source_template_id", "request_cursor", "response_cursor")
  };
}

export function normalizeOverDisplayedExtraItems22C14Q(items: unknown): Record<string, unknown>[] {
  if (!Array.isArray(items)) return [];
  return items
    .filter((raw): raw is Record<string, unknown> => Boolean(raw) && typeof raw === "object")
    .map((raw) => normalizeOverDisplayedExtraItem22C14Q(raw));
}

export function unresolvedOvercollectionReviewActive(
  state: WholeProfileHarvestState,
  scanDiagnostics: Record<string, unknown>
): boolean {
  const needsValidation = scanDiagnostics.over_displayed_validation_status === "needs_validation"
    || String(scanDiagnostics.count_semantics_status ?? "") === "overcollected_needs_validation";
  return needsValidation
    && scanDiagnostics.over_displayed_same_profile_validated !== "yes"
    && scanDiagnostics.over_displayed_validation_status !== "validated_same_profile"
    && (state.scan_job.status === "completed" || state.profile_scan.status === "success" || state.verify.status === "success");
}

export function buildOvercollectionReviewPresentation(diagnostics: Record<string, unknown>): {
  title: string;
  description: string;
  emptyState: string | null;
  extraCount: number | null;
  displayedCount: number | null;
  collectableCount: number | null;
} {
  const extraCount = numberDiagnostic22C14R(diagnostics.over_displayed_count);
  const displayedCount = numberDiagnostic22C14R(diagnostics.displayed_profile_count ?? diagnostics.expected_profile_video_count);
  const collectableCount = numberDiagnostic22C14R(diagnostics.collectable_count ?? diagnostics.api_unique_count);
  const validated = diagnostics.over_displayed_validation_status === "validated_same_profile"
    && diagnostics.over_displayed_same_profile_validated === "yes";
  const outsideProfile = diagnostics.over_displayed_validation_status === "outside_profile_detected"
    || diagnostics.count_semantics_status === "failed_overcollection_outside_profile";
  const needsValidation = diagnostics.over_displayed_validation_status === "needs_validation"
    || String(diagnostics.count_semantics_status ?? "") === "overcollected_needs_validation";
  const videoWord = extraCount === 1 ? "video" : "videos";
  if (needsValidation) {
    return {
      title: "Scan needs review",
      description: "Over-display exact-item validation is required before collecting.",
      emptyState: "Over-display exact-item validation is required before collecting.",
      extraCount,
      displayedCount,
      collectableCount
    };
  }
  if (validated) {
    const extraLabel = extraCount == null ? "additional" : String(extraCount);
    const visibleLabel = displayedCount == null ? "the visible page count" : String(displayedCount);
    const totalLabel = collectableCount == null ? "videos" : `${collectableCount} videos`;
    return {
      title: "Scan complete",
      description: `Douyin shows ${visibleLabel} on the profile page; API found ${extraLabel} more from the same creator (validated). ${totalLabel} are ready to collect.`,
      emptyState: null,
      extraCount,
      displayedCount,
      collectableCount
    };
  }
  if (outsideProfile) {
    const extraLabel = extraCount == null ? "extra" : String(extraCount);
    return {
      title: "Review extra videos",
      description: `API returned ${extraLabel} ${videoWord} beyond the visible profile count. At least one does not match this creator — review before collecting.`,
      emptyState: extraCount == null
        ? "Extra API videos need review before collecting."
        : (extraCount === 1
          ? "1 extra API video needs review before collecting."
          : `${extraCount} extra API videos need review before collecting.`),
      extraCount,
      displayedCount,
      collectableCount
    };
  }
  const extraLabel = extraCount == null ? "extra" : String(extraCount);
  return {
    title: "Review extra API videos",
    description: `API returned ${extraLabel} ${videoWord} beyond the visible profile count. Confirm they belong to this creator before collecting.`,
    emptyState: extraCount == null
      ? "Extra API videos need review before collecting."
      : (extraCount === 1
        ? "1 extra API video needs review before collecting."
        : `${extraCount} extra API videos need review before collecting.`),
    extraCount,
    displayedCount,
    collectableCount
  };
}

function overDisplayedCursorOrTemplateValid22C14Q(value: unknown): boolean {
  return countSemanticsNonEmptyString22C14Q(value) || numberDiagnostic22C14R(value) != null;
}

function overDisplayedItemizedProofValid22C14Q(diagnostics: Record<string, unknown>): boolean {
  const rawCount = numberDiagnostic22C14R(diagnostics.over_displayed_count);
  const count = rawCount == null ? 0 : Math.max(0, rawCount);
  if (count <= 0) return true;
  if (countSemanticsNumberArrayLength22C14Q(diagnostics.over_displayed_extra_ids_exact) !== count) return false;
  if (countSemanticsNumberArrayLength22C14Q(diagnostics.over_displayed_extra_items_exact) !== count) return false;
  if (diagnostics.over_displayed_validation_status !== "validated_same_profile") return false;
  if (diagnostics.over_displayed_same_profile_validated !== "yes") return false;
  const items = normalizeOverDisplayedExtraItems22C14Q(diagnostics.over_displayed_extra_items_exact);
  if (items.length === 0 && !countSemanticsNonEmptyString22C14Q(diagnostics.over_displayed_itemized_reason_summary)) return false;
  return items.every((raw) => {
    if (!raw || typeof raw !== "object") return false;
    const item = normalizeOverDisplayedExtraItem22C14Q(raw as Record<string, unknown>);
    const indexedApiEvidence = numberDiagnostic22C14R(overDisplayedItemValue22C14Q(item, "page_index", "page_index_found")) != null
      && numberDiagnostic22C14R(overDisplayedItemValue22C14Q(item, "raw_index", "raw_index_in_page", "raw_index_found")) != null
      && numberDiagnostic22C14R(overDisplayedItemValue22C14Q(item, "accepted_index", "accepted_index_in_api_order", "index_in_final_order")) != null
      && countSemanticsNonEmptyString22C14Q(overDisplayedItemValue22C14Q(item, "source_endpoint", "source_url", "endpoint_path", "request_url_path"))
      && overDisplayedCursorOrTemplateValid22C14Q(overDisplayedItemValue22C14Q(item, "source_cursor", "cursor", "page_marker", "source_template_id", "request_cursor", "response_cursor"));
    const legacySameProfileEvidence = countSemanticsNonEmptyString22C14Q(overDisplayedItemValue22C14Q(item, "profile_url", "source_profile_url", "target_profile_url"));
    const sameProfileValidated = item.same_profile_validated === "yes" || item.same_profile_validation_status === "same_profile";
    return countSemanticsNonEmptyString22C14Q(item.aweme_id)
      && (indexedApiEvidence || legacySameProfileEvidence)
      && sameProfileValidated
      && countSemanticsNonEmptyString22C14Q(overDisplayedItemValue22C14Q(item, "author_sec_uid", "author_user_id", "author_id", "source_profile_identifier", "target_profile_identifier", "requested_profile_identifier", "profile_url", "source_profile_url", "target_profile_url"));
  });
}

/** Single extra same-profile video with ledger proof does not require manual review. */
function benignSingleOverdisplayAutoValidated22C14Q(
  diagnostics: Record<string, unknown>
): boolean {
  const count = numberDiagnostic22C14R(diagnostics.over_displayed_count);
  if (count !== 1) return false;
  if (diagnostics.over_displayed_validation_status === "outside_profile_detected") return false;
  if (diagnostics.over_displayed_validation_status === "validated_same_profile"
    && diagnostics.over_displayed_same_profile_validated === "yes") {
    return true;
  }
  if (diagnostics.over_displayed_extra_source === "accepted_target_ledger_boundary_tail"
    && diagnostics.accepted_target_ledger_present === "yes"
    && diagnostics.over_displayed_validation_status === "validated_same_profile") {
    return true;
  }
  const ids = diagnostics.over_displayed_extra_ids_exact;
  if (!Array.isArray(ids) || ids.length !== 1) return false;
  const items = normalizeOverDisplayedExtraItems22C14Q(diagnostics.over_displayed_extra_items_exact);
  if (items.length !== 1) return false;
  const item = items[0]!;
  return item.same_profile_validated === "yes" || item.same_profile_validation_status === "same_profile";
}

function overDisplayedInvariantProofBlocking22C14Q(diagnostics: Record<string, unknown>): boolean {
  const overDisplayedCount = Math.max(0, numberDiagnostic22C14R(diagnostics.over_displayed_count) ?? 0);
  const displayed = numberDiagnostic22C14R(diagnostics.displayed_profile_count ?? diagnostics.expected_profile_video_count);
  const persisted = numberDiagnostic22C14R(diagnostics.persisted_count ?? diagnostics.scan_job_total_persisted ?? diagnostics.profile_queue_total_count);
  const persistedExceedsDisplayed = displayed != null && persisted != null && persisted > displayed;
  return (overDisplayedCount > 0 || persistedExceedsDisplayed) && !overDisplayedItemizedProofValid22C14Q(diagnostics);
}

function countSemanticsTerminalAllowed22C14Q(diagnostics: Record<string, unknown>): boolean {
  const status = String(diagnostics.count_semantics_status ?? "");
  if (overDisplayedInvariantProofBlocking22C14Q(diagnostics)) return false;
  if (status === "completed_with_api_over_displayed_count") {
    return overDisplayedItemizedProofValid22C14Q(diagnostics);
  }
  return status === "full_match"
    || status === "completed_with_displayed_count_mismatch"
    || status === "completed_after_secondary_recovery"
    || status === "completed_with_partial_secondary_recovery";
}

function numberDiagnostic22C14R(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" && value.trim() ? Number(value) : Number.NaN;
  return Number.isFinite(numeric) ? numeric : null;
}

function activeCurrentScanProgress22C14R(state: WholeProfileHarvestState, diagnostics = mergedScanDiagnostics22C13B(state)): boolean {
  const scanRescanInFlight = state.workflow.scan.status === "running"
    && (state.workflow.active_task === "scan_profile" || state.workflow.action_lock === "scan_profile");
  if (scanRescanInFlight) return true;
  const scanJobActive = state.scan_job.status === "running" || state.scan_job.status === "retry_wait";
  if (
    !scanJobActive
    && state.scan_job.status === "completed"
    && state.profile_scan.status === "success"
  ) {
    const expected = resolveScanJobExpectedCount(state);
    const persisted = Math.max(
      state.scan_job.total_persisted ?? 0,
      state.profile_scan.accepted_target_count ?? 0,
      state.verify.verified_target_count ?? 0
    );
    if (persisted > 0 && scanPersistedMeetsExpectedCount(expected, persisted)) return false;
  }
  if (scanJobActive) return true;
  const terminalFailure = state.workflow.scan.status === "failed"
    || state.scan_job.status === "failed"
    || state.profile_scan.status === "failed"
    || state.verify.status === "failed"
    || String(diagnostics.scan_finalization_result ?? "") === "failed";
  if (terminalFailure && state.workflow.active_task !== "scan_profile" && state.scan_job.status !== "running" && state.scan_job.status !== "retry_wait") return false;
  const workflowActive = state.workflow.active_task === "scan_profile" || state.workflow.action_lock === "scan_profile" || state.workflow.scan.status === "running";
  const runtimeRunId = typeof diagnostics.scan_run_id === "string" && diagnostics.scan_run_id.trim() ? diagnostics.scan_run_id.trim() : null;
  const matchingRun = runtimeRunId == null || runtimeRunId === state.run_id || runtimeRunId === state.scan_job.scan_job_id;
  if (scanJobActive) return !terminalFailure;
  const progressSignals = [
    diagnostics.scan_progress_discovered,
    diagnostics.scan_progress_pages,
    diagnostics.scan_progress_requests,
    diagnostics.scan_progress_update_seq,
    diagnostics.scan_job_page_count,
    diagnostics.scan_job_request_count,
    state.scan_job.total_discovered,
    state.scan_job.page_count,
    state.scan_job.request_count
  ].map(numberDiagnostic22C14R);
  const hasPositiveProgress = progressSignals.some((value) => value != null && value > 0);
  const hasRuntimeProgress = typeof diagnostics.scan_progress_updated_at !== "undefined" || typeof diagnostics.scan_progress_update_seq !== "undefined";
  return !terminalFailure && matchingRun && workflowActive && (hasPositiveProgress || hasRuntimeProgress);
}

function scanNearCompleteAllowed22C14B(state: WholeProfileHarvestState, diagnostics = mergedScanDiagnostics22C13B(state)): boolean {
  const expectedRaw = diagnostics.expected_profile_video_count ?? state.scan_job.expected_count;
  const collectedRaw = diagnostics.scan_job_total_persisted ?? diagnostics.profile_queue_total_count ?? state.scan_job.total_persisted;
  const remainingRaw = diagnostics.scan_progress_remaining ?? diagnostics.scan_completeness_missing_count ?? diagnostics.missing_profile_video_count;
  const expected = typeof expectedRaw === "number" ? expectedRaw : typeof expectedRaw === "string" ? Number(expectedRaw) : null;
  const collected = typeof collectedRaw === "number" ? collectedRaw : typeof collectedRaw === "string" ? Number(collectedRaw) : null;
  const remaining = typeof remainingRaw === "number" ? remainingRaw : typeof remainingRaw === "string" ? Number(remainingRaw) : null;
  if (expected == null || !Number.isFinite(expected) || expected <= 0) return false;
  if (collected == null || !Number.isFinite(collected) || collected >= expected) return false;
  const gapCount = remaining != null && Number.isFinite(remaining) ? Math.max(remaining, 0) : Math.max(expected - collected, 0);
  const threshold = Math.max(5, Math.ceil(expected * 0.01));
  const finalizationResult = String(diagnostics.scan_finalization_result ?? "");
  return gapCount > 0
    && gapCount <= threshold
    && (finalizationResult === "incomplete" || finalizationResult === "completed_with_warning")
    && (state.scan_job.status === "failed" || state.scan_job.status === "completed");
}

export function getActiveProfilePostScanBlockedReason(state: WholeProfileHarvestState): string | null {
  return activeProfilePostScanUnresolved22C14B(state, mergedScanDiagnostics22C13B(state));
}

function activeProfilePostScanUnresolved22C14B(state: WholeProfileHarvestState, diagnostics = mergedScanDiagnostics22C13B(state)): string | null {
  if (activeCurrentScanProgress22C14R(state, diagnostics)) return null;
  const statusCode = diagnostics.active_profile_post_fetch_response_status_code ?? diagnostics.active_profile_post_page_fetch_last_status_code_22C14B ?? state.scan_job.last_status_code;
  const templateFound = diagnostics.active_profile_post_template_found ?? diagnostics.minimal_scan_active_profile_post_template_found_22C13B;
  const requiredKeysAvailable = diagnostics.active_profile_post_template_required_query_keys_available ?? diagnostics.minimal_scan_active_profile_post_template_required_query_keys_available_22C13B;
  const expectedRaw = diagnostics.expected_profile_video_count ?? state.scan_job.expected_count;
  const collectedRaw = diagnostics.scan_job_total_persisted ?? diagnostics.profile_queue_total_count ?? state.scan_job.total_persisted;
  const expected = typeof expectedRaw === "number" ? expectedRaw : typeof expectedRaw === "string" ? Number(expectedRaw) : null;
  const collected = typeof collectedRaw === "number" ? collectedRaw : typeof collectedRaw === "string" ? Number(collectedRaw) : null;
  const expectedKnown = expected != null && Number.isFinite(expected) && expected > 0;
  const nearCompleteTerminal = scanNearCompleteAllowed22C14B(state, diagnostics);
  const retrying = state.scan_job.status === "retry_wait" || state.workflow.scan.status === "running";
  const failed = state.scan_job.status === "failed" || state.workflow.scan.status === "failed" || state.profile_scan.status === "failed" || state.verify.status === "failed";
  const staleResumeRecoveryActive = diagnostics.stale_resume_recovery_attempted === "yes"
    && diagnostics.stale_resume_recovery_result === "restarted_from_fresh_cursor"
    && state.scan_job.has_more_state === true
    && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait");
  const resumableBudgetExhausted = diagnostics.auto_continuation_limit_reached === "yes"
    || diagnostics.continuation_reason === "auto_continuation_limit_reached"
    || diagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || diagnostics.final_exhaustion_mode === "manual_continuation"
    || diagnostics.page_budget_exhausted === "yes"
    || diagnostics.partial_scan_resumable === "yes"
    || diagnostics.continuation_available === "yes"
    || diagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || diagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted";
  const activeUnusable = (statusCode != null && statusCode !== 0 && statusCode !== "0") || templateFound === "no" || requiredKeysAvailable === "no" || (String(state.scan_job.last_error ?? "").includes("active_profile_post") && !resumableBudgetExhausted);
  if (staleResumeRecoveryActive || resumableBudgetExhausted) return null;
  if ((!failed && nearCompleteTerminal) || (!failed && countSemanticsTerminalAllowed22C14Q(diagnostics))) return null;
  if (expectedKnown && activeUnusable && retrying) return "Active profile-post source is retrying; Scan Profile must finish before collecting.";
  if (expectedKnown && activeUnusable && failed) return "Active profile-post source failed; rerun Scan Profile before collecting.";
  return null;
}

function largeProfileAuthoritativeQueueCount22C14B(state: WholeProfileHarvestState, diagnostics: Record<string, unknown>): number | null {
  const visibleRaw = diagnostics.queue_total_visible ?? state.harvest.queue.length;
  const visible = typeof visibleRaw === "number" ? visibleRaw : typeof visibleRaw === "string" ? Number(visibleRaw) : state.harvest.queue.length;
  const candidates = [
    diagnostics.queue_total_persisted,
    diagnostics.scan_job_total_persisted,
    diagnostics.profile_queue_total_count,
    state.scan_job.total_persisted
  ];
  for (const total of candidates) {
    const numeric = typeof total === "number" ? total : typeof total === "string" && total.trim() ? Number(total) : Number.NaN;
    if (Number.isFinite(numeric) && numeric > 0 && (diagnostics.large_profile_mode === "yes" || !Number.isFinite(visible) || numeric >= visible)) return Math.round(numeric);
  }
  return null;
}

function getAuthoritativeScanStopReason(diagnostics: Record<string, unknown>): string {
  const authoritative = diagnostics.scan_stop_authoritative;
  return typeof authoritative === "string" && authoritative.trim() ? authoritative.trim() : "none";
}

function profileScanReady(state: WholeProfileHarvestState): boolean {
  const diagnostics = mergedScanDiagnostics22C13B(state);
  const jobExpected = resolveScanJobExpectedCount(state);
  const jobPersisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0
  );
  const validProfileUrlDetected = validDouyinProfileUrl22C11B(state.profile_url)
    || validDouyinProfileUrl22C11B(state.page_context.current_url)
    || validDouyinProfileUrl22C11B(diagnostics.profile_url)
    || validDouyinProfileUrl22C11B(diagnostics.current_url)
    || validDouyinProfileUrl22C11B(diagnostics.tab_url);
  if (scanPersistedMeetsExpectedCount(jobExpected, jobPersisted) && validProfileUrlDetected) {
    return true;
  }
  if (scanPaginationExhaustedWithPersisted(state) && validProfileUrlDetected && jobPersisted > 0) {
    return true;
  }
  const nearCompleteAllowed = scanNearCompleteAllowed22C14B(state, diagnostics);
  const countSemanticsAllowed = countSemanticsTerminalAllowed22C14Q(diagnostics);
  const countSemanticsStatus = String(diagnostics.count_semantics_status ?? "");
  const overDisplayedProofBlocking = overDisplayedInvariantProofBlocking22C14Q(diagnostics);
  const outsideProfileOvercollectionBlocking = countSemanticsStatus === "failed_overcollection_outside_profile" || diagnostics.scan_health_verdict === "failed_overcollection_outside_profile";
  const countSemanticsBlocking = countSemanticsStatus === "incomplete_internal_loss" || countSemanticsStatus === "incomplete_api_not_exhausted" || countSemanticsStatus === "overcollected_needs_validation" || outsideProfileOvercollectionBlocking || overDisplayedProofBlocking;
  const staleResumeRecoveryActive = diagnostics.stale_resume_recovery_attempted === "yes"
    && diagnostics.stale_resume_recovery_result === "restarted_from_fresh_cursor"
    && state.scan_job.has_more_state === true
    && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait");
  const resumableBudgetExhausted = diagnostics.auto_continuation_limit_reached === "yes"
    || diagnostics.continuation_reason === "auto_continuation_limit_reached"
    || diagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || diagnostics.final_exhaustion_mode === "manual_continuation"
    || diagnostics.page_budget_exhausted === "yes"
    || diagnostics.partial_scan_resumable === "yes"
    || diagnostics.continuation_available === "yes"
    || diagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || diagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted";
  if (!staleResumeRecoveryActive && !resumableBudgetExhausted && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait" || state.scan_job.status === "paused" || state.scan_job.status === "failed") && state.scan_job.has_more_state === true && !nearCompleteAllowed && !scanPersistedMeetsExpectedCount(jobExpected, jobPersisted)) return false;
  if (activeProfilePostScanUnresolved22C14B(state, diagnostics) != null) return false;
  const authoritativeStopReason = getAuthoritativeScanStopReason(diagnostics);
  const expectedRaw = diagnostics.expected_profile_video_count;
  const largeProfileQueueTotal = largeProfileAuthoritativeQueueCount22C14B(state, diagnostics);
  const collectedRaw = largeProfileQueueTotal ?? diagnostics.profile_queue_total_count ?? state.harvest.queue.length;
  const expected = typeof expectedRaw === "number" ? expectedRaw : typeof expectedRaw === "string" ? Number(expectedRaw) : null;
  const collected = typeof collectedRaw === "number" ? collectedRaw : typeof collectedRaw === "string" ? Number(collectedRaw) : null;
  const lastScannerResult = String(diagnostics.lastScannerResult ?? diagnostics.last_scanner_result ?? "");
  const finalizationResult = String(diagnostics.scan_finalization_result ?? "");
  const completenessBlocked = diagnostics.scan_completeness_ready_blocked === "yes" || diagnostics.scan_completeness_gate_result === "blocked";
  const domOnlyFallback = diagnostics.scan_completeness_dom_only_fallback === "yes" || (diagnostics.scan_fallback_used === "yes" && diagnostics.scan_completeness_active_fetch_meaningful === "no");
  const missingRaw = diagnostics.scan_completeness_missing_count ?? diagnostics.missing_profile_video_count;
  const missing = typeof missingRaw === "number" ? missingRaw : typeof missingRaw === "string" ? Number(missingRaw) : null;
  const nearCompleteThreshold = expected != null && Number.isFinite(expected) && expected > 0 ? Math.max(5, Math.ceil(expected * 0.01)) : null;
  const severeUndercount = expected != null && collected != null && missing != null && Number.isFinite(expected) && Number.isFinite(collected) && Number.isFinite(missing) && expected > 0 && collected < expected && missing > Math.max(5, Math.ceil(expected * 0.01));
  if (countSemanticsBlocking) return false;
  const scanFailed = state.scan_job.status === "failed"
    || state.profile_scan.status === "failed"
    || state.workflow.scan.status === "failed"
    || state.verify.status === "failed";
  if (countSemanticsAllowed && !scanFailed && getActiveProfilePostScanBlockedReason(state) == null && collected != null && Number.isFinite(collected) && collected > 0) return true;
  if ((completenessBlocked || (domOnlyFallback && severeUndercount)) && !nearCompleteAllowed) return false;
  if ((authoritativeStopReason === "incomplete" || lastScannerResult === "incomplete" || finalizationResult === "incomplete") && !nearCompleteAllowed && !resumableBudgetExhausted) return false;
  if (authoritativeStopReason === "overcollected" || lastScannerResult === "overcollected" || finalizationResult === "overcollected") return false;
  if (authoritativeStopReason === "expected_semantics_unverified" || lastScannerResult === "expected_semantics_unverified" || finalizationResult === "expected_semantics_unverified") return false;
  if (expected != null && collected != null && Number.isFinite(expected) && Number.isFinite(collected) && expected > 0 && collected < expected && !validProfileUrlDetected && !nearCompleteAllowed) return false;
  if (validProfileUrlDetected && collected != null && Number.isFinite(collected) && (collected >= 20 || nearCompleteAllowed) && !(expected != null && Number.isFinite(expected) && expected > 0 && collected < expected && domOnlyFallback && !nearCompleteAllowed)) return true;
  if (!validProfileUrlDetected && expected != null && collected != null && Number.isFinite(expected) && Number.isFinite(collected) && expected > 0 && collected < expected && !nearCompleteAllowed) return false;
  if (!validProfileUrlDetected && expected != null && collected != null && Number.isFinite(expected) && Number.isFinite(collected) && expected > 0 && collected > expected && diagnostics.expected_profile_video_count_semantics_verified === "yes") return false;
  return (
    (state.profile_scan.status === "success" && state.profile_scan.accepted_target_count > 0)
    || state.verify.verified_target_count > 0
    || (state.verify.status === "success" && state.verify.accepted_target_count > 0)
  );
}

function classificationReady(state: WholeProfileHarvestState): boolean {
  const diagnostics = mergedScanDiagnostics22C13B(state);
  const jobExpected = resolveScanJobExpectedCount(state);
  const jobPersisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.verify.verified_target_count ?? 0,
    state.profile_scan.accepted_target_count ?? 0
  );
  if (scanPersistedMeetsExpectedCount(jobExpected, jobPersisted) && jobPersisted > 0) {
    return true;
  }
  if ((scanNearCompleteAllowed22C14B(state, diagnostics) || countSemanticsTerminalAllowed22C14Q(diagnostics)) && (state.harvest.queue.length > 0 || state.verify.verified_target_count > 0 || state.scan_job.total_persisted > 0)) {
    return true;
  }
  return state.classification.status === "success"
    && (
      state.classification.total_candidates > 0
      || state.classification.counts.collect > 0
      || state.classification.counts.skip > 0
      || state.classification.collect_aweme_ids.length > 0
      || state.classification.targets.length > 0
      || state.profile_scan.target_details.length > 0
    );
}

function collectQueueReady(state: WholeProfileHarvestState): boolean {
  const diagnostics = mergedScanDiagnostics22C13B(state);
  const jobExpected = resolveScanJobExpectedCount(state);
  const jobPersisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.verify.verified_target_count ?? 0,
    state.profile_scan.accepted_target_count ?? 0
  );
  if (scanPersistedMeetsExpectedCount(jobExpected, jobPersisted) && jobPersisted > 0) {
    return true;
  }
  const countSemanticsStatus = String(diagnostics.count_semantics_status ?? "");
  if (countSemanticsStatus === "incomplete_internal_loss" || countSemanticsStatus === "incomplete_api_not_exhausted" || countSemanticsStatus === "overcollected_needs_validation" || countSemanticsStatus === "failed_overcollection_outside_profile" || diagnostics.scan_health_verdict === "failed_overcollection_outside_profile" || overDisplayedInvariantProofBlocking22C14Q(diagnostics)) return false;
  const staleResumeRecoveryActive = diagnostics.stale_resume_recovery_attempted === "yes"
    && diagnostics.stale_resume_recovery_result === "restarted_from_fresh_cursor"
    && state.scan_job.has_more_state === true
    && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait");
  const resumableBudgetExhausted = diagnostics.auto_continuation_limit_reached === "yes"
    || diagnostics.continuation_reason === "auto_continuation_limit_reached"
    || diagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || diagnostics.final_exhaustion_mode === "manual_continuation"
    || diagnostics.page_budget_exhausted === "yes"
    || diagnostics.partial_scan_resumable === "yes"
    || diagnostics.continuation_available === "yes"
    || diagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || diagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted";
  if (!staleResumeRecoveryActive && !resumableBudgetExhausted && (state.scan_job.status === "running" || state.scan_job.status === "retry_wait" || state.scan_job.status === "paused" || state.scan_job.status === "failed") && state.scan_job.has_more_state === true && !scanNearCompleteAllowed22C14B(state, diagnostics) && !countSemanticsTerminalAllowed22C14Q(diagnostics) && !scanPersistedMeetsExpectedCount(jobExpected, jobPersisted)) return false;
  const largeProfileQueueTotal = largeProfileAuthoritativeQueueCount22C14B(state, diagnostics);
  if (largeProfileQueueTotal != null) return largeProfileQueueTotal > 0;
  if (!scanSessionTrustedForStoredProfile(state)) return state.harvest.queue.length > 0;
  return state.harvest.queue.length > 0
    || (state.classification.status === "success" && state.classification.collect_aweme_ids.length > 0);
}

const ACTIONABLE_QUEUE_STATUSES = new Set([
  "pending",
  "new",
  "retry",
  "incomplete",
  "needs_metadata",
  "failed_recoverable"
]);

function harvestQueueActionableCount(state: WholeProfileHarvestState): number {
  return state.harvest.queue.filter((item) => ACTIONABLE_QUEUE_STATUSES.has(item.status)).length;
}

function postScanSnapshotActionableCount(snapshot: NonNullable<WholeProfileHarvestState["post_scan_counter_snapshot"]>): number {
  return Math.max(0, snapshot.new) + Math.max(0, snapshot.queue) + Math.max(0, snapshot.incomplete) + Math.max(0, snapshot.need_retry);
}

/** True when terminal scan totals are trustworthy for the active tab and collect should be routable. */
function scanRoutingPresentationComplete(state: WholeProfileHarvestState): boolean {
  const activeTabUrl = typeof state.page_context.current_url === "string" && state.page_context.current_url.trim()
    ? state.page_context.current_url.trim()
    : typeof state.safety.tab_health.current_url === "string" && state.safety.tab_health.current_url.trim()
      ? state.safety.tab_health.current_url.trim()
      : null;
  if (activeTabUrl && detectProfileContextMismatch(state, activeTabUrl)) return false;
  if (!persistedScanJobTotalsTrustedForStoredProfile(state)) return false;
  const expected = resolveScanJobExpectedCount(state);
  const persisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0
  );
  if (persisted <= 0) return false;
  if (
    state.scan_job.status === "completed"
    && state.profile_scan.status === "success"
    && scanPersistedMeetsExpectedCount(expected, persisted)
  ) {
    return true;
  }
  if (state.layer.profile_scan_ready && scanPersistedMeetsExpectedCount(expected, persisted)) return true;
  return false;
}

/** True when there is at least one video left to collect (tiles New/Queue/Incomplete/Retry). */
function hasActionableCollectWork(state: WholeProfileHarvestState): boolean {
  if (collectPresentationSuppressed(state)) return false;
  if (isHybridTailGapClosed(state)) return false;
  if (isHybridUnreachableTailGapOffer(state)) return false;
  const expected = resolveScanJobExpectedCount(state);
  const persisted = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.accepted_target_count ?? 0,
    state.verify.verified_target_count ?? 0
  );
  if (
    persistedScanJobTotalsTrustedForStoredProfile(state)
    && state.scan_job.status === "completed"
    && state.profile_scan.status === "success"
    && scanPersistedMeetsExpectedCount(expected, persisted)
    && persisted > 0
    && harvestQueueActionableCount(state) === 0
  ) {
    const snapshot = state.post_scan_counter_snapshot;
    if (snapshot?.status === "applied") {
      if (postScanSnapshotActionableCount(snapshot) > 0) return true;
      const alreadyCollected = snapshot.already_collected ?? 0;
      if (alreadyCollected > 0 && alreadyCollected >= persisted) return false;
    } else {
      return true;
    }
  }
  const snapshot = state.post_scan_counter_snapshot;
  if (snapshot?.status === "applied") {
    if (postScanSnapshotActionableCount(snapshot) > 0) return true;
    if (state.harvest.pending > 0) return true;
    return harvestQueueActionableCount(state) > 0;
  }
  if (state.harvest.pending > 0) return true;
  if (harvestQueueActionableCount(state) > 0) return true;
  return false;
}

function collectRoutingActionKey(state: WholeProfileHarvestState): DouyinScannerWorkflowActionKey {
  if (isHybridUnreachableTailGapOffer(state)) return "close_unreachable_tail_gap";
  return hasActionableCollectWork(state) ? "start_collecting" : "open_capture_inbox";
}

function debugRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function latestDebugSummary(state: WholeProfileHarvestState): Record<string, unknown> {
  return mergedScanDiagnostics22C13B(state);
}

function isTerminalCollectionPhase(state: WholeProfileHarvestState, diagnostics: Record<string, unknown>): boolean {
  const stage = String(diagnostics.start_collecting_stage ?? "");
  const result = String(diagnostics.last_scanner_result ?? "");
  return state.phase === "batch_safe_mode_completed"
    || state.phase === "completed"
    || stage === "stopped_after_one_item"
    || result === "batch_safe_mode_completed"
    || result === "one_item_saved_verified"
    || result === "one_item_saved_unverified"
    || result === "failed";
}

export function isCollectionRunnerActive(state: WholeProfileHarvestState, nowMs = Date.now()): boolean {
  return deriveAuthoritativeRunnerLock(state, nowMs).active;
}

function isCollecting(state: WholeProfileHarvestState): boolean {
  return isCollectionRunnerActive(state);
}

export function readinessDecisionPresentationPhase(
  state: WholeProfileHarvestState,
  workflowReadiness: DouyinScannerWorkflowReadiness,
  overcollectionReviewNeeded: boolean
): ScannerPresentationPhase {
  if (workflowReadiness.collecting || workflowReadiness.paused) return "collecting";
  if (state.workflow.scan.status === "running" || state.scan_job.status === "running" || state.profile_scan.status === "running") {
    return "scan_in_progress";
  }
  if (overcollectionReviewNeeded) return "review_overcollection";
  if (workflowReadiness.profileScanReady && !workflowReadiness.calibrationReady) return "scan_complete";
  return workflowReadiness.profileScanReady ? "scan_complete" : "profile_context_gate";
}

export function getDouyinScannerWorkflowReadiness(state: WholeProfileHarvestState): DouyinScannerWorkflowReadiness {
  const scanDiagnostics = mergedScanDiagnostics22C13B(state);
  const currentRunIds = [scanDiagnostics.scan_run_id, state.run_id, state.scan_job.scan_job_id]
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    .map((value) => value.trim());
  const forensicExportAvailable = scanDiagnostics.forensic_export_available === "yes";
  const forensicExportRunId = typeof scanDiagnostics.forensic_export_scan_run_id === "string"
    ? String(scanDiagnostics.forensic_export_scan_run_id).trim()
    : null;
  const forensicExportMatchesCurrentRun = forensicExportAvailable && forensicExportRunId != null && currentRunIds.includes(forensicExportRunId);
  const overDisplayedCount = numberDiagnostic22C14R(scanDiagnostics.over_displayed_count);
  const itemizedSameProfileProofReady = scanDiagnostics.accepted_target_ledger_present === "yes"
    && overDisplayedCount != null
    && overDisplayedCount > 0
    && scanDiagnostics.over_displayed_validation_status === "validated_same_profile"
    && scanDiagnostics.over_displayed_same_profile_validated === "yes"
    && scanDiagnostics.scan_health_verdict === "ready_api_over_displayed_count"
    && scanDiagnostics.count_semantics_status === "completed_with_api_over_displayed_count"
    && overDisplayedItemizedProofValid22C14Q(scanDiagnostics);
  const validatedSameProfileReady = itemizedSameProfileProofReady
    && scanSessionTrustedForStoredProfile(state)
    && (forensicExportMatchesCurrentRun
      || forensicExportRunId == null
      || currentRunIds.length === 0
      || scanDiagnostics.final_verdict === "validated_same_profile");
  const explicitOutsideProfileDetected = String(scanDiagnostics.count_semantics_status ?? "") === "failed_overcollection_outside_profile"
    || scanDiagnostics.scan_health_verdict === "failed_overcollection_outside_profile"
    || scanDiagnostics.over_displayed_validation_status === "outside_profile_detected"
    || scanDiagnostics.final_verdict === "outside_profile_detected";
  const unresolvedForensicContradiction = overDisplayedInvariantProofBlocking22C14Q(scanDiagnostics) && !validatedSameProfileReady;
  const benignSingleOverdisplay = benignSingleOverdisplayAutoValidated22C14Q(scanDiagnostics);
  const overdisplayValidationSignalPresent = (overDisplayedCount != null && overDisplayedCount > 0)
    || String(scanDiagnostics.count_semantics_status ?? "") === "overcollected_needs_validation"
    || String(scanDiagnostics.count_semantics_status ?? "") === "failed_overcollection_outside_profile"
    || scanDiagnostics.over_displayed_validation_status === "needs_validation"
    || scanDiagnostics.over_displayed_validation_status === "outside_profile_detected"
    || scanDiagnostics.final_verdict === "ledger_missing"
    || scanDiagnostics.final_verdict === "ledger_incomplete"
    || scanDiagnostics.final_verdict === "outside_profile_detected";
  const unresolvedValidationNeeded = !benignSingleOverdisplay
    && overdisplayValidationSignalPresent
    && !validatedSameProfileReady
    && (
    String(scanDiagnostics.count_semantics_status ?? "") === "overcollected_needs_validation"
    || scanDiagnostics.over_displayed_validation_status === "needs_validation"
    || scanDiagnostics.final_verdict === "ledger_missing"
    || scanDiagnostics.final_verdict === "ledger_incomplete"
    || (forensicExportAvailable !== true || forensicExportMatchesCurrentRun !== true)
    || unresolvedForensicContradiction
  );
  const validationReviewBlocking = scanDiagnostics.over_displayed_validation_status === "needs_validation"
    || String(scanDiagnostics.count_semantics_status ?? "") === "overcollected_needs_validation"
    || String(scanDiagnostics.count_semantics_status ?? "") === "failed_overcollection_outside_profile";
  const effectiveValidatedSameProfileReady = (validatedSameProfileReady || benignSingleOverdisplay)
    && !(validationReviewBlocking && scanDiagnostics.over_displayed_same_profile_validated !== "yes" && !benignSingleOverdisplay);
  const overcollectionReviewNeeded = overcollectionDiagnosticsTrusted(state, scanDiagnostics)
    && !benignSingleOverdisplay
    && (
      explicitOutsideProfileDetected
      || unresolvedValidationNeeded
      || (validationReviewBlocking && scanDiagnostics.over_displayed_same_profile_validated !== "yes")
    );
  const resumableBudgetExhausted = scanDiagnostics.auto_continuation_limit_reached === "yes"
    || scanDiagnostics.continuation_reason === "auto_continuation_limit_reached"
    || scanDiagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
    || scanDiagnostics.final_exhaustion_mode === "manual_continuation"
    || scanDiagnostics.page_budget_exhausted === "yes"
    || scanDiagnostics.partial_scan_resumable === "yes"
    || scanDiagnostics.continuation_available === "yes"
    || scanDiagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false"
    || scanDiagnostics.scan_stop_authoritative === "incomplete_api_budget_exhausted";
  const activeSourceBlockedReason = getActiveProfilePostScanBlockedReason(state);
  const scanPresentationComplete = scanRoutingPresentationComplete(state);
  const scannerBusy = getDouyinScannerBusyState(state);
  const activeScanProgress = !scannerBusy.isStale && !scanPresentationComplete && activeCurrentScanProgress22C14R(state, scanDiagnostics);
  const scanBusyBlocksRouting = !scanPresentationComplete
    && scannerBusy.isBusy
    && (scannerBusy.busySource === "scan.status" || scannerBusy.busySource === "classification.status");
  const busy = scanBusyBlocksRouting || activeScanProgress;
  // Hybrid collect skips modal DOM calibration; treat as satisfied for routing.
  const calibrationReady = isCollectCalibrationSatisfied(state);
  const scanReady = effectiveValidatedSameProfileReady ? true : profileScanReady(state);
  const classReady = classificationReady(state);
  const queueReady = collectQueueReady(state);
  const collecting = isCollecting(state);
  const collectionRunnerActive = collecting;
  const primaryActionLockedReason = collectionRunnerActive ? "collection_running" as const : null;
  const pausing = isPausing(state);
  const paused = isPaused(state);
  const safetyBlocked = state.safety.captcha_detected || state.safety.checkpoint_detected || state.safety.safety_status === "needs_attention" || state.safety.safety_status === "blocked" || state.safety.safety_status === "fatal";
  const scanOrClassifyBusy = busy && (activeScanProgress || scannerBusy.busySource === "scan.status" || scannerBusy.busySource === "classification.status");
  const canScanProfile = !busy && !paused && !collecting;
  const nearCompleteAllowed = scanNearCompleteAllowed22C14B(state);
  const effectiveQueueReady = effectiveValidatedSameProfileReady ? true : queueReady;
  const actionableCollectWork = hasActionableCollectWork(state);
  const hybridCollect = isHybridNetworkCacheModeEnabledForCollect(state);
  const hybridMetricsReadyCount = hybridCollect ? countQueueItemsWithHybridMetrics(state.harvest.queue) : 0;
  const scanStillRunning = state.workflow.scan.status === "running" || state.profile_scan.status === "running" || state.verify.status === "running";
  const hybridMetricsUnavailable = hybridCollect
    && !scanStillRunning
    && actionableCollectWork
    && state.harvest.queue.length > 0
    && hybridMetricsReadyCount === 0;
  const hybridMetricsBlockedReason = hybridMetricsUnavailable
    ? "Video list is ready but metrics are not loaded yet. Keep the Douyin profile tab open, scroll the video list, then Scan Profile again."
    : null;
  const canStartCollecting = calibrationReady && scanReady && classReady && effectiveQueueReady && actionableCollectWork && !busy && !pausing && !paused && !collecting && !safetyBlocked && !hybridMetricsUnavailable;
  const canReset = true;
  let nextActionKey: DouyinScannerWorkflowActionKey;
  let disabledReason: string | null = null;

  if (pausing) {
    nextActionKey = "pause";
    disabledReason = "Pause requested. Stopping after the current video.";
  } else if (collecting) {
    nextActionKey = "pause";
    disabledReason = null;
  } else if (paused) {
    nextActionKey = "resume";
    disabledReason = state.harvest.resume_available ? null : "No paused run to resume.";
  } else if (isHybridUnreachableTailGapOffer(state)) {
    nextActionKey = "close_unreachable_tail_gap";
    disabledReason = null;
  } else if (scanOrClassifyBusy) {
    nextActionKey = "scan_profile";
    disabledReason = null;
  } else if (overcollectionReviewNeeded) {
    nextActionKey = "review_overcollection";
    disabledReason = "Over-display exact-item validation is required before collecting.";
  } else if (resumableBudgetExhausted) {
    nextActionKey = "scan_profile";
    disabledReason = null;
  } else if (nearCompleteAllowed && effectiveQueueReady && !calibrationReady) {
    nextActionKey = "calibrate";
    disabledReason = null;
  } else if (nearCompleteAllowed && effectiveQueueReady && calibrationReady) {
    nextActionKey = collectRoutingActionKey(state);
    disabledReason = actionableCollectWork ? (canStartCollecting ? null : null) : "No new or incomplete videos to collect.";
  } else if (effectiveValidatedSameProfileReady && effectiveQueueReady && !calibrationReady) {
    nextActionKey = "calibrate";
    disabledReason = null;
  } else if (effectiveValidatedSameProfileReady && effectiveQueueReady && calibrationReady) {
    nextActionKey = collectRoutingActionKey(state);
    disabledReason = actionableCollectWork ? (canStartCollecting ? null : null) : "No new or incomplete videos to collect.";
  } else if (activeSourceBlockedReason != null && !nearCompleteAllowed) {
    nextActionKey = "scan_profile";
    disabledReason = activeSourceBlockedReason;
  } else if (!scanReady) {
    nextActionKey = "scan_profile";
    disabledReason = resumableBudgetExhausted ? null : null;
  } else if (!classReady) {
    nextActionKey = "scan_profile";
    disabledReason = null;
  } else if (effectiveQueueReady && !calibrationReady) {
    nextActionKey = "calibrate";
    disabledReason = null;
  } else if (effectiveQueueReady && calibrationReady) {
    nextActionKey = collectRoutingActionKey(state);
    disabledReason = actionableCollectWork ? (canStartCollecting
      ? null
      : hybridMetricsBlockedReason
        ?? (busy
        ? scannerBusy.busyReason ?? SCANNER_BUSY_WAIT_MESSAGE
        : safetyBlocked
          ? "Resolve the Douyin security check before collecting."
          : paused
            ? "Resume before collecting."
            : !scanReady
              ? "Scan Profile first."
              : !classReady
                ? "Scan Profile first."
                : !queueReady
                  ? "No videos are queued for collection."
                  : !calibrationReady
                    ? "Calibrate 4 Points first."
                    : null)) : "No new or incomplete videos to collect.";
  } else {
    nextActionKey = "open_capture_inbox";
    disabledReason = "No new or incomplete videos to collect.";
  }

  return {
    calibrationReady,
    profileScanReady: effectiveValidatedSameProfileReady ? true : scanReady,
    classificationReady: classReady,
    collectQueueReady: effectiveQueueReady,
    collecting,
    collectionRunnerActive,
    primaryActionLockedReason,
    paused,
    busy,
    canScanProfile,
    canStartCollecting,
    canReset,
    nextActionKey,
    disabledReason,
    hybridMetricsBlockedReason
  };
}

function scannerPrimaryActionDecisionReason(readiness: DouyinScannerWorkflowReadiness): string {
  if (readiness.nextActionKey === "review_overcollection") return "overcollection_itemized_validation_required";
  if (readiness.nextActionKey === "scan_profile" && !readiness.profileScanReady) return "profile_scan_required_before_calibration";
  if (readiness.nextActionKey === "scan_profile" && !readiness.classificationReady) return "classification_required_after_profile_scan";
  if (readiness.nextActionKey === "calibrate") return readiness.profileScanReady ? "validated_same_profile_api_overdisplay_warning_continue_to_calibration" : "calibration_required_after_profile_scan";
  if (readiness.nextActionKey === "start_collecting") return readiness.profileScanReady ? "validated_same_profile_api_overdisplay_warning_continue_to_collect" : "profile_scan_and_calibration_ready";
  if (readiness.nextActionKey === "pause") return readiness.collecting ? "collection_running" : "pause_in_progress";
  if (readiness.nextActionKey === "resume") return "collection_paused";
  return "no_pending_collection_queue";
}

function getCanonicalScannerPrimaryActionUnreconciled(state: WholeProfileHarvestState): CanonicalScannerPrimaryAction {
  const workflowReadiness = getDouyinScannerWorkflowReadiness(state);
  const scanDiagnostics = mergedScanDiagnostics22C13B(state);
  const scannerBusy = getDouyinScannerBusyState(state);
  const nearCompleteAllowed = scanNearCompleteAllowed22C14B(state);
  const runnerLock = deriveAuthoritativeRunnerLock(state);
  const canonicalUiState = String(runnerLock.diagnostics.trace_ui_canonical_state ?? "idle");
  const waitingForActiveTab = canonicalUiState === "waiting_for_active_tab";
  const pausedTabInactive = canonicalUiState === "paused_tab_inactive";
  const startupAckMissingRecoverable = state.collect_job.state === "start_failed_recoverable"
    && !state.collect_job.runner_ack_at
    && state.collect_job.failure_reason === "collect_runner_not_started";
  const effectiveActionKey = startupAckMissingRecoverable ? "resume" : workflowReadiness.nextActionKey;
  const collectActive = effectiveActionKey === "pause";
  const openingTarget = collectActive && state.workflow.collection.status === "opening_target";
  const calibration = getCanonicalCalibrationReady(state);
  const backendSessionReady = state.harvest.backend.capture_session.status === "ready"
    && ((typeof state.harvest.backend.capture_session.session_id === "string" && state.harvest.backend.capture_session.session_id.length > 0)
      || (typeof state.capture_session_id === "string" && state.capture_session_id.length > 0));
  const hybridCollect = isHybridNetworkCacheModeEnabledForCollect(state);
  const pendingCount = state.harvest.queue.filter((item) => item.status === "pending" || item.status === "new" || item.status === "retry" || item.status === "incomplete" || item.status === "needs_metadata" || item.status === "failed_recoverable").length;
  const extractionReady = workflowReadiness.profileScanReady && calibration.ready;
  const reason = startupAckMissingRecoverable
    ? "startup_ack_missing_recoverable"
    : scannerPrimaryActionDecisionReason(workflowReadiness);
  const overcollectionReview = overcollectionDiagnosticsTrusted(state, mergedScanDiagnostics22C13B(state))
    && workflowReadiness.nextActionKey === "review_overcollection";
  const presentationPhase = readinessDecisionPresentationPhase(state, workflowReadiness, overcollectionReview);
  const workflowPhase = resolveScannerWorkflowPhase(presentationPhase, {
    nextActionKey: workflowReadiness.nextActionKey,
    collecting: workflowReadiness.collecting,
    paused: workflowReadiness.paused,
    profileScanReady: workflowReadiness.profileScanReady,
    calibrationReady: workflowReadiness.calibrationReady
  });
  const decisionTrace: CanonicalScannerPrimaryActionDecisionTrace = {
    selectorVersion: "22C-11B",
    selector_version: "22C-11B",
    profileScanReady: workflowReadiness.profileScanReady,
    profile_scan_ready: workflowReadiness.profileScanReady,
    canonicalCalibrationReady: calibration.ready,
    canonical_calibration_ready: calibration.ready,
    extractionReady,
    extraction_ready: extractionReady,
    backendSessionReady,
    backend_session_ready: backendSessionReady,
    collection_status: state.workflow.collection.status,
    collection_runner_active: workflowReadiness.collectionRunnerActive,
    primary_action_locked_reason: workflowReadiness.primaryActionLockedReason,
    queue_count: state.harvest.queue.length,
    pending_count: pendingCount,
    scanner_busy: workflowReadiness.busy,
    selectedAction: effectiveActionKey,
    selected_action: effectiveActionKey,
    reason,
    workflow_phase: workflowPhase,
    presentation_phase: presentationPhase,
    diagnostics_trusted: overcollectionDiagnosticsTrusted(state, mergedScanDiagnostics22C13B(state))
  };

  switch (effectiveActionKey) {
    case "pause":
      return {
        key: "pause",
        title: openingTarget ? "Opening first video" : state.workflow.collection.status === "pausing" ? "Pausing collection" : waitingForActiveTab || pausedTabInactive ? "Collecting paused" : canonicalUiState === "running" ? "Collecting videos" : "Collecting videos",
        description: openingTarget
          ? "Opening the first queued profile modal before collecting metadata."
          : state.workflow.collection.status === "pausing"
            ? "Pause requested. The runner will stop after the current safe checkpoint."
            : waitingForActiveTab || pausedTabInactive
              ? (state.harvest.pause_message ?? "Return to the Douyin tab to continue collecting.")
              : "Collection is running. Use the footer Pause control if Douyin asks for a check or the tab needs attention.",
        label: state.workflow.collection.status === "pausing"
          ? "Pausing..."
          : waitingForActiveTab || pausedTabInactive
            ? "Resume"
            : "Collecting videos...",
        enabled: false,
        disabledReason: state.workflow.collection.status === "pausing"
          ? "Pause requested. Stopping after the current video."
          : waitingForActiveTab || pausedTabInactive
            ? (state.harvest.pause_message ?? "Resume when the Douyin tab is ready again.")
            : null,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "resume": {
      const backendAuthPaused = state.harvest.paused_reason === "backend_auth_required"
        || (state.harvest.paused_reason === "douyin_login_required"
          && state.harvest.pause_diagnostics
          && typeof state.harvest.pause_diagnostics === "object"
          && (state.harvest.pause_diagnostics as Record<string, unknown>).source === "hybrid_flush");
      return {
        key: "resume",
        title: backendAuthPaused ? "Resume after backend login" : "Resume collecting",
        description: startupAckMissingRecoverable
          ? (state.harvest.pause_message ?? "Collect startup did not receive runner ACK. Start Collecting can safely retry.")
          : (state.harvest.pause_message ?? (backendAuthPaused ? "Sign in to the app again, then press Resume." : "Resume when the Douyin tab is ready again.")),
        label: startupAckMissingRecoverable ? "Start Collecting" : "Resume",
        enabled: startupAckMissingRecoverable ? true : state.harvest.resume_available,
        disabledReason: startupAckMissingRecoverable ? null : workflowReadiness.disabledReason,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    }
    case "scan_profile": {
      const activeScan = scannerBusy.busySource === "scan.status" || activeCurrentScanProgress22C14R(state);
      const continuationDiagnostics = mergedScanDiagnostics22C13B(state);
      const continuationAvailable = continuationDiagnostics.auto_continuation_limit_reached === "yes"
        || continuationDiagnostics.continuation_reason === "auto_continuation_limit_reached"
        || continuationDiagnostics.scan_job_stop_reason === "auto_continuation_limit_reached"
        || continuationDiagnostics.final_exhaustion_mode === "manual_continuation"
        || continuationDiagnostics.continuation_available === "yes"
        || continuationDiagnostics.partial_scan_resumable === "yes"
        || continuationDiagnostics.page_budget_exhausted === "yes"
        || continuationDiagnostics.final_gap_reason === "api_budget_exhausted_before_has_more_false";
      return {
        key: "scan_profile",
        title: activeScan ? "Scanning Profile" : scannerBusy.busySource === "classification.status" ? "Classifying Videos" : continuationAvailable ? "Continue Scan" : "Scan Profile",
        description: activeScan
          ? "Scanning the current profile and discovering video cards."
          : scannerBusy.busySource === "classification.status"
            ? "Classifying scanned videos and building the collection queue."
            : continuationAvailable
              ? "Large profile scan paused cleanly. Continue Scan will resume from the saved continuation cursor and fetch the remaining unseen pages."
              : "Scan this Douyin profile and build a collection plan.",
        label: activeScan ? "Scanning..." : scannerBusy.busySource === "classification.status" ? "Classifying..." : continuationAvailable ? "Continue Scan" : "Scan Profile",
        enabled: activeScan ? false : workflowReadiness.canScanProfile,
        disabledReason: activeScan || scannerBusy.busySource === "classification.status" ? null : workflowReadiness.disabledReason,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    }
    case "review_overcollection": {
      const reviewPresentation = buildOvercollectionReviewPresentation(scanDiagnostics);
      return {
        key: "review_overcollection",
        title: reviewPresentation.title,
        description: reviewPresentation.description,
        label: reviewPresentation.extraCount == null
          ? "Review Extra Videos"
          : (reviewPresentation.extraCount === 1 ? "Review 1 Extra Video" : `Review ${reviewPresentation.extraCount} Extra Videos`),
        enabled: true,
        disabledReason: null,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    }
    case "calibrate":
      return {
        key: "calibrate",
        title: "Calibrate 4 Points",
        description: "Click like, comment, favorite, and share once before collecting.",
        label: "Calibrate 4 Points",
        enabled: true,
        disabledReason: workflowReadiness.disabledReason,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "start_collecting":
      return {
        key: "start_collecting",
        title: "Start Collecting",
        description: workflowReadiness.hybridMetricsBlockedReason
          ? workflowReadiness.hybridMetricsBlockedReason
          : hybridCollect && !backendSessionReady
          ? "Save Session is created automatically, then videos are collected (up to 500 per click)."
          : backendSessionReady
            ? "Collect metadata from the queued profile videos and save to Capture Inbox."
            : "Creates Save Session if needed, then collects queued videos.",
        label: "Start Collecting",
        enabled: workflowReadiness.canStartCollecting,
        disabledReason: workflowReadiness.disabledReason,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "skip_hybrid_incomplete":
      return {
        key: "skip_hybrid_incomplete",
        title: "Finish collection",
        description: "Skip videos that are missing metrics and complete this profile.",
        label: "Skip incomplete",
        enabled: workflowReadiness.canStartCollecting,
        disabledReason: workflowReadiness.disabledReason,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "close_unreachable_tail_gap":
      return {
        key: "close_unreachable_tail_gap",
        title: "Close unreachable gap",
        description: "Finish with videos already in Capture Inbox when missing IDs cannot be found on Douyin.",
        label: "Close unreachable",
        enabled: true,
        disabledReason: null,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "open_capture_inbox":
      return {
        key: "open_capture_inbox",
        title: "Open Capture Inbox",
        description: workflowReadiness.disabledReason ?? "No new or incomplete videos to collect.",
        label: "Open Capture Inbox",
        enabled: true,
        disabledReason: null,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
    case "sign_in_to_app":
      return {
        key: "sign_in_to_app",
        title: "Sign in to app",
        description: "Sign in to the Web Dashboard before collecting videos.",
        label: "Sign in to app",
        enabled: true,
        disabledReason: null,
        source: "getCanonicalScannerPrimaryAction",
        selectorVersion: "22C-11B",
        calibration,
        decisionTrace
      };
  }
}

export function getCanonicalScannerPrimaryAction(state: WholeProfileHarvestState): CanonicalScannerPrimaryAction {
  return sanitizeCanonicalPrimaryAction(getCanonicalScannerPrimaryActionUnreconciled(state), state);
}
 
function missingFlushReason(readiness: WholeProfileHarvestReadiness, state: WholeProfileHarvestState): string {
  if (!readiness.backend_session_ready) return "Create a scan session first.";
  if (state.harvest.backend.payload_preview.guard && !state.harvest.backend.payload_preview.guard.ok) return "Data check failed. Fix save data before saving.";
  if (!readiness.payload_preview_ready) return "Run a data check first.";
  if (!readiness.payload_guard_passed) return "Data check must pass before saving.";
  return "Save is not ready yet.";
}

export function getNextRecommendedAction(
  state: WholeProfileHarvestState,
  readiness: Omit<WholeProfileHarvestReadiness, "next_recommended_action">
): WholeProfileHarvestRecommendedAction {
  const hasExtractedResults = extractedResults(state).length > 0;
  if (isPaused(state)) {
    if (state.harvest.paused_reason === "captcha_detected") {
      return {
        code: "solve_captcha_then_resume",
        label: "Solve security check",
        reason: "Complete the Douyin verification manually, then click Resume."
      };
    }
    if (readiness.resume_ready) {
      return {
        code: "resume",
        label: "Resume",
        reason: "Continue the paused run from the last saved progress point."
      };
    }
  }

  const scannerWorkflow = getDouyinScannerWorkflowReadiness(state);

  if (scannerWorkflow.nextActionKey === "scan_profile") {
    return {
      code: "verify_profile",
      label: "Scan Profile",
      reason: "Scan this Douyin profile and build a collection plan."
    };
  }

  if (scannerWorkflow.nextActionKey === "open_capture_inbox") {
    return {
      code: "review_results",
      label: "Open Capture Inbox",
      reason: "No new or incomplete videos to collect. Open Capture Inbox to review existing videos."
    };
  }

  if (scannerWorkflow.nextActionKey === "calibrate") {
    return {
      code: "calibrate_4_points",
      label: "Calibrate 4 Points",
      reason: "Click like, comment, favorite, and share before collecting queued videos."
    };
  }

  if (scannerWorkflow.nextActionKey === "start_collecting" && !hasExtractedResults) {
    return {
      code: "run_extraction",
      label: "Start Collecting",
      reason: "Collect metadata from queued profile videos."
    };
  }

  if (!readiness.backend_session_ready) {
    return {
      code: "prepare_backend_session",
      label: "Create Scan Session",
      reason: "Create a scan session before writing any videos to Capture Inbox."
    };
  }

  if (!readiness.payload_preview_ready || !readiness.payload_guard_passed) {
    return {
      code: "build_payload_preview",
      label: "Data check",
      reason: "Check one extracted video before writing anything to Capture Inbox."
    };
  }

  if (state.harvest.backend.one_item_flush.status !== "succeeded") {
    return {
      code: "flush_one_item",
      label: "Save 1 Video",
      reason: "Test Capture Inbox write with one video before saving the whole batch."
    };
  }

  if (readiness.batch_flush_ready) {
    return {
      code: "flush_batch",
      label: "Save to Capture Inbox",
      reason: "Save extracted videos sequentially with progress checkpoints."
    };
  }

  if (state.status === "completed" || state.harvest.status === "completed" || state.harvest.backend.batch_flush.status === "completed") {
    return {
      code: "review_results",
      label: "Open Capture Inbox",
      reason: "Saving is complete. Open /selection/capture-inbox to review collected videos."
    };
  }

  return {
    code: "none",
    label: "All set",
    reason: "No follow-up action is required right now."
  };
}

export function getWholeProfileHarvestReadiness(state: WholeProfileHarvestState): WholeProfileHarvestReadiness {
  const calibration_ready = isCollectCalibrationSatisfied(state);
  const extractedCount = extractedResults(state).length;
  const profile_scan_ready = profileScanReady(state);
  const dry_run_ready = (
    state.dry_run.status === "success"
    || state.dry_run.status === "completed_with_warnings"
    || (state.dry_run.pass > 0 && state.dry_run.fail === 0)
  );
  const classification_ready = classificationReady(state);
  const extraction_ready = profile_scan_ready && calibration_ready && classification_ready && collectQueueReady(state) && !state.safety.captcha_detected && !state.safety.checkpoint_detected;
  const backend_session_ready = state.harvest.backend.capture_session.status === "ready"
    && ((typeof state.harvest.backend.capture_session.session_id === "string" && state.harvest.backend.capture_session.session_id.length > 0)
      || (typeof state.capture_session_id === "string" && state.capture_session_id.length > 0));
  const payload_preview_ready = state.harvest.backend.payload_preview.status === "ready"
    && state.harvest.backend.payload_preview.payload != null
    && typeof state.harvest.backend.payload_preview.target_aweme_id === "string"
    && state.harvest.backend.payload_preview.target_aweme_id.length > 0;
  const payload_guard_passed = state.harvest.backend.payload_preview.guard?.ok === true;
  const one_item_flush_ready = backend_session_ready
    && payload_preview_ready
    && payload_guard_passed
    && state.harvest.backend.one_item_flush.status !== "running";
  const batch_flush_ready = backend_session_ready
    && extractedCount > 0
    && flushableExtractedResults(state).length > 0
    && oneItemFlushSucceeded(state)
    && state.harvest.backend.batch_flush.status !== "running";
  const safetyAllowsResume = state.safety.safety_status === "safe" || state.safety.safety_status === "recoverable" || state.safety.safety_status === "stale";
  const resume_ready = isPaused(state) && state.harvest.resume_available && safetyAllowsResume && !state.safety.safety_user_action_required;
  const stop_ready = isBusy(state);

  const baseReadiness = {
    calibration_ready,
    profile_scan_ready,
    dry_run_ready,
    extraction_ready,
    backend_session_ready,
    payload_preview_ready,
    payload_guard_passed,
    one_item_flush_ready,
    batch_flush_ready,
    resume_ready,
    stop_ready
  };

  return {
    ...baseReadiness,
    next_recommended_action: getNextRecommendedAction(state, baseReadiness)
  };
}

export function getWholeProfileHarvestActionState(state: WholeProfileHarvestState): WholeProfileHarvestActionState {
  const readiness = getWholeProfileHarvestReadiness(state);
  const workflowReadiness = getDouyinScannerWorkflowReadiness(state);
  const scannerBusy = getDouyinScannerBusyState(state);
  const busy = scannerBusy.isBusy;
  const busyDisabledReason = scannerBusy.busyReason ?? SCANNER_BUSY_WAIT_MESSAGE;
  const calibrationReady = readiness.calibration_ready;
  const hasExtractedResults = extractedResults(state).length > 0;
  const flushableCount = flushableExtractedResults(state).length;
  const runHarvestLabel = state.harvest_options.batch === "all_remaining"
    ? "Extract All Remaining"
    : state.harvest_options.batch === "next_5"
      ? "Extract Next 5"
      : state.harvest_options.batch === "next_20"
        ? "Extract Next 20"
        : "Extract Next 10";

  const dryRunDisabledReason = busy
    ? busyDisabledReason
    : !readiness.profile_scan_ready
    ? "Scan Profile first."
    : !calibrationReady
      ? "Calibrate 4 Points first."
      : null;

  const runHarvestDisabledReason = workflowReadiness.canStartCollecting
    ? null
    : busy
      ? busyDisabledReason
      : state.safety.captcha_detected || state.safety.checkpoint_detected || state.safety.safety_status === "needs_attention" || state.safety.safety_status === "blocked" || state.safety.safety_status === "fatal"
        ? state.safety.safety_user_action_required ? "Attention needed in the Douyin tab before collecting." : "Reconnect Douyin tab before collecting."
        : !workflowReadiness.profileScanReady
          ? "Scan Profile first."
          : !workflowReadiness.classificationReady
            ? "Scan Profile first."
            : !workflowReadiness.collectQueueReady
              ? "No videos are queued for collection."
              : !workflowReadiness.calibrationReady
                ? "Calibrate 4 Points first."
                : workflowReadiness.paused
                  ? "Resume before collecting."
                  : null;

  const prepareBackendDisabledReason = busy
    ? busyDisabledReason
    : !hasExtractedResults
      ? "Extract at least one video before creating a Save Session."
      : readiness.backend_session_ready
        ? null
        : null;

  const buildPayloadDisabledReason = busy
    ? busyDisabledReason
    : !hasExtractedResults
      ? "No extracted videos are ready yet."
      : !readiness.backend_session_ready
        ? "Create a Save Session first."
        : null;

  const flushBatchDisabledReason = busy && state.harvest.backend.batch_flush.status !== "running"
    ? busyDisabledReason
    : !readiness.backend_session_ready
      ? "Create a Save Session first."
      : !hasExtractedResults
        ? "No extracted videos are ready to save."
        : !oneItemFlushSucceeded(state)
          ? "Save 1 Video first to verify Capture Inbox write."
          : flushableCount <= 0
          ? "No videos remain to save."
          : state.harvest.backend.batch_flush.status === "running"
            ? "Save to Capture Inbox is already running."
            : null;

  return {
    verifyProfile: {
      enabled: workflowReadiness.canScanProfile,
      visible: true,
      disabledReason: workflowReadiness.canScanProfile ? null : scannerBusy.busySource === "scan.status" || scannerBusy.busySource === "classification.status" ? null : busy ? busyDisabledReason : workflowReadiness.paused ? "Resume before scanning." : null,
      label: scannerBusy.busySource === "scan.status" ? "Scanning..." : scannerBusy.busySource === "classification.status" ? "Classifying..." : "Scan Profile"
    },
    dryRunFirst: {
      enabled: dryRunDisabledReason === null,
      visible: true,
      disabledReason: dryRunDisabledReason,
      label: "Test First 3"
    },
    dryRunLast: {
      enabled: dryRunDisabledReason === null,
      visible: true,
      disabledReason: dryRunDisabledReason,
      label: "Test Last 3"
    },
    dryRunRandom: {
      enabled: dryRunDisabledReason === null,
      visible: true,
      disabledReason: dryRunDisabledReason,
      label: "Test 3 Videos"
    },
    runHarvest: {
      enabled: workflowReadiness.canStartCollecting,
      visible: true,
      disabledReason: runHarvestDisabledReason,
      label: runHarvestLabel
    },
    prepareBackendSession: {
      enabled: prepareBackendDisabledReason === null && !readiness.backend_session_ready,
      visible: !readiness.backend_session_ready && hasExtractedResults,
      disabledReason: prepareBackendDisabledReason,
      label: "Create Scan Session"
    },
    buildPayloadPreview: {
      enabled: buildPayloadDisabledReason === null && (!readiness.payload_preview_ready || !readiness.payload_guard_passed),
      visible: hasExtractedResults && readiness.backend_session_ready && (!readiness.payload_preview_ready || !readiness.payload_guard_passed),
      disabledReason: buildPayloadDisabledReason,
      label: "Data check"
    },
    flushOneItem: {
      enabled: readiness.one_item_flush_ready,
      visible: true,
      disabledReason: readiness.one_item_flush_ready ? null : missingFlushReason(readiness, state),
      label: "Save 1 Video"
    },
    flushBatch: {
      enabled: readiness.batch_flush_ready,
      visible: true,
      disabledReason: readiness.batch_flush_ready ? null : flushBatchDisabledReason,
      label: "Save to Capture Inbox"
    },
    stop: {
      enabled: readiness.stop_ready,
      visible: readiness.stop_ready,
      disabledReason: readiness.stop_ready ? null : "No running step to stop."
    },
    resume: {
      enabled: readiness.resume_ready,
      visible: isPaused(state) && state.harvest.resume_available,
      disabledReason: readiness.resume_ready ? null : state.safety.safety_user_action_required ? "Attention needed in the Douyin tab before Resume." : "No paused run to resume."
    },
    resetHarvest: {
      enabled: workflowReadiness.canReset,
      visible: true,
      disabledReason: workflowReadiness.canReset ? null : "Stop the current run before resetting harvest state."
    }
  };
}
