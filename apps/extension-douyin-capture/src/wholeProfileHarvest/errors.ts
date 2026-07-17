export type WholeProfileHarvestErrorCode =
  | "not_douyin_tab"
  | "content_script_unavailable"
  | "detector_failed"
  | "profile_resolve_failed"
  | "modal_profile_resolve_failed"
  | "modal_close_failed"
  | "profile_transition_failed"
  | "profile_navigation_required"
  | "modal_to_profile_navigation_failed"
  | "profile_navigation_failed_still_modal"
  | "profile_navigation_timeout"
  | "profile_navigation_or_grid_ready_timeout"
  | "profile_grid_not_ready"
  | "profile_scanner_not_started"
  | "profile_scanner_exception"
  | "profile_scan_failed"
  | "profile_scan_timeout"
  | "profile_grid_not_ready_timeout"
  | "profile_aweme_extraction_failed"
  | "douyin_login_required"
  | "douyin_checkpoint_required"
  | "profile_scan_runner_not_started"
  | "profile_scan_no_round_started"
  | "profile_scan_preflight_failed"
  | "scan_action_route_not_hit"
  | "scan_background_route_not_hit"
  | "scan_tab_not_found"
  | "scan_tab_not_douyin"
  | "scan_content_script_unavailable"
  | "scan_content_script_injection_failed"
  | "scan_dom_probe_failed"
  | "scan_dom_probe_timeout"
  | "scan_dom_probe_handler_missing"
  | "scan_dom_probe_message_failed"
  | "scan_dom_probe_malformed_response"
  | "scan_dom_probe_execute_script_failed"
  | "scan_dom_probe_not_invoked"
  | "legacy_scanner_not_invoked_after_dom_probe"
  | "legacy_dispatch_failed"
  | "productive_probe_legacy_dispatch_missing"
  | "legacy_scanner_message_handler_missing"
  | "legacy_scanner_timeout"
  | "legacy_scanner_threw"
  | "legacy_scanner_zero_verified_targets"
  | "legacy_queue_adapter_zero_output"
  | "profile_candidate_normalization_failed"
  | "profile_scan_queue_persist_failed"
  | "profile_scan_ready_state_update_failed"
  | "scan_tab_resolve_timeout"
  | "scan_profile_ensure_content_script_timeout"
  | "scan_profile_legacy_route_bypassed_probe"
  | "profile_expected_count_stale_after_reset"
  | "profile_expected_count_unavailable"
  | "profile_scroll_container_not_found"
  | "profile_scan_returned_no_cards"
  | "no_videos_found"
  | "profile_scan_incomplete"
  | "target_validation_empty"
  | "target_classification_failed"
  | "verify_required"
  | "calibration_required"
  | "no_verified_targets"
  | "dry_run_recommended"
  | "harvest_not_enabled_in_phase18i_a"
  | "capture_session_create_failed"
  | "capture_session_endpoint_missing"
  | "capture_session_schema_rejected"
  | "capture_session_backend_error"
  | "capture_session_network_error"
  | "capture_session_response_missing_session_id"
  | "capture_session_not_found"
  | "capture_session_verify_failed"
  | "payload_preview_missing"
  | "backend_finalized_metadata_required"
  | "harvest_no_targets_processed"
  | "harvest_all_targets_failed"
  | "harvest_some_targets_failed"
  | "harvest_target_failed"
  | "captcha_detected"
  | "modal_navigation_timeout"
  | "modal_id_mismatch"
  | "modal_metrics_timeout"
  | "data_integrity_mismatch"
  | "payload_contains_disallowed_field_local"
  | "backend_schema_rejected"
  | "backend_secret_guard_rejected"
  | "backend_flush_failed"
  | "backend_auth_required"
  | "backend_success_but_no_capture_inbox_item"
  | "user_stopped"
  | "retry_limit_reached"
  | "dry_run_some_targets_failed"
  | "dry_run_all_targets_failed"
  | "legacy_feature_disabled";

export type WholeProfileHarvestError = {
  code: WholeProfileHarvestErrorCode;
  message: string;
  next_action: string;
  details?: unknown;
};

