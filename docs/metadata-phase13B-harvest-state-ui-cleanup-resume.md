# Phase 13B Harvest State UI Cleanup Resume

## Current Phase

Phase 13B fixes Smart Harvest mode UI and stop/pause progress consistency in the Douyin capture extension only.

## Implemented Files

- `apps/extension-douyin-capture/src/types.ts`
  - Added `paused` and `stopped` harvest phase/current-state values.
- `apps/extension-douyin-capture/src/popupProgress.ts`
  - Added `normalizeHarvestProgressForDisplay()`.
  - Added normalized display-running behavior.
  - Added paused phase tone and stopped/paused titles.
- `apps/extension-douyin-capture/src/popup.ts`
  - Restores and persists Smart harvest mode.
  - Stops polling before Stop Harvest response render.
  - Renders normalized stopped progress.
  - Avoids immediate stale progress refresh after Stop Harvest.
  - Disables mode controls while harvest is running.
- `apps/extension-douyin-capture/src/modalHarvest.ts`
  - Operator stop becomes paused/stopped rather than failed.
- `apps/extension-douyin-capture/src/contentScript.ts`
  - Stop Harvest returns immediate non-running paused progress.
- `apps/extension-douyin-capture/public/popup.html`
  - Smart harvest mode now uses radio-card UI with three internal values.
- `apps/extension-douyin-capture/public/popup.css`
  - Added mode-card and paused progress styling.
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
  - Added assertions for stale stop normalization, mode UI, mode persistence, stop polling, and button-state source behavior.
- `docs/metadata-phase13B-harvest-state-ui-cleanup-log.md`
  - Phase log.
- `docs/metadata-phase13B-harvest-state-ui-cleanup-resume.md`
  - This resume document.

## Remaining Verification

Run from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Checklist

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist` after build.
2. Open a supported Douyin profile tab.
3. Open the extension popup.
4. Confirm Smart harvest mode displays three readable cards:
   - New + incomplete
   - New only
   - Refresh all
5. Select `New only`, close/reopen popup, and confirm the selection persists.
6. Select `New + incomplete` before normal harvest retest.
7. Start Smart Capture & Harvest from the profile/modal workflow.
8. While progress panel shows a running phase, click Stop Harvest.
9. Confirm the popup shows `Harvest paused` or `Harvest stopped`, not `Harvest running`.
10. Confirm the phase pill shows `Paused by operator`, `Paused`, or `Stopped`, not `Extracting metrics...`, `Loading next video...`, or `Waiting for modal change...`.
11. Confirm counts/target index remain visible.
12. Confirm Resume Harvest is available and Smart Capture/mode/calibration controls are re-enabled.

## Non-Goals Preserved

No backend, web app, metric extraction, calibrated point workflow, CDP/debug workflow, or broad harvest algorithm rewrite was introduced in Phase 13B.