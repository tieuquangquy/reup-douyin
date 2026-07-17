# Phase 17E Modal Bootstrap and Test Current Video Log

## Scope

Phase 17E fixes the modal-page Smart Capture bootstrap and allows Test Current Video to run on a modal page without a capture session.

In scope:
- Extension modal bootstrap in apps/extension-douyin-capture.
- Test Current Video popup/content-script flow.
- Sessionless target queue recognition for modal Smart Capture.
- Modal profile URL resolution by stripping modal_id.
- Extension tests and operator docs for the changed workflow.

Out of scope:
- Tile Gallery UI changes.
- Calibrated-point workflow redesign.
- CDP/debug workflow changes.
- Five-point calibration restoration.
- Backend Capture Inbox behavior changes.
- Crawler, video processing, scoring, or publishing implementation.

## Root Cause

The modal workflow still treated capture_session as a required precondition for modal actions. That made the popup block Smart Capture and related modal states before it could bootstrap a harvest plan from the modal URL. The target queue helper also encoded a capture-session requirement, so a valid target queue without latest_capture_session_id was treated as unknown.

Test Current Video also needed a modal-local path that uses the current modal_id as the temporary target_aweme_id and reads calibrated metrics from the content script without backend writes, target queue state, or Capture Inbox side effects.

## Implementation Notes

- Modal URL resolution now strips modal_id while preserving the profile path and non-modal query params.
- Sessionless non-empty target queues are treated as known.
- Modal coverage no longer requires a capture session for can_harvest_all.
- Popup current-state blocking no longer returns capture_session_required for a ready modal.
- Test Current Video now sends REUP_DOUYIN_PROBE_CURRENT_MODAL and displays duration, like, comment, favorite, share, source, and integrity status.
- Content script Test Current Video waits for the current modal id to remain stable, extracts calibrated metrics, and validates before/after/extracted IDs against the current modal id.
- Smart Capture on a modal with no known target queue temporarily opens the profile URL, builds the harvest plan through /douyin-extension/harvest-plan, saves plan/targets/evidence in smart state, and returns to the original modal URL.

## Required Test Current Video Error Reasons

- modal_id_missing
- calibration_missing
- modal_metrics_timeout
- data_integrity_mismatch
- calibrated_point_read_failed

## Verification

Executed extension test suite:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Result: passed. The workspace test command also ran the extension build and dist module resolution check as part of the package test script.
