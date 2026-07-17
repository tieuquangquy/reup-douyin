# Phase 10G Smart State And Views Fix Resume

## Summary

Two production-facing bugs were fixed:

1. Smart Capture popup no longer stays stuck in stale recalibration state when viewport data is valid again.
2. Tile Gallery no longer shows misleading `Views 0` when real view_count is missing.

## Smart state behavior

- popup now reconciles stored smart state against live calibration/probe/viewport data
- stale viewport recalibration errors are cleared automatically when the viewport is valid

## Tile Gallery behavior

- trusted real views:
  - `Views <real value>`
- unknown real views + likes:
  - `Est. Views <low-high range>`
- unknown real views + no likes:
  - `Views —`

## Safety

- no backend ingestion changes
- no canonical `view_count` overwrite
- no estimated ER substitution
