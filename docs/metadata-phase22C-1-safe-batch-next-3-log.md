# Phase 22C-1 Safe Batch Next 3 Log

## Scope
- Implement Phase 22C-1 only in the extension Start Collecting flow.
- Extend the existing one-item backend-proof runner into a safe sequential batch mode capped at 3 items.
- Reuse the same active Capture Session for the same profile across the whole batch.
- Skip already saved, backend-verified, complete, skipped, duplicate, or extracted queue items.
- Stop safely on captcha, checkpoint, login/risk, or repeated item failures.
- Keep changes scoped to backend-proof Start Collecting flow only; do not redesign Capture Inbox UI or add Next 10 behavior.

## Changes Applied
- Audit confirmed `runBatchCollectNext3SafeMode()` already existed in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) and `runStartCollectingWorkflow()` already dispatched to it when `effective_batch_limit > 1`.
- [`runBatchCollectNext3SafeMode()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) is now exported for direct regression coverage and no longer falls back into one-item mode when there are no pending targets. It returns a clear `batch_safe_mode_no_pending` result with `batch_stop_reason = "no_pending_video"`.
- [`prepareHarvestQueue()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) now preserves the existing queue during `next_3_safe` runs even on the first item, so the batch runner does not collapse the queue to a single item when it delegates into the one-item runner.
- [`runOneItemCollectAndSave()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) now preserves cumulative `processed / updated / flushed / failed` counters during `next_3_safe` batch runs instead of resetting them to one-item values after each save.
- The one-item runner now checks `detectCaptchaOrCheckpoint()` before and after modal open so safe batch mode can stop with an exact captcha risk reason instead of silently continuing.
- Safe batch diagnostics are explicit and stable: `batch_mode`, `batch_safe_mode`, `requested_batch_limit`, `effective_batch_limit`, `batch_runner_called`, `batch_run_id`, `batch_selected_aweme_ids`, `batch_processed_count`, `batch_success_count`, `session_id_used_for_all_items`, `queue_preserved_after_batch`, and checkpoint summaries.

## Validation Notes
- Added explicit regression coverage in [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) for:
  - direct `runBatchCollectNext3SafeMode()` execution
  - `requested_batch_limit = 10` capped to `effective_batch_limit = 3`
  - max-3 processing with queue preservation
  - skip behavior for saved / complete / duplicate targets
  - no-pending batch result
  - same-session reuse across the batch
  - checkpoint ordering and safe delays
  - pause / captcha stop conditions
  - one-item dispatch when batch mode is disabled
