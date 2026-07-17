# Phase 22C-11B - Hard prune extension codebase and isolate reset buttons from Scan Profile

## Summary

This phase removed the remaining active/test-facing direct-legacy Scan Profile runtime and kept one active `22C-11B` Scan Profile route:

Popup Scan Profile -> background `runScanProfile22C11B` -> content script `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B` -> compact queue adapter -> terminal finalization.

The reset modal remains with three buttons, but its diagnostics no longer stamp old `22C-9D` scan-profile versions. Reset now reports itself as isolated from Scan Profile routing.

## Root cause

The codebase still contained:

- an exported background-owned Scan Profile runtime for old `22C-9Z-10` direct-legacy scanning
- tests that still asserted that old runtime must dispatch `DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z10`
- stale reset diagnostics expecting old `22C-9D` markers

That left the codebase internally inconsistent even though the active UI route had already moved to the minimal `22C-11B` path.

## Reset button audit

1. `Fix stuck run`
   - Mode: `current_run`
   - Keeps: profile, queue, session, calibration, settings
   - Clears: `active_task`, `action_lock`, transient running/flush state
   - Risk after fix: does not stamp old Scan Profile runtime markers

2. `Refresh profile`
   - Mode: `current_profile_rescan`
   - Keeps: calibration, settings
   - Clears: queue, profile scan state, expected-count diagnostics, backend session linkage
   - Risk after fix: isolated from active Scan Profile routing, reports `22C-11B-reset-isolated`

3. `Switch profile`
   - Mode: `new_profile`
   - Keeps: calibration, settings
   - Clears: local queue/session for current profile
   - Backend data: not deleted
   - Risk after fix: isolated from Scan Profile routing, explicit confirmation remains required

## Deletion audit

| File | Function / handler | Action | Reason |
| --- | --- | --- | --- |
| `apps/extension-douyin-capture/src/background.ts` | `runBackgroundOwnedScanProfile` | DELETE | Old Scan Profile-only orchestrator, no longer used by active route |
| `apps/extension-douyin-capture/src/background.ts` | `createBackgroundScanProfileRuntime` | DELETE | Legacy background runtime exported only for stale tests |
| `apps/extension-douyin-capture/src/background.ts` | `runDirectLegacyProfileScan22C9Z10` | DELETE | Broken direct-legacy Scan Profile-only path |
| `apps/extension-douyin-capture/src/background.ts` | `runInlineDirectLegacyProfileScanFallback22C9Z10` | DELETE | Fallback for deleted direct-legacy path |
| `apps/extension-douyin-capture/src/background.ts` | `inlineDirectLegacyProfileScanFallback22C9Z10` | DELETE | Inline DOM fallback for deleted direct-legacy path |
| `apps/extension-douyin-capture/src/background.ts` | `DIRECT_LEGACY_SCAN_ERROR_ORDER_22C9Z10` | DELETE | Only served deleted direct-legacy route |
| `apps/extension-douyin-capture/src/contentScript.ts` | old `22C-10H/22C-10I` canonical handlers and `22C-9Z3` legacy scan handler | KEEP unreachable / removed from active listener | Active route now uses only `DOUYIN_SCAN_PROFILE_MINIMAL_22C11B*` |
| `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts` | reset diagnostics stampers | KEEP and update | Shared reset behavior is required, but now isolated |
| `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts` | old no-round / direct-legacy repair guards | KEEP unreachable from active path | Defensive legacy normalization kept for old state reads only |

## Files changed

- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/background.test.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/test.ts`

## Active path after cleanup

- Runtime version: `22C-11B`
- Controller version: `22C-11B-minimal-scan-profile`
- Engine marker: `minimal_active_works_scan_profile_22C11B`
- Queue source mode: `fresh_current_run_only`
- Reset isolation marker: `reset_buttons_isolated = yes`

## Test result

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

All passed after removing the stale direct-legacy runtime surface and updating reset expectations to `22C-11B`.

## Manual retest checklist

1. Reload unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Click `Scan Profile`.
4. Verify diagnostics show:
   - `scanner_runtime_version = 22C-11B`
   - `state_machine_version = 22C-11B`
   - `active_scan_profile_engine = minimal_active_works_scan_profile_22C11B`
   - `old_scan_profile_paths_deleted = yes`
   - `reset_buttons_isolated = yes`
5. Open reset modal and verify:
   - `Fix stuck run` preserves queue/session
   - `Refresh profile` clears scan queue/state only
   - `Switch profile` clears local queue/session only
6. Confirm no active diagnostics regress to:
   - `22C-9C`
   - `22C-10I`
   - `direct_legacy_scan_handler_missing`
   - `profile_scan_no_round_started`
