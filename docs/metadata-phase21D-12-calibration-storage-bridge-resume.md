# Phase 21D-12 Calibration Storage Bridge Resume

## Resume Point

Phase 21D-12 adds a canonical scanner calibration bridge so the new Douyin Scanner UI recognizes completed four-point calibration stored by the existing content-script runner.

## Key Files

- `apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts`
  - Canonical model and storage sync/migration helper.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`
  - Whole Profile Harvest calibration state shape and normalization.
- `apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`
  - Calibration readiness and primary next-action flow.
- `apps/extension-douyin-capture/src/popup.ts`
  - Popup calibration sync lifecycle and Advanced diagnostics.
- `apps/extension-douyin-capture/src/storageKeys.ts`
  - Explicit calibration reset key list now includes canonical scanner keys.
- `apps/extension-douyin-capture/src/wholeProfileHarvest.calibration.test.ts`
  - Focused canonical calibration bridge tests.

## Expected Behavior

After the operator completes Calibrate 4 Points:

1. Existing runner writes `douyinRightRailCalibration`.
2. Popup calls `syncDouyinCalibrationFromStorage(...)`.
3. The helper normalizes `like_count`, `comment_count`, `favorite_count`/`favourite_count`, and `share_count` into canonical points.
4. The helper writes `douyinProfileScanner.calibration` and `douyinProfileScanner`.
5. Whole Profile Harvest state receives canonical calibration diagnostics.
6. `calibration_ready` becomes `true` only when all four points exist.
7. Main chip shows Cal ready.
8. If profile scan and queue are ready, scanner primary action becomes Start Collecting without requiring a popup reload.

## Validation Commands

Run from repository root:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Notes

- This phase does not change backend API contracts, classification endpoints, modal extractor internals, or collect/save runner behavior.
- Harvest reset remains calibration-preserving.
- Explicit calibration reset and factory reset clear canonical scanner calibration in addition to legacy calibration keys.
