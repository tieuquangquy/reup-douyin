# Phase 19A Readiness Gating Test Simplification Log

## Step
Implement Phase 19A only: fix readiness/action gating inconsistencies in the Douyin Profile Harvester and simplify main Run tab test actions to one operator-friendly `Test 3 Videos` action.

## Scope
- Keep changes inside `apps/extension-douyin-capture` and Phase 19A docs only.
- Fix contradictory readiness, next recommended action, and disabled-reason behavior for whole-profile harvesting.
- Simplify the main Run tab so operators see one recommended dry-run action instead of three separate first/last/random test buttons.
- Preserve internal compatibility where legacy dry-run modes still exist in code paths that are not part of the main operator Run tab.

## Findings
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts) was the canonical source for readiness and action gating, but it still used the public recommendation code `dry_run_random_3` and wording `Test 3 Random Videos`.
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts) exposed `Test First 3`, `Test Last 3`, and `Test 3 Random Videos` together in the main Run tab secondary actions, which conflicted with the simplified operator workflow.
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html) still rendered three dry-run buttons in the main Run tab and still used legacy `Test 3 Random Videos` wording in quick-start copy.
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts) still wired the main popup Run tab to first/last/random dry-run buttons even though Phase 19A requires one operator-facing dry-run action.
- Focused tests already existed for readiness, wording, view-model output, popup cleanup, and popup workflow, so the Phase 19A refactor could stay tightly scoped.

## Decisions Made
- Promote one public operator-facing recommendation code and label: `test_3_videos` / `Test 3 Videos`.
- Keep legacy first/last dry-run handlers only as internal compatibility paths, not as main Run tab operator actions.
- Make extraction gating deterministic by explicitly blocking extraction until profile scan, calibration, and the simplified dry-run check are all ready.
- Keep the main Run tab secondary actions minimal: `Scan Profile`, `Test 3 Videos`, and `Reset`.

## Files Touched
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.ts`](apps/extension-douyin-capture/src/popupWorkflow.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts)
- [`apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`](apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts)
- [`docs/metadata-phase19A-readiness-gating-test-simplification-log.md`](docs/metadata-phase19A-readiness-gating-test-simplification-log.md)
- [`docs/metadata-phase19A-readiness-gating-test-simplification-resume.md`](docs/metadata-phase19A-readiness-gating-test-simplification-resume.md)

## Behavior Changes
- [`getNextRecommendedAction()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:101) now returns `test_3_videos` with operator-friendly `Test 3 Videos` wording when dry-run proof is missing.
- [`getWholeProfileHarvestActionState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts:258) now blocks extraction with explicit reasons in this order: busy, missing profile scan, missing calibration, missing `Test 3 Videos` proof.
- [`getRunTabViewModel()`](apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:756) now promotes one main dry-run action and removes first/last dry-run buttons from Run tab secondary actions.
- [`renderWholeProfileRunTab()`](apps/extension-douyin-capture/src/popup.ts:601) now wires only the simplified Run tab action set.
- [`PRODUCTION_BUTTON_IDS`](apps/extension-douyin-capture/src/popupWorkflow.ts:1) no longer includes `dryRunFirstButton` or `dryRunLastButton` because those are no longer main production Run tab controls.

## Verification Notes
- Passed workspace extension test suite via:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test`
- That run also completed the extension build because the test script already executes [`npm run build`](apps/extension-douyin-capture/package.json) before its final dist resolution assertion.
- Key passing outputs included:
  - `popup workflow simplification tests passed`
  - `wholeProfileHarvest readiness/action gating tests passed`
  - `wholeProfileHarvest stepper/summary view-model tests passed`
  - `wholeProfileHarvest wording polish tests passed`
  - `extension dist module resolution tests passed`

## Status
Implementation and test-suite validation for Phase 19A are complete. Separate explicit `typecheck` and `build` commands still need to be run if strict per-command verification is required beyond the passing test script.
