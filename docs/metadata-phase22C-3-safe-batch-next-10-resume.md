# Phase 22C-3 Resume

## Implemented

- Canonical popup batch runner upgraded from Next 3 to Next 10.
- Production runner targets now point to:
  - `runBatchCollectNext10SafeMode`
  - `wholeProfileHarvest/controller.runBatchCollectNext10SafeMode`
- Existing `runBatchCollectNext3SafeMode()` retained as a debug/test wrapper only.
- Safe batch inner loop remains sequential and still delegates every item to `runOneItemCollectAndSave()`.
- Start Collecting and Resume now derive requested batch limit from current options/state and cap it at 10.
- Diagnostics updated to emit:
  - `batch_mode = next_10_safe`
  - `effective_batch_limit = 10`
  - `active_runner_target = wholeProfileHarvest/controller.runBatchCollectNext10SafeMode`

## Regression Coverage Added/Updated

- Max 10 processed items per run.
- Item `#11` is not processed.
- Session reuse across all 10 items.
- Queue preservation after the batch.
- Checkpoint ordering across item 1..10.
- Counter progression after 10 and 20 verified saves.
- Resume dispatch target points to Next 10 safe runner.
- Legacy runner remains blocked in production.

## Non-Goals Kept

- No extractor rewrite.
- No backend save rewrite.
- No UI redesign.
- No unbounded whole-profile collection.
- No parallel processing.

## Manual Retest Focus

1. Scan Profile on a queue with more than 10 pending videos.
2. Start Collecting once.
3. Confirm only 10 items are processed.
4. Confirm item `#11` remains pending.
5. Confirm Capture Inbox shows up to 10 new items in the same session.
6. Pause during the run and confirm Resume continues from the next pending item.
7. Run Start Collecting again and confirm the next 10 pending items are selected.
