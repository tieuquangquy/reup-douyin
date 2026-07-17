# Phase 18I-H Batch Backend Flush Checkpoint Log

## Scope

Implemented Phase 18I-H only for the extension whole-profile harvest flow on top of [`douyinWholeProfileHarvest`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:1): expand from the verified one-item backend flush baseline into a safe sequential batch backend flush with per-item checkpoints, resume-ready persisted queue state, Capture Inbox readback verification, mode-aware skip-complete behavior, and popup/progress visibility. This step remains extension-scoped and does not introduce legacy runtime reuse, V2 staged-harvest reuse, worker orchestration, queue infrastructure, or API contract changes.

## Completed Changes

### Canonical Queue + State
- Added [`buildCanonicalBatchFlushQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:110) to construct a backend replay queue from extracted harvest results instead of profile-scan targets.
- The queue builder now:
  - deduplicates by `aweme_id`
  - reuses persisted batch-flush queue metadata where available
  - skips already-complete items for `new_and_incomplete` and `new_only`
  - resets skipped/completed assumptions for `refresh_all`
  - preserves resume-facing fields such as attempts, last error, checkpoint sequence, and prior Capture Inbox item id where appropriate
- Batch-flush runtime state continues to live under [`harvest.backend.batch_flush`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts:267), which is updated after every item checkpoint.

### Controller Runtime
- Added batch-flush request/queue helpers in [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:687):
  - [`buildBatchFlushRequestSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:687)
  - [`classifyBatchFlushError()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:697)
  - [`summarizeBatchFlushQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:705)
  - [`checkpointBatchFlush()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:729)
- Added [`flushBatchFromHarvestResults()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:763) to run sequential backend replay from extracted canonical results.
- The new batch controller path now:
  - refuses to run while harvest extraction is still running
  - requires an existing canonical capture session
  - rebuilds or resumes a persisted batch queue
  - performs local payload guard validation per item
  - submits one item at a time through [`flushCanonicalHarvestPayload()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:619)
  - verifies each submitted aweme via [`verifyCaptureInboxItemCreated()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:643)
  - writes a durable checkpoint after each skip, failure, or verified success
  - pauses cleanly on operator stop and records resume index
  - stops hard on payload guard failure, backend failure, or readback verification failure

### Popup / Progress / Operator Visibility
- Added the operator-facing [`Flush Batch`](apps/extension-douyin-capture/public/popup.html:76) action to [`popup.html`](apps/extension-douyin-capture/public/popup.html:36).
- Wired [`flushBatchFromPopup()`](apps/extension-douyin-capture/src/popup.ts:313) in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts:1) to call [`flushBatchFromHarvestResults()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:763) with the canonical selected mode and batch limit.
- Updated popup helper/status text so the extraction-first path and explicit batch replay path are both visible to the operator in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts:263) and [`popup.html`](apps/extension-douyin-capture/public/popup.html:38).
- Extended [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3) with batch rows:
  - `Batch flush`
  - `Batch flush current`
  - `Batch flush checkpoints`
  - `Batch flush verify`
  - `Batch flush error`

### Tests
- Expanded [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:3) with Phase 18I-H coverage for:
  - mode-aware batch queue construction
  - skip-complete behavior after a prior one-item flush
  - successful sequential batch replay
  - Capture Inbox readback verification failure handling
  - progress-summary visibility for batch state

## API Impact

No API code changes were required for this phase.

The extension continues to rely on existing endpoints/contracts:
- [`POST /douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts:511)
- [`GET /douyin-extension/capture-sessions/{capture_session_id}/items`](apps/api/src/api/routes/capture_inbox.py:134)

Phase 18I-H therefore remains extension-scoped unless a later validation pass proves backend idempotency/readback changes are required.

## Non-Goals Preserved
- No legacy runtime reuse.
- No V2 staged-harvest reuse.
- No automatic backend writes during the main extraction loop.
- No worker/distributed queue changes.
- No API schema changes.
- No publish automation.

## Validation Status
- Code changes were added in [`canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts:110), [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:763), [`popup.ts`](apps/extension-douyin-capture/src/popup.ts:313), [`popup.html`](apps/extension-douyin-capture/public/popup.html), [`progress.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3), and [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:251).
- A workspace extension test command was started via [`npm run -w apps/extension-douyin-capture test -- --runInBand`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:1), but final terminal output was not available during this handoff.
- Validation must therefore remain **unresolved** until the active terminal result is captured and any resulting failures are addressed.

## Notes
- This phase builds directly from the verified one-item baseline rather than introducing a new backend pipeline.
- Batch replay remains explicit operator action after extraction, not an implicit side effect of [`runHarvest()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:478).
- Readback verification remains the source of truth for success, so backend success without a matching Capture Inbox session item is treated as a failed batch item.
