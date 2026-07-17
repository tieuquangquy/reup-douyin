# Phase 3I Capture Inbox Reconciliation and Payload Sanitizer

## Scope

Phase 3I fixes the remaining `Collecting videos` issues observed after Phase 3H manual validation:

- Capture Inbox already had more same-profile captured/ready items than the extension counted after Scan Profile.
- The fourth one-item collect attempt was blocked locally before backend submission by guard-visible legacy/raw metric paths under `raw_dom_detail_metrics`.

This phase intentionally does not change scanner discovery, auto-scroll, profile discovery, backend validation, `/douyin-extension/full-modal-harvest` schema semantics, calibration state, queue reset scope, pending item state, current-index handling, or Phase 3E profile-safe capture-session verification.

## Root causes

### Reconciliation count mismatch

Phase 3H reconciliation was session-safe but too narrow for the observed backend data. It counted items only from sessions whose session-level fields proved the current profile. Manual validation showed Capture Inbox could contain same-profile captured/ready items in listed sessions where session-level profile proof was missing or incomplete.

The backend APIs available to the extension remain session-oriented:

- `runtime.listCaptureSessions()` lists Capture Inbox sessions.
- `runtime.listCaptureSessionItems(captureSessionId)` lists items for one explicit session.

There is no existing profile-level Capture Inbox item query available to the extension without changing backend API semantics.

### Local payload guard rejection

The backend full-modal schema requires finalized metric fields under `raw_dom_detail_metrics`. Backend ingestion also reads `payload.raw_dom_detail_metrics` to decide whether a modal payload is finalized and to normalize item metadata.

Therefore Phase 3I could not remove `raw_dom_detail_metrics` itself without changing `/douyin-extension/full-modal-harvest` schema semantics. The safe fix is to build a clean backend DTO before local guards, normalize legacy aliases, strip unsupported/debug/raw fields, and preserve schema-required finalized metric fields.

## Reconciliation behavior

After Scan Profile builds the canonical queue, the extension performs non-blocking backend reconciliation against listed Capture Inbox sessions.

Data sources:

- `runtime.listCaptureSessions()`.
- `runtime.listCaptureSessionItems(captureSessionId)` for sessions that are eligible for inspection.

Session handling:

- Sessions with explicit matching current-profile proof are fully eligible.
- Sessions with explicit mismatching profile proof are skipped.
- Sessions with missing/unverifiable session-level profile proof may be inspected, but only item records that prove the current profile are counted.

Profile proof keys:

- Session-level normalized profile URL from `submitted_profile_url`, `page_url`, `metadata_json`, `diagnostics_json`, `raw_summary_json`, or `result_summary_json`.
- Session-level profile identifier from `normalized_profile_identifier` or equivalent metadata/summary fields.
- Item-level profile URL from `profile_url`, `metadata_json.profile_url`, or `raw_payload_json.profile_url`.
- Item-level profile identifier from `source_profile_external_id`, `metadata_json.source_profile_external_id`, `metadata_json.normalized_profile_identifier`, or `raw_payload_json.source_profile_external_id`.

Item match keys:

- Preferred queue match key: `aweme_id`.
- Backend item fallbacks for deriving an aweme id: `source_video_external_id`, `video_external_id`, and `external_id`.

Count behavior:

- Backend items with a same-profile proof and matching queue aweme id mark the queue item as `already_collected` / complete.
- Same-profile backend items not present in the scanned queue are counted in diagnostics as unmatched backend items.
- Scanned queue items without backend matches remain pending/actionable.
- Backend lookup failure remains non-blocking and does not fail Scan Profile.

Expected manual count after the reported scenario:

- If Capture Inbox has 15 same-profile captured/ready backend items and the scanned queue has 110 items, the extension should report approximately 15 already collected and approximately 95 new/pending, subject to exact scan membership and duplicate aweme ids.

## Reconciliation diagnostics

Phase 3I adds redacted diagnostics so manual validation can distinguish data-source coverage from matching failures:

