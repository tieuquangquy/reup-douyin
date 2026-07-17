# Phase 22C-9Z-6 Direct Legacy Scan Production Path Log

## Why post-probe handoff was bypassed
22C-9Z-5 proved the DOM probe could complete but production still failed before invoking the legacy scanner. 22C-9Z-6 removes post-probe handoff and productive gate from the production success path.

## Direct message path
Popup Scan Profile now enters the background-owned Scan Profile route, resolves the tab, verifies content script ping, then background `scanProfile()` sends `DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z6` to the content script.

## Content handler
`contentScript.ts` registers `DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z6` and reuses `legacyVerifiedProfileScanner22C9ZNoGit(...)`, which wraps `collectProfileCardsUntilStable(...)`.

## Queue adapter behavior
The background/controller path consumes `verified_targets` and `verified_target_details` from the recovered legacy scanner and marks diagnostics with `legacy_verified_target_queue_adapter_22C9Z6`. The production path does not call backend flush and does not apply Next 10 truncation during scan verification.

## Specific errors
Direct dispatch maps missing receiving-end errors to `legacy_scanner_message_handler_missing`, zero verified targets to `legacy_scanner_zero_verified_targets`, and thrown scanner errors to `legacy_scanner_threw`.

## Tests run
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

## Manual retest
1. Reload the extension.
2. Open a Douyin profile tab.
3. Click Scan Profile.
4. Confirm diagnostics show `scanner_runtime_version = 22C-9Z-6`, `direct_legacy_scan_version = 22C-9Z-6`, and `direct_legacy_scan_message_type = DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z6`.
5. Confirm `profile_queue_total_count > 0` and `profileScanReady = yes`.
