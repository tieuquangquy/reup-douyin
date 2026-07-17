# Phase 21D-6 State Binding + Compact Settings Resume

## Status

Phase 21D-6 implementation is complete pending final standalone validation commands.

## Completed Work

- Scanner popup state binding was corrected in `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`.
- Compact main screen rendering was updated in `apps/extension-douyin-capture/src/popup.ts`.
- Static popup markup was updated in `apps/extension-douyin-capture/public/popup.html`.
- Compact empty state and collapsed settings CSS were added in `apps/extension-douyin-capture/public/popup.css`.
- View-model and static popup tests were updated in:
  - `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`

## Behavior Summary

- Before profile scan:
  - Header badge shows `Ready`.
  - Stats grid is hidden.
  - Empty state shows `Scan profile to build collection plan.`
  - Settings are collapsed by default.
- After profile scan:
  - Header badge shows the best available video count, such as `55 videos`.
  - Stats grid renders New / Incomplete / Already collected / Queue.
- If a completed scan has no eligible videos:
  - Empty state shows `No eligible videos found.`
- Health chips now use broader display-only state detection:
  - Profile state from page/profile URL signals.
  - API ready/idle/offline from existing backend status and errors.
  - Calibration ready from readiness, calibrated status, or point count.
- Primary action no longer shows calibration when calibration is already ready.
- Rendering remains display-only and does not call backend/scanner/collector actions.

## Validation Already Run

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Result: passed.

## Remaining Validation

Run standalone:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual Retest Checklist

1. Open the extension popup before scanning a profile.
2. Confirm the badge reads `Ready`, not `0 videos`.
3. Confirm the stats grid is hidden and the empty state says `Scan profile to build collection plan.`
4. Confirm settings show a collapsed summary: `New + incomplete · Next 10 · Safe`.
5. Click `Edit` and confirm Mode / Batch / Speed selects expand.
6. Scan a profile and confirm the badge changes to the found video count.
7. Confirm the stats grid renders New / Incomplete / Already collected / Queue.
8. Confirm calibrated state shows `Cal ready` and does not produce a calibration primary action.
