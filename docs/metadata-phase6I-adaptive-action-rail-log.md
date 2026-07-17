# Phase 6I-E Adaptive Action Rail Detection Log

## Scope

Phase 6I-E only: fix Full Modal Harvest action rail detection when valid compact count candidates are rejected as `outside_right_rail`.

Touched area:
- `apps/extension-douyin-capture`
- focused extension tests
- Phase 6I-E documentation

Non-goals:
- no backend changes
- no metadata normalizer changes
- no backend browser crawling
- no captcha bypass
- no fake metrics

## Root Cause

The previous Full Modal Harvest rail detection depended on a fixed right-viewport x-band. On some Douyin full modal layouts, the action rail compact count column is near the active video/modal right edge but not inside the fixed viewport-right band. Valid compact count texts such as `90`, `6`, `32`, and `10` could therefore be rejected as `outside_right_rail`, causing `action_blocks_missing: compact_counts_rejected` even though modal detection, duration extraction, and compact count parsing were working.

## Implementation Summary

- Added richer action rail diagnostics to extension types and probe/detail metric payloads:
  - viewport width and height
  - active video rect
  - modal candidate rect
  - computed rail x-band
  - all compact count candidates with text, value, rect, accepted flag, and reason
  - y-sorted compact count clusters
  - selected compact count cluster
- Replaced fixed x-band pre-rejection with adaptive compact-count cluster detection:
  - collect visible compact count candidates first
  - reject profile/video-card anchors, caption/rating text, hashtags/long text, bottom timeline/time text, and candidates outside action-rail y range
  - cluster eligible compact counts by close x centers around the vertical column
  - score clusters by 3-4 candidate count, vertical stacking/gaps, active video/modal side geometry, and y range
  - select the best accepted cluster and map y order as like/comment/favorite/share
- Preserved profile grid fallback as like-only fallback. It does not fill comment, favorite, or share.
- Updated probe status semantics:
  - `PASS`: duration plus like/comment/favorite/share detected
  - `WARN`: duration plus reliable like detected, optional action counts missing
  - `FAIL`: aweme id missing, duration missing, or no reliable like/action source
- Updated override behavior so a `WARN` probe requires explicit override before Full Modal Harvest starts.

## Tests Added/Updated

Focused tests now cover:
- adaptive x-cluster maps `90/6/32/10` when outside the old viewport-right 15 percent band
- compact count candidates outside the fixed rail but inside the selected vertical cluster are accepted
- profile card compact numbers are rejected
- bottom player time remains rejected
- caption/rating numbers remain rejected
- only-like extraction returns `WARN`, not `FAIL`
- profile grid fallback fills only `like_count`
- probe and harvest extraction still use the same extractor output

## Verification

Focused modal harvest test was run successfully:

```cmd
cd apps/extension-douyin-capture && npx tsx src/modalHarvest.test.ts
```

Result: passed.

Full extension test remains to be run after documentation is created.
