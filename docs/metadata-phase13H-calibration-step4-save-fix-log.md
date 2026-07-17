# Phase 13H Calibration Step 4 Save Fix Log

## Root Cause

The calibration overlay only listened for `click` events on the overlay. On Douyin, page handlers can intercept or stop normal click propagation before the calibration flow reliably records the final SHARE point. The existing flow also finalized only from that click path, so a missed SHARE click left the overlay stuck at Step 4/4 with no saved calibration.

## Event Capture Fix

The content script now registers document-level capture-phase listeners for calibration input:

- `pointerdown`
- `mousedown`
- `click`

The primary path is capture-phase `pointerdown`, so the calibration code sees the coordinate before Douyin bubbling handlers can swallow the event. The handler calls `preventDefault()` and `stopPropagation()` and records `clientX`/`clientY`.

A 250ms debounce prevents the same physical action from being recorded multiple times across `pointerdown`, `mousedown`, and `click`.

## Four-Point Calibration Contract

Production calibration remains exactly four points:

1. `like_count`
2. `comment_count`
3. `favorite_count`
4. `share_count`

The stored version is `phase13h_four_point_calibration`. `next_video_button` is not required for production calibration.

## Storage Key

The canonical storage key remains:

`douyinRightRailCalibration`

It is used by content-script save/load/clear paths and popup read paths.

## Finalize/Save Behavior

After recording `share_count`, the content script:

1. Builds the complete four-point calibration.
2. Saves it to `chrome.storage.local` under `douyinRightRailCalibration`.
3. Shows `Calibration saved: 4/4 points.` as a page toast.
4. Removes overlay and listeners.
5. Resolves the popup request with the saved calibration.

If Escape is pressed before completion, listeners and overlay are removed and partial state is not saved as valid.

If storage save fails, the flow reports `calibration_save_failed` instead of silently closing as if calibration succeeded.

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

## Live Retest Steps

1. Reload the unpacked extension.
2. Open a Douyin modal with visible right-rail counts.
3. Click Start Right Rail Calibration.
4. Click LIKE count.
5. Confirm the overlay advances to Step 2/4.
6. Click COMMENT count.
7. Click FAVORITE count.
8. Click SHARE count.
9. Confirm the overlay disappears automatically.
10. Confirm the page toast says `Calibration saved: 4/4 points.`
11. Reopen or refresh the popup.
12. Confirm Calibration shows calibrated and the calibrated viewport matches the current page viewport.
13. Run Probe Current Modal Metrics again because the last probe is stale/not applicable after recalibration.
