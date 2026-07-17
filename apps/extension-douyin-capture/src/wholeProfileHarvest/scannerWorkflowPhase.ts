import type { DouyinScannerWorkflowReadiness, ScannerActionKey } from "./readiness.js";
import type { ScannerPresentationPhase } from "./scanAuthorityDiagnostics.js";

export type ScannerWorkflowPhase =
  | "idle"
  | "scanning"
  | "finalizing"
  | "review"
  | "calibrate"
  | "collect"
  | "inbox"
  | "paused"
  | "blocked";

const PHASE_ALLOWED_ACTIONS: Record<ScannerWorkflowPhase, ScannerActionKey[]> = {
  idle: ["scan_profile"],
  scanning: ["scan_profile", "pause"],
  finalizing: ["scan_profile"],
  review: ["review_overcollection", "scan_profile"],
  calibrate: ["calibrate", "scan_profile"],
  collect: ["start_collecting", "pause", "open_capture_inbox"],
  inbox: ["open_capture_inbox"],
  paused: ["resume", "scan_profile"],
  blocked: ["scan_profile", "calibrate"]
};

export function resolveScannerWorkflowPhase(
  presentationPhase: ScannerPresentationPhase,
  readiness: Pick<DouyinScannerWorkflowReadiness, "nextActionKey" | "collecting" | "paused" | "profileScanReady" | "calibrationReady">
): ScannerWorkflowPhase {
  if (readiness.paused) return "paused";
  if (readiness.collecting) return "collect";
  if (presentationPhase === "scan_in_progress") return "scanning";
  if (presentationPhase === "scan_finalizing" || presentationPhase === "scan_finalizing_timeout") return "finalizing";
  if (presentationPhase === "review_overcollection" || readiness.nextActionKey === "review_overcollection") return "review";
  if (readiness.nextActionKey === "open_capture_inbox") return "inbox";
  if (!readiness.profileScanReady) return "idle";
  if (!readiness.calibrationReady && readiness.nextActionKey === "calibrate") return "calibrate";
  if (readiness.nextActionKey === "start_collecting") return "collect";
  return readiness.profileScanReady ? "collect" : "idle";
}

export function isActionAllowedForWorkflowPhase(
  phase: ScannerWorkflowPhase,
  actionKey: ScannerActionKey
): boolean {
  return PHASE_ALLOWED_ACTIONS[phase].includes(actionKey);
}

export function workflowPhaseAllowedActions(phase: ScannerWorkflowPhase): ScannerActionKey[] {
  return [...PHASE_ALLOWED_ACTIONS[phase]];
}
