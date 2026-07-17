# Phase 22C-9G — Scan Profile Dispatch Tab Resolution Resume

## Goal
Make Scan Profile use a single reliable dispatch bridge: popup resolves a Douyin tab, sends explicit `tabContext`, background ACKs immediately, background owns scan execution, tab resolution/ping/probe diagnostics are persisted, and terminal paths always clear locks.

## Expected Diagnostics
Successful dispatch should show `22C-9G` for scanner runtime, state machine, scan controller, and scan action trace. `background_route_hit` should be `true`, `background_route_status` should be `accepted`, `scan_run_id` should be populated, and `scanner_runtime_owner` should be `background`.

## Popup Dispatch Contract
The popup action is `dispatchBackgroundScanProfileAction22C9G`. It queries the active current-window tab, validates `douyin.com`, then sends `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9G` with `traceVersion: "22C-9G"` and `tabContext`. It does not run the DOM probe or scan locally.

## Background Resolver Contract
The background scan runtime resolves explicit `tabContext.tabId` first, then falls back to active current window, active last-focused window, and all Douyin tabs. Failure finalizes through the background finalizer with explicit tab errors instead of leaving `resolving_tab` pending.

## Watchdog and Finalizer
The background route writes watchdog start/deadline diagnostics and uses `finalizeBackgroundScanProfile22C9G` for thrown exceptions and timeouts. The finalizer clears `active_task` and `action_lock`, records `scan_finalization_result`, and writes `scan_finalized_at`.

## Stale Lock Recovery
Popup recovery repairs stale `scan_profile` locks older than 30 seconds if no `scan_finalized_at` exists. It preserves calibration, queue, Start Collecting, Pause/Resume, and Reset state.

## Manual Retest Steps
1. Reload the extension build.
2. Open a Douyin profile tab and focus it.
3. Open the popup and click Scan Profile.
4. Confirm diagnostics show `scan_action_trace_version = 22C-9G`.
5. Confirm `background_route_hit = true` and `background_route_status = accepted`.
6. Confirm `scan_run_id` starts with `scan_profile_22C9G_`.
7. Confirm tab diagnostics populate with a strategy and URL.
8. Confirm content-script ping is attempted after tab resolution.
9. If the tab is invalid, confirm an explicit tab error and unlocked UI.
10. If a timeout is forced, confirm finalization clears `active_task` and `action_lock`.

## Validation Commands
- `npx --workspace @reup-douyin/extension-douyin-capture tsx src/modalWholeProfileTest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
