# Phase 22B — One-item Collect + Save Smoke Log

## Scope

Implemented Phase 22B only: Start Collecting now runs a developer-safe `one_item_smoke_test` path that selects one pending collect target, opens the detail/modal source, extracts real modal metrics, builds a clean finalized-only backend payload, saves through the existing Capture Inbox ingest endpoint, and verifies session item readback.

## Active Data Paths Confirmed

- Capture session create/reuse endpoint: `POST /douyin-extension/capture-session`.
- Item ingest endpoint/service: `POST /douyin-extension/full-modal-harvest`, handled by backend full-modal harvest ingest.
- Capture Inbox readback endpoint: `GET /douyin-extension/capture-sessions/{capture_session_id}/items`.
- Backend request envelope: `douyin_full_modal_harvest.v1` with `capture_session_id`, `started_at`, `page`, `capture_context`, `items`, `progress`, and `commit_policy`.
- Capture Inbox UI route was not changed.

## Implementation Notes

- `runStartCollectingWorkflow()` forces `collect_mode = one_item_smoke_test` and `batch_limit = 1`.
- `getFirstPendingCollectTarget(state)` returns one queue target with pending-like state and skips saved/complete/skipped/duplicate-like states.
- The one-item runner creates or reuses a capture session and records local diagnostics with `capture_session_source = scanner_collect` without sending that source in the ingest payload.
- Detail opening prefers an existing modal/source URL, then video URL/source URL, then a built video URL fallback.
- Required extracted fields are real modal metrics only: duration text/seconds plus like, comment, favorite, and share counts.
- `buildCaptureInboxItemPayload()` produces the existing full-modal harvest request envelope with `commit_policy = finalized_only`.
- `guardCaptureInboxPayload()` rejects disallowed/debug/secret-like keys, nested `capture_session_id`, `capture_session_source`, and missing required ids/metrics.
- Backend save is confirmed before queue state is marked saved/extracted; readback failure results in `saved_unverified` diagnostics.

## Backend Touch Status

No backend code was changed. Backend tests were not added for this phase because existing endpoints/services were reused unchanged.

## Validation So Far

- Focused `wholeProfileHarvest.test.ts` passed.
- Extension typecheck passed.
- Full extension test/build validation is still pending at this log point.
