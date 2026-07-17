import type { ModalWholeProfileCardScanResult } from "../modalWholeProfileTest.js";
import { wholeProfileHarvestError } from "./errors.js";
import { validateWholeProfileTargets, type WholeProfileTargetValidationResult } from "./targetValidation.js";

export type WholeProfileScannerTransport = {
  scanProfile(tabId: number, profileUrl: string): Promise<ModalWholeProfileCardScanResult>;
};

export type WholeProfileScanResult = WholeProfileTargetValidationResult & {
  scan_rounds: number;
  stop_reason: string | null;
  scroll_container_found: boolean;
  partial_scan: boolean;
  expected_profile_video_count: number | null;
  final_found_count: number;
  missing_expected_count: number | null;
  diagnostics: unknown | null;
};

export async function scanWholeProfileTargets(transport: WholeProfileScannerTransport, tabId: number, profileUrl: string): Promise<WholeProfileScanResult> {
  const scan = await transport.scanProfile(tabId, profileUrl);
  if (scan.status !== "success") throw wholeProfileHarvestError(profileScanFailureCode(scan.reason), scan);
  const validation = validateWholeProfileTargets(scan.cards, scan.diagnostics.candidate_classifications, profileUrl);
  return {
    ...validation,
    scan_rounds: scan.diagnostics.rounds,
    stop_reason: scan.diagnostics.stop_reason,
    scroll_container_found: scan.diagnostics.scroll_container_found,
    partial_scan: scan.diagnostics.partial_scan,
    expected_profile_video_count: scan.diagnostics.expected_profile_video_count,
    final_found_count: scan.diagnostics.final_found_count,
    missing_expected_count: scan.diagnostics.missing_expected_count,
    diagnostics: scan.diagnostics
  };
}

function profileScanFailureCode(reason: string | null | undefined) {
  if (reason === "profile_grid_not_ready") return "profile_grid_not_ready";
  if (reason === "profile_grid_not_ready_timeout") return "profile_grid_not_ready_timeout";
  if (reason === "profile_aweme_extraction_failed") return "profile_aweme_extraction_failed";
  if (reason === "douyin_login_required") return "douyin_login_required";
  if (reason === "douyin_checkpoint_required" || reason === "login_or_captcha_blocked") return "douyin_checkpoint_required";
  if (reason === "no_videos_found" || reason === "profile_empty_detected") return "no_videos_found";
  if (reason === "scan_content_script_injection_failed") return "scan_content_script_injection_failed";
  if (reason === "scan_content_script_unavailable") return "scan_content_script_unavailable";
  if (reason === "scan_dom_probe_failed") return "scan_dom_probe_failed";
  if (reason === "scan_dom_probe_timeout") return "scan_dom_probe_timeout";
  if (reason === "scan_dom_probe_not_invoked") return "scan_dom_probe_not_invoked";
  if (reason === "scan_dom_probe_handler_missing") return "scan_dom_probe_handler_missing";
  if (reason === "scan_dom_probe_message_failed") return "scan_dom_probe_message_failed";
  if (reason === "scan_dom_probe_malformed_response") return "scan_dom_probe_malformed_response";
  if (reason === "scan_dom_probe_execute_script_failed") return "scan_dom_probe_execute_script_failed";
  if (reason === "legacy_scanner_not_invoked_after_dom_probe") return "legacy_scanner_not_invoked_after_dom_probe";
  if (reason === "legacy_dispatch_failed") return "legacy_dispatch_failed";
  if (reason === "productive_probe_legacy_dispatch_missing") return "productive_probe_legacy_dispatch_missing";
  if (reason === "legacy_scanner_message_handler_missing") return "legacy_scanner_message_handler_missing";
  if (reason === "legacy_scanner_timeout") return "legacy_scanner_timeout";
  if (reason === "legacy_scanner_threw") return "legacy_scanner_threw";
  if (reason === "legacy_scanner_zero_verified_targets") return "legacy_scanner_zero_verified_targets";
  if (reason === "legacy_queue_adapter_zero_output") return "legacy_queue_adapter_zero_output";
  if (reason === "profile_candidate_normalization_failed") return "profile_candidate_normalization_failed";
  if (reason === "profile_scan_queue_persist_failed") return "profile_scan_queue_persist_failed";
  if (reason === "profile_scan_ready_state_update_failed") return "profile_scan_ready_state_update_failed";
  if (reason === "scan_tab_not_found") return "scan_tab_not_found";
  if (reason === "scan_tab_not_douyin") return "scan_tab_not_douyin";
  if (reason === "profile_scan_timeout" || reason === "scan_timeout" || reason === "timeout") return "profile_scan_timeout";
  if (reason === "profile_scroll_container_not_found" || reason === "scroll_container_not_found") return "profile_scroll_container_not_found";
  return "profile_scan_failed";
}
