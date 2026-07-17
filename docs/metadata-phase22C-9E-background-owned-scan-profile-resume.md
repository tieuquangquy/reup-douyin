# Phase 22C-9E Background-Owned Scan Profile Resume

## Goal

Scan Profile execution must be owned by the background service worker, not by popup runtime. Popup lifetime should no longer determine whether the scan can finish or finalize diagnostics.

## Current Contract

- Popup dispatches `DOUYIN_SCANNER_START_SCAN_PROFILE` with `traceVersion: "22C-9E"`.
- Background handles the message, creates `scan_run_id`, and launches `runScanProfileWorkflow()` with a background runtime.
- Background runtime resolves the active tab, ensures content script readiness, probes the DOM, sends the profile scan message, and persists diagnostics.
- Controller preserves background-provided `scan_run_id` and watchdog diagnostics.
- Content script echoes `traceVersion: "22C-9E"` and `scan_run_id` in DOM probe diagnostics.

## Expected Diagnostics

A healthy 22C-9E Scan Profile run should show:

- `scan_action_trace_version: "22C-9E"`
- `scanner_runtime_owner: "background"`
- `background_route_hit: true`
- `controller_route_hit: true`
- `scan_run_id: "scan_profile_22C9E_*"`
- `scan_watchdog_started_at` populated
- `scan_watchdog_deadline_at` populated
- `scan_watchdog_fired: "no"` unless the watchdog actually times out
- `tab_resolve_result` populated on tab resolution failure paths
- `content_script_ensure_status` populated on content-script readiness paths
- `profile_dom_probe_status` populated after DOM probe
- `scan_finalization_result` populated by controller completion or failure handling

## Stale Lock Recovery

Popup state recovery now detects broken popup-owned Scan Profile locks where:

- `workflow.action_lock === "scan_profile"`
- `workflow.active_task === "scan_profile"`
- no `scan_run_id`
- no `scan_watchdog_started_at`

Those locks are cleared with `scan_profile_stale_lock_recovered` so the new background route can be used.

## Validation Commands

Focused static tests:

```cmd
npx --workspace @reup-douyin/extension-douyin-capture tsx src/popupWorkflow.test.ts && npx --workspace @reup-douyin/extension-douyin-capture tsx src/modalWholeProfileTest.test.ts && npx --workspace @reup-douyin/extension-douyin-capture tsx src/wholeProfileHarvest.viewModel.test.ts
```

Full validation to run before handoff:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual Retest

1. Reload the extension.
2. Open a supported Douyin profile tab.
3. Open popup and click Scan Profile.
4. Close or defocus popup while scan is running.
5. Reopen popup and verify scan state continues to advance.
6. Check Advanced diagnostics for `22C-9E`, background ownership, populated `scan_run_id`, watchdog timestamps, tab/content/probe diagnostics, and finalization result.

## Out of Scope

- Backend API changes.
- Capture Inbox frontend changes.
- Review Board changes.
- Reup Score changes.
- Collection payload/flush changes.
- Popup UI redesign.
- Calibration requirements for Scan Profile.
