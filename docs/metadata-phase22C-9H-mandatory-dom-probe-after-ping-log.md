# Phase 22C-9H - Mandatory DOM Probe After Ping Log

## Scope
- Implemented Phase 22C-9H only for background-owned Scan Profile.
- Preserved Start Collecting, pause/resume, reset, backend APIs, Capture Inbox, payload flush, and calibration behavior outside the Scan Profile path.

## Audit Finding
- The controller path after content script ping is `verifyProfile()` -> `completeProfileVerify()` -> `scanWholeProfileTargets()` -> `transport.scanProfile()`.
- `scanWholeProfileTargets()` already calls `transport.scanProfile()`, so the background runtime DOM probe entrypoint was reachable.
- The observed `ping ok` with probe diagnostics as `none` came from diagnostics/version gaps: ping-ok diagnostics did not re-persist tab fields, active controller diagnostics could overwrite newer route markers, and the DOM probe path still used older generic/22C-9F naming instead of an explicit 22C-9H message.

## Changes
- Bumped active Scan Profile runtime markers to `22C-9H` across popup, background, controller, and scan run ids.
- Added `DOUYIN_SCANNER_START_SCAN_PROFILE_22C9H` and `DOUYIN_PROFILE_DOM_PROBE_22C9H` message types.
- Background now persists tab diagnostics after successful content script ping and records `ping_ok_without_tab_diagnostics` if the invariant is broken.
- Background now writes `probing_dom` start diagnostics before sending the DOM probe message.
- Background sends `DOUYIN_PROFILE_DOM_PROBE_22C9H` with `scan_run_id` and `traceVersion: 22C-9H`, with a 10 second timeout.
- Content script handles `DOUYIN_PROFILE_DOM_PROBE_22C9H` and returns DOM facts plus probe diagnostics without mutating scanner state.
- Missing-handler DOM probe failures now attempt `chrome.scripting.executeScript` fallback via `inlineProfileDomProbe22C9H` and persist fallback attempt/result/error fields.
- DOM probe failures normalize to specific scan errors instead of falling through to generic `profile_scan_failed`.

## Validation Plan
- Run the extension static/runtime tests.
- Run TypeScript typecheck.
- Run extension build.
