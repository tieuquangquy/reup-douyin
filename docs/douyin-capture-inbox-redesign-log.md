# Douyin Capture Inbox Redesign Log

## Scope

Redesign Capture Inbox from a technical staging list into an operator-friendly staging workspace and add a Reup Queue after Review Board approval.

## Audited boundaries

- Extension current-page capture remains the ingestion path.
- Capture Session and Captured Item remain the staging persistence layer.
- Review Board remains backed by canonical VideoCandidate rows.
- Canonical downstream entities remain SourceProfile, SourceVideo, CrawlSession, VideoMetricSnapshot, and VideoCandidate.
- Reup Queue must reference canonical candidates/source videos and must not create a second review system.
- Publish Control and Publish Drafts remain downstream publish surfaces and should not be rewritten.

## Implementation plan

1. Add operator-oriented Capture Inbox projections: session summary, work buckets, item cards, item detail details.
2. Add durable Reup Queue persistence linked to VideoCandidate and SourceVideo.
3. Add API endpoints for listing queue items and enqueuing approved candidates.
4. Wire Review Board approval to queue creation without changing candidate review semantics.
5. Add web types/API client methods, Capture Inbox UX redesign, Reup Queue page, and navigation.
6. Add focused tests for UI copy, API contracts, and queue idempotency.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No automated publish implementation.
- No second candidate/review architecture.
- No raw secrets or private paths in logs/UI.
- No distributed worker runtime implementation in this slice.

## Work log

- 2026-04-27: Audited repository rules, Capture Inbox route/schema/service/UI, Review Board candidate flow, job model, publish-control queue patterns, and navigation structure.
- 2026-04-27: Decided to implement a narrow Reup Queue linked to canonical VideoCandidate and SourceVideo, with optional Job linkage for future worker execution.
- 2026-04-27: Added Reup Queue backend enum, SQLAlchemy model, Alembic migration, schemas, service, and FastAPI routes. Enqueue is idempotent by workspace/candidate and only accepts approved VideoCandidate rows.
- 2026-04-27: Redesigned Capture Inbox into an operator staging workspace with workflow copy, session summary/count reconciliation, grouped staging queues, next-action guidance, item detail drawer, and raw details behind disclosure panels.
- 2026-04-27: Added Reup Queue web types, API client methods, navigation, route, grouped queue page, queue detail drawer, and Review Board Send to Reup Queue transition controls.
- 2026-04-27: Added/updated focused tests for Capture Inbox source copy, Reup Queue UI, Review Board transition controls, navigation, and backend queue idempotency.

## Verification

- `python -m unittest tests.test_reup_queue_service tests.test_douyin_extension_capture_service` from `apps/api`: passed, 14 tests.
- `npx tsx apps/web/src/test/capture-inbox.test.ts`: passed.
- `npx tsx apps/web/src/test/reup-queue.test.ts`: passed.
- `npx tsx apps/web/src/test/review-board.test.ts`: passed.
- `npx tsx apps/web/src/test/route-nav.test.ts`: passed.
- `npm run typecheck`: passed.

## Current limitations

- Reup Queue is durable and operator-visible, but this slice does not start worker processing, rendering, export, or publish jobs automatically.
- Queue item lifecycle mutation actions such as retry, cancel, hold, mark completed, or attach jobs remain future work.
- Review Board queueing is explicit through Send to Reup Queue; approval itself does not create hidden queue side effects.
