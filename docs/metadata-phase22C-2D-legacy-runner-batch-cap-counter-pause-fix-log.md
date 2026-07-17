# Phase 22C-2D Legacy Runner Kill / Batch Cap / Counter / Pause Fix Log

## Scope
- Route popup Start Collecting and Resume away from the legacy whole-profile modal runner and through the safe Next 3 batch runner.
- Keep safe batch effective collection capped at 3 items even when UI/options request a larger batch.
- Preserve authoritative batch diagnostics and queue/counter summaries for operator visibility.
- Add safe pause checkpoints so a pause requested during extraction is honored before backend commit.
- Keep backend saves guarded by finalized metric, payload-shape, target-match, and pause-state checks.
- Preserve local-first extension boundaries; no crawler, backend schema, queue service, or SaaS infrastructure changes were introduced.

## Changes Applied
- [`runStartCollectingWorkflow()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1511) now dispatches Start Collecting to [`runBatchCollectNext3SafeMode()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:426) with safe-batch diagnostics instead of the legacy whole-profile runner.
- [`resumeHarvest()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1426) now clears stale canonical pause/stop flags, records resume diagnostics with [`buildResumeDiagnostics()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:4899), and then routes Resume into [`runBatchCollectNext3SafeMode()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:426).
- [`runBatchCollectNext3SafeMode()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:426) clamps requested batch size to an effective maximum of 3 and records requested/effective limits, batch run id, selected aweme ids, processed counts, success counts, limit reached status, and stop reason.
- [`canCommitItemToBackend()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3833) blocks backend commit when required metrics are missing, payload guard fails, payload target mismatches, or pause/stop is active before commit.
- [`runOneItemCollectAndSave()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:3844) rereads storage after modal metric extraction and merges any pause request written during extraction into the local state before validation, payload build, and backend flush.
- [`acknowledgePauseCollecting()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:2122) records explicit pause checkpoint diagnostics, including the checkpoint that triggered safe pause.
- [`getScannerControlPanelViewModel()`](../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts:1288) and related counter helpers keep saved/pending views based on verified queue/result state rather than synthetic increments.
- [`resumeWholeProfileHarvestFromPopup()`](../apps/extension-douyin-capture/src/popup.ts:1713) presents Resume as safe Next 3 collection with canonical backend verification.

## Regression Coverage
- [`wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:823) covers popup Start Collecting dispatch through safe batch and verifies safe-batch diagnostics.
- [`wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1479) covers Resume dispatch through safe batch.
- [`wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1310) covers at-most-3 safe-batch processing, backend verification, selected ids, and stop summaries.
- [`wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1624) covers pause requested during extraction and verifies backend flush is not called before commit.
- [`wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1902) covers resuming from a paused checkpoint and verifies pause/stop flags are cleared before safe-batch processing.
- [`wholeProfileHarvest.viewModel.test.ts`](../apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts:511) covers scanner action/counter behavior for running, pausing, stale, and paused states.

## Validation
- Passed focused whole-profile regression with [`npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../apps/extension-douyin-capture/package.json:8).
- Passed [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](../apps/extension-douyin-capture/package.json:7).
- Passed [`npm --workspace @reup-douyin/extension-douyin-capture run build`](../apps/extension-douyin-capture/package.json:6).
- Passed full extension validation with [`npm --workspace @reup-douyin/extension-douyin-capture run test`](../apps/extension-douyin-capture/package.json:8), including test suite, build, and dist module resolution.
