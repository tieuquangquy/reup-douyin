# Phase 21D-9 Scan, Calibration, and Reset Fix Log

## Scope

Implemented Phase 21D-9 only for the Douyin Capture extension popup scanner workflow. This pass was limited to popup view-model action priority, readiness selection, calibration state mapping, reset behavior, popup handler wiring, tests, and documentation.

## Problems fixed

- The scanner primary action no longer forces calibration before the first profile scan.
- Completing four-point calibration now updates the whole-profile scanner state so the popup can immediately render `Cal ready`.
- Reset now visibly clears scanner workflow state while preserving calibration.

## Primary action priority

The scanner control panel now prioritizes actions as follows:

1. Running collection shows `Pause`.
2. Paused collection shows `Resume`.
3. Missing profile scan shows `Scan Profile`.
4. Profile scan without successful classification still shows `Scan Profile`.
5. Classified queue with videos and missing calibration shows `Calibrate 4 Points`.
6. Classified queue with videos and ready calibration shows `Start Collecting`.
7. Classified queue with no eligible videos shows `Open Capture Inbox`.

This preserves the product decision that calibration must never block the first profile scan.

## Calibration readiness

Added a canonical readiness helper that treats calibration as ready when any reliable source proves readiness:

- `status === "calibrated"`
- `calibrationStatus === "calibrated"`
- `ready === true`
- `point_count >= 4`
- `pointCount >= 4`
- stored `points` include all required right-rail metrics
- stored alias points include like, comment, favorite, and share

Stale missing status fields no longer override complete stored calibration points.

## Calibration completion behavior

After `Calibrate 4 Points` succeeds, the popup writes the calibrated whole-profile state and re-renders scanner product state. The user should see `Cal ready` immediately without needing to close and reopen the popup.

## Reset behavior

Reset now clears scanner workflow state, including profile scan result, classification result, queue, collection results, current target, running or paused state, errors, and readiness layer flags. Calibration and local scanner context/options are preserved by default.

## Tests run

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The full test command also executed the extension build and dist module resolution check successfully.

## Files changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-9-scan-calibration-reset-fix-log.md`
- `docs/metadata-phase21D-9-scan-calibration-reset-fix-resume.md`
