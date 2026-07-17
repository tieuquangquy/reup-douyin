# Phase 22B-6 Calibration State Preservation Log

## Scope
- Fix calibration state being overwritten after Scan Profile and classification state writes in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:219).
- Preserve canonical calibration across non-calibration workflow writes.
- Hydrate canonical calibration from canonical storage keys when whole-profile state is stale or missing calibration.
- Keep canonical primary action on `start_collecting` after scan when calibration is already ready.

## Changes
- Added calibration comparison helpers in [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:803).
- Updated [`readWholeProfileHarvestState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:219) to read [`DOUYIN_SCANNER_CALIBRATION_KEY`](apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts:24) and [`DOUYIN_SCANNER_STORAGE_ROOT_KEY`](apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts:25).
- Updated [`writeWholeProfileHarvestState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:244) to preserve the more complete calibration snapshot before persisting.
- Updated [`verifyProfile()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:425) so scan bootstrap carries forward stored calibration instead of resetting to idle calibration.
- Added regression coverage in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Diagnostics
- Added hydration diagnostics: `calibration_hydrated_from_storage`, `calibration_hydrated_source`, `calibration_ready_after_hydration`, `calibration_point_count_after_hydration`.
- Added write-preservation diagnostics: `calibration_preserved`, `calibration_preserved_source`, `calibration_ready_after_write`, `calibration_point_count_after_write`.
- Added verify bootstrap diagnostics for carried-forward calibration.

## Validation
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json)
