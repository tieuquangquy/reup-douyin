import type {
  DouyinPageContext,
  DouyinPageViewport,
  FullModalHarvestControlOptions,
  FullModalHarvestProgress,
  FullModalHarvestProbeResult,
  RightRailCalibration,
  RightRailCalibrationPoint,
  RightRailCalibrationPointName,
  SmartCaptureHarvestState,
  SmartCaptureHarvestWorkflowState
} from "./types.js";

export const SHOW_LEGACY_DEBUG_ACTIONS = false;
export const RIGHT_RAIL_CALIBRATION_KEY = "douyinRightRailCalibration";
export const LAST_PROBE_RESULT_KEY = "douyinLastProbeResult";
export const SMART_CAPTURE_HARVEST_STATE_KEY = "douyinSmartHarvestState";

export const PRODUCTION_BUTTON_IDS = [
  "reconnectDouyinButton",
  "startCalibrationButton",
  "clearCalibrationButton",
  "verifyProfileButton",
  "dryRunRandomButton",
  "runHarvestButton",
  "resetWholeProfileHarvestButton",
  "copyDebugJsonButton",
  "clearLegacyStateButton"
] as const;

export const LEGACY_DEBUG_BUTTON_IDS = [
  "detectButton",
  "attachCdpButton",
  "detachCdpButton",
  "statusCdpButton",
  "probeCdpButton",
  "refreshCdpButton"
] as const;

export type DouyinPopupPageKind = "profile" | "modal" | "video" | "other" | "unknown";

export type DouyinPopupPageState = {
  kind: DouyinPopupPageKind;
  url: string | null;
  modalId: string | null;
};

export type PopupOperationalSnapshot = {
  backendReachable: "yes" | "no" | "unknown";
  supportedDouyinTab: "yes" | "no" | "unknown";
  captureSessionId: string | null;
  calibration: RightRailCalibration | null;
  lastProbe: FullModalHarvestProbeResult | null;
  harvestProgress: FullModalHarvestProgress | null;
  smartState: SmartCaptureHarvestState | null;
  lastError: string | null;
  pageState?: DouyinPopupPageState;
  pageContext?: DouyinPageContext | null;
  contentScriptStatus?: "ready" | "missing" | "failed";
  detectorStatus?: "ready" | "failed";
  detectorError?: string | null;
  currentPageViewport?: DouyinPageViewport | null;
  currentPageViewportSource?: "content_script" | "content_script_viewport_unavailable";
};

export const VIEWPORT_RECALIBRATION_MESSAGE = "Viewport changed significantly. Recalibrate before Smart Capture & Harvest.";
export const CALIBRATION_INCOMPLETE_MESSAGE = "Calibration incomplete. Recalibrate with four points: like, comment, favorite, share.";
export const MODAL_REQUIRED_MESSAGE = "Open the first video modal, then click Resume Smart Capture & Harvest.";
export const CAPTURE_SESSION_REQUIRED_MESSAGE = "Capture session missing. Open profile and run Capture current page, or run Smart Capture from profile first.";
export const CONTENT_SCRIPT_VIEWPORT_UNAVAILABLE = "content_script_viewport_unavailable";
export const CONTENT_SCRIPT_VIEWPORT_RETRY_MESSAGE = "Reconnect Douyin tab";
export const DETECTOR_RECONNECT_MESSAGE = "Reconnect Douyin tab";

export type PopupBlockingReasonSeverity = "error" | "warning" | "ready" | "neutral";

export type PopupBlockingReason = {
  state: SmartCaptureHarvestWorkflowState;
  message: string;
  nextAction: string | null;
  severity: PopupBlockingReasonSeverity;
};

const CALIBRATED_POINT_SOURCES = new Set(["calibrated_point_dom", "calibrated_point_ocr", "mixed_calibrated_point"]);
const REQUIRED_CALIBRATION_POINTS: RightRailCalibrationPointName[] = ["like_count", "comment_count", "favorite_count", "share_count"];

export type RightRailCalibrationValidationStatus = "missing" | "partial" | "valid";

export type RightRailCalibrationValidation = {
  status: RightRailCalibrationValidationStatus;
  pointCount: number;
  missingPoints: RightRailCalibrationPointName[];
};

