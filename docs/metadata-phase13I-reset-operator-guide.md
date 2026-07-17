# Phase 13I Reset Operator Guide

## Why Reload Does Not Clear Extension Storage

Reloading an unpacked Chrome extension restarts extension scripts and refreshes files, but it does not automatically delete persisted `chrome.storage.local` or `chrome.storage.sync` state. That means old harvest progress, pending queues, calibration, probes, and workflow state can survive extension reloads and continue to appear in the popup.

Phase 13I adds explicit reset controls so the operator can clear stale local extension state without touching backend/database data.

## Maintenance Section

Open the extension popup and use the Maintenance section near the bottom.

Buttons:

1. Reset Harvest State
2. Reset Calibration
3. Factory Reset Extension

## Reset Harvest State

Use this first when the popup shows stale harvest status, for example:

- Harvest paused
- Target index `0 / 49`
- Current not detected
- Remaining target count from an old run
- Stale navigation/backend/detector error
- Pending or failed queues that should no longer resume

This reset clears only harvest/runtime state and preserves calibration and operator preferences.

Cleared keys:

- `douyinFullModalHarvestState`
- `reupDouyinFullModalHarvestFlushQueue`
- `douyinSmartCaptureHarvestState`
- `douyinLastProbeResult`
- `douyinFullModalHarvestProgress`
- `douyinSmartHarvestState`
- `douyinTargetAwemeQueue`
- `douyinPendingFlushQueue`
- `douyinRetryQueue`
- `douyinFailedQueue`
- `douyinCdpStatus`
- `douyinCdpDebugState`

Preserved:

- Local API base URL
- Right rail calibration
- Harvest mode
- Install id

Expected result:

- Success banner: `Harvest state reset.`
- Harvest: idle
- Current state: idle/ready
- Pending: 0
- Failed: 0
- Last error: none
- No stale `Harvest paused 0/49` progress panel

## Reset Calibration

Use this when calibration points are wrong, viewport changed, or old probe results are tied to stale calibration.

Cleared keys:

- `douyinRightRailCalibration`
- `douyinLastProbeResult`
- `rightRailCalibration`

Preserved:

- Local API base URL
- Harvest mode
- Harvest state
- Capture session cache unless separately factory-reset

Expected result:

- Success banner: `Calibration reset.`
- Calibration: missing
- Last probe: not applicable

If harvest appears to be running, stop/reset harvest first.

## Factory Reset Extension

Use this only when extension-local state is confusing or inconsistent and a clean local extension state is needed.

The confirmation prompt is:

`Factory reset will clear calibration, harvest progress, pending queue, and cached capture state. Backend database will not be changed. Continue?`

Cleared local keys:

- All Reset Harvest State keys
- All Reset Calibration keys

Cleared sync keys:

- `lastCaptureSessionId`
- `lastCaptureId`

Preserved intentionally:

- `apiBaseUrl`
- `harvestMode`
- `installId`

Backend/database records are not deleted.

Expected result:

- Success banner: `Extension state reset.`
- Harvest: idle
- Calibration: missing
- Last probe: not applicable
- API base URL unchanged

## Live Retest Steps

1. Build the extension.
2. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
3. Open a Douyin tab and open the extension popup.
4. Confirm Maintenance appears near the bottom.
5. If stale harvest state appears, click Reset Harvest State.
6. If prompted about running harvest, confirm.
7. Confirm `Harvest state reset.` appears.
8. Confirm the stale paused progress panel disappears.
9. Confirm Harvest is idle and Last error is none.
10. Click Reset Calibration.
11. Confirm `Calibration reset.` appears.
12. Confirm Calibration is missing and Last probe is not applicable.
13. Click Factory Reset Extension.
14. Confirm the warning says backend database will not be changed.
15. Continue.
16. Confirm `Extension state reset.` appears.
17. Confirm Local API base URL was preserved.
