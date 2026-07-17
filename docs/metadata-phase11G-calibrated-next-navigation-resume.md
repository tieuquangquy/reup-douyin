# Phase 11G Calibrated Next Navigation Resume Notes

## Retryable Stop States

A Full Modal Harvest stop caused by missing or ineffective next navigation is intended to be recoverable by the operator.

Relevant states:

- `no_next_video`
- `navigation_timeout`
- `failed_stage = no_next_point_calibrated`
- `failed_stage = modal_id_change_timeout`

## Missing Next Point

If the stored calibration has only four metric points, Probe can still pass, but Full Modal Harvest is blocked. The popup and progress state instruct the operator:

`Next video point missing. Recalibrate and click the down/next button as step 5.`

Resume will not continue until the operator recalibrates with the fifth next-video/down-arrow point.

## Manual Next Then Resume

If calibrated navigation times out, the pending batch is flushed and the operator sees:

`Click next video manually, then Resume Harvest.`

Resume behavior:

1. The content script reads the current modal id from `modal_id` or `/video/{aweme_id}`.
2. If the current modal id differs from the last harvested aweme, harvest continues extraction from the current modal.
3. If the current modal id is unchanged, the controller attempts the calibrated next click again.
4. If the same aweme is repeatedly observed after navigation attempts, `duplicate_loop_detected` prevents an infinite loop.

## Persisted Diagnostics

The persisted harvest state includes:

- `next_point_status`
- `previous_aweme_id`
- `navigation_retries`
- `last_navigation_result`
- `failed_stage`
- `consecutive_duplicate_count`

These fields are restored into popup progress so the operator can see the exact resume condition after reopening the popup.
