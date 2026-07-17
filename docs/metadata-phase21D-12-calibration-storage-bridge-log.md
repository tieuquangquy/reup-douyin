# Phase 21D-12 Calibration Storage Bridge Log

## Scope

Implemented the Phase 21D-12 calibration storage bridge for the Douyin Scanner popup only. This change keeps the existing four-point calibration runner intact and adds a canonical scanner calibration bridge at `douyinProfileScanner.calibration`.

## Findings

- The active four-point calibration runner is still the content-script handler for `REUP_DOUYIN_START_RIGHT_RAIL_CALIBRATION`.
- Completed calibration is written to Chrome local storage at `douyinRightRailCalibration`.
- Legacy alias `rightRailCalibration` may still exist and must be read, but not quarantined or deleted by scanner reset.
- Whole Profile Harvest reset already preserves calibration; Phase 21D-12 extends the explicit calibration reset key list to include canonical scanner calibration keys.

## Implemented

- Added canonical calibration helper in `apps/extension-douyin-capture/src/wholeProfileHarvest/calibration.ts`.
- Added `normalizeDouyinCalibration(...)` with canonical point names: `like`, `comment`, `favorite`, `share`.
- Normalized British spelling aliases (`favourite`, `favourite_count`) to canonical `favorite`.
- Added `syncDouyinCalibrationFromStorage(...)` to read canonical and legacy storage keys and migrate complete calibration into:
  - `douyinProfileScanner.calibration`
  - `douyinProfileScanner.calibration` under the root bridge key `douyinProfileScanner`
- Updated Whole Profile Harvest state normalization to preserve canonical calibration diagnostics.
- Updated popup lifecycle to sync calibration before rendering, reconnect-derived refresh, primary action selection, calibration completion, and collect gating.
- Updated runtime `getCalibration()` to use canonical scanner calibration instead of direct legacy-only storage reads.
- Updated readiness/action flow so scanner primary action can advance to Start Collecting once profile scan, queue, and four-point calibration are ready.
- Added Advanced diagnostics rows for calibration readiness, source, point count, point presence, missing points, migration status, checked key count, and update timestamp.
- Added canonical keys to calibration reset scope while keeping harvest reset calibration-preserving.
- Added focused calibration bridge tests.

## Validation So Far

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed after implementation.
