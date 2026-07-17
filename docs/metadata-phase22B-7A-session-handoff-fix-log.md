# Phase 22B-7A Session Handoff Fix Log

## Scope

- Extension capture-session create/verify handoff only.
- No item extraction or Capture Inbox UI changes.

## Why backend created a session but extension still said Session missing

- The backend create route already created the session in the same Capture Inbox store.
- The extension handoff path still depended on a narrow `session_id` parse and a generic create/verify failure path.
- `Start Collecting` then fell through into a generic blocked state instead of persisting a verified session.
- The old flow also continued past session setup into one-item collection preflight, which made session handoff harder to diagnose.

## Active create path

- Extension runtime create call: `createWholeProfilePopupRuntime().createCanonicalHarvestSession()`
- Controller handoff path: `runStartCollectingWorkflow()` -> `runStartCollectingPreflight()` -> `ensureBackendCaptureSession()` -> `createCanonicalHarvestSession()`
- Create URL: `POST /douyin-extension/capture-session`

## Actual backend create response shape

The backend route response model is:

```json
{
  "ok": true,
  "session_id": "<uuid>",
  "created": true,
  "profile_url": "...",
  "source": "whole_profile_harvest",
  "run_id": "..."
}
```

This comes from:

- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/schemas/douyin_extension.py`

## Session id parser behavior

The extension now uses `extractCaptureSessionId(responseBody)` and accepts:

1. `session_id`
2. `id`
3. `capture_session_id`
4. `session.id`
5. `session.session_id`
6. `data.session_id`
7. `data.id`

Unknown shapes do not silently pass. The handoff fails with:

- `Capture session created but response did not include session_id.`

and diagnostics include a shortened response body.

## Verification strategy

Preferred verification now uses the same Capture Inbox store that the web UI uses:

1. `GET /capture-inbox/sessions`
2. Match by exact session id

Fallback:

1. `GET /douyin-extension/capture-sessions/{session_id}/items`

The list endpoint is preferred because it proves the session exists even when it is still empty.

## State persistence behavior

After verification succeeds, the extension persists:

- `capture_session_id`
- `harvest.capture_session_status = "ready"`
- `harvest.backend.capture_session.status = "ready"`
- `harvest.backend.capture_session.session_id`
- `debug.last_request_summary` session diagnostics
- `debug.last_response_summary` session diagnostics

`Start Collecting` now stops at:

- `phase = "session_verified"`
- `last_scanner_result = "session_ready"`

It does not proceed to item extraction in this phase.

## Duplicate session prevention

- If a verified local session exists, the extension reuses it and does not create a new session.
- If a local session id is stale, the extension discards it after failed verification and creates one fresh session.
- Repeated `Start Collecting` clicks reuse the verified session instead of creating duplicates.

Diagnostics added:

- `session_reused`
- `stale_session_discarded`
- `session_created_this_click`

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
