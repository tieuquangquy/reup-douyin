# Phase 22B-2 Backend Session Proof + One-Item Ingest Resume

## Current Status

Phase 22B-2 implementation is complete for the extension path and has passing validation.

## Behavior Summary

Start Collecting now enters `one_item_backend_proof` mode. The controller verifies a local `capture_session_id` against the backend item readback endpoint before reuse. If the local ID is stale or missing, it creates a backend session and verifies that new session before opening a modal, extracting metrics, building a payload, or saving an item.

The save path remains exactly one item. It uses the existing full-modal harvest ingest endpoint and then verifies the saved aweme through the session item readback endpoint.

## Important Diagnostics

The one-item flow records:

- `collect_mode`
- `session_verify_url`
- `session_list_url`
- `session_create_url`
- `item_save_url`
- `session_local_id`
- `session_verify_status`
- `session_verify_response`
- `session_exists_in_backend`
- `session_create_status`
- `session_create_response`
- `session_verified`
- `session_id_verified`
- `backend_item_save_called`
- `backend_save_status`
- `backend_save_url`
- `backend_response_status`
- `backend_response_short`
- `backend_item_id`
- `backend_error_code`
- `backend_error_stage`
- `verify_items_status`
- `verify_items_count`
- `verify_aweme_found`
- `session_list_after_save_status`
- `session_list_after_save_count`
- `session_ribbon_captured_count`

## Validation Already Run

```bash
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Both passed. The test script also runs the extension build.

## Follow-Up Considerations

- A future phase can expose actual popup `api_base_url` / Capture Inbox web origin values directly through the controller runtime if UI-level origin mismatch diagnostics need to be exact rather than runtime consistency labels.
- A future phase can add a dedicated session-list readback call after save if the UI ribbon captured count must be verified from `GET /capture-inbox/sessions`; Phase 22B-2 uses item readback as the proof endpoint.
- No Capture Inbox frontend UI code was modified in this phase.
