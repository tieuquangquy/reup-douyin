# Phase 22B-5 — Single source of truth for primary action

## Scope
- Extension-only Phase 22B-5 work in [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts), [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts), [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts), [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts), and related tests.
- No backend API contract changes.
- No Capture Inbox UI changes.
- No auto-start calibration behavior.

## What changed
- Added canonical calibration readiness metadata in [`getCanonicalCalibrationReady()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:1) so canonical point completeness wins over conflicting legacy flags while still reporting source and conflict state.
- Kept scanner primary-action selection centralized in [`getCanonicalScannerPrimaryAction()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:1) with explicit metadata fields:
  - selector source
  - selector version
  - canonical calibration snapshot
- Updated [`getScannerControlPanelViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1) and [`getDouyinScannerMainViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1) to consume the canonical selector instead of rebuilding action state locally.
- Updated advanced diagnostics in [`getWholeProfileHarvestProgressViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1) to expose canonical calibration and primary-action metadata from the same selector path the UI uses.
- Updated popup primary-action dispatch in [`runWholeProfilePrimaryActionFromPopup()`](apps/extension-douyin-capture/src/popup.ts:823) to read [`getCanonicalScannerPrimaryAction()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:1) directly before routing by action key.
- Enriched Start Collecting preflight diagnostics in [`runStartCollectingPreflight()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:260) with canonical calibration fields without changing the existing blocked-stage split between calibration and backend-session failures.

## Behavioral result
- The primary action shown in the scanner card and the metadata shown in advanced diagnostics now share one selector.
- Conflicting legacy calibration flags no longer force the UI toward Calibrate when canonical four-point readiness is already satisfied.
- Start Collecting backend-session verification failures stay classified as backend-session failures and do not mutate the canonical primary action to Calibrate.
- Popup dispatch remains action-key based and does not infer behavior from button labels.

## Regression coverage added
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
  - canonical calibration conflict behavior
  - canonical selector metadata shape
  - delegation of legacy readiness helper to canonical readiness
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
  - popup primary click path uses canonical selector directly
  - scanner control panel and scanner main VM parity with canonical selector
  - advanced diagnostics exposure of canonical selector/calibration metadata
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
  - blocked backend-session Start Collecting keeps canonical calibration diagnostics
  - blocked backend-session Start Collecting keeps canonical primary action at Start Collecting, not Calibrate
