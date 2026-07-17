# Phase 12E Final Four-Point Harvest Operator Guide

## Goal

Use Smart Capture & Harvest on a Douyin modal feed with four calibrated metric points. The extension should capture the current modal video, flush harvested metadata when needed, automatically move to the next modal video, and continue until the target count is reached or a real retryable stop occurs.

## Required calibration

Only four points are required:

1. Like count
2. Comment count
3. Favorite count
4. Share count

Do not calibrate a next-video/down-arrow point. The production workflow does not require `next_video_button`.

## Normal workflow

1. Reload the unpacked extension from `apps/extension-douyin-capture/dist`.
2. Open Douyin and navigate to a profile/search grid.
3. Open a video modal so the URL contains `modal_id`, or use a direct `/video/{aweme_id}` URL.
4. Click Start Right Rail Calibration if calibration is missing.
5. Click the four visible metric count points in order: like, comment, favorite, share.
6. Click Probe Current Modal Metrics.
7. Confirm Probe PASS.
8. Click Smart Capture & Harvest.
9. Keep the modal open while harvest runs.

## Expected progress behavior

For each video, the progress panel should move through these states:

1. `extracting_metrics`
2. `queued_item`
3. `flushing` when a flush threshold or final flush is reached
4. `loading_next_video`
5. `waiting_modal_change`
6. back to `extracting_metrics` after the next `modal_id` / aweme id is detected

The popup should show Video X / Y and should not show `Next point missing` as a normal production requirement.

## Automatic navigation behavior

After extracting and queueing the current modal item, the extension attempts next-video navigation without a fifth calibrated point:

1. Click an existing modal next-control if the page exposes one.
2. Focus the modal/page and send `ArrowDown`.
3. Send `PageDown`.
4. Send wheel down.
5. Focus again and retry `ArrowDown`.

The extension waits for `modal_id` or `/video/{aweme_id}` to change. It only proceeds when the detected id is non-empty and different from the previous video id.

## If navigation times out

A timeout means the extension tried the restored navigation sequence but the visible Douyin page did not move to a different aweme id within the timeout window.

Recovery steps:

1. Confirm the pending item was flushed or remains resumable.
2. Manually press ArrowDown or click the visible next video control in Douyin.
3. Wait until the URL `modal_id` changes.
4. Click Resume Smart Capture & Harvest.

Resume does not require a next-video calibration point.

## What should not appear

The production popup should not ask for:

- five-point calibration
- `next_video_button`
- `Next point missing` as a normal blocker
- CDP/debug workflow

## Verification checklist

- Probe PASS uses four calibrated metric points.
- Video 1 captures duration, like, comment, favorite, and share.
- Posted fields are preserved when already available.
- Backend flush succeeds when the backend is reachable.
- The page advances from Video 1 to Video 2 automatically.
- `current_index` advances after modal id change.
- Duplicate count does not increment immediately after extracting the current item.
- No fake `view_count` is displayed or sent by this workflow.
