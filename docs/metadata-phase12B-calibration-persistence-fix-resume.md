# Phase 12B Calibration Persistence Fix Resume

## Current status

Phase 12B implementation is complete for extension calibration persistence and stale probe cleanup.

## Files changed

- `apps/extension-douyin-capture/src/types.ts`
  - Added optional `viewport_source` to `RightRailCalibration`.
  - Added `partial` to Smart Capture calibration status.

- `apps/extension-douyin-capture/src/contentScript.ts`
  - Calibration overlay now shows explicit Step 1/5 through Step 5/5 labels.
  - Saved calibration now includes `viewport_source: "content_script"`.

- `apps/extension-douyin-capture/src/popupWorkflow.ts`
  - Added `validateRightRailCalibration()`.
  - Added missing/partial/valid calibration semantics.
  - Smart state reconciliation no longer carries PASS probe status when calibration is missing/partial.
  - Smart harvest guard blocks old four-point calibration with the next-video-point message.

- `apps/extension-douyin-capture/src/popup.ts`
  - Popup reader now accepts Phase 12A calibration versions instead of only `phase10a`.
  - Start Calibration re-reads saved calibration from storage, validates it, clears stale probe, and refreshes immediately.
  - Missing/partial calibration clears `douyinLastProbeResult`.
  - Show Calibration displays version, viewport, viewport source, point count, validation status, and all five points.
  - Added `content_script_not_ready` and `calibration_incomplete` operator-facing failure mapping.

- `apps/extension-douyin-capture/src/popupWorkflow.test.ts`
  - Added/updated Phase 12B tests and source assertions for validation, canonical key usage, stale probe clearing, and five-point overlay persistence.

## Root cause to preserve in handoff

The exact root cause was popup-side version validation drift: content script saved Phase 12A calibration, but popup `isRightRailCalibration()` only accepted `phase10a`, so the popup treated the newly saved calibration as missing. Separately, stale `douyinLastProbeResult` was read independently of calibration validity, so an old PASS could remain visible while calibration was missing.

## Verification performed

Implementation run:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Both passed.

## Final verification still expected before handoff completion

Run the required full command sequence:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live retest steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin tab.
3. Open a Douyin profile and open the first video modal.
4. In the extension popup, click Clear Calibration.
5. Confirm Calibration is missing and Last probe is not PASS.
6. Click Start Right Rail Calibration.
7. On the page overlay, click:
   - LIKE count
   - COMMENT count
   - FAVORITE count
   - SHARE count
   - NEXT video button / down arrow
8. Confirm popup shows Calibration: calibrated and calibrated viewport is populated.
9. Click Show Calibration and confirm point count is 5/5 with all five points displayed.
10. Click Probe Current Modal Metrics and confirm Last probe can become PASS for the current modal.
11. Click Smart Capture & Harvest and confirm it proceeds beyond calibration guard.
