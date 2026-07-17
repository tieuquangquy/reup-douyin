# Phase 12G Harvest Completion Retry Failed Resume

## Resume Behavior

On resume, Smart Capture & Harvest restores the target queue and `target_status_map`. The controller finds the first unprocessed target and routes directly to it when possible.

If no unprocessed targets remain, the controller performs final flush and completes immediately without navigating to another modal.

## Completion Rule

A target is processed when its status is one of:

- `updated`
- `failed`
- `skipped`

The batch completes when `processed_count >= target_count`.

## Off-by-one Guard

- UI target indices are clamped to `1..target_count`.
- `failed_at_index` is clamped to `target_count`.
- Duplicates do not advance current index.
- Out-of-queue awemes are not counted as target items.

## Retry Failed Only

Retry mode rebuilds the target queue from failed statuses only, resets those targets to `pending`, leaves updated targets untouched, and merges retry results back into the same harvest state.
