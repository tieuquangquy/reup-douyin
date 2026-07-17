# Phase 22C-2F Stability Lock Regression Resume

## Locked behavior

- Start Collecting uses safe batch mode only
- batch remains capped at 3
- one-item save/verify remains canonical
- same session is reused
- queue is preserved
- counters reconcile from canonical queue/backend-linked state
- pause/resume remains stable
- legacy whole-profile runner remains blocked

## Key diagnostics

- `active_runner_target`
- `batch_mode`
- `effective_batch_limit`
- `batch_processed_count`
- `final_session_id`
- `session_reused`
- `queue_preserved_after_batch`
- `popup_counters_updated_realtime`
- `legacy_runner_target_blocked`

## Regression coverage

- forbidden legacy runner dispatch
- safe batch max-3 behavior
- counter progression across repeated runs
- pause/resume and stale pausing recovery
- Posted/thumbnail/duration metadata behavior

## Commands

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