export function classifyDouyinPopupPage(href: string | null | undefined): DouyinPopupPageState {
  if (!href) return { kind: "unknown", url: null, modalId: null };
  try {
    const url = new URL(href);
    const modalId = url.searchParams.get("modal_id")?.trim() || null;
    const videoMatch = url.pathname.match(/\/video\/([^/?#]+)/);
    if (modalId) return { kind: "modal", url: url.toString(), modalId };
    if (videoMatch?.[1]) return { kind: "video", url: url.toString(), modalId: videoMatch[1] };
    if (/\/user\/[^/?#]+/.test(url.pathname)) return { kind: "profile", url: url.toString(), modalId: null };
    return { kind: "other", url: url.toString(), modalId: null };
  } catch {
    return { kind: "unknown", url: href, modalId: null };
  }
}

export function isFreshModalProbe(
  probe: FullModalHarvestProbeResult | null,
  pageState?: DouyinPopupPageState
): boolean {
  if (!probe || !pageState?.modalId) return false;
  if (probe.aweme_id !== pageState.modalId) return false;
  if (probe.probe_status !== "PASS" || !probe.ready_for_full_harvest) return false;
  return CALIBRATED_POINT_SOURCES.has(probe.source_used ?? "");
}

export function displayProbeStatus(
  probe: FullModalHarvestProbeResult | null,
  pageState?: DouyinPopupPageState
): "PASS" | "WARN" | "FAIL" | "none" | "stale" | "not applicable" {
  if (!probe) return "none";
  if (!pageState?.modalId) return "not applicable";
  if (!isFreshModalProbe(probe, pageState)) return "stale";
  return probe.probe_status ?? "none";
}

export function describeHarvestState(progress: FullModalHarvestProgress | null): "idle" | "running" | "stopped" {
  if (!progress) return "idle";
  if (progress.running) return "running";
  if (progress.stopped_reason || progress.last_error || progress.can_resume) return "stopped";
  return "idle";
}

export function hasSignificantViewportChange(
  calibrationViewport: { width: number; height: number } | null,
  currentViewport: { width: number; height: number } | null
): boolean {
  if (!calibrationViewport || !currentViewport) return false;
  const widthDelta = Math.abs(currentViewport.width - calibrationViewport.width) / Math.max(1, calibrationViewport.width);
  const heightDelta = Math.abs(currentViewport.height - calibrationViewport.height) / Math.max(1, calibrationViewport.height);
  return widthDelta > 0.15 || heightDelta > 0.15;
}

export function nextRequiredAction(snapshot: PopupOperationalSnapshot): string {
  return computeCurrentBlockingReason(snapshot).nextAction ?? "Smart Capture & Harvest / Resume Harvest";
}

export function computeCurrentBlockingReason(snapshot: PopupOperationalSnapshot): PopupBlockingReason {
  const pageType = snapshot.pageContext?.page_type ?? snapshot.pageState?.kind ?? "unknown";
  const calibrationValidation = validateRightRailCalibration(snapshot.calibration);
  const contentScriptUnavailable = snapshot.contentScriptStatus != null && snapshot.contentScriptStatus !== "ready";
  const detectorUnavailable = snapshot.detectorStatus === "failed";
  const captureSessionId = snapshot.captureSessionId ?? null;
  const currentModalExists = Boolean(snapshot.pageState?.modalId);
  const probePassed = calibrationValidation.status === "valid" && isFreshModalProbe(snapshot.lastProbe, snapshot.pageState);
  const currentState = snapshot.smartState?.current_state;
  const nextRequiredAction = snapshot.smartState?.next_required_action;
  const stateMessage = snapshot.smartState?.last_error;

  if (snapshot.backendReachable === "no") return { state: "backend_unavailable", message: "Backend unavailable. Start local API backend.", nextAction: "Start local API backend", severity: "error" };
  if (snapshot.supportedDouyinTab === "no") return { state: "unsupported_tab", message: "Open supported Douyin tab.", nextAction: "Open supported Douyin tab", severity: "error" };
  if (contentScriptUnavailable) return { state: "content_script_unavailable", message: "Reconnect Douyin tab.", nextAction: DETECTOR_RECONNECT_MESSAGE, severity: "error" };
  if (detectorUnavailable) return { state: "detector_unavailable", message: "Detector unavailable. Click Reconnect Douyin tab.", nextAction: DETECTOR_RECONNECT_MESSAGE, severity: "error" };
  if (pageType === "profile" && !captureSessionId) return { state: "profile_capture_required", message: "Capture profile first.", nextAction: "Capture current page or Smart Capture & Harvest", severity: "neutral" };
  if (pageType === "profile") return { state: "modal_required", message: MODAL_REQUIRED_MESSAGE, nextAction: MODAL_REQUIRED_MESSAGE, severity: "neutral" };
  if (!currentModalExists) return { state: "modal_required", message: MODAL_REQUIRED_MESSAGE, nextAction: MODAL_REQUIRED_MESSAGE, severity: "neutral" };
  if (calibrationValidation.status === "missing") return { state: "calibration_required", message: "Calibrate 4 Points on the modal video.", nextAction: "Calibrate 4 Points", severity: "warning" };
  if (calibrationValidation.status === "partial") return { state: "calibration_required", message: CALIBRATION_INCOMPLETE_MESSAGE, nextAction: CALIBRATION_INCOMPLETE_MESSAGE, severity: "warning" };
  if (!probePassed) return { state: "probe_required", message: "Probe Current Modal.", nextAction: "Probe Current Modal", severity: "neutral" };
  if (currentState === "harvesting" || currentState === "loading_next_video" || currentState === "waiting_modal_change" || currentState === "flushing") {
    return {
      state: currentState === "harvesting" ? "harvesting" : currentState,
      message: stateMessage ?? "Harvesting.",
      nextAction: nextRequiredAction ?? "Show Progress",
      severity: "neutral"
    };
  }
  if (currentState === "paused") return { state: "paused", message: stateMessage ?? "Harvest paused.", nextAction: nextRequiredAction ?? "Resume Harvest", severity: "neutral" };
  if (currentState === "completed" || currentState === "completed_with_warnings" || currentState === "completed_noop") return { state: currentState, message: stateMessage ?? "Harvest completed.", nextAction: nextRequiredAction ?? "Review results", severity: "neutral" };
  if (currentState === "failed") return { state: "failed", message: stateMessage ?? "Harvest failed.", nextAction: nextRequiredAction ?? "Review error", severity: "error" };
  return { state: "harvest_ready", message: "Ready to harvest.", nextAction: "Smart Capture & Harvest / Resume Harvest", severity: "ready" };
}

export function validateRightRailCalibration(calibration: RightRailCalibration | null | undefined): RightRailCalibrationValidation {
  if (!calibration || typeof calibration !== "object") return { status: "missing", pointCount: 0, missingPoints: [...REQUIRED_CALIBRATION_POINTS] };
  const points = calibration.points;
  const pointCount = REQUIRED_CALIBRATION_POINTS.filter((pointName) => isCalibrationPoint(points?.[pointName])).length;
  const missingPoints = REQUIRED_CALIBRATION_POINTS.filter((pointName) => !isCalibrationPoint(points?.[pointName]));
  const hasViewport = Number.isFinite(calibration.viewport_width) && calibration.viewport_width > 0 && Number.isFinite(calibration.viewport_height) && calibration.viewport_height > 0;
  if (!hasViewport || pointCount === 0) return { status: "missing", pointCount, missingPoints };
  return { status: missingPoints.length === 0 ? "valid" : "partial", pointCount, missingPoints };
}

function isCalibrationPoint(point: RightRailCalibrationPoint | undefined): point is RightRailCalibrationPoint {
  return Boolean(
    point &&
      Number.isFinite(point.x) &&
      Number.isFinite(point.y) &&
      Number.isFinite(point.x_ratio) &&
      Number.isFinite(point.y_ratio)
  );
}

export function viewportWarningMessage(
  calibrationViewport: { width: number; height: number } | null,
  currentViewport: ({ width: number; height: number; source?: string } | null)
): string {
  void calibrationViewport;
  if (!currentViewport || currentViewport.source !== "content_script") return "none";
  return "none";
}

export function reconcileSmartState(snapshot: PopupOperationalSnapshot): SmartCaptureHarvestState | null {
  const baseState = snapshot.smartState ?? createSmartState();
  const pageType = snapshot.pageContext?.page_type ?? snapshot.pageState?.kind ?? "unknown";
  const pageRequiresModal = pageType === "profile";
  const captureSessionId = snapshot.captureSessionId ?? baseState.latest_capture_session_id;
  const calibrationValidation = validateRightRailCalibration(snapshot.calibration);
  const probePassed = calibrationValidation.status === "valid" && isFreshModalProbe(snapshot.lastProbe, snapshot.pageState);

  const contentScriptUnavailable = snapshot.contentScriptStatus != null && snapshot.contentScriptStatus !== "ready";

  if (snapshot.backendReachable === "no") return createSmartState({ ...baseState, current_state: "backend_unavailable", next_required_action: nextRequiredAction(snapshot), last_error: null });
  if (snapshot.supportedDouyinTab === "no") return createSmartState({ ...baseState, current_state: "unsupported_tab", next_required_action: nextRequiredAction(snapshot), last_error: null });
  if (contentScriptUnavailable) return createSmartState({ ...baseState, current_state: "content_script_unavailable", next_required_action: DETECTOR_RECONNECT_MESSAGE, last_error: snapshot.detectorError ?? CONTENT_SCRIPT_VIEWPORT_UNAVAILABLE });
  if (snapshot.detectorStatus === "failed") return createSmartState({ ...baseState, current_state: "detector_unavailable", next_required_action: DETECTOR_RECONNECT_MESSAGE, last_error: snapshot.detectorError ?? "detector_unavailable" });

  if (pageRequiresModal) {
    return createSmartState({
      ...baseState,
      latest_capture_session_id: captureSessionId ?? null,
      current_state: captureSessionId ? "modal_required" : "profile_capture_required",
      next_required_action: captureSessionId ? MODAL_REQUIRED_MESSAGE : "Capture current page or Smart Capture & Harvest",
      last_probe_status: "none",
      current_aweme_id: null,
      last_error: null
    });
  }

  if (calibrationValidation.status === "missing") {
    return createSmartState({
      ...baseState,
      latest_capture_session_id: captureSessionId ?? null,
      calibration_status: "missing",
      current_state: "calibration_required",
      next_required_action: "Start Right Rail Calibration, click like/comment/favorite/share, then resume Smart Capture & Harvest.",
      last_probe_status: "none",
      last_error: null
    });
  }

  if (calibrationValidation.status === "partial") {
    return createSmartState({
      ...baseState,
      latest_capture_session_id: captureSessionId ?? null,
      calibration_status: "partial",
      current_state: "calibration_required",
      next_required_action: CALIBRATION_INCOMPLETE_MESSAGE,
      last_probe_status: "none",
      last_error: null
    });
  }

  if (snapshot.calibration && (contentScriptUnavailable || (!snapshot.currentPageViewport && !snapshot.pageContext && !snapshot.pageState))) {
    return createSmartState({
      ...baseState,
      latest_capture_session_id: captureSessionId ?? null,
      calibration_status: "calibrated",
      current_state: "calibration_required",
      next_required_action: CONTENT_SCRIPT_VIEWPORT_RETRY_MESSAGE,
      last_probe_status: snapshot.lastProbe?.probe_status ?? baseState.last_probe_status,
      last_error: CONTENT_SCRIPT_VIEWPORT_UNAVAILABLE
    });
  }

  const hadStaleViewportBlock = baseState.last_error === "viewport_changed_significantly" || baseState.next_required_action === VIEWPORT_RECALIBRATION_MESSAGE;
  const hadStaleDetectorBlock = baseState.last_error === "detector_unavailable" || baseState.last_error === "direct_execution_failed" || baseState.next_required_action === DETECTOR_RECONNECT_MESSAGE;
  return createSmartState({
    ...baseState,
    latest_capture_session_id: captureSessionId ?? null,
    calibration_status: "calibrated",
    current_state: hadStaleViewportBlock && baseState.current_state === "calibration_required" ? "capture_ready" : probePassed ? "harvest_ready" : baseState.current_state,
    last_probe_status: probePassed ? "PASS" : baseState.last_probe_status,
    last_error: hadStaleViewportBlock || hadStaleDetectorBlock ? null : baseState.last_error,
    next_required_action: hadStaleViewportBlock && baseState.current_state === "calibration_required" ? "Start harvest" : probePassed ? "Smart Capture & Harvest / Resume Harvest" : hadStaleViewportBlock || hadStaleDetectorBlock ? nextRequiredAction(snapshot) : baseState.next_required_action
  });
}

export function startHarvestGuard(snapshot: PopupOperationalSnapshot): { ok: true } | { ok: false; message: string } {
  const calibrationValidation = validateRightRailCalibration(snapshot.calibration);
  if (calibrationValidation.status === "missing") {
    return { ok: false, message: "Calibrate 4 Points on the modal video." };
  }
  if (calibrationValidation.status === "partial") {
    return { ok: false, message: CALIBRATION_INCOMPLETE_MESSAGE };
  }
  if (!snapshot.lastProbe) {
    return { ok: false, message: "Test Current Video has not passed. Click Test Current Video first." };
  }
  if (!isFreshModalProbe(snapshot.lastProbe, snapshot.pageState)) {
    return { ok: false, message: "Test Current Video has not passed. Click Test Current Video first." };
  }
  return { ok: true };
}

export function createSmartState(overrides?: Partial<SmartCaptureHarvestState>): SmartCaptureHarvestState {
  return {
    current_state: "idle",
    next_required_action: "Run Capture current page",
    latest_capture_session_id: null,
    latest_capture_id: null,
    captured_item_count: 0,
    captured_at: null,
    profile_url: null,
    last_probe_status: "none",
    calibration_status: "missing",
    target_count: 0,
    target_aweme_ids: [],
    harvest_mode: "new_and_incomplete",
    scan_summary: undefined,
    current_index: 0,
    current_aweme_id: null,
    harvested_count: 0,
    flushed_count: 0,
    updated_count: 0,
    failed_count: 0,
    eta_seconds: null,
    last_error: null,
    updated_at: new Date().toISOString(),
    ...overrides
  };
}

export function smartHarvestStartOptions(state: SmartCaptureHarvestState): FullModalHarvestControlOptions {
  return {
    target_count: Math.max(1, state.target_aweme_ids.length || state.target_count || state.captured_item_count || 49),
    flush_every_n_items: 5,
    delay_between_items_ms: 5_000,
    per_item_timeout_ms: 15_000,
    stop_on_captcha: true,
    stop_on_no_next: true,
    allow_probe_warnings: false,
    capture_session_id: state.latest_capture_session_id,
    capture_id: state.latest_capture_id,
    target_aweme_ids: state.target_aweme_ids,
    profile_card_evidence_by_aweme_id: state.profile_card_evidence_by_aweme_id ?? {}
  };
}

export function smartStateFromHarvestProgress(
  currentState: SmartCaptureHarvestWorkflowState,
  nextRequiredAction: string | null,
  previous: SmartCaptureHarvestState,
  progress: FullModalHarvestProgress
): SmartCaptureHarvestState {
  const complete = progress.current_state === "completed" || progress.current_state === "completed_with_warnings" || (!progress.running && !progress.can_resume && (progress.processed_count ?? 0) >= progress.target_count);
  const completedWithWarnings = progress.current_state === "completed_with_warnings" || (complete && progress.failed_count > 0);
  const currentPhase = progress.phase ?? null;
  const runningState = currentPhase === "loading_next_video"
    ? "loading_next_video"
    : currentPhase === "waiting_modal_change"
      ? "waiting_modal_change"
      : currentPhase === "flushing"
        ? "flushing"
        : currentState;
  const defaultRunningAction = currentPhase === "flushing"
    ? "Flush Pending"
    : "Show Progress";
  const pausedMessage = progress.last_error ?? progress.flush_error_message ?? previous.last_error ?? "Harvest paused.";
  const pausedAction = nextRequiredAction ?? (progress.can_resume ? "Resume Harvest" : "Review results");

  return createSmartState({
    ...previous,
    current_state: complete
      ? (completedWithWarnings ? "completed_with_warnings" : "completed")
      : progress.running
        ? runningState
        : progress.can_resume
          ? "paused"
          : currentState,
    next_required_action: complete
      ? "Review results"
      : progress.running
        ? (nextRequiredAction ?? defaultRunningAction)
        : progress.can_resume
          ? pausedAction
          : nextRequiredAction,
    target_count: progress.target_count,
    target_aweme_ids: previous.target_aweme_ids,
    harvest_mode: previous.harvest_mode,
    scan_summary: previous.scan_summary,
    current_index: progress.current_index ?? previous.current_index,
    current_aweme_id: progress.current_aweme_id,
    harvested_count: progress.harvested_count,
    flushed_count: progress.flushed_count,
    updated_count: progress.updated_count,
    failed_count: progress.failed_count,
    eta_seconds: progress.eta_seconds ?? null,
    last_error: complete && !completedWithWarnings
      ? null
      : progress.running
        ? progress.last_error ?? progress.flush_error_message ?? previous.last_error ?? null
        : progress.can_resume
          ? pausedMessage
          : progress.last_error ?? progress.flush_error_message ?? null,
    updated_at: new Date().toISOString()
  });
}
