# Phase 22C-2A — Stuck Pausing Lock Fix Resume

## Scope completed

- fixed stuck `harvest_pausing` / `collect_videos` lock
- added cooperative pause acknowledgment after current item
- added immediate pause acknowledgment when the runner is already idle/detached
- added stale pausing watchdog recovery
- preserved batch Next 3 queue/session/checkpoint behavior
- kept one-item save verification unchanged

## Key implementation points

- `requestPauseCollecting()` now acknowledges immediately when no live `collect_videos` task is actually active.
- `runBatchCollectNext3SafeMode()` now writes heartbeat diagnostics and acknowledges pause at safe boundaries instead of leaving `pausing` stuck.
- `runOneItemCollectAndSave()` now preserves an externally requested pause after the current item finishes and checkpoints.
- `recoverStalePausingLock()` recovers stale `pausing` state after 60s with no progress heartbeat/checkpoint.
- readiness/view-model logic no longer treats `pausing` with cleared lock as still actively pausing.

## Main diagnostics added

- `pause_acknowledged_at`
- `pause_acknowledged_after_aweme`
- `pause_checkpoint_aweme`
- `pause_checkpoint_status`
- `resume_available`
- `force_clear_lock_called`
- `force_clear_lock_reason`
- `force_clear_lock_at`
- `batch_heartbeat_at`
- `batch_heartbeat_stage`
- `batch_heartbeat_aweme`
- `pausing_stale_detected`
- `pausing_stale_age_ms`
- `pausing_stale_recovered_at`
- `stale_lock_cleared`
- `batch_stop_reason = user_paused`

## Tests added/updated

- idle pause acknowledges immediately
- pause after current item clears `active_task` and `action_lock`
- pause after current item sets `pause_acknowledged_at`
- batch pause summary exposes checkpoint and resume diagnostics
- stale pausing recovery clears lock and preserves queue/session
- reset records forced lock clear when busy

## Verification status

Passed:

- targeted `wholeProfileHarvest.test.ts`
- extension workspace test suite
- extension typecheck
- extension build
