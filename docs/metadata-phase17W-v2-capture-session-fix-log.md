# Phase 17W V2 Capture Session Fix Log

## Scope

Phase 17W fixes `capture_session_not_found` for Whole Profile Staged Harvest V2 without reconnecting V2 to legacy Smart Capture or `capture-current-page`.

## Root Cause

Phase 17V intentionally isolated Whole Profile Staged Harvest V2 from the legacy Harvest and Smart Capture runtimes. The backend full-modal harvest ingest still resolved a `CaptureSession` from either an explicit legacy session id or the latest legacy Douyin Capture Inbox session. Because V2 no longer creates that legacy session, finalized-only writes could fail at `resolve_capture_session` with `capture_session_not_found`.

## Backend Changes

- Added `POST /douyin-extension/capture-session` for V2 session preflight.
- Added `DouyinExtensionCaptureSessionRequest` and `DouyinExtensionCaptureSessionResponse` schemas.
- Created zero-item `CaptureSession` rows with deterministic `capture_id = whole_profile_staged_harvest_v2:{run_id}`.
- Made V2 session creation idempotent by resolving an existing session by V2 source plus `run_id`.
- Extended full-modal harvest request schema with explicit V2 session/run/profile/target metadata.
- Updated full-modal session resolution order:
  1. explicit `capture_session_id`, validated against source/profile when supplied;
  2. V2 fallback by `capture_session_source == whole_profile_staged_harvest_v2` plus `run_id`;
  3. legacy latest-session fallback.

## Extension Changes

- Whole Profile Staged Harvest V2 now creates the isolated Capture Inbox session after verified queue/calibration preflight and before opening target 1.
- V2 state persists `capture_session_id`, `capture_session_source`, `capture_session_created`, `capture_session_status`, and `capture_session_error`.
- If session creation fails, V2 marks the run failed with `capture_session_create_failed`, does not open a target, and does not call full-modal harvest.
- Finalized payloads include explicit session metadata, `run_id`, `profile_url`, `target_aweme_id`, and `source_video_external_id`.
- Missing backend session failures are classified as `capture_session_not_found` with V2-specific operator guidance instead of generic `backend_schema_rejected`.
- Popup V2 status now displays capture session status, short session id, and source.

## Tests And Verification

Added/updated tests for:

- V2 route registration and request acceptance.
- V2 zero-item session preflight and idempotency.
- explicit V2 session resolution and missing explicit session rejection.
- V2 run-id fallback before legacy latest-session fallback.
- extension source-level V2 isolation, isolated capture-session creation, finalized payload session metadata, and error classification.

Verification performed:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture exec tsx src/modalWholeProfileTest.test.ts`
- `python -m py_compile apps/api/src/schemas/douyin_extension.py apps/api/src/api/routes/douyin_extension.py apps/api/src/services/douyin_extension_capture_service.py apps/api/tests/test_douyin_extension_routes.py apps/api/tests/test_douyin_extension_capture_service.py`

Backend `pytest` was attempted but blocked because the active Python interpreter has no `pytest` module installed.
