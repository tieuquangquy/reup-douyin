# Capture Inbox Metrics + Filter Backend Resume

## Task
Implement backend/data/API wiring so Capture Inbox supports metrics visibility and advanced backend filtering aligned with `/intake` schema semantics.

## Current Status
Audit complete. Docs-first artifacts created.

## Completed
- Re-read repository constraints in [`AGENTS.md`](AGENTS.md:1).
- Audited intake schema source in [`intake.py`](apps/api/src/schemas/intake.py:12) and [`candidates.py`](apps/api/src/schemas/candidates.py:10).
- Audited Capture Inbox API/service in [`capture_inbox.py`](apps/api/src/api/routes/capture_inbox.py:81) and [`capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py:494).
- Confirmed staged metric normalization in [`_build_item()`](apps/api/src/services/capture_inbox_service.py:687) and response hydration in [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:88).
- Created:
  - `docs/capture-inbox-metrics-filter-backend-log.md`
  - `docs/capture-inbox-metrics-filter-backend-architecture.md`
  - `docs/capture-inbox-metrics-filter-backend-resume.md`

## Next Steps
Completed for this scoped task.

## Final Changed Files
- [`apps/api/src/schemas/capture_inbox.py`](apps/api/src/schemas/capture_inbox.py)
- [`apps/api/src/services/capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py)
- [`apps/api/src/api/routes/capture_inbox.py`](apps/api/src/api/routes/capture_inbox.py)
- [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py)
- [`apps/web/src/types/capture-inbox.ts`](apps/web/src/types/capture-inbox.ts)
- [`apps/web/src/lib/api.ts`](apps/web/src/lib/api.ts)

## Verification Summary
- Web: `npm run -w apps/web typecheck` ✅
- API tests: `python -m unittest tests.test_douyin_extension_capture_service -q` (run from [`apps/api`](apps/api)) ✅

## Scope Constraints
- Filter logic remains backend/API source of truth.
- Raw staged items are preserved (filtering is query-time only).
- No frontend redesign was introduced.
- No extension-side filtering was introduced.
