# Phase 22C-3 Log

## Summary

This phase upgrades the production safe batch path from Next 3 to Next 10 without changing the canonical one-item extraction/save pipeline.

## Why Next 10 Is Safe Now

- Batch collection already reuses the verified one-item pipeline.
- The scanner already writes a checkpoint after every item.
- Queue preservation, session reuse, pause/resume, safety stop, and legacy-runner blocking were stabilized in earlier phases.
- The only behavior change in this phase is the safe batch cap and its production dispatch target.

## Active Batch Runner Path

- `runStartCollectingWorkflow()`
- `runBatchCollectNext10SafeMode()`
- `runBatchCollectSafeModeInternal()`
- `runOneItemCollectAndSave()` per item

`runBatchCollectNext3SafeMode()` remains as a debug/test wrapper and is no longer the canonical popup dispatch target.

## Batch Limit Enforcement

- Production canonical runner target:
  - `runBatchCollectNext10SafeMode`
  - `wholeProfileHarvest/controller.runBatchCollectNext10SafeMode`
- Hard cap:
  - `effective_batch_limit = min(requested_batch_limit, 10)`
- No run may process item `#11`.

## Session Reuse

- One backend Capture Session is created or reused before batch work starts.
- The same `session_id` is used for all items in the run.
- Repeated Start Collecting and Resume continue using the same active session.

## Queue Skip Behavior

- Up to 10 pending items are selected.
- These statuses are skipped:
  - `backend_verified`
  - `saved`
  - `complete`
  - `skipped`
  - `duplicate`
  - `failed_permanent`
- Queue shape is preserved after each processed item and after the full batch.

## Checkpoint Behavior

- Checkpoint writes still happen after every success/failure/skip.
- Batch checkpoint schema continues to preserve:
  - `batch_run_id`
  - `session_id`
  - `processed_aweme_ids`
  - `saved_aweme_ids`
  - `failed_aweme_ids`
  - `skipped_aweme_ids`
  - `next_pending_aweme_id`

## Pause / Resume Behavior

- Pause is cooperative and stops before opening the next item.
- Resume reloads state, reuses the same session, skips already verified items, and dispatches back into `runBatchCollectNext10SafeMode()`.

## Safety / Captcha Behavior

- Captcha, verify, login, or lost-tab safety events still stop batch mode.
- Safe batch writes a checkpoint before returning control.

## Counter Behavior

- Popup counters continue to derive from canonical queue state plus backend reconciliation.
- Regression coverage now locks:
  - `59 -> 49 -> 39` for `New` and `Queue`
  - `0 -> 10 -> 20` for `Already collected`

## Legacy Runner Protection

- Production popup Start Collecting and Resume remain blocked from dispatching `runRealModalExtractionHarvest`.
- Forbidden stored runner targets still migrate out of state before any collection run begins.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
