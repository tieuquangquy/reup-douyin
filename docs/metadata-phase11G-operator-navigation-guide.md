# Phase 11G Operator Navigation Guide

## When To Recalibrate

Recalibrate if Full Modal Harvest says:

`Next video point missing. Recalibrate and click the down/next button as step 5.`

New five-point calibrations are stored with `version: "phase11g_calibrated_points_with_next"`.

The calibration sequence is now five clicks:

1. LIKE count
2. COMMENT count
3. FAVORITE count
4. SHARE count
5. NEXT video button / down arrow

Old four-point calibration still supports Probe, but Full Modal Harvest needs the fifth next-video point.

## Live Retest Steps

1. Open the Douyin profile page.
2. Open the first modal video.
3. In the extension popup, run Start Right Rail Calibration.
4. Click the four visible metric count labels, then click the next/down button as step 5.
5. Run Probe Current Modal Metrics and confirm PASS.
6. Run Smart Capture & Harvest.
7. Confirm the progress panel shows `Next point: calibrated`.
8. Confirm the first item extracts metrics and flushes pending data.
9. Confirm the phase changes through `queued_item`, `loading_next_video`, `waiting_modal_change`, and back to `extracting_metrics` on the next modal.
10. Confirm `Current aweme` changes from the first modal id to the next modal id.
11. If navigation times out, manually click the next video and then click Resume Harvest.
12. Confirm Resume continues from the manually selected modal if its aweme id differs from the last harvested aweme.

## Expected Progress Diagnostics

The popup progress panel includes:

- Next point: `calibrated` or `missing`
- Previous aweme
- Current aweme
- Navigation retries
- Last navigation result
- Failed stage

Expected last navigation results include:

- `clicked_next_point`
- `arrow_down_fallback`
- `wheel_fallback`
- `modal_changed`
- `timeout`

Expected failed stages include:

- `no_next_point_calibrated`
- `next_click_no_effect`
- `modal_id_change_timeout`

## Safe Recovery

If Full Modal Harvest stops after a successful flush, do not restart the whole profile run first. Instead:

1. Read the progress failed stage.
2. If the next point is missing, recalibrate with five points.
3. If the next click had no effect or timed out, click the next video manually.
4. Click Resume Harvest.
