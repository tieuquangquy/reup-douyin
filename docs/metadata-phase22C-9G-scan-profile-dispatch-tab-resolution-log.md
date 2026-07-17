# Phase 22C-9G — Scan Profile Dispatch Tab Resolution Log

## Scope
Implemented Phase 22C-9G only for the extension Scan Profile dispatch bridge, background route acknowledgement, tab resolution diagnostics, watchdog/finalization, and stale scan lock recovery.

## Root Cause
Scan Profile could enter the canonical popup path but still hang because the popup only sent a generic background command without explicit tab context. The background then relied on active-tab resolution from the service worker and could remain at `resolving_tab` with no tab diagnostics or content-script ping. Diagnostics also mixed stale version markers from popup/controller/background paths, making it hard to know which route owned the scan.

## Version/Path Cleanup
The active Scan Profile dispatch path now stamps `22C-9G` for scanner runtime, state machine, scan controller, and scan action trace diagnostics. The popup primary action target now names `dispatchBackgroundScanProfileAction22C9G`, and the active background message is `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9G`.

## Popup TabContext Dispatch
Before dispatching Scan Profile, the popup queries `chrome.tabs.query({ active: true, currentWindow: true })`, validates a Douyin URL, and passes `tabContext` with tab id, url, title, and window id. If the popup cannot resolve a valid Douyin tab, it writes `scan_popup_tab_not_found` or `scan_popup_tab_not_douyin` and does not start the background scan job.

## Background ACK Behavior
The background route persists accepted diagnostics immediately, including `background_route_hit = true`, `background_route_status = accepted`, `scan_run_id`, background ownership, and running scan lock state. It then returns `{ ok: true, accepted: true, scan_run_id }` before the async scan job continues.

## Tab Resolver Strategy
The background runtime resolves tabs in this priority: explicit popup tab id via `tabs.get`, active current window, active last-focused window, then all Douyin tabs. Each result writes tab strategy, result, URL, status, and Douyin validation diagnostics.

## Watchdog/Finalization
A background watchdog is started for resolving_tab and the persisted state includes started/deadline diagnostics. Terminal failure and thrown exceptions go through `finalizeBackgroundScanProfile22C9G`, which clears `active_task` and `action_lock`, writes finalization status/time, and sets the last scanner result/error.

## Stale Lock Recovery
Popup state recovery now repairs stale background-owned `scan_profile` locks older than 30 seconds when no finalization timestamp exists. It preserves calibration and collection state while clearing only the stale scan lock.

## Tests
Static coverage was added to `modalWholeProfileTest.test.ts` for the 22C-9G popup dispatcher, message type, background ACK, tab resolver strategy, watchdog/finalizer, content ping, DOM probe handoff, stale recovery, and lock clearing.
