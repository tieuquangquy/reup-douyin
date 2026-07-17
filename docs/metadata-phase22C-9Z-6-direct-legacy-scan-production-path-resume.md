# Phase 22C-9Z-6 Direct Legacy Scan Production Path Resume

## Phase
22C-9Z-6 - Bypass post-probe handoff completely and run legacy scanner directly after content ping.

## Implemented path
Background Scan Profile now proceeds from tab resolve and content-script ping to `DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z6`. The content script handler calls `legacyVerifiedProfileScanner22C9ZNoGit(...)` / `collectProfileCardsUntilStable(...)` and returns verified targets for the existing controller queue adaptation.

## Production-control changes
DOM probe is retained as diagnostic-only (`dom_probe_role = diagnostic_only`). Its failure no longer fails production verification after a successful content-script ping. Background finalization no longer injects the old ping-ok/probe-missing or productive-probe-without-dispatch invariant failures.

## Diagnostics to verify
- `scanner_runtime_version = 22C-9Z-6`
- `state_machine_version = 22C-9Z-6`
- `scan_controller_version = 22C-9Z-6-scan-controller`
- `direct_legacy_scan_version = 22C-9Z-6`
- `scan_engine_used = legacy_verified_profile_scroll_scanner_22C9Z6`
- `scan_queue_builder_used = legacy_verified_target_queue_adapter_22C9Z6`
- `dom_probe_role = diagnostic_only`

## Errors
Expected direct-path errors are `legacy_scanner_message_handler_missing`, `legacy_scanner_timeout`, `legacy_scanner_zero_verified_targets`, `legacy_scanner_threw`, and `legacy_queue_adapter_zero_output`.

## Validation so far
`npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed after the direct handler and background route changes.
