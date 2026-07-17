# Phase 17W V2 Capture Session Operator Guide

## Goal

Confirm Whole Profile Staged Harvest V2 creates its own isolated Capture Inbox session before the first target and that finalized writes no longer fail with `capture_session_not_found`.

## Preconditions

- API service is running.
- Extension build with Phase 17W changes is loaded in Chrome or Edge.
- A verified Whole Profile modal queue exists from the V2-compatible modal whole-profile verification flow.
- Calibration is available and valid.

## Live Retest Steps

1. Open the Douyin profile used for the verified queue.
2. Open the extension popup.
3. Confirm the verified target count is present.
4. Start Whole Profile Staged Harvest V2.
5. Before target 1 opens, confirm the V2 panel shows:
   - `Capture session: creating`, then `ready`.
   - a non-empty short capture session id.
   - `Capture session source: whole_profile_staged_harvest_v2`.
6. Let target 1 open and settle.
7. Let V2 extract, validate, build, and flush the finalized payload.
8. Confirm the backend request to `/douyin-extension/full-modal-harvest` succeeds and does not return `capture_session_not_found`.
9. Confirm the V2 run continues to later targets or completes according to the selected target limit.
10. If a failure occurs, inspect the V2 panel reason:
    - `capture_session_create_failed` means the preflight endpoint failed before target navigation.
    - `capture_session_not_found` means the preflight session was not present or the finalized payload did not include the session id.

## Expected Payload Fields

Each finalized V2 full-modal payload should include:

- `capture_session_id`
- `capture_session_source = whole_profile_staged_harvest_v2`
- `run_id`
- `profile_url`
- `target_aweme_id`
- `source_video_external_id`

## Expected Backend Behavior

The backend should resolve the Capture Inbox session in this order:

1. explicit `capture_session_id` from the finalized payload;
2. V2 fallback by `capture_session_source` and `run_id`;
3. legacy latest Douyin session fallback.

## Non-Goals

This phase does not add crawler logic, video processing, scoring, automatic publishing, CDP/debug harvesting, or legacy Smart Capture reconnection for V2.
