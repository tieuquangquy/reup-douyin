# Phase 22C-2A — Stuck Pausing Lock Fix Log

## Why Pausing got stuck

The stuck state came from a split pause flow:

1. `requestPauseCollecting()` immediately wrote:
   - `phase = harvest_pausing`
   - `workflow.collection.status = pausing`
   - `active_task = collect_videos`
   - `action_lock = collect_videos`

2. The lock was only cleared later if the live runner reached a cooperative pause checkpoint.

3. If the runner had already gone idle, was between item loops, or the popup was looking at stale `pausing` state, nothing acknowledged the pause and nothing cleared the lock.

That left the UI stuck in:
- `Status: harvesting`
- `Phase: harvest_pausing`
- `Primary action: Pausing...`
- `action_lock = collect_videos`

## Pause state machine

Implemented canonical state transitions:

- Running
  - `collection.status = running`
  - `phase = batch_collecting` or active collection phase
  - `active_task = collect_videos`
  - `action_lock = collect_videos`

- Pause clicked
  - `collection.status = pausing`
  - `phase = harvest_pausing`
  - `pause_requested = true`
  - `pause_requested_at = now`
  - `pause_reason = user_requested`

- Pause acknowledged
  - `collection.status = paused`
  - `phase = paused`
  - `pause_acknowledged_at = now`
  - `active_task = null`
  - `action_lock = null`
  - `resume_available = true`

- Stale recovered
  - `collection.status = paused`
  - `phase = paused_stale_recovered`
  - `pause_acknowledged_at = now`
  - `active_task = null`
  - `action_lock = null`
  - `last_scanner_result = paused_stale_recovered`

## Cooperative pause points

Safe batch mode now checks and records pause state at:

1. before selecting next target
2. before opening modal
3. after one-item checkpoint returns
4. before safe delay
5. after safe delay

The one-item runner also preserves a requested pause after the current item completes and before the next item starts.

## Stale pausing watchdog

Added stale recovery for:

- `collection.status = pausing`
- `pause_requested = true`
- `pause_acknowledged_at = null`

Recovery triggers when no heartbeat or checkpoint has advanced for more than 60 seconds.

Heartbeat sources:
- `batch_heartbeat_at`
- `harvest.last_checkpoint_at`
- `workflow.collection.updated_at`
- `harvest.updated_at`
- `pause_requested_at`

Recovery result:
- `phase = paused_stale_recovered`
- `action_lock = null`
- `active_task = null`
- `resume_available = true`

## Reset while pausing

Reset behavior was kept functionally the same, but now records forced lock-clear diagnostics when reset is executed during:
- busy collection
- stale pausing
- active `collect_videos` lock

## Resume behavior

Resume behavior remains:
- reload paused queue/checkpoint
- reuse same session
- preserve queue
- continue from next pending item

This phase did not change item extraction or save semantics.

## Tests run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
