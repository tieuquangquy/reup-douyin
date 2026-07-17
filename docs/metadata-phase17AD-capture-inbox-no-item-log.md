# Phase 17AD Log — Capture Inbox no-item after V2 session

## Scope
Phase 17AD only: trace and fix Capture Inbox no-item issue after Whole Profile Staged Harvest V2 session creation.

## Root-cause trace (A/B/C/D)
- A) Finalized flush not executed: **Not primary** in reproduced failing path; flush request reached backend.
- B) Full-modal accepted but no item create/update: **Primary gap**. Backend could return success-like payload while `item_created_or_updated=false` and missing `capture_inbox_item_id`.
- C) Item exists but session-item API not returning: **Addressed** by dedicated endpoint and explicit counts payload.
- D) UI fetched but filters hid items: **Addressed** with explicit loaded-vs-hidden diagnostics and endpoint source hint.

## Implemented changes

### API
- Added session items endpoint and debug endpoint:
  - `GET /douyin-extension/capture-sessions/{capture_session_id}/items`
  - `GET /douyin-extension/capture-sessions/{capture_session_id}/debug`
- Added response schemas for session-counts, items-by-session, and debug events.
- Tightened full-modal ingest semantics in service:
  - strict response fields: `code`, `stage`, `reason`, `capture_session_resolved_by`, `aweme_id`
  - response `success` no longer implies success if no item was created/updated
  - emits `last_ingest_events` metadata for latest ingest outcomes

### Extension (V2 staged harvest)
- In direct flush path, if backend response has no `capture_inbox_item_id` OR `item_created_or_updated !== true`, mark target failed with `capture_inbox_item_not_created`.
- Preserve traceability in failure event details (`backend_code`, `backend_stage`, `backend_reason`).

### Web Capture Inbox
- Open session flow now hydrates items from the new extension-session items endpoint.
- Session empty-state now surfaces endpoint source and keeps explicit diagnostics context.

## Verification
- API:
  - `python -m unittest tests.test_douyin_extension_routes tests.test_douyin_extension_capture_service` ✅
- Extension:
  - `npm run test` ✅
- Web:
  - `npx tsx src/test/capture-inbox.test.ts` ✅

## Notes
- Changes are scoped to Phase 17AD and keep local-first architecture boundaries intact.
- No crawler/processing scope expansion introduced.
