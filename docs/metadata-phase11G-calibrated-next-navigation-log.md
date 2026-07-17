# Phase 11G Calibrated Next Navigation Log

## Scope

Phase 11G fixes Full Modal Harvest stopping at `no_next_video` after the first successfully persisted modal item. The change is limited to `apps/extension-douyin-capture` plus tests and docs.

## Root Cause

Full Modal Harvest already extracted and flushed the first modal item successfully, but the active harvest loop still depended on brittle Douyin next-control selection and keyboard-only navigation. Douyin's modal next/down control is not stable enough to discover by selector, so the controller could not advance from the current `aweme_id` and stopped with `no_next_video`.

## Implementation Summary

- `RightRailCalibration` now supports optional `next_video_button` as a fifth point.
- The content-script calibration sequence now prompts for LIKE, COMMENT, FAVORITE, SHARE, then NEXT video/down arrow.
- Probe remains compatible with old four-point metric calibration because metric extraction still reads only metric points.
- Full Modal Harvest requires `next_video_button` before starting or resuming.
- The harvest loop now uses calibrated next-point navigation after each item is queued and flushed.
- Progress state now includes next point status, previous/current aweme ids, retry count, last navigation result, failed stage, and consecutive duplicate count.

## Navigation Strategy

`navigateNextVideoByCalibratedPoint` computes the click target from the current content-script viewport:

1. `x = next_video_button.x_ratio * viewport.width`
2. `y = next_video_button.y_ratio * viewport.height`
3. `document.elementFromPoint(x, y)` resolves the live target.
4. The content script dispatches `pointerdown`, `mousedown`, `mouseup`, and `click`.
5. The controller polls every 300ms for modal id change from either `modal_id` or `/video/{aweme_id}`.
6. If unchanged, fallbacks run in order: ArrowDown, wheel down, second calibrated click.
7. If still unchanged, harvest stops with a retryable next-video failure and flushes pending items.

## Duplicate Handling

The controller no longer counts the just-harvested current `aweme_id` as a duplicate when it is re-observed before navigation. `duplicate_count` increments only after a navigation attempt returns the same aweme again. `consecutive_duplicate_count` stops the loop as `duplicate_loop_detected` after repeated same-aweme observations.

## Tests

Coverage was added for:

- fifth-point calibration storage
- calibrated coordinate click sequence
- modal id change detection
- missing next point blocking Full Harvest navigation
- duplicate counting source guards
- progress UI navigation diagnostics
- missing-next-point and timeout operator guidance
