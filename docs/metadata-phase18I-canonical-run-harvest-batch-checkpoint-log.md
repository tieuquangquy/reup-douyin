# Phase 18I Canonical Run Harvest Batch Checkpoint Log

Phase 18I implements the canonical Run Harvest path on top of `douyinWholeProfileHarvest` only.

## Scope

- Uses verified targets from canonical Verify Profile state.
- Builds a bounded batch queue with default batch size `10`, default mode `new_and_incomplete`, and default speed `safe`.
- Creates or reuses a capture session before processing targets.
- Opens each target through a direct profile modal URL.
- Extracts modal metrics through the calibrated modal probe path.
- Builds an allowlisted canonical payload and guards against debug/state/secret leakage.
- Flushes each finalized item to the backend and requires `capture_inbox_item_id`.
- Writes a durable checkpoint after each target.
- Pauses on captcha/checkpoint without bypassing it.
- Resumes from pending and retryable failed queue items.

## Non-goals

- No V2 staged harvest runtime.
- No legacy harvest runtime.
- No full-modal pending flush queue.
- No CDP/debug runtime.
- No crawler, scoring, filtering, or auto-publishing.

## State

The canonical state key remains `douyinWholeProfileHarvest`. Phase 18I extends the existing state with harvest queue, current target, checkpoint timestamps, result counters, capture session id, backend response summary, and pause/stop fields.

## Checkpoint behavior

A checkpoint is persisted when a target moves to `processing`, and again after success or failure. Successful backend flushes increment `updated` and `flushed`; failures are recorded in `results` with an error code so they can be retried when retryable.
