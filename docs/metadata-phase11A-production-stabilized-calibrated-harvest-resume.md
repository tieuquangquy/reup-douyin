# Phase 11A Production Stabilized Calibrated Harvest Resume

## Summary

Phase 11A stabilizes the final production path:

- calibrated-point probe/harvest in extension
- backend ingest compatibility for calibrated-point evidence
- truthful `Views` vs `Est. Views` behavior in Tile Gallery

## Smart popup behavior

- stale viewport recalibration state is reconciled from live viewport/calibration/probe data
- old viewport error banner is cleared automatically when the guard passes

## Backend ingest behavior

- calibrated-point `extraction_source` values are accepted
- calibrated evidence versions are accepted
- repeated flush remains idempotent
- explicit `capture_session_id` remains preferred

## Tile Gallery behavior

- real trusted views:
  - `Views <real value>`
- unknown views + likes:
  - `Est. Views <low-high range>`
- unknown views + no likes:
  - `Views —`

Estimated values remain frontend-only.
