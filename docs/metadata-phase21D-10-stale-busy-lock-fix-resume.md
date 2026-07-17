# Phase 21D-10 — Stale busy/running lock fix resume

Date: 2026-05-07

## Completed

Phase 21D-10 was implemented for the extension scanner UI.

## Files changed

- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase21D-10-stale-busy-lock-fix-log.md`
- `docs/metadata-phase21D-10-stale-busy-lock-fix-resume.md`

## Key implementation notes

- `getScannerBusyState(state)` is the canonical busy selector for the new scanner UI.
- The selector reports `isBusy`, `busyReason`, `busySource`, and `isStale`.
- Running locks older than two minutes are stale and do not block Scan Profile.
- Running locks with no timestamp are considered stale after popup reload.
- Paused state does not count as busy and enables Resume.
- Action gating only shows `Wait for the current step to finish.` when canonical busy state is actually busy.
- Reset preserves calibration but clears workflow progress and stale lock state.
- Legacy/V2/smart capture/safe runner state is not used by the new scanner busy gate.

## Tests added or updated

Coverage was added for:

1. Scan Profile enabled when no real running task exists.
2. Stale running scan state older than two minutes enables Scan Profile.
3. Stale legacy harvest running state does not block Scan Profile.
4. Active scan running disables Scan Profile with `Wait for the current step to finish.`
5. Paused state is not busy.
6. Paused state enables Resume.
7. Reset clears busy/action workflow state.
8. After Reset, primary action is Scan Profile.
9. After Reset, Scan Profile is enabled.
10. Scan success clears the scan running lock.
11. Scan error clears the scan running lock.
12. Classification failure does not leave classification busy.
13. Calibration failure does not leave collect busy.
14. Old legacy running flags do not block the new scanner UI.
15. Existing render/build validation still runs without backend calls from rendering.

## Validation status

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test`: passed.
- Build passed through the extension test script; run standalone build before final report if a separate build line is required.

## Manual retest

1. Open the extension popup on a Douyin profile with no active scanner job.
2. Confirm the primary action says `Scan Profile`.
3. Confirm the button is enabled.
4. Confirm no `Action blocked — Wait for the current step to finish.` alert appears.
5. If the popup was previously stuck, click Reset and confirm calibration remains while Scan Profile becomes enabled.
