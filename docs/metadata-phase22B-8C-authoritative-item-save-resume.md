# Phase 22B-8C Authoritative Item Save Resume

## Current phase

Phase 22B-8C makes one-item save authoritative: the extension only counts an item as saved after backend readback proves it exists in the Capture Inbox session.

## Active save path

Extension:

`runStartCollectingWorkflow()` -> `runOneItemCollectAndSave()` -> `flushOneCanonicalHarvestPayload()`

Backend:

`POST /douyin-extension/full-modal-harvest`

Readback:

`GET /douyin-extension/capture-sessions/{session_id}/items`

## Backend store

The backend endpoint writes to `CaptureSession` and `CapturedItem`, the same store used by Capture Inbox and the session items endpoint.

## Key behavior

- Backend response is parsed with `parseCaptureInboxItemSaveResult`.
- Save and verify session ids must match.
- Verification can match by source video external id, aweme id, video id, or URLs containing the aweme id.
- Unverified save is not counted as saved.
- Metric-complete finalized modal payloads can create backend items without requiring title/thumbnail profile-card evidence.

## Retest checklist

1. Scan profile.
2. Confirm calibration is ready.
3. Click Start Collecting.
4. Confirm backend response has `item_created_or_updated = true` or verify finds the aweme.
5. Confirm `Verify = verified`.
6. Confirm item id appears when available.
7. Refresh Capture Inbox and confirm `Captured >= 1`.
8. Confirm `Saved count = 1` only when verify finds the item.
9. Confirm unverified readback leaves `saved_count_after = 0`.

## Tests

- Focused extension and backend tests passed.
- Full required validation pending final run.
