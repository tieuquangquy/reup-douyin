# Phase 22C-2F Stability Lock Regression Log

## Stable flow summary

Production popup flow remains:

1. Scan Profile
2. Classify queue
3. Start Collecting
4. `runBatchCollectNext3SafeMode`
5. `runOneItemCollectAndSave` per item
6. backend save
7. backend verify
8. checkpoint after each item
9. stop after max 3 items

## Legacy runner cleanup verification

- Start Collecting dispatch stays on `runBatchCollectNext3SafeMode`
- Resume dispatch stays on `runBatchCollectNext3SafeMode`
- forbidden stored runner targets are migrated out of scanner state
- production popup code does not import or dispatch `runRealModalExtractionHarvest`

## Batch 3 behavior

- hard cap remains `effective_batch_limit = 3`
- item #4 is not processed in the same click
- same Capture Inbox session is reused across repeated batch runs
- queue is preserved after each item and after batch completion
- backend verify is still required before queue items are treated as saved

## Counter behavior

- counters derive from canonical queue state plus verified backend-linked items
- regression coverage locks:
  - `59 -> 56 -> 53` new/queue progression
  - `0 -> 3 -> 6` already-collected progression
- popup flow diagnostics now include:
  - `active_runner_target`
  - `batch_mode`
  - `effective_batch_limit`
  - `batch_processed_count`
  - `final_session_id`
  - `session_reused`
  - `queue_preserved_after_batch`
  - `popup_counters_updated_realtime`

## Pause/resume behavior

- pause request is acknowledged after current safe checkpoint
- stale pausing lock still recovers
- resume continues from the next pending item in the same session

## Metadata behavior

- thumbnail stays aweme-scoped
- Get APP image remains rejected
- duration stays canonical and aweme-scoped
- Posted raw text is preserved
- Posted display is `dd/mm/yyyy` when parseable
- Chinese date/relative coverage remains locked for:
  - `4天前`
  - `1周前`
  - `4月28日`
  - `2026年4月28日`

## Manual retest checklist

1. Scan Profile on a supported Douyin profile.
2. Start Collecting and confirm safe batch processes only 3 items.
3. Confirm same Capture Inbox session is reused on the second Start Collecting click.
4. Confirm counters move from queue/new down by 3 and already-collected up by 3.
5. Pause during batch and confirm Resume continues from the next pending item.
6. Confirm popup never dispatches the legacy whole-profile runner.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
