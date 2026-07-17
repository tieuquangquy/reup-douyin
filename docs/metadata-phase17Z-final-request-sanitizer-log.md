# Phase 17Z Log — Final Request Body Sanitizer for V2 Full-Modal Flush

## 1) Root cause
The V2 UI was showing a sanitized payload preview, but that preview was not guaranteed to be the exact body sent to [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts:1422). As a result, disallowed fields (specifically `payload.capture_session_source`) could still reach backend even when preview diagnostics said sanitized.

## 2) Final-boundary sanitizer
Implemented final-boundary sanitization at flush time in [`flushWholeProfileFinalizedPayloadV2()`](apps/extension-douyin-capture/src/popup.ts:1422):
- clone exact request object into `finalRequestBodyBeforeSanitize`
- sanitize this exact object via [`sanitizeFinalFullModalHarvestRequestBodyV2()`](apps/extension-douyin-capture/src/popup.ts:1681)
- only send sanitized `finalBody` to backend

## 3) Deep removed_paths behavior
Added recursive deep sanitizer/inspector:
- [`sanitizeFinalFullModalHarvestRequestBodyV2()`](apps/extension-douyin-capture/src/popup.ts:1681)
- [`findDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1661)

It removes disallowed fields at any nested path and records `removed_paths` such as:
- `payload.capture_session_source`
- `items[0].payload.capture_session_source`

## 4) Local assertion before fetch
Immediately after sanitize in [`flushWholeProfileFinalizedPayloadV2()`](apps/extension-douyin-capture/src/popup.ts:1422):
- run deep assertion with [`findDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1661)
- if any path remains: throw local error and block backend call
- classified upstream as `payload_contains_disallowed_field_local`

Backend-returned secret-field rejection remains classified as `payload_contains_disallowed_field_backend`.

## 5) UI/diagnostics switched to final-body truth
V2 state/summary now tracks final request body diagnostics (not preview-only):
- `final_request_body_before_sanitize_preview`
- `final_request_body_preview`
- `final_request_removed_fields`
- `final_request_has_capture_session_source`
- `final_request_has_capture_session_id`

Rendered in [`renderWholeProfileStagedHarvestV2()`](apps/extension-douyin-capture/src/popup.ts:1426).

## 6) Scope and boundaries
Changed only extension-side V2 flow and tests/docs:
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts)
- this log + resume doc

No scanner/calibration/dry-run behavior changed.

## 7) Tests run
Executed:
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## 8) Result
All above commands passed after updating source assertions in [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts:334) for final-body sanitize flow.

## 9) Live retest guidance
1. Reload extension build from [`apps/extension-douyin-capture/dist`](apps/extension-douyin-capture/dist).
2. Run V2 staged harvest on a known profile target queue.
3. In V2 panel, verify:
   - `Final request has capture_session_source: false`
   - `Final request removed fields` includes path when present
4. Confirm no backend 422 `extension_payload_contains_secret_field` appears for V2 flush.
