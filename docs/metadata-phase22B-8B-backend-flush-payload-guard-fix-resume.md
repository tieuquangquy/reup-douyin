# Phase 22B-8B Backend Flush Payload Guard Fix Resume

## Current phase

Phase 22B-8B fixes the one-item Start Collecting save pipeline so backend save only happens after extraction, payload preview, and guard pass.

## Active failure path

The active path is:

`runStartCollectingWorkflow()` -> `runOneItemCollectAndSave()` -> `flushOneCanonicalHarvestPayload()` -> popup runtime `flushCanonicalHarvestPayload()`

The popup runtime previously posted to `/douyin-extension/full-modal-harvest` with `request_headers` embedded in the JSON payload. This made the save path fragile and could produce generic flush failures with no captured backend response.

## Fixed pipeline

The one-item pipeline now enforces:

1. modal context valid
2. metadata extraction succeeds
3. payload preview exists
4. payload guard passes
5. Capture Inbox item endpoint is called
6. backend response is captured
7. session items are verified

## Endpoint

The endpoint remains:

`POST /douyin-extension/full-modal-harvest`

It is treated as `capture_inbox_item_create` for finalized one-item payloads.

## Diagnostics to check

Successful save should show:

- `payload_preview_ready = yes`
- `payload_guard_passed = yes`
- `backend_item_save_called = true`
- `backend_item_save_endpoint_kind = capture_inbox_item_create`
- `backend_save_status = success`
- `last_flush_response` present
- `verify_items_status = success`
- `verify_aweme_found = true`

Failure before save should show:

- exact stage
- `backend_item_save_called = false`
- `backend_save_status = not_called`

## Retest steps

1. Scan profile.
2. Confirm calibration is ready.
3. Click Start Collecting.
4. Confirm modal opens with `profile_url?modal_id=<aweme_id>`.
5. Confirm extraction fields are present.
6. Confirm payload preview and guard pass before backend save.
7. Confirm Capture Inbox item appears after refresh.
8. Confirm only one item is processed.

## Tests

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` passed.
- `npx tsx apps/extension-douyin-capture/src/extensionBackendClient.test.ts` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.
