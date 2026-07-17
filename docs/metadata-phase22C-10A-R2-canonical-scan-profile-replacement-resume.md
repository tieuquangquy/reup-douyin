# Phase 22C-10A-R2 Resume Notes

## Active Route

Scan Profile is now background-owned by `runCanonicalScanProfile22C10A` in `apps/extension-douyin-capture/src/background.ts`.

Expected runtime markers:

- `scanner_runtime_version = 22C-10A`
- `state_machine_version = 22C-10A`
- `scan_controller_version = 22C-10A-canonical-orchestrator`
- `active_scan_profile_engine = canonical_single_path_22C10A`
- `canonical_orchestrator_entered = yes`
- `old_scan_profile_engine_bypassed = yes`

## Content Script

Canonical handlers:

- `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A_PING`
- `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A`

The main handler calls the existing `collectProfileCardsUntilStable(...)` path through `runModalTestProfileScan`.

## Manual Retest

1. Build and reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Click Scan Profile.
4. Confirm canonical diagnostics are visible.
5. On success confirm:
   - `canonical_handler_self_test = success`
   - `canonical_scan_message_sent = yes`
   - `canonical_content_handler_received = yes`
   - `canonical_scanner_function = collectProfileCardsUntilStable`
   - `scan_queue_builder_used = canonical_verified_target_queue_adapter_22C10A`
   - `profile_queue_total_count > 0`
   - `profileScanReady = yes`

## Remaining Risk

Old 22C-9Z helper code remains in source as unreachable compatibility/test code. The active popup/background route no longer calls it.
