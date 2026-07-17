# Reup Queue Lifecycle Log

## Purpose

This log captures the implementation plan and decisions for the Reup Queue lifecycle slice. The slice turns Reup Queue from a downstream holding list into an operator processing workspace while preserving the existing ingestion and review boundaries.

## Required Boundary Decisions

- Extension capture remains the primary ingestion path.
- Capture Inbox remains the raw/staging workspace.
- Review Board remains the canonical review surface backed by `VideoCandidate`.
- Reup Queue remains downstream of Review Board approval and is linked to existing `VideoCandidate` and `SourceVideo` records.
- This slice does not introduce a second review/candidate architecture.
- This slice does not implement automatic publish execution.
- API actions model explicit operator intent; approval does not create hidden processing side effects.

## Audit Findings

- `ReupQueueItem` already persists durable queue rows with candidate/source links, status, priority, timestamps, optional job/render/publish links, error fields, and metadata.
- Existing backend support is limited to list and enqueue from approved candidates.
- Existing Reup Queue UI groups items and shows details, but has no lifecycle mutation actions.
- Existing job infrastructure has durable job/step state, retry, resume, cancellation, and idempotency fields.
- Existing media infrastructure has `MediaAsset` and `RenderOutput`, but Reup Queue does not yet express media-prep readiness.
- Existing publish infrastructure is downstream and should remain untouched except for future-ready links.
- The web type currently expects list metadata as `total`, while the API returns `total_count`; this slice should normalize the contract.

## Implementation Plan

1. Define an explicit lifecycle action model for queue item transitions.
2. Add narrow media-prep handoff fields to Reup Queue without building a full media pipeline.
3. Add backend service methods for deterministic state transitions.
4. Add API schemas/routes for item detail and item actions.
5. Update web types/API client and Reup Queue UI with state-aware actions.
6. Add focused tests for transitions, action availability, media handoff, UI affordances, and existing enqueue behavior.
7. Verify Python tests, web tests, and TypeScript typecheck.

## Lifecycle States For This Slice

The existing enum remains the foundation:

- `READY_FOR_PROCESSING`
- `WAITING_FOR_MEDIA`
- `WAITING_FOR_METADATA`
- `PROCESSING`
- `READY_TO_EXPORT`
- `READY_TO_PUBLISH`
- `FAILED_NEEDS_ATTENTION`
- `COMPLETED`
- `CANCELLED`

This slice treats `READY_TO_EXPORT` as the clean terminal handoff point for media preparation. `READY_TO_PUBLISH` stays available for existing future-ready compatibility, but no publish automation is introduced.

## Operator Actions For This Slice

- `START_PROCESSING`: move eligible items into explicit processing.
- `MARK_MEDIA_READY`: record media-prep readiness and advance to metadata or export readiness.
- `MARK_BLOCKED`: record safe blocked reason and route to the correct waiting/failed state.
- `HOLD`: pause an active queue item with a reason.
- `RESUME`: return held/waiting work to processing or ready state.
- `RETRY`: clear failure context and return to processing readiness.
- `CANCEL`: stop downstream queue work.
- `MARK_COMPLETED`: close work after downstream completion is known.

## Current Verification Status

- Audit completed.
- Documentation created before implementation.
- Backend lifecycle implementation completed.
- Web Reup Queue lifecycle UI implementation completed.
- Media-prep handoff implemented as an explicit operator transition ending at `READY_TO_EXPORT`.
- Verification completed successfully:
  - `python -m unittest tests.test_reup_queue_service tests.test_douyin_extension_capture_service`
    - Result: 17 tests passed.
  - `npx tsx apps/web/src/test/reup-queue.test.ts`
    - Result: Reup Queue UI tests passed.
  - `npm run typecheck`
    - Result: TypeScript typecheck passed.
