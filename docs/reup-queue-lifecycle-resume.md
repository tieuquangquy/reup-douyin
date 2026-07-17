# Reup Queue Lifecycle Resume

## Resume Point

The Reup Queue lifecycle slice is implemented and verified. Continue future work from the explicit lifecycle/action/media-prep handoff model added in this slice; do not assume automatic publishing, full media processing, or queue-worker execution exists yet.

## Completed

- Read repository rules in `AGENTS.md`.
- Audited existing Reup Queue backend model, service, route, schema, UI, web types, and tests.
- Audited reusable job state-machine patterns and existing media/publish models.
- Created this lifecycle documentation set before code changes.
- Added lifecycle and media-prep fields to `ReupQueueItem`.
- Added explicit operator actions and state-aware transition validation.
- Added item detail and action API endpoints.
- Updated Reup Queue web types, API client functions, grouping/detail UI, and operator action buttons.
- Added backend and web source tests for lifecycle actions and media-prep handoff.
- Verified Python tests, Reup Queue UI source test, and TypeScript typecheck.

## Implementation Direction

The slice should implement a narrow operator-driven lifecycle around the existing `ReupQueueItem` model:

- Keep existing `ReupQueueStatus` values.
- Add explicit operator action requests and deterministic transition handling.
- Add media-prep handoff metadata on queue items rather than introducing a second media workflow system.
- End the media-prep handoff at `READY_TO_EXPORT` for this slice.
- Keep publish automation out of scope.

## Implemented Backend Changes

- Extend `ReupQueueItem` with safe lifecycle/media-prep fields.
- Add Alembic migration after the existing `0022_reup_queue` revision.
- Add schemas for action requests/responses and available action summaries.
- Add service methods for item lookup, transition validation, action execution, next-action guidance, and action availability.
- Add route for item detail and route for action execution.
- Keep enqueue idempotent and approval-only.

## Implemented Web Changes

- Extend Reup Queue TypeScript types.
- Add API client functions for detail/action endpoints.
- Update Reup Queue page with state-aware operator buttons.
- Show media-prep readiness, blocked/failed reasons, hold/cancel/completion timestamps, and honest unknown values.
- Preserve source opening and downstream editor links.
- Normalize list response metadata so UI does not rely on a mismatched `total`/`total_count` contract.

## Verification Completed

- `python -m unittest tests.test_reup_queue_service tests.test_douyin_extension_capture_service`
  - Result: 17 tests passed.
- `npx tsx apps/web/src/test/reup-queue.test.ts`
  - Result: Reup Queue UI tests passed.
- `npm run typecheck`
  - Result: TypeScript typecheck passed.

## Non-Goals To Preserve

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering implementation.
- No full queue worker implementation.
- No publish automation.
- No new candidate/review system.
- No raw secrets or private local paths in UI/logs.
