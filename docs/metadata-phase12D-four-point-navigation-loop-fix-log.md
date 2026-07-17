# Phase 12D Four-Point Navigation Loop Fix Log

## Scope

Phase 12D was limited to `apps/extension-douyin-capture` plus regression tests and documentation. No backend, web app, CDP/debug workflow, crawler, or broad calibrated metric extraction changes were made.

## Root Cause

The harvest flow had two remaining regressions after the four-point restoration:

1. `contentScript.runHarvestController()` bootstrapped the current item before starting the controller loop. That could return a queued Video 1 snapshot to the popup while the visible state still looked like `extracting_metrics`, making the operator see Video 1 harvested and pending but no navigation attempt.
2. Normal progress UI still rendered the legacy next-point row, so a valid four-point calibration appeared as `Next point: missing` even though `next_video_button` was no longer required.
3. Navigation still carried calibrated-next-point semantics instead of using keyboard-first modal navigation.
4. The popup rendered a point-in-time progress snapshot without one-second polling, so elapsed, average/video, and ETA could stay stale while harvest was running.

## Production Next-Point Requirement Removed

Normal Smart Capture & Harvest now treats four metric points as production-ready:

- `like_count`
- `comment_count`
- `favorite_count`
- `share_count`

The normal progress navigation view no longer displays `Next point: missing`. Stored legacy `next_point_status` remains only as compatibility state for old records and is not a production gate.

## Restored Four-Point Navigation Behavior

`navigateNextModalAutomatically()` now drives normal modal advancement without requiring `next_video_button`:

1. focus page and send `ArrowDown`
2. send `PageDown`
3. send wheel scroll down
4. focus again and send `ArrowDown`
5. optional visible next-control click heuristic fallback

`waitForModalIdChange()` continues polling detected aweme/modal ID and succeeds only when the current ID differs from the previous ID.

## Harvest Loop Phase Transitions

The loop now owns extraction and navigation directly:

1. `extracting_metrics`
2. extract duration + calibrated metric counts
3. queue item
4. increment harvested/pending counts
5. persist `queued_item`
6. flush when needed
7. stop when target reached
8. otherwise persist `loading_next_video`
9. persist `waiting_modal_change`
10. attempt automatic navigation
11. on modal change, continue extracting the next modal
12. on navigation timeout, flush pending and stop resumably

The phase is no longer left as `extracting_metrics` after the item has already been queued.

## Resume Behavior

Resume no longer requires a next point. If the current modal is already harvested, resume attempts automatic navigation again. If the operator manually moved to another modal before pressing Resume Harvest, the controller extracts the current new modal directly.

## Timer And Progress

The popup now polls harvest progress every second while running. This keeps elapsed time, average seconds per item, ETA, counts, phase, and navigation diagnostics moving while the popup remains open.

## Tests Run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

All commands passed.

## Live Retest Steps

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open a Douyin video modal on a profile/search grid.
3. Confirm four-point calibration exists for like, comment, favorite, and share only.
4. Start Smart Capture & Harvest with a target greater than 1.
5. Confirm Video 1 extracts duration and all four counts.
6. Confirm the progress panel shows `queued_item`, then `loading_next_video` / `waiting_modal_change` instead of remaining on `extracting_metrics`.
7. Confirm there is no normal `Next point: missing` row in the popup.
8. Confirm the page advances automatically by keyboard/scroll behavior.
9. If navigation times out, confirm pending items flush, stopped reason is navigation timeout, then press ArrowDown manually or click next video and use Resume Harvest.
