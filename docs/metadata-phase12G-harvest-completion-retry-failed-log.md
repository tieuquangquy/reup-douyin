# Phase 12G Harvest Completion And Retry Failed Log

## Scope

Phase 12G stabilizes Smart Capture & Harvest completion inside `apps/extension-douyin-capture` only.

## Root Cause

Harvest progress previously mixed harvested item count, navigation attempts, duplicate encounters, and target queue progress. A late per-video failure after `target_count` was effectively processed could still drive navigation to the next modal and surface `#target_count+1` / `failed_at_index > target_count`.

## Changes

- `target_aweme_ids` is the source of truth for `target_count` when present.
- Per-target status map records `pending`, `updated`, `failed`, and `skipped` states.
- Completion is based on processed target status count, not navigation count.
- Per-video timeout/navigation failures mark one target failed and continue unless fatal thresholds are reached.
- `completed_with_warnings` is used when all targets are processed but at least one failed.
- Retry Failed Only is available from the popup when a failed/warning terminal harvest exists.

## Non-goals

No backend, web app, metric extraction, CDP/debug, five-point calibration, or fake metric changes were made.
