# Phase 13I Extension Reset Controls Log

## Scope

Phase 13I adds popup Maintenance reset controls only inside `apps/extension-douyin-capture`. Backend data, web app behavior, metric extraction, and calibrated point extraction workflow are unchanged.

## Root Cause

Reloading or reinstalling an unpacked extension does not necessarily clear `chrome.storage.local` or `chrome.storage.sync` values for the extension id. The stale popup state came from persisted extension-local harvest progress and smart-harvest state, especially stored harvest progress such as `douyinFullModalHarvestState`, `reupDouyinFullModalHarvestFlushQueue`, `douyinSmartCaptureHarvestState`, and stale probe data. On popup refresh those keys were restored and rendered as a paused harvest such as target index `0 / 49` even when the operator intended a clean restart.

## Reset Controls Added

A new Maintenance section was added to the popup with three buttons:

- Reset Harvest State
- Reset Calibration
- Factory Reset Extension

## Reset Harvest State Behavior

Reset Harvest State is the default safe reset. It stops any in-memory content-script harvest controller through `REUP_DOUYIN_RESET_FULL_MODAL_HARVEST_STATE`, stops popup progress polling, clears persisted harvest/runtime queues, and refreshes the popup immediately.

If a harvest is running, the popup asks:

`Harvest is running. Stop and reset harvest state?`

After reset the popup renders idle detail state and hides the stale harvest progress panel.

## Reset Calibration Behavior

Reset Calibration clears calibration and stale probe data only. It preserves API base URL, harvest mode, and harvest state. If harvest appears to be running, it blocks with:

`Harvest is running. Stop harvest before resetting calibration.`

After reset the popup shows calibration missing and last probe not applicable.

## Factory Reset Behavior

Factory Reset Extension asks:

`Factory reset will clear calibration, harvest progress, pending queue, and cached capture state. Backend database will not be changed. Continue?`

After confirmation it stops in-memory harvest state, clears all known extension-local runtime/calibration/cache state, removes selected capture session identifiers from sync storage, preserves Local API base URL, and refreshes the popup.

## Storage Keys Cleared

### Reset Harvest State

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

### Reset Calibration

- `douyinRightRailCalibration`
- `douyinLastProbeResult`
- `rightRailCalibration`

### Factory Reset Extension

Clears all Reset Harvest State and Reset Calibration keys, plus sync keys:

- `lastCaptureSessionId`
- `lastCaptureId`

Preserved intentionally:

- `apiBaseUrl`
- `harvestMode`
- `installId`

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

Full test/build verification pending at this log creation step.

## Live Retest Steps

1. Build the extension.
2. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
3. Open the extension popup.
4. Confirm the Maintenance section is visible.
5. With stale paused harvest state visible, click Reset Harvest State.
6. Confirm any running-harvest prompt if shown.
7. Confirm the success banner says `Harvest state reset.`
8. Confirm the stale `Harvest paused 0/49` panel disappears.
9. Confirm status summary shows Harvest idle and Last error none.
10. Click Reset Calibration.
11. Confirm the success banner says `Calibration reset.`
12. Confirm Calibration missing and Last probe not applicable.
13. Click Factory Reset Extension.
14. Confirm the danger prompt text states backend database will not be changed.
15. Continue the reset.
16. Confirm the success banner says `Extension state reset.`
17. Confirm the API base URL remains unchanged.
