# Phase 17X V2 Failure Diagnostics Log

## Why generic V2 failure was insufficient

The prior banner only showed a single generic failure outcome, which hid the exact break point in Whole Profile Staged Harvest V2. Operators could not distinguish preflight/session creation/payload/backend failures.

## New trace and diagnostics fields

`douyinWholeProfileStagedHarvestV2` now carries explicit diagnostics fields:

- `fail_stage`
- `fail_reason`
- `capture_session_status` (`missing|creating|ready|failed`)
- `capture_session_id`
- `capture_session_request_preview`
- `capture_session_response`
- `payload_preview`
- `flush_request_preview`
- `flush_response`
- `backend_status_code`
- `backend_error_code`
- `backend_error_stage`
- `backend_error_body`
- `last_successful_stage`
- `trace[]`

Trace event coverage added for:

- `preflight_started`
- `verified_queue_loaded`
- `calibration_resolved`
- `capture_session_create_started`
- `capture_session_create_success`
- `capture_session_create_failed`
- `target_open_started`
- `target_extract_success`
- `payload_built`
- `payload_contains_capture_session_id`
- `flush_started`
- `flush_success`
- `flush_failed`

## Session diagnostics behavior

- Session create request preview is persisted before/with create flow.
- Session create response is persisted.
- Missing `session_id` response hard-fails with `fail_stage=capture_session_create` and `fail_reason=capture_session_response_missing_session_id`.
- Hard precheck blocks target loop if capture session is not `ready` or session id missing:
  - `fail_stage=capture_session_preflight`
  - `fail_reason=capture_session_id_missing_before_target_loop`

## Payload diagnostics behavior

- Payload preview is persisted for each target.
- Payload validation blocks backend flush if `capture_session_id` is missing:
  - `fail_stage=payload_validation`
  - `fail_reason=payload_missing_capture_session_id`

## Backend response classification behavior

Flush failure classification now distinguishes:

- `capture_session_not_found` (with explicit V2 guidance text)
- `backend_schema_rejected`
- `finalized_metadata_required`
- `backend_network_error` (`backend_flush_failed: ...`)

Each failure persists backend diagnostics fields (`backend_status_code`, `backend_error_code`, `backend_error_stage`, `backend_error_body`) and records `flush_failed` trace.

## Verification runs

Executed:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅
- `cd apps/api && python -m compileall src scripts` ✅
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status` ❌ (existing backend secret-field rejection for `payload.capture_session_source` in multiple full-modal tests)

## Live retest steps

1. Run Verify queue for profile.
2. Run V2 staged harvest from popup.
3. If failed, inspect V2 panel fields (`fail_stage`, `fail_reason`, backend fields, payload checks) and `Debug JSON`.
4. Confirm trace contains ordered events through failing stage.
5. For session failures, verify `capture_session_request_preview` and `capture_session_response`.
6. For flush failures, verify backend classification (`capture_session_not_found` vs schema/finalized/network).