- `backend_reconciliation_status`
- `backend_reconciliation_source`
- `backend_reconciliation_profile_scope`
- `backend_reconciliation_profile_identifier`
- `backend_reconciliation_listed_session_count`
- `backend_reconciliation_total_session_count`
- `backend_reconciliation_session_count`
- `backend_reconciliation_item_count`
- `backend_reconciliation_backend_count`
- `backend_reconciliation_matched_count`
- `backend_reconciliation_unmatched_backend_count`
- `backend_reconciliation_unmatched_queue_count`
- `backend_reconciliation_unmatched_count`
- `backend_reconciliation_match_key`

These fields do not include raw DOM, cookies, tokens, credentials, request headers, or full private local paths.

## Payload sanitizer behavior

The one-item collect path now builds and records sanitizer diagnostics for the clean Capture Inbox payload before running local guards and before attempting the backend request.

Preserved schema-required fields:

- `raw_dom_detail_metrics.duration_seconds`
- `raw_dom_detail_metrics.duration_text`
- `raw_dom_detail_metrics.like_count`
- `raw_dom_detail_metrics.comment_count`
- `raw_dom_detail_metrics.favorite_count`
- `raw_dom_detail_metrics.share_count`
- `raw_dom_detail_metrics.extraction_source`
- `raw_dom_detail_metrics.confidence`

Normalized legacy alias:

- `raw_dom_detail_metrics.duration` is mapped to schema-required `raw_dom_detail_metrics.duration_seconds` when `duration_seconds` is absent.

Stripped/blocked classes:

- Unsupported top-level fields such as `diagnostics`, `debug`, `state`, `runtime`, and `capture_session_source` are not included in the clean DTO.
- Raw/debug/leaky nested keys continue to be removed by the sanitizer and blocked by existing guards.
- Sanitizer diagnostics record paths and reasons only, not raw values.

Guard ordering:

1. Build the full-modal Capture Inbox payload from extracted modal evidence.
2. Build a clean DTO and collect sanitizer diagnostics.
3. Run `guardNoSecretDebugLeakage`.
4. Run `guardCaptureInboxPayload`, including canonical allowed-field checks and required Capture Inbox fields.
5. Run the backend client guard for `/douyin-extension/full-modal-harvest`.
6. Submit to the backend only if all guards pass.

No guard was weakened or bypassed.

## One-item collect diagnostics

The scanner diagnostics now include redacted payload sanitizer summary fields:

- `payload_sanitized_removed_disallowed_fields_count`
- `payload_sanitized_removed_disallowed_field_names`

These diagnostics are intended to confirm that legacy/raw aliases were handled before local guard evaluation without logging the underlying metric values.

## Pause / Resume preservation

Phase 3I does not alter the Phase 3H Pause/Resume state model:

- A valid paused collect run keeps `resume_available: true` and can resume from its checkpoint.
- Stale paused state without a resumable checkpoint is recovered safely.
- Queue, calibration, backend session state, current aweme, pending items, and current index are not cleared by sanitizer or reconciliation changes.
- Resume continues through the same canonical collection and Phase 3E session-verification path after sanitizer success.

## Tests

Focused coverage was added/updated for:

- Phase 3I reconciliation diagnostics in the whole-profile controller source checks.
- Item-level same-profile fallback for otherwise unverifiable Capture Inbox sessions.
- Payload sanitizer diagnostics in the one-item collect path.
- Clean payload builder preservation of schema-required metric counts.
- Legacy `raw_dom_detail_metrics.duration` alias mapping to `duration_seconds` without logging raw values.

## Manual validation checklist

After loading the built extension:

1. Preserve calibration and reset only the current run if needed.
2. Scan/Refresh the same profile that has known Capture Inbox captured/ready items.
3. Confirm `Already collected` reflects same-profile backend items across listed sessions, including the previously missing backend items.
4. Confirm `New` / pending count is the scanned queue count minus already collected matches, allowing for exact scan membership.
5. Start/Continue Collecting.
6. Confirm the previously blocked fourth item now reaches the backend when finalized metrics are present.
7. Confirm local diagnostics show sanitizer field names/counts but no raw metric values, raw DOM, cookies, tokens, or headers.
8. Click Pause only during active collection and confirm a valid paused state exposes Resume.
9. Resume and confirm collection continues from the checkpoint instead of clearing queue/session/calibration/current target state.
