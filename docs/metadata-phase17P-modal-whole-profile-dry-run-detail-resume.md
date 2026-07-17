# Phase 17P Modal Whole Profile Dry-run Detail Resume

## Current Status

Phase 17P introduces `phase17p_modal_whole_profile_dry_run_detail` runtime state for the Modal Whole Profile beta test.

## Resume Semantics

Dry-run starts from a verified target queue when `douyinModalWholeProfileTestRun` is completed and contains targets plus a resolved profile URL. This avoids rescanning unless the operator resets Modal Test or changes the profile context.

If dry-run is selected without verified targets, the verify scan path runs first, builds the refresh-all harvest plan, and then continues into dry-run.

## State Written

Only the isolated key is written:

- `douyinModalWholeProfileTestRun`

Dry-run does not write:

- `douyinSafeHarvestRun`
- Smart Capture harvest state
- full modal pending queues
- Capture Inbox or Tile Gallery data

## Failure Handling

Each target failure is recorded as a row and dry-run continues to the next target. Final statuses are:

- all pass: `completed`
- partial fail: `completed_with_warnings` with `dry_run_some_targets_failed`
- all fail: `failed` with `dry_run_all_targets_failed`

## Operator Recovery

If a dry-run fails because modal navigation or metric extraction timed out, keep the Modal Whole Profile test panel JSON and rerun after refreshing the Douyin tab and confirming calibration is valid.
