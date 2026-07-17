# Backend 422 Diagnostic Capture

## Purpose

Phase 3C adds diagnostic-only capture for one-item `POST /douyin-extension/full-modal-harvest` failures that surface in the popup as `backend_schema_rejected`. Phase 3D exposes those already-redacted details in the popup through a focused copy action. Phase 3E separates true schema 422 responses from semantic capture-session 422 responses and prevents stale/wrong-profile capture session reuse before the flush.

The change is intended to answer one question: which backend 422 field or service-level code rejected the one-item flush? For Phase 3E, it also records why a local `capture_session_id` was reused or discarded.

## Scope

Changed extension files:

- [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts)
- [apps/extension-douyin-capture/src/types.ts](../../apps/extension-douyin-capture/src/types.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts)
- [apps/extension-douyin-capture/src/popup.ts](../../apps/extension-douyin-capture/src/popup.ts)
- [apps/extension-douyin-capture/public/popup.html](../../apps/extension-douyin-capture/public/popup.html)
- [apps/extension-douyin-capture/src/extensionBackendClient.test.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.test.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest.backendFlow.test.ts)
- [apps/extension-douyin-capture/src/popupWorkflow.test.ts](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts)

No backend schema, backend persistence, payload semantics, scanner, auto-scroll, calibration, queue, retry, or validation behavior was intentionally changed.

## Where diagnostics are captured

### Request shape

The one-item flush request summary is built in [apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts) and delegates to [apps/extension-douyin-capture/src/extensionBackendClient.ts](../../apps/extension-douyin-capture/src/extensionBackendClient.ts).

Captured request fields are shape-only and redacted:

- `schema_version`
- `capture_session_id_valid_uuid`
- shortened `capture_session_id`
- `item_count`
- first item keys after secret-like key filtering
- first item `aweme_id` presence
- first item `source_video_external_id` presence
- `duration_seconds` presence, type, and value category
- `source_url` presence
- `posted_at` presence, type, and parseability
- metric count fields presence/type for `like_count`, `comment_count`, `favorite_count`, and `share_count`
- `commit_policy`
- target/source identifier presence

Headers are intentionally omitted from the request summary.

### Response shape

Failed one-item saving paths now summarize backend responses into:

- `response_summary_status`
- `http_status`
- `backend_code`
- `backend_stage`
- `backend_message`
- `backend_detail`
- `validation_error_paths`
- `response_json_parse_status`
- `response_text_parse_status`
- `error_code`
- `retryable`
- redacted response body keys

The summary is stored on the harvest state in the same diagnostic surfaces already used by the popup:

- `state.harvest.backend.one_item_flush.response_summary`
- `state.harvest.last_backend_response`
- `state.debug.last_response_summary`

This makes the popup's Backend Flow detail row show `Last flush response: available in Details` after a one-item 422 failure.

## Redaction policy

Diagnostics must not store:

- cookies
- authorization headers
- auth tokens
- CSRF tokens
- credentials
- passwords
- API keys
- raw headers
- raw HTML
- raw DOM payloads
- the full raw request payload

The response diagnostic intentionally records validation locations but not raw Pydantic validation messages. This keeps field-level paths visible without storing arbitrary backend response text.

## Phase 3E capture session reuse rule

Start Collecting must not reuse a locally stored `capture_session_id` solely because that UUID exists in the backend. Local session reuse is allowed only after the backend session list proves the session belongs to the current normalized profile.

Accepted proof signals are:

- exact normalized submitted/profile/page URL match after query/hash removal, so `modal_id` does not create a false mismatch;
- matching `/user/<profile_identifier>` path;
- matching profile identifier in session metadata.

If the backend session exists but points to another profile, the extension discards it for the current run and creates a fresh session. Diagnostics include `stale_session_discarded: "yes"`, `stale_session_discard_reason: "profile_mismatch"`, a shortened stale session id, and `session_reuse_reason: "not_reused_profile_mismatch"`.

If the backend session record lacks enough profile fields to verify ownership, reuse fails closed. Diagnostics include `session_reuse_blocked_reason: "backend_session_profile_unverifiable"`, and the extension creates a fresh session without clearing calibration or the scan queue.

## Phase 3E backend 422 mapping

Semantic backend capture-session failures such as `detail.code: "capture_session_not_found"` with `detail.stage: "resolve_capture_session"` now surface as `capture_session_not_found` diagnostics instead of being collapsed into `http_422_schema_error`. Pydantic validation-array 422 responses continue to map to `http_422_schema_error` and continue to expose only redacted validation paths.

## Manual reproduction and evidence capture

1. Reload the extension build in Chrome.
2. Open the target Douyin profile.
3. Run Scan Profile.
4. Let auto-scroll complete enough to produce at least one queued target.
5. Click Start Collecting.
6. Wait for the one-item flush to fail with `backend_schema_rejected` if the issue reproduces.
7. Open the popup Advanced panel.
8. Open `Progress + Diagnostics`.
9. Open `Payload and save details`.
10. Confirm `Last flush request` is `available in Details`.
11. Confirm `Last flush response` is `available in Details`.
12. Click `Copy Backend Error Details`.
13. Paste the copied redacted JSON into the investigation note and inspect:
    - `last_flush_response_summary.http_status`
    - `last_flush_response_summary.backend_code`
    - `last_flush_response_summary.backend_stage`
    - `last_flush_response_summary.backend_message` or `last_flush_response_summary.backend_detail`
    - `last_flush_response_summary.validation_error_paths`
    - `last_flush_response_summary.response_json_parse_status`
    - request `duration_seconds_*` fields under `last_flush_request_summary`
    - request `posted_at_*` fields under `last_flush_request_summary`
    - request `capture_session_id_valid_uuid` under `last_flush_request_summary`
    - request `metric_count_fields` under `last_flush_request_summary`

The popup also renders the same short redacted JSON in a copyable preview block below the button. This UI is diagnostic-only and does not change the request payload or backend behavior.

## Interpreting common outcomes

- `validation_error_paths` populated with paths such as `body.items.0...` means FastAPI/Pydantic rejected the request before or during request model parsing.
- `backend_code` with a service code such as `finalized_metadata_required` means the backend route received the body and rejected it at service validation time.
- `backend_code: capture_session_not_found` plus `backend_stage: resolve_capture_session` means backend session resolution rejected the explicit session, usually because the session is missing or profile-mismatched. Phase 3E should prevent the stale/wrong-profile local reuse variant by creating a fresh profile-safe session before flushing.
- `capture_session_id_valid_uuid: false` points to session handoff/session ID shape as a likely issue.
- `duration_seconds_value_category: non_numeric`, `zero`, or `negative` points to duration normalization as a likely issue.
- `posted_at_parseable: false` points to date/time normalization as a likely issue.

## Follow-up rule

Use the captured redacted evidence before changing schemas or payload construction. Any later fix should be a separate targeted phase with one diagnosed cause, not a speculative schema-loosening change.
