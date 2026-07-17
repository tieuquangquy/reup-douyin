# Phase 22B-6 Calibration State Preservation Resume

## Completed
- Whole-profile state writes now preserve canonical calibration via [`writeWholeProfileHarvestState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:244).
- Whole-profile state reads now hydrate canonical calibration from [`DOUYIN_SCANNER_CALIBRATION_KEY`](apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts:24) and [`DOUYIN_SCANNER_STORAGE_ROOT_KEY`](apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts:25) in [`readWholeProfileHarvestState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:219).
- [`verifyProfile()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:425) no longer resets calibration to idle during scan bootstrap.
- Regression coverage was added in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).
- Validation completed with [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json), [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json), and [`npm --workspace @reup-douyin/extension-douyin-capture run build`](apps/extension-douyin-capture/package.json).

## Key Invariant
- Non-calibration workflow writes must keep the more complete calibration snapshot.
- Canonical storage calibration must be able to restore whole-profile state calibration if the in-state snapshot is stale, missing, or weaker.
- After a successful scan/classification with existing ready calibration, the canonical primary action must remain `start_collecting`.

## Touched Files
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase22B-6-calibration-state-preservation-log.md`](docs/metadata-phase22B-6-calibration-state-preservation-log.md)
- [`docs/metadata-phase22B-6-calibration-state-preservation-resume.md`](docs/metadata-phase22B-6-calibration-state-preservation-resume.md)
