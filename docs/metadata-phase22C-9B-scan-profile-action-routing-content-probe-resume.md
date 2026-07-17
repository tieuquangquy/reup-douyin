# Phase 22C-9B Resume Notes

## Active Route

Scan Profile is a popup-owned route, not a background route:

`scannerPrimaryActionButton` -> `runWholeProfilePrimaryActionFromPopup()` -> `handlePrimaryActionClick("scan_profile")` -> `verifyWholeProfileFromPopup()` -> `runScanProfileWorkflow()` -> `verifyProfile()` -> popup runtime `scanProfile()` -> content script.

## Root Fix

The real popup runtime `scanProfile()` now performs the required pre-scan stages itself:

- active tab resolve
- Douyin tab check
- `DOUYIN_SCANNER_PING`
- content script reconnect/injection attempt if ping fails
- `DOUYIN_PROFILE_DOM_PROBE`
- diagnostic persistence
- profile scan message

The key change is that the runtime returns diagnostic-rich failed scan results instead of throwing before controller persistence.

## Diagnostics Contract

After Scan Profile click, diagnostics should include:

- `scan_profile_action_trace.traceVersion = "22C-9B"`
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

Advanced diagnostics also expose route summary rows for popup route, background route, controller route, tab resolution, content ping, injection, DOM probe, and no-round reason.

## Legacy Handling

No product route was found that intentionally uses a background scan-profile controller. Legacy modal-profile scan helpers remain for internal test/dry-run support, but the product Scan Profile runtime now wraps the legacy scan message with the canonical 22C-9B ping/probe route.

## Error Behavior

Before DOM probe, failures are classified as route/content-script errors:

- `scan_tab_not_found`
- `scan_tab_not_douyin`
- `scan_content_script_unavailable`
- `scan_content_script_injection_failed`
- `scan_dom_probe_failed`

`profile_scan_no_round_started` should only occur after a probe-backed route has run and no more specific grid/login/checkpoint/empty reason applies.

## Files Touched

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/profileScanner.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- scan/profile tests
- this document pair

## Manual Retest

Run Scan Profile on the previously failing profile. If the content script and page are healthy, DOM probe fields should populate and the scanner should proceed to round 1 when video candidates exist. If it fails earlier, the error should identify tab/content script/probe failure directly.
