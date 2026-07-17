# Phase 13H Calibration Step 4 Save Fix Resume

## Status

Phase 13H implementation is complete in the extension and focused tests pass as part of the extension test suite.

## Files Changed

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Calibration overlay now uses document capture-phase event listeners.
  - Finalizes immediately after `share_count` is recorded.
  - Saves version `phase13h_four_point_calibration`.
  - Uses canonical key `douyinRightRailCalibration`.
  - Shows `Calibration saved: 4/4 points.` after save.

- `apps/extension-douyin-capture/src/types.ts`
  - Added `phase13h_four_point_calibration` to `RightRailCalibrationVersion`.

- `apps/extension-douyin-capture/src/popup.ts`
  - Accepts the new calibration version when reading stored calibration.

- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - Added assertions covering the four-point steps, capture-phase `pointerdown`, debounce, canonical version, success toast, and canonical storage key.

## Root Cause Summary

The overlay depended on the overlay click listener. On Douyin, normal click propagation can be swallowed by page handlers, so the SHARE click at Step 4/4 could fail to reach calibration finalization.

## Retest Summary

Run calibration on a modal and click the four visible metric counts. The SHARE click should save and close the overlay without requiring any fifth point or second click.

## Commands Already Run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

Run the final explicit build command before final handoff if not already run after docs:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run build
```
