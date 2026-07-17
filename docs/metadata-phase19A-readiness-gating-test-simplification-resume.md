# Phase 19A Readiness Gating Test Simplification Resume

## Current Step
Complete Phase 19A verification and prepare the final delivery report for the simplified whole-profile Run tab workflow.

## Done
- Audited the existing readiness, next-action, and popup Run tab wiring in [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Reworked [`getNextRecommendedAction()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:101) so the operator-facing dry-run recommendation is `test_3_videos` / `Test 3 Videos`.
- Tightened extraction disabled-reason logic in [`getWholeProfileHarvestActionState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:258) so calibration is explicitly required before extraction.
- Simplified [`getRunTabViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:756) to expose one operator-friendly dry-run action in the main Run tab.
- Updated [`popup.html`](apps/extension-douyin-capture/public/popup.html) and [`popup.ts`](apps/extension-douyin-capture/src/popup.ts) so the main Run tab shows and wires `Scan Profile`, `Test 3 Videos`, `Extract Next 10`, `Pause`, `Resume`, `Reset`, and related guidance without the old first/last test buttons.
- Updated focused tests in [`wholeProfileHarvest.readiness.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts), [`wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts), [`wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts), [`phase18aPopupCleanup.test.ts`](apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts), and [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts).
- Fixed the follow-on production button-count assertion after removing first/last dry-run buttons from [`PRODUCTION_BUTTON_IDS`](apps/extension-douyin-capture/src/popupWorkflow.ts:1).
- Verified the full extension test suite passes with [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json).

## In Progress
- Run explicit standalone verification commands for [`typecheck`](apps/extension-douyin-capture/package.json) and [`build`](apps/extension-douyin-capture/package.json).
- Prepare the final Phase 19A delivery report in the requested structure.

## Next Exact Task
Run:
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

Then deliver the final Phase 19A report.

## Key Files To Continue
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/src/popupWorkflow.ts`](apps/extension-douyin-capture/src/popupWorkflow.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [`docs/metadata-phase19A-readiness-gating-test-simplification-log.md`](docs/metadata-phase19A-readiness-gating-test-simplification-log.md)
- [`docs/metadata-phase19A-readiness-gating-test-simplification-resume.md`](docs/metadata-phase19A-readiness-gating-test-simplification-resume.md)
