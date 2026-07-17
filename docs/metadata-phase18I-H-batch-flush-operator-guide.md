# Phase 18I-H Batch Flush Operator Guide

## Before Running

1. Open the target Douyin profile page in the active tab.
2. Click [`Verify Profile`](apps/extension-douyin-capture/public/popup.html:40) and confirm verified targets are present.
3. Complete calibration and dry-run checks before running a real extraction batch.
4. Click [`Run Harvest`](apps/extension-douyin-capture/public/popup.html:75) and wait until extracted results exist.
5. Confirm the progress panel shows a ready capture session and extracted harvest rows from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).
6. Use [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76) only after extraction has already produced canonical results.

## What Phase 18I-H Adds

Phase 18I-H keeps the main harvest path extraction-first, but adds a queue-wide operator action: [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76).

That action uses [`flushBatchFromHarvestResults()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:763) to:
- build a backend replay queue from extracted results
- skip already-complete items when the selected mode requires it
- submit one aweme at a time to the backend
- checkpoint after every item
- verify each backend write through capture-session readback
- preserve a resume point if the operator stops the batch or a failure occurs

[`Flush One Item`](apps/extension-douyin-capture/public/popup.html:77) still exists for a single validated preview target, but [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76) is the Phase 18I-H path for safe sequential replay.

## Standard Operator Flow

1. Click [`Verify Profile`](apps/extension-douyin-capture/public/popup.html:40).
2. Run a dry run if needed.
3. Click [`Run Harvest`](apps/extension-douyin-capture/public/popup.html:75).
4. Wait until the extraction batch completes or pauses with extracted results available.
5. Select the intended mode in [`#wholeProfileHarvestMode`](apps/extension-douyin-capture/public/popup.html:44):
   - `new_and_incomplete`
   - `new_only`
   - `refresh_all`
6. Select the intended batch size in [`#wholeProfileHarvestBatch`](apps/extension-douyin-capture/public/popup.html:52).
7. Click [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76).
8. Watch the progress panel for:
   - `Batch flush`
   - `Batch flush current`
   - `Batch flush checkpoints`
   - `Batch flush verify`
   - `Batch flush error`
9. If the batch stops or fails, inspect the progress rows and copied debug state before retrying.

## What the Progress Panel Means

Batch rows come from [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).

- `Batch flush`
  - shows status plus processed/succeeded/skipped/failed/pending counts
  - example: `completed · 2/2 processed · ok 1 · skip 1 · fail 0 · pending 0`
- `Batch flush current`
  - shows the current aweme being replayed or the saved resume point
- `Batch flush checkpoints`
  - shows how many durable per-item flush checkpoints were persisted
- `Batch flush verify`
  - shows the last readback verification state plus the last flushed aweme id
- `Batch flush error`
  - shows the current structured batch failure code and operator-facing message

## Mode Semantics

The batch queue is built by [`buildCanonicalBatchFlushQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:110).

- `new_and_incomplete`
  - skips targets that already have a persisted `capture_inbox_item_id`
  - replays extracted results that are still incomplete from a backend-write perspective
- `new_only`
  - behaves like a stricter skip-complete mode for extracted results not yet flushed
- `refresh_all`
  - rebuilds the queue as pending even for previously flushed items
  - use only when an intentional full replay is needed

## Stop / Resume Behavior

Phase 18I-H checkpoints after every item through [`checkpointBatchFlush()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:729).

This means:
- operator stop requests pause the batch with a saved resume index
- already-verified items should not need to rerun in skip-complete modes
- failed verification or backend failure leaves the queue in a visible failed state
- a future retry can resume from persisted batch state rather than rebuilding from scratch

## Common Failure States

Structured errors come from [`errors.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:1) and controller classification in [`classifyBatchFlushError()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:697).

Important failure cases include:
- [`payload_preview_missing`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:94)
  - Meaning: extracted state was not sufficient to build a flushable payload.
  - Operator action: rerun extraction for the affected target.
- [`capture_session_not_found`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:93)
  - Meaning: backend no longer recognizes the capture session.
  - Operator action: rerun extraction flow to recreate the session before replaying again.
- [`backend_finalized_metadata_required`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:95)
  - Meaning: backend rejected the payload as not fully finalized.
  - Operator action: rerun extraction for the target.
- [`backend_secret_guard_rejected`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:107)
  - Meaning: guarded data leaked into the payload.
  - Operator action: do not retry until payload construction is fixed.
- [`backend_success_but_no_capture_inbox_item`](apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts:109)
  - Meaning: backend returned success but capture-session readback did not confirm the item.
  - Operator action: inspect copied debug data and backend logs before rerunning.

## Copying Diagnostics

If batch flush fails, use the popup debug workflow backed by [`copyDebugState()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1673).

Inspect at least:
- `debug.last_request_summary`
- `debug.last_response_summary`
- `harvest.backend.batch_flush`
- `harvest.backend.payload_preview`
- `harvest.results`

These records show the replay path, target aweme id, backend response shape, verification status, checkpoint counts, and resume point.

## Guardrails
- Do not treat [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76) as automatic publishing.
- Do not run it before extraction results exist.
- Do not assume backend success is enough; readback verification is still required.
- Do not switch to legacy or V2 paths for recovery.
- Do not widen this flow into web/API/worker changes unless validation proves the existing backend contract is insufficient.
