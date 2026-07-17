# Phase 13E stale detector state fix log

## Scope

Phase 13E is limited to `apps/extension-douyin-capture` popup state, popup preflight, popup banner behavior, and extension tests/docs. Backend, web app, metric extraction, calibrated-point workflow, CDP/debug workflow, and database behavior were not changed.

## Root cause

The top popup banner could preserve a historical direct-execution detector failure after a later refresh proved the active tab was healthy. The historical message originated from the direct execution detector fallback and popup action error projection: `direct_execution_failed` maps to `Could not execute the Douyin detector in this tab.` and `runPopupAction()` renders that as the current red status. `renderOperationalStatus()` only cleared stale viewport warnings, so a stale detector red banner could remain while diagnostics showed `Content script: ready` and `Detector: ready`.

A second state-priority bug existed in `reconcileSmartState()`: the final transition could set `harvest_ready` when a fresh PASS probe existed even if `captureSessionId` was missing. That made `Capture session: missing` coexist with `Current state: harvest_ready`.

## Blocking reason priority

`computeCurrentBlockingReason()` now derives the current popup blocker from current diagnostics in this order:

1. `backend_unavailable`
2. `unsupported_tab`
3. `content_script_unavailable`
4. `detector_unavailable`
5. `capture_session_required`
6. `modal_required`
7. `calibration_required`
8. `probe_required`
9. `harvest_ready`
10. `harvesting`
11. `paused`
12. `completed`
13. `failed`

Detector-unavailable is only returned when the current detector status is failed. If the detector is currently ready, stale `last_error` values do not produce a detector blocker.

## Capture session missing behavior

When the current page is profile and no capture session exists, the state remains `profile_capture_required` so the operator can capture the profile first. When the current page is modal/video and no capture session exists, the state becomes `capture_session_required` and the popup shows the operator instruction:

`Capture session missing. Open profile and run Capture current page, or run Smart Capture from profile first.`

`harvest_ready` now requires a known capture session.

## Banner rendering rules

The top banner is now rendered from the current blocking reason rather than stale historical errors. Current fatal blockers use red error status. Missing capture session and missing calibration are non-red operator guidance. Ready state shows `Ready to harvest.` Historical direct-execution detector errors are cleared once current diagnostics show a ready content script and ready detector.

## Tests run

Pending at log creation. The required commands are:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Reload the extension.
2. Open a supported Douyin profile tab.
3. Click Reconnect Douyin tab and confirm diagnostics show content script ready and detector ready.
4. Navigate to/open a modal without a stored capture session.
5. Refresh/open the popup.
6. Confirm no red stale detector banner is shown.
7. Confirm Capture session is `missing` and Current state is `capture_session_required`, not `harvest_ready`.
8. Click Smart Capture & Harvest or Resume Harvest on the modal and confirm the blocker says to capture the profile first, not detector unavailable.
9. Return to the profile and run Capture current page or Smart Capture from the profile to create a capture session.
10. Reopen the modal and confirm calibration/probe/harvest readiness follows the current blocker order.
