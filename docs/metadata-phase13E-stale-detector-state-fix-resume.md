# Phase 13E stale detector state fix resume

## Completed changes

Phase 13E centralized popup blocking-state computation and normalized impossible popup states in `apps/extension-douyin-capture`.

Changed areas:

- Added `capture_session_required` workflow state.
- Added `computeCurrentBlockingReason()` for current diagnostic blockers.
- Updated `nextRequiredAction()` and `reconcileSmartState()` to respect capture-session priority.
- Cleared stale detector/direct-execution state when current diagnostics show detector ready.
- Updated popup banner rendering to use the current blocker.
- Added shared current-state preflight hooks to popup actions.
- Added tests covering stale detector clearing, capture-session priority, and preflight/banner source assertions.

## Root cause

Historical detector errors were rendered into the top popup status by popup action error handling. Refresh diagnostics did not recompute the top banner from current content-script/detector readiness, so an old `Could not execute the Douyin detector` message could remain visible and psychologically/action-wise block the operator.

`reconcileSmartState()` also allowed a fresh PASS probe to produce `harvest_ready` without first requiring a known capture session.

## Current priority

The current blocker order is:

1. backend unavailable
2. unsupported tab
3. content script unavailable
4. detector unavailable
5. capture session required
6. modal required
7. calibration required
8. probe required
9. harvest ready
10. harvesting
11. paused
12. completed
13. failed

## Capture-session rule

Missing capture session is handled before calibration, probe, and harvest readiness on modal/video pages. A modal with missing capture session must be `capture_session_required`, not `harvest_ready`.

## Banner rule

The top banner now follows the current blocking reason. Stale historical detector errors are not shown as the current red alert after detector readiness is confirmed.

## Verification commands

Run from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest

1. Reload the unpacked extension.
2. Open a supported Douyin tab.
3. Click Reconnect Douyin tab.
4. Confirm diagnostics show content script ready and detector ready.
5. Open a modal without a saved capture session.
6. Confirm the top banner does not show the stale detector execution error.
7. Confirm current state is `capture_session_required`.
8. Click Smart Capture & Harvest, Resume Harvest, Probe Current Modal, Start Calibration, Flush Pending, and Show Progress as applicable and confirm blockers come from current diagnostics.
9. Capture the profile first, reopen the modal, then continue calibration/probe/harvest.
