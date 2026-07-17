# Phase 22C-2D Legacy Runner Kill / Batch Cap / Counter / Pause Fix Resume

## Completed
- Start Collecting now uses [`runBatchCollectNext3SafeMode()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:426) through [`runStartCollectingWorkflow()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1511), avoiding legacy whole-profile runner dispatch for the popup path.
- Resume now uses [`resumeHarvest()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1426) to clear stale pause/stop flags, record resume diagnostics, and enter the same safe Next 3 batch path.
- Safe-batch requested/effective limit diagnostics and at-most-3 enforcement are centralized in [`runBatchCollectNext3SafeMode()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:426).
- Backend commit is guarded by [`canCommitItemToBackend()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3833), including the pause-before-commit guard.
- Pause requested during [`extractModalMetrics()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:4046) is preserved by rereading state in [`runOneItemCollectAndSave()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3844) before payload validation and flush.
- Pause acknowledgement diagnostics include the checkpoint name from [`acknowledgePauseCollecting()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2122).
- Popup Resume wording/diagnostics now describe safe Next 3 canonical backend verification in [`resumeWholeProfileHarvestFromPopup()`](../apps/extension-douyin-capture/src/popup.ts:1713).

## Validation Status
- Passed [`npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/package.json:8).
- Passed [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](../apps/extension-douyin-capture/package.json:7).
- Passed [`npm --workspace @reup-douyin/extension-douyin-capture run build`](../apps/extension-douyin-capture/package.json:6).
- Passed [`npm --workspace @reup-douyin/extension-douyin-capture run test`](../apps/extension-douyin-capture/package.json:8), including the extension test suite, build, and dist module resolution.

## Files Touched In This Step
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](../apps/extension-douyin-capture/src/popup.ts)
- [`docs/metadata-phase22C-2D-legacy-runner-batch-cap-counter-pause-fix-log.md`](metadata-phase22C-2D-legacy-runner-batch-cap-counter-pause-fix-log.md)
- [`docs/metadata-phase22C-2D-legacy-runner-batch-cap-counter-pause-fix-resume.md`](metadata-phase22C-2D-legacy-runner-batch-cap-counter-pause-fix-resume.md)

## Notes For Future Work
- Keep legacy [`runRealModalExtractionHarvest()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:4357) out of popup Start/Resume dispatch paths; it may remain only for older direct test/helpers until explicitly retired.
- Preserve safe-batch diagnostics when adding future batch controls so requested UI size and effective local-safe size remain visible.
- Any future long-running collector changes should keep pause/stop checks before backend commit and avoid overwriting pause state written by concurrent popup actions.
