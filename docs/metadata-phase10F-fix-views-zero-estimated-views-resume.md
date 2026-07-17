# Phase 10F Fix Views Zero / Estimated Views Resume

## Summary

Tile Gallery no longer falls back to `Views 0` when real view_count is missing.

## Current card behavior

- trusted real views:
  - `Views <real value>`
- missing real views + positive likes:
  - `Est. Views <low-high range>`
- missing real views + missing likes:
  - `Views —`
- real trusted zero:
  - `Views 0`

## Safety

- estimated values remain frontend-only
- canonical `view_count` is unchanged
- no real engagement rate is recomputed from estimated views
