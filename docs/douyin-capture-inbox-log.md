# Douyin Capture Inbox Log

## 2026-04-27

### Request

Implement the long-term Douyin extension ingestion architecture based on Capture Sessions, Capture Inbox, Enrichment, and Promotion-to-Review. Raw extension captures must not be pushed directly into the Review Board.

### Audit Completed So Far

- Read repository working rules in `AGENTS.md`.
- Audited extension capture schemas and endpoint.
- Audited current extension capture service and found direct canonical ingest plus candidate evaluation.
- Audited canonical downstream models: `SourceProfile`, `CrawlSession`, `SourceVideo`, `VideoMetricSnapshot`, and `VideoCandidate`.
- Audited Review Board backend boundary: `/candidates` lists persisted `VideoCandidate` rows.
- Audited SQLAlchemy/Alembic conventions for adding models and migrations.
- Audited web API client and navigation route conventions.
- Audited extension payload TypeScript shape.

### Key Finding

Current `capture_current_page` immediately calls source ingest and candidate evaluation. This is the direct-to-review shortcut that must be replaced by a staging-first Capture Inbox flow.

### Planned Scope

- Add Capture Session and Captured Item persistence.
- Keep the existing extension endpoint working.
- Change extension capture response to point to Capture Inbox.
- Add API endpoints for listing sessions/items and manual actions.
- Add lightweight synchronous enrichment/readiness handling.
- Add promotion that uses the existing canonical source ingest and candidate evaluation services.
- Add Capture Inbox UI under Ops Console.
- Add tests proving raw capture does not immediately create Review Board candidates.

### Explicit Non-Goals

- No crawler implementation.
- No distributed queue implementation.
- No alternate Review Board or alternate candidate table.
- No external Douyin live dependency in tests.
- No broad rewrite of unrelated intake/account flows.

### Implementation Completed

- Added persisted Capture Inbox storage with `capture_sessions` and `captured_items` plus status enums.
- Changed `POST /douyin-extension/capture-current-page` to stage extension captures instead of directly applying canonical ingest/candidate evaluation.
- Added Capture Inbox API endpoints for sessions, items, and manual actions.
- Added enrichment/readiness logic for video id, profile id, source URL, duplicate key, preview readiness, and honest unknown states.
- Added promotion that reuses canonical `SourceIngestService` and `CandidateEvaluationService` so Review Board remains backed only by promoted `VideoCandidate` rows.
- Added Ops Console Capture Inbox UI at `/ops/extensions/douyin/capture-inbox` with reconciliation metrics, staged item table, and manual actions.
- Updated extension manager capture result copy to point operators to Capture Inbox and show staged counts.
- Added API and web tests for staging-first behavior, canonical promotion, route/navigation, UI actions, and Review Board boundary copy.

### Verification Results

- `python -m pytest tests/test_douyin_extension_capture_service.py` could not run because the active Python environment does not have `pytest` installed.
- `python -m unittest tests.test_douyin_extension_capture_service` passed: 6 tests.
- `npm run typecheck --workspace apps/web` passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/route-nav.test.ts && npx tsx apps/web/src/test/douyin-extension-manager-ux.test.ts` passed.
