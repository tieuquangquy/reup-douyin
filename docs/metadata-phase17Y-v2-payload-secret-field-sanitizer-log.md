# Phase 17Y Log — Whole Profile Staged Harvest V2 Payload Secret-Field Sanitizer

## Scope
Phase 17Y only: fix V2 Whole Profile staged harvest backend 422 `extension_payload_contains_secret_field` caused by outbound payload containing `capture_session_source`.

## Root Cause
The V2 flush request body for `/douyin-extension/full-modal-harvest` was still carrying `capture_session_source` in the backend payload envelope/diagnostics path. Backend secret-field validation rejects secret-like fields and returned 422 with `extension_payload_contains_secret_field`.

## Changes Implemented

### 1) Sanitize before flush
Added sanitizer in popup V2 path:
- `sanitizeWholeProfileFullModalPayloadV2(payload)`
- Removes disallowed fields from outbound backend payload, including `capture_session_source` and secret-like key patterns.
- Returns `{ payload, removedFields }` for diagnostics.

### 2) Preflight disallowed-field assertion
Added:
- `assertNoDisallowedPayloadFields(payload)`
- Executed after sanitize and before backend flush.
- If any disallowed field remains, run is blocked locally and classified as:
  - `fail_stage=payload_validation`
  - `fail_reason=payload_contains_disallowed_field`

### 3) Backend payload contract correction
Updated V2 finalized request builder so backend payload no longer includes `capture_session_source`.
`capture_session_source` remains local-only runtime/UI diagnostic state.

### 4) Failure classification mapping
Updated V2 error classification so backend secret-field rejection maps to explicit local classification:
- backend code/message patterns:
  - `extension_payload_contains_secret_field`
  - `payload_contains_disallowed_field`
  - `capture_session_source`
- mapped to local:
  - `payload_contains_disallowed_field`

### 5) UI diagnostics updates
V2 panel diagnostics now include:
- whether payload contains `capture_session_source` (expected false)
- list of sanitized removed fields

### 6) Test updates
Updated source-based extension assertions to enforce new contract:
- no `capture_session_source` in backend V2 payload build
- sanitizer invoked before flush
- disallowed preflight assertion present
- explicit disallowed-field classification string present

## Files Touched
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`

## Validation Snapshot
- Extension test suite: pass
- Extension build (within test pipeline): pass

## Notes
- API code was not changed for Phase 17Y; issue resolved at extension request-shaping boundary.
- Change preserves local-first diagnostics while enforcing backend-safe payload contract.