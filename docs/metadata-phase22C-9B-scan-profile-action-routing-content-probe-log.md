# Phase 22C-9B Scan Profile Action Routing Content Probe Log

## Scope

Implemented Phase 22C-9B only. Backend APIs, Capture Inbox UI, Review Board, Reup Score, calibration requirements, and modal metadata extraction were not changed.

## Why 22C-9A Still Showed DOM Probe None

22C-9A added the DOM probe inside the scanner/content code, but the real popup runtime `scanProfile()` path sent `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE` directly. If that message failed or returned a zero-round result before the content scanner ran, the controller received an exception or an unprobed failure and persisted `profile_scan_no_round_started` without `profile_dom_probe`.

## Actual Scan Profile Route Found

The active route is:

`scannerPrimaryActionButton` -> `runWholeProfilePrimaryActionFromPopup()` -> `handlePrimaryActionClick("scan_profile")` -> `verifyWholeProfileFromPopup()` -> `runScanProfileWorkflow(createWholeProfilePopupRuntime())` -> `verifyProfile()` -> `completeProfileVerify()` -> popup runtime `scanProfile()` -> content script.

There is no production background scan-profile controller route; backend/background routing is not used for this action. The trace records that as `backgroundHandlerName = not_applicable_popup_runtime`.

## Legacy Handlers Found

Legacy modal whole-profile helpers still exist for internal modal test coverage and dry-run fixtures, but the product primary action routes through `runScanProfileWorkflow()`. The old direct profile scan message path is now wrapped by the 22C-9B canonical popup runtime path that pings, injects if needed, probes DOM, and only then starts the scan message.

## Content Script Ping/Injection

Added canonical messages:

- `DOUYIN_SCANNER_PING`
- `DOUYIN_PROFILE_DOM_PROBE`

The popup scan runtime now:

1. resolves the active tab,
2. verifies it is Douyin,
3. pings the content script,
4. attempts content-script injection/reconnect if ping fails,
5. sends `DOUYIN_PROFILE_DOM_PROBE`,
6. persists the probe result into scan diagnostics,
7. starts `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE`.

If ping/injection fails, it returns `scan_content_script_unavailable` or `scan_content_script_injection_failed`, not `profile_scan_no_round_started`.

## DOM Probe Persistence

The popup runtime returns a failed `ModalWholeProfileCardScanResult` with full diagnostics instead of throwing before diagnostics can be saved. `failState()` then persists the diagnostics through `last_response_summary`.

The persisted diagnostics include:

- `scan_profile_action_trace`
- `profile_dom_probe`
- `profile_dom_probe_status`
- `scan_grid_ready`
- `video_link_count`
- `aweme_link_count`
- `grid_card_candidate_count`
- `content_script_ping_result`
- `content_script_injection_result`
- `content_script_probe_response_received`
- `scan_no_round_reason`

## Error Classification

Added scan-route errors:

- `scan_tab_not_found`
- `scan_tab_not_douyin`
- `scan_content_script_unavailable`
- `scan_content_script_injection_failed`
- `scan_dom_probe_failed`

The existing 22C-9A page-level errors remain:

- `profile_grid_not_ready_timeout`
- `profile_aweme_extraction_failed`
- `douyin_login_required`
- `douyin_checkpoint_required`
- `no_videos_found`

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

Full extension test/build pending at this checkpoint.

## Manual Retest Steps

1. Reload the extension.
2. Open a Douyin profile tab.
3. Click Scan Profile before calibration.
4. Open advanced diagnostics.
5. Confirm scanner runtime or scan action trace shows `22C-9B`.
6. Confirm DOM probe fields are populated even if scan fails.
7. If the content script is unavailable, confirm the error is content-script specific, not `profile_scan_no_round_started`.
