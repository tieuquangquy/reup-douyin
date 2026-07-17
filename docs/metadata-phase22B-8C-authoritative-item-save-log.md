# Phase 22B-8C Authoritative Item Save Log

## Scope

- Extension one-item save authority and verification.
- Minimal backend finalized ingest compatibility.
- No Capture Inbox frontend changes.
- No batch processing.

## Why one-item flush said succeeded but Capture Inbox stayed 0

The extension treated the backend flush transport as successful before proving that a Capture Inbox item existed. The unverified branch still wrote a completed state with saved/flushed counts, even when:

- `item_created_or_updated = false`
- `capture_inbox_item_id = null`
- session item readback returned `not_found`

The backend `full-modal-harvest` finalized-only path also required profile-card title/caption and thumbnail evidence before creating a new item. Live calibrated modal payloads can have complete modal metrics but missing profile-card title/thumbnail, so the backend accepted the request path but did not create an item visible in the Capture Inbox session.

## Current flush endpoint audited

The active extension path is:

`runStartCollectingWorkflow()` -> `runOneItemCollectAndSave()` -> `flushOneCanonicalHarvestPayload()`

The backend URL is:

`POST /douyin-extension/full-modal-harvest`

This endpoint writes to the same `CaptureSession` / `CapturedItem` store read by:

`GET /douyin-extension/capture-sessions/{session_id}/items`

## Authoritative endpoint used

The phase keeps `/douyin-extension/full-modal-harvest` as the authoritative one-item endpoint because its backend service creates `CapturedItem` rows for `commit_policy = finalized_only`.

Backend compatibility was narrowed to the creation gate:

- complete modal metrics are sufficient for finalized one-item item creation
- profile-card title/thumbnail are no longer mandatory for the backend to create the item
- the created item remains in the existing Capture Inbox store

## Response parser behavior

The extension now exposes `parseCaptureInboxItemSaveResult(responseBody)`.

It supports:

- `item_id`
- `id`
- `capture_inbox_item_id`
- `item.id`
- `data.item_id`
- `result.item_id`

It also parses:

- `created`
- `updated`
- `source_video_external_id`
- `metadata_status`
- `review_status`

## Verify behavior

After backend save, the extension verifies with the same session id used for save:

`GET /douyin-extension/capture-sessions/{session_id}/items`

Matching accepts:

- `source_video_external_id`
- `aweme_id`
- `video_id`
- `source_url` containing the aweme id
- `modal_id`
- `share_url` or `url` containing the aweme id

Diagnostics include `save_session_id`, `verify_session_id`, `session_id_match`, `verify_matched_by`, and `verify_item_id`.

## Count and status correction

If verification does not find the item:

- `status = failed`
- `collection.status = failed`
- `one_item_status = saved_unverified`
- `one_item_flush.status = failed`
- `saved_count_after = 0`
- `harvest.updated = 0`
- `harvest.flushed = 0`

If verification finds the item:

- `one_item_status = saved_verified`
- `last_scanner_result = one_item_saved_verified`
- `harvest.updated = 1`
- `harvest.flushed = 1`
- item id is recorded when available

## Capture Inbox UI

Capture Inbox frontend files were untouched.

## Tests run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `cd apps/api; python -m unittest tests.test_douyin_extension_capture_service`
- Full required validation pending final run.