const ERROR_MESSAGES: Record<WholeProfileHarvestErrorCode, { message: string; next_action: string }> = {
  not_douyin_tab: { message: "Open a Douyin profile or modal tab first.", next_action: "Open Douyin and reconnect the extension." },
  content_script_unavailable: { message: "Douyin content script is unavailable.", next_action: "Click Reconnect Douyin Tab and try again." },
  detector_failed: { message: "Could not detect the current Douyin page.", next_action: "Refresh the tab, reconnect, and try again." },
  profile_resolve_failed: { message: "Could not resolve a profile URL from the current page.", next_action: "Open a Douyin profile page or a profile modal URL." },
  modal_profile_resolve_failed: { message: "Could not resolve the modal to its source profile URL.", next_action: "Open the modal from a Douyin profile URL and try again." },
  modal_close_failed: { message: "Could not leave the modal video view before scanning profile.", next_action: "The extension will try hard navigation to the profile. If it still fails, open the profile URL directly and run Verify Profile." },
  profile_transition_failed: { message: "Could not transition from modal URL to profile URL.", next_action: "Refresh the profile page and try Verify Profile again." },
  profile_navigation_required: { message: "Profile navigation is required before scanning.", next_action: "Open the resolved profile URL or click Verify Profile again." },
  modal_to_profile_navigation_failed: { message: "Could not navigate from modal to profile page.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_navigation_failed_still_modal: { message: "Profile navigation failed because the active page is still a modal.", next_action: "Open the resolved profile URL directly and run Verify Profile again." },
  profile_navigation_timeout: { message: "Timed out opening profile page before scanning.", next_action: "Reopen the resolved profile URL or click Verify Profile again." },
  profile_navigation_or_grid_ready_timeout: { message: "Could not open the profile page for scanning.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_grid_not_ready: { message: "Could not find profile video grid.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_scanner_not_started: { message: "Profile scanner did not start.", next_action: "Reconnect the Douyin tab and run Verify Profile again." },
  profile_scanner_exception: { message: "Profile scanner threw an exception.", next_action: "Refresh the profile and run Verify Profile again." },
  profile_scan_failed: { message: "Profile scan failed.", next_action: "Refresh the profile and run Verify Profile again." },
  profile_scan_timeout: { message: "Profile scan timed out.", next_action: "Wait for the profile to finish loading, then verify again." },
  profile_grid_not_ready_timeout: { message: "Profile grid did not become ready before scanning.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_aweme_extraction_failed: { message: "Profile video links were found, but no valid aweme id could be extracted.", next_action: "Copy diagnostics and refresh the Douyin profile before retrying Scan Profile." },
  douyin_login_required: { message: "Douyin login is required before scanning this profile.", next_action: "Log in on the Douyin tab, then run Scan Profile again." },
  douyin_checkpoint_required: { message: "Douyin checkpoint or captcha blocked profile scanning.", next_action: "Complete the checkpoint in the Douyin tab, then click Resume or Scan Profile again." },
  profile_scan_runner_not_started: { message: "Profile scanner did not start.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_scan_no_round_started: { message: "Profile scanner exited before starting a scan round.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  profile_scan_preflight_failed: { message: "Profile scan preflight failed.", next_action: "Open the Douyin profile page, wait for it to load, then try Scan Profile again." },
  scan_action_route_not_hit: { message: "Scan Profile popup route was not reached.", next_action: "Reload the extension popup and try Scan Profile again." },
  scan_background_route_not_hit: { message: "Scan Profile background route was not reached.", next_action: "Reload the extension and try Scan Profile again." },
  scan_tab_not_found: { message: "No active tab was available for Scan Profile.", next_action: "Open the Douyin profile tab and try again." },
  scan_tab_not_douyin: { message: "The active tab is not a Douyin page.", next_action: "Open a Douyin profile tab and try Scan Profile again." },
  scan_content_script_unavailable: { message: "Douyin content script was unavailable before profile scan.", next_action: "Refresh the Douyin tab, reconnect the extension, and try Scan Profile again." },
  scan_content_script_injection_failed: { message: "Could not inject the Douyin content script before profile scan.", next_action: "Refresh the Douyin tab and check extension site permissions." },
  scan_dom_probe_failed: { message: "Profile DOM probe failed before scanning.", next_action: "Refresh the Douyin tab and try Scan Profile again." },
  scan_dom_probe_timeout: { message: "Profile DOM probe timed out before scanning.", next_action: "Wait for the profile grid to load, refresh the Douyin tab, and try Scan Profile again." },
  scan_dom_probe_handler_missing: { message: "Profile DOM probe handler is missing from the content script.", next_action: "Reload the extension and refresh the Douyin tab before retrying Scan Profile." },
  scan_dom_probe_message_failed: { message: "Profile DOM probe message failed before scanning.", next_action: "Refresh the Douyin tab, reconnect the extension, and try Scan Profile again." },
  scan_dom_probe_malformed_response: { message: "Profile DOM probe returned an invalid response.", next_action: "Copy diagnostics, reload the extension, and try Scan Profile again." },
  scan_dom_probe_execute_script_failed: { message: "Fallback DOM probe injection failed before scanning.", next_action: "Check extension site permissions, refresh the Douyin tab, and try Scan Profile again." },
  scan_dom_probe_not_invoked: { message: "Profile DOM probe was not invoked after content script ping succeeded.", next_action: "Reload the extension, refresh the Douyin tab, and try Scan Profile again." },
  legacy_scanner_not_invoked_after_dom_probe: { message: "Legacy profile scanner was not invoked after the DOM probe found videos.", next_action: "Reload the extension, refresh the Douyin tab, and run Scan Profile again." },
  legacy_dispatch_failed: { message: "Productive DOM probe completed, but dispatching the legacy profile scanner failed.", next_action: "Reload the extension, refresh the Douyin tab, and run Scan Profile again." },
  productive_probe_legacy_dispatch_missing: { message: "Productive DOM probe completed, but legacy scanner dispatch was not recorded.", next_action: "Copy diagnostics, reload the extension, refresh the Douyin profile tab, and run Scan Profile again." },
  legacy_scanner_message_handler_missing: { message: "Legacy profile scanner message handler is missing from the content script.", next_action: "Reload the extension and refresh the Douyin tab before retrying Scan Profile." },
  legacy_scanner_timeout: { message: "Legacy profile scanner timed out after DOM probe succeeded.", next_action: "Wait for the profile grid to finish loading, then run Scan Profile again." },
  legacy_scanner_threw: { message: "Legacy profile scanner threw after DOM probe succeeded.", next_action: "Copy diagnostics, refresh the Douyin profile, and run Scan Profile again." },
  legacy_scanner_zero_verified_targets: { message: "Legacy profile scanner returned zero verified targets after DOM probe succeeded.", next_action: "Copy diagnostics and retry on the loaded profile grid." },
  legacy_queue_adapter_zero_output: { message: "Legacy profile scanner returned targets, but the queue adapter produced zero queue items.", next_action: "Copy diagnostics and reload the extension before retrying." },
  profile_candidate_normalization_failed: { message: "Profile DOM probe candidates could not be normalized.", next_action: "Copy diagnostics, refresh the Douyin profile, and run Scan Profile again." },
  profile_scan_queue_persist_failed: { message: "Profile scan candidates were found, but the queue could not be persisted.", next_action: "Reload the extension and run Scan Profile again." },
  profile_scan_ready_state_update_failed: { message: "Profile scan queue was built, but scan readiness was not set.", next_action: "Copy diagnostics and reload the extension before retrying." },
  scan_tab_resolve_timeout: { message: "Timed out resolving the active Douyin tab before profile scan.", next_action: "Focus the Douyin profile tab and try Scan Profile again." },
  scan_profile_ensure_content_script_timeout: { message: "Timed out ensuring the Douyin content script before profile scan.", next_action: "Refresh the Douyin tab, reconnect the extension, and try Scan Profile again." },
  scan_profile_legacy_route_bypassed_probe: { message: "A legacy Scan Profile route bypassed the DOM probe.", next_action: "Reload the extension and use the primary Scan Profile button." },
  profile_expected_count_stale_after_reset: { message: "Profile expected count was stale after reset.", next_action: "Run Scan Profile again after the profile grid is visible." },
  profile_expected_count_unavailable: { message: "Profile expected count is unavailable.", next_action: "Continue scanning until the grid stabilizes or refresh the profile." },
  profile_scroll_container_not_found: { message: "Profile scroll container was not found.", next_action: "Refresh the profile and verify the video grid is visible." },
  profile_scan_returned_no_cards: { message: "Profile scan returned no cards.", next_action: "Confirm the profile has visible videos, then verify again." },
  no_videos_found: { message: "No videos were found on this profile.", next_action: "Open a profile with visible videos or rescan after the profile loads." },
  profile_scan_incomplete: { message: "Profile scan ended before all expected videos were collected.", next_action: "Wait for the profile to finish loading, then run Verify Profile again." },
  target_validation_empty: { message: "No valid profile video targets were found.", next_action: "Verify the profile page has visible video cards." },
  target_classification_failed: { message: "Could not classify existing items. Harvest will treat targets as unknown.", next_action: "Check backend status and API logs, then run Verify Profile again." },
  verify_required: { message: "Run Verify Profile first.", next_action: "Click Verify Profile before dry-run or harvest." },
  calibration_required: { message: "Calibrate 4 Points first.", next_action: "Click Calibrate 4 Points before dry-run or harvest." },
  no_verified_targets: { message: "No verified targets are available for harvest.", next_action: "Run Verify Profile again on a profile with visible videos." },
  dry_run_recommended: { message: "Run Dry-run Random 3 before real harvest.", next_action: "Run Dry-run Random 3 before real harvest." },
  harvest_not_enabled_in_phase18i_a: { message: "Run Harvest execution will be implemented in Phase 18I-G after queue/checkpoint/captcha modules are complete.", next_action: "Review queue preview only in Phase 18I-A." },
  capture_session_create_failed: { message: "Could not create canonical capture session.", next_action: "Check backend status, then run harvest again." },
  capture_session_endpoint_missing: { message: "Canonical capture session endpoint was not found.", next_action: "Confirm the API is updated and exposes POST /douyin-extension/capture-session." },
  capture_session_schema_rejected: { message: "Backend rejected the canonical capture session schema.", next_action: "Copy debug JSON and align extension/backend capture session request fields." },
  capture_session_backend_error: { message: "Backend failed while creating the canonical capture session.", next_action: "Check API logs for the capture_session_create stage, then retry." },
  capture_session_network_error: { message: "Extension could not reach the backend capture session endpoint.", next_action: "Confirm the API base URL is reachable from the extension popup." },
  capture_session_response_missing_session_id: { message: "Backend response did not include a capture session id.", next_action: "Fix backend response contract before retrying harvest." },
  capture_session_not_found: { message: "Backend could not find the canonical capture session for this one-item flush.", next_action: "Run Harvest again to recreate the capture session before retrying Flush One Item." },
  capture_session_verify_failed: { message: "Could not create or verify Capture Inbox session.", next_action: "Check backend status and API base URL, then run Start Collecting again." },
  payload_preview_missing: { message: "No validated payload preview is available for one-item flush.", next_action: "Run Harvest until a target is extracted, then retry Flush One Item." },
  backend_finalized_metadata_required: { message: "Backend rejected one-item flush because finalized modal metadata is required.", next_action: "Re-run extraction for the target and verify the finalized payload preview before retrying." },
  harvest_no_targets_processed: { message: "No harvest targets were processed.", next_action: "Check per-target diagnostics and retry after fixing the first failure reason." },
  harvest_all_targets_failed: { message: "All harvest targets failed. Check per-target errors.", next_action: "Review top failure reason and failed target rows before retrying." },
  harvest_some_targets_failed: { message: "Some harvest targets failed. Check per-target errors.", next_action: "Review failed target rows and retry failed targets if needed." },
  harvest_target_failed: { message: "Harvest target failed. Check per-target errors.", next_action: "Review the target row stage and error code." },
  captcha_detected: { message: "Captcha/checkpoint detected. Solve it manually in the Douyin tab, then click Resume.", next_action: "Solve the captcha manually and click Resume." },
  modal_navigation_timeout: { message: "Timed out opening target modal.", next_action: "Retry dry-run or verify the target is still available." },
  modal_id_mismatch: { message: "Opened modal does not match target aweme id.", next_action: "Retry dry-run after refreshing the profile." },
  modal_metrics_timeout: { message: "Timed out extracting modal metrics.", next_action: "Confirm calibration still matches the Douyin layout." },
  data_integrity_mismatch: { message: "Target data integrity check failed.", next_action: "Retry after refreshing the Douyin tab." },
  payload_contains_disallowed_field_local: { message: "Canonical harvest payload contains a disallowed field.", next_action: "Fix payload builder before retrying harvest." },
  backend_schema_rejected: { message: "Backend rejected the canonical harvest payload schema.", next_action: "Fix backend/API contract before resuming." },
  backend_secret_guard_rejected: { message: "Backend rejected payload secret/debug leakage.", next_action: "Remove disallowed fields before resuming." },
  backend_flush_failed: { message: "Backend flush failed.", next_action: "Check backend status and retry." },
  backend_auth_required: { message: "Backend login expired during collection.", next_action: "Sign in to the app again in extension settings, then press Resume." },
  backend_success_but_no_capture_inbox_item: { message: "Backend succeeded but did not return a Capture Inbox item id.", next_action: "Fix backend response contract before resuming." },
  user_stopped: { message: "Harvest paused by operator.", next_action: "Click Resume to continue pending targets." },
  retry_limit_reached: { message: "Retry limit reached for target.", next_action: "Review failed target and continue remaining targets." },
  dry_run_some_targets_failed: { message: "Some dry-run targets failed.", next_action: "Review failed rows and retry dry-run if needed." },
  dry_run_all_targets_failed: { message: "All dry-run targets failed.", next_action: "Check calibration and profile readiness, then retry." },
  legacy_feature_disabled: { message: "This legacy harvest feature is disabled. Use Whole Profile Harvest.", next_action: "Use Verify Profile and Dry-run actions." }
};

export function wholeProfileHarvestError(code: WholeProfileHarvestErrorCode, details?: unknown): WholeProfileHarvestError {
  const base = ERROR_MESSAGES[code];
  const error: WholeProfileHarvestError = { code, message: base.message, next_action: base.next_action };
  if (typeof details !== "undefined") error.details = details;
  return error;
}

export function errorToStateMessage(error: WholeProfileHarvestError): string {
  return `${error.code}: ${error.message}`;
}
