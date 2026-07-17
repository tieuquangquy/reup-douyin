# Phase 22B-2 Backend Session Proof + One-Item Ingest Log

## Scope

Phase 22B-2 connects Start Collecting to the existing backend Capture Inbox session and item APIs without changing the Capture Inbox frontend UI.

## Implemented

- Added backend bridge support for `GET` requests while preserving the existing `REUP_DOUYIN_POST_BACKEND` runtime message.
- Changed extension Capture Inbox session item readback to call `GET /douyin-extension/capture-sessions/{capture_session_id}/items`.
- Added backend session proof before one-item collection:
  - verify an existing local `capture_session_id` before reuse;
  - ignore stale local IDs when backend readback fails;
  - create a backend Capture Inbox session when no verified backend session exists;
  - verify the created session before extraction or item save.
- Kept Phase 22B-1 modal-first behavior intact for profile-modal calibration by opening `profile_url_without_query + "?modal_id=" + aweme_id`.
- Saves exactly one item through `POST /douyin-extension/full-modal-harvest` only after backend session proof and payload guard success.
- Preserved the payload guard that rejects disallowed fields such as `capture_session_source`, `debug`, `diagnostics`, and nested secret/debug fields.
- Added Phase 22B-2 diagnostics for session proof, save/readback status, backend item ID, and readback item verification.

## Files Changed

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extensionBackendClient.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/extensionBackendClient.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

## Existing Backend APIs Used

- `POST /douyin-extension/capture-session`
- `GET /douyin-extension/capture-sessions/{capture_session_id}/items`
- `POST /douyin-extension/full-modal-harvest`
- `GET /capture-inbox/sessions` is recorded as a Capture Inbox session-list diagnostic path; the extension does not call it in this phase.

## Validation

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
```

The extension test command includes an extension build step. No backend files were changed, so backend validation was not required.

## Notes

- `api_base_url` and `capture_inbox_web_origin` are represented as extension/backend consistency diagnostics because the controller runtime does not currently expose popup-only DOM configuration values directly.
- `session_list_after_save_*` diagnostics are recorded as `not_called` / `null` because this phase verifies saved items through the existing item readback endpoint rather than adding an additional session-list call.
