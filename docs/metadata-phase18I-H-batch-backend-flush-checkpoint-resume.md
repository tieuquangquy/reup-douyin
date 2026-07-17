# Phase 18I-H Batch Backend Flush Checkpoint Resume

## Current State

Phase 18I-H is partially implemented in the extension whole-profile harvest flow.

Implemented code paths now exist for:
- batch queue construction through [`buildCanonicalBatchFlushQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:110)
- sequential backend replay through [`flushBatchFromHarvestResults()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:763)
- popup action wiring through [`flushBatchFromPopup()`](apps/extension-douyin-capture/src/popup.ts:313)
- operator progress visibility through [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3)
- extension test coverage additions in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:251)

## Files Touched
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts)
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/public/popup.html`](apps/extension-douyin-capture/public/popup.html)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`docs/metadata-phase18I-H-batch-backend-flush-checkpoint-log.md`](docs/metadata-phase18I-H-batch-backend-flush-checkpoint-log.md)
- [`docs/metadata-phase18I-H-batch-backend-flush-checkpoint-resume.md`](docs/metadata-phase18I-H-batch-backend-flush-checkpoint-resume.md)
- [`docs/metadata-phase18I-H-batch-flush-operator-guide.md`](docs/metadata-phase18I-H-batch-flush-operator-guide.md)

## Resume Focus

The next continuation should start with validation and compile/test confirmation before widening scope.

Priority order:
1. Capture the final result of the still-running validation command [`npm run -w apps/extension-douyin-capture test -- --runInBand`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1).
2. Fix any TypeScript or test failures limited to Phase 18I-H files only.
3. Re-run extension validation until the batch-flush path is confirmed green.
4. Only touch API code if validation proves existing idempotency/readback behavior is insufficient.

## Expected Behavior

Phase 18I-H should preserve these semantics:
- the main harvest flow remains extraction-first and does not automatically flush backend items
- [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76) replays extracted results sequentially
- every item writes a durable checkpoint through [`checkpointBatchFlush()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:729)
- `new_and_incomplete` and `new_only` skip already-complete results when `capture_inbox_item_id` is already present
- `refresh_all` rebuilds a replayable pending queue even for previously flushed items
- readback verification failure must remain a visible failure state
- no legacy state/runtime or V2 staged-harvest flow may be used

## Validation Snapshot

Validation is currently unresolved.

What is known:
- the extension workspace test command was launched
- final terminal output was not available during this handoff
- docs intentionally record validation as pending rather than claiming a pass

## API Notes

No API files were changed in this step.

Keep API todos closed unless one of these becomes true during validation:
- backend cannot reliably behave idempotently for repeated full-modal harvest replay
- capture-session readback cannot distinguish created/updated items well enough for operator recovery
- a contract mismatch blocks the extension batch replay path

## Guardrails
- Do not migrate to legacy runtime.
- Do not reuse V2 staged-harvest code paths.
- Do not move backend replay into the main extraction loop.
- Do not broaden scope into worker, database, or web app changes.
- Do not claim validation passed until the terminal result is actually captured.
