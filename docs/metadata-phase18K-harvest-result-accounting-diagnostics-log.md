# Phase 18K Harvest Result Accounting Diagnostics Log

## Scope

Phase 18K fixes canonical Whole Profile Run Harvest result accounting and diagnostics when a batch finishes with zero updated targets and all processed targets failed.

## Root Cause

The canonical harvest finalizer treated any non-zero failed count as `completed_with_warnings`, regardless of whether any target actually updated or skipped successfully. The target catch path also stored only a compact error string in the failed result, so the final progress summary could show `0 / 0 / 10` while keeping top-level `last_error` empty after final completion.

## Final Status Accounting Rules

- `processed = 0`: top-level `status=failed`, `phase=failed`, `harvest.status=failed`, `last_error.code=harvest_no_targets_processed`.
- `updated = 0`, `skipped = 0`, `failed > 0`: top-level `status=failed`, `phase=failed`, `harvest.status=failed`, `last_error.code=harvest_all_targets_failed`.
- `updated > 0`, `failed > 0`: top-level `status=completed`, `phase=harvest_completed`, `harvest.status=completed_with_warnings`, `last_error.code=harvest_some_targets_failed`.
- `updated > 0`, `failed = 0`: top-level `status=completed`, `phase=harvest_completed`, `harvest.status=completed`, `last_error=null`.
- `skipped > 0`, `updated = 0`, `failed = 0`: top-level `status=completed`, `phase=harvest_completed`, `harvest.status=completed`.

## Per-Target Failure Diagnostics

Each target result now records the failure stage, error code/message, attempt count, whether modal open/extraction/payload/flush happened, backend status/error code, compact metrics, item id, and completion time. The target catch path converts all thrown errors into structured target failures and checkpoints after each failed target.

## Failure Summary

`harvest.failure_summary` aggregates failed target rows into `failed_count`, sorted `top_failure_reasons`, and sampled failed target aweme ids with code and stage.

## UI Diagnostics

The Whole Profile progress summary now exposes `Top failure` and compact `Recent harvest rows` so an operator can see failure reasons without opening debug JSON.

## Copy Debug JSON

Copy Debug JSON continues to copy the canonical state and now includes `harvest.queue`, `harvest.results`, `harvest.failure_summary`, `debug.last_request_summary`, `debug.last_response_summary`, and structured `last_error`. No giant DOM/raw HTML is added.

## Tests Run

- Pending final validation in this work session: `npm --workspace @reup-douyin/extension-douyin-capture run test`
- Pending final validation in this work session: `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- Pending final validation in this work session: `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Live Retest Steps

1. Reload the extension build in the browser.
2. Open a Douyin profile with verified targets.
3. Run Verify Profile.
4. Run a random dry-run sample and confirm it is unaffected.
5. Run canonical Run Harvest with batch limit 10.
6. If every target fails, confirm top-level Status is failed, Harvest status is failed, Last error is `harvest_all_targets_failed`, Top failure is visible, and Recent harvest rows show per-target failure codes/stages.
7. Copy Debug JSON and confirm `state.harvest.results` and `state.harvest.failure_summary` are present.
