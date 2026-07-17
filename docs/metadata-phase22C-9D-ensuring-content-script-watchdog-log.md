# Phase 22C-9D Ensuring Content Script Watchdog Log

## Scope
- Fixed Scan Profile hangs at `phase=ensuring_content_script`.
- Limited changes to the extension Scan Profile controller, popup active-tab/content-script ensure path, diagnostics, tests, and docs.
- No backend, Capture Inbox, Review Board, batch collection, payload, or calibration requirement changes.

## Root Cause
- `runScanProfileWorkflow` persisted `verifying / ensuring_content_script` with `active_task=scan_profile` and `action_lock=scan_profile`.
- `verifyProfile` then awaited popup runtime tab/content-script work without a controller deadline.
- Popup `chrome.tabs.query`, content-script ping, and injection paths were not consistently timeboxed.
- If any of those awaited operations never resolved, controller catch/finalization never ran, diagnostics stopped before tab/content-script fields, and the scanner remained busy forever.

## Implemented Changes
- Added a 30 second Scan Profile watchdog around `verifyProfile` and the content-script ensure stage.
- Added terminal timeout failure code `scan_profile_ensure_content_script_timeout`.
- Added active Douyin tab resolution with current window, last focused window, and Douyin tab enumeration fallbacks.
- Added timeboxed content-script ping and injection with explicit errors.
- Ensured failed/timeout Scan Profile paths clear `workflow.active_task` and `workflow.action_lock`.
- Persisted watchdog, tab resolver, ping, injection, and finalization diagnostics into scanner debug summaries.
- Exposed 22C-9D diagnostic rows in the scanner progress view model.

## Validation Plan
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
