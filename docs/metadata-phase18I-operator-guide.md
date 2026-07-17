# Phase 18I Operator Guide

## Before running

1. Open a supported Douyin profile page.
2. Click **Verify Profile** and wait until verified targets are present.
3. Complete 4-point calibration.
4. Keep the backend running and reachable from the extension API base URL.

## Run Harvest

Click **Run Harvest** in the Whole Profile Harvest panel. The Phase 18I default run is:

- mode: `new_and_incomplete`
- batch limit: `10`
- speed: `safe`

The run opens each target modal directly from the verified profile URL, extracts finalized modal metrics, merges safe profile-card evidence, and flushes an allowlisted backend payload.

## Progress

The popup summary shows harvest status, mode, batch limit, speed, current target, updated/skipped/failed counts, flushed/pending counts, last checkpoint, last success, pause reason, capture session id, and last error.

## Captcha or checkpoint

If Douyin shows captcha, login, security check, or abnormal traffic, the run pauses. Solve the checkpoint manually in the browser tab, then click **Resume**.

## Resume

Resume uses only `douyinWholeProfileHarvest` and continues pending or retryable failed queue items. It does not use legacy/V2 runtime state.

## Backend success criteria

A target is considered updated only when the backend response is successful, reports `item_created_or_updated`, and returns `capture_inbox_item_id`.
