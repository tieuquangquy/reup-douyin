# Phase 12D Four-Point Navigation Loop Fix Resume

## Status

Phase 12D extension changes are complete and verified.

## Files Changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `docs/metadata-phase12D-four-point-navigation-loop-fix-log.md`
- `docs/metadata-phase12D-four-point-navigation-loop-fix-resume.md`

## What Changed

### Next-Point Regression Removed

The normal production progress view no longer shows `Next point: missing`. Four-point calibration remains valid for production Smart Capture & Harvest. Legacy `next_video_button` compatibility types and helper functions remain only for old-state compatibility and tests; they are not required by the normal harvest path.

### Harvest Loop Fixed

`runHarvestController()` no longer pre-bootstraps Video 1 before `start()`. The controller loop now performs extraction, queueing, optional flush, navigation, modal-change wait, and continuation in one state machine.

### Navigation Restored

`navigateNextModalAutomatically()` performs keyboard-first navigation using `ArrowDown`, `PageDown`, wheel, focus plus `ArrowDown`, then optional visible next-control heuristic fallback.

### Resume Fixed

Resume compares the current modal against harvested IDs. A new manually selected modal is extracted directly. The same already-harvested modal triggers another automatic navigation attempt.

### Timer Fixed

The popup starts one-second harvest progress polling while running and stops polling when harvest stops. This refreshes elapsed, average/video, ETA, phase, counts, and recent items.

## Verification Commands

All required commands passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest Checklist

1. Load `apps/extension-douyin-capture/dist` as the unpacked extension.
2. Open a Douyin modal with the four-point calibration already saved.
3. Start Smart Capture & Harvest for multiple videos.
4. Verify metrics extract for Video 1 and the row `Next point: missing` is absent.
5. Verify phase advances through `queued_item` and then navigation phases.
6. Verify the modal changes automatically.
7. Verify elapsed/avg/ETA update while running.
8. On timeout, verify pending is flushed and Resume Harvest works after manual ArrowDown or manual next click.
