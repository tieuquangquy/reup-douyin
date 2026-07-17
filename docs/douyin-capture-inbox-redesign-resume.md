# Douyin Capture Inbox Redesign Resume

## Current task

Redesign the Douyin Capture Inbox into an operator-friendly staging workspace and connect it to a Reup Queue so the workflow is:

Capture Inbox -> Review Board -> Reup Queue -> Publish/Export.

## Key decisions

- Capture Inbox remains the staging layer for extension captures.
- Review Board remains the review decision layer for canonical VideoCandidate records.
- Reup Queue is a downstream work queue for approved canonical candidates, not another review board.
- Queue rows should be idempotent by workspace and video candidate.
- Queue items should expose operator buckets such as ready for processing, waiting for media, waiting for metadata prep, ready to export/publish, failed/needs attention, and completed.
- Technical raw diagnostics should be available in detail panels, not dominate the main Capture Inbox list.

## Files expected to change

- apps/api/src/enums/__init__.py
- apps/api/src/models/reup_queue.py
- apps/api/src/models/__init__.py
- apps/api/src/schemas/reup_queue.py
- apps/api/src/services/reup_queue_service.py
- apps/api/src/api/routes/reup_queue.py
- apps/api/src/main.py
- apps/api/src/api/routes/candidates.py
- apps/api/src/schemas/candidates.py
- apps/api/src/services/candidate_service.py
- apps/api/alembic/versions/0022_reup_queue.py
- apps/web/src/types/capture-inbox.ts
- apps/web/src/types/reup-queue.ts
- apps/web/src/types/review-board.ts
- apps/web/src/lib/api.ts
- apps/web/src/components/capture-inbox/CaptureInboxPage.tsx
- apps/web/src/components/reup-queue/ReupQueuePage.tsx
- apps/web/src/components/review-board/ReviewBoardPage.tsx
- apps/web/src/app/reup-queue/page.tsx or apps/web/src/app/ops/reup-queue/page.tsx
- apps/web/src/lib/navigationConfig.ts
- apps/web/src/test/capture-inbox.test.ts
- apps/web/src/test/review-board.test.ts
- New focused API test for Reup Queue service.

## Verification to run

- python -m pytest tests/test_reup_queue_service.py tests/test_douyin_extension_capture_service.py
- npm run typecheck
- npx tsx apps/web/src/test/capture-inbox.test.ts
- npx tsx apps/web/src/test/review-board.test.ts
- npx tsx apps/web/src/test/route-nav.test.ts

## Risks

- Existing test DB fixtures may require migration awareness if a new table is added.
- Review Board source tests may assert specific strings and need minimal, scoped updates.
- Reup Queue should not create real processing jobs until the operator explicitly starts processing or a future worker is introduced.
