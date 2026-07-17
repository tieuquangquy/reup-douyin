# Phase 22B-8B Backend Flush Payload Guard Fix Log

## Scope

- Extension one-item collection pipeline only.
- No Capture Inbox frontend changes.
- No batch processing.
- No backend contract changes.

## Why backend flush failed

The Start Collecting path reached the correct profile modal and built the one-item payload, but the popup runtime sent the flush headers as a `request_headers` field inside the JSON body. The backend/local full-modal guard path treats unexpected or debug-like request fields as unsafe, so the transport could fail before returning a normal backend response. The controller then surfaced a generic `Backend flush failed` while diagnostics still looked like payload preview and guard had not completed.

## Old path classification

The endpoint was `/douyin-extension/full-modal-harvest`. This endpoint is not merely debug legacy; backend service code creates finalized Capture Inbox items when `commit_policy = "finalized_only"` and the item payload is finalized. The bug was the extension transport and diagnostics around that endpoint, not the Capture Inbox UI.

## Correct endpoint used

The one-item runner continues to use:

- `POST /douyin-extension/full-modal-harvest`
- endpoint kind: `capture_inbox_item_create`

The request now sends one-item flush metadata as HTTP headers:

- `X-Reup-Douyin-Flush-Path: canonical-whole-profile-harvest-one-item`
- `X-Reup-Douyin-Run-Id`
- `X-Reup-Douyin-Target-Aweme-Id`

The JSON body no longer receives a `request_headers` field.

## Payload preview and guard behavior

Before backend save, the runner requires:

1. valid profile-modal extraction context
2. extracted duration or duration text
3. extracted like/comment/favorite/share counts
4. built Capture Inbox payload
5. local payload guard pass
6. capture session id
7. aweme/source video id

If any requirement fails, backend save is not called and diagnostics record the exact stage.

## Backend response capture behavior

The popup runtime now returns structured failed save responses instead of throwing away the response body. Diagnostics include:

- `backend_item_save_url`
- `backend_item_save_method`
- `backend_item_save_endpoint_kind`
- `backend_response_status`
- `backend_response_short`
- `last_flush_response`
- `backend_network_error`
- `backend_timeout`

## Verify item behavior

After a successful save response, the runner reads:

`GET /douyin-extension/capture-sessions/{session_id}/items`

It verifies the current aweme id is present. If save succeeds but readback does not find the item, the run ends as `saved_unverified`.

## Count behavior

On one-item failure, the runner no longer leaves `one_item_flush` stuck as `running` and does not reset pending count to zero. It preserves current aweme and increments/keeps visible failure state.

## Capture Inbox UI

Capture Inbox frontend files were untouched.

## Tests run

- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/extensionBackendClient.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
