# Douyin Network-First Pipeline Fix Resume

## Current task

Implement a generic network-first hardening pass for Douyin visible profile-grid captures after the user authorized proceeding without real one-item evidence.

## Evidence status

No accessible real evidence is available. The user explicitly authorized a generic architecture/code fix based only on high-level symptoms. Do not present any result as validated against a real HAR or real API payload.

## Completed before implementation

- Re-read repository rules.
- Confirmed evidence limitation.
- Audited extension, backend, and frontend pipeline paths.
- Identified status-model conflation and portrait-thumbnail rendering as scoped fixes.

## Implementation checklist

1. Extension - completed
   - Added canonical status fields to the payload contract.
   - Preserved network-first extraction for content-script capture.
   - Labeled direct fallback as DOM fallback and emitted truthful missing/network diagnostics.
   - Added poster aspect ratio metadata for profile-grid thumbnails.
2. Backend - completed
   - Accepted new fields from the extension.
   - Derived canonical preview, source-link, and media-asset statuses.
   - Exposed response fields used by the frontend.
   - Logged safe status counts.
3. Frontend - completed
   - Added response types for canonical fields.
   - Replaced single media status rendering with source-link and media-asset rendering.
   - Kept canonical fields first for thumbnail, duration, posted, and metrics.
   - Rendered portrait posters without a 16:9 crop.
4. Tests - completed
   - Updated extension tests for the new status model.
   - Updated API tests for backend normalization and response hydration.
   - Updated web tests for resolver and UI semantics.
5. Verification - completed
   - Passed targeted package tests and type checks listed below.

## Verification results

- Passed: `npm --prefix apps/extension-douyin-capture test`.
- Passed: `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts` from `apps/web`.
- Passed: `npm --prefix apps/web run typecheck`.
- Passed: `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- Environment note: `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py` could not run because `pytest` is not installed in the active Python environment; the equivalent `unittest` command passed.
- Invocation note: `npm --prefix apps/web run test -- capture-inbox.test.ts capture-inbox-canonical.test.ts` runs the full web test script with appended arguments and triggered an unrelated duplicated path lookup before the targeted tests; the targeted Capture Inbox tests passed from `apps/web`.

## Important constraints

- Keep code scoped to Capture Inbox/Douyin extension capture.
- Do not introduce new infrastructure dependencies.
- Do not log secrets, cookies, tokens, full private paths, or raw evidence blobs.
- Keep local-first behavior compatible with future SaaS-ready boundaries.
