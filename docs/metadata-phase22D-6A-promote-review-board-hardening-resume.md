# Phase 22D-6A Promote to Review Board Hardening Resume

## Scope Completed

Phase 22D-6A hardened the existing Promote -> Review Board handoff only. No new Review Board module, UI redesign, crawler change, auto-promote path, Reup Score formula change, or backend deletion behavior was added.

## Files Changed

- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-6A-promote-review-board-hardening-log.md`
- `docs/metadata-phase22D-6A-promote-review-board-hardening-resume.md`

## Existing Promote Audit

- Individual Promote: `contextualActions()` -> `MediaTile` -> `TileActionGrid` -> `runAction("promote_now")` -> `runCaptureInboxAction()`.
- Bulk Promote: `BatchActionBar` -> `BulkActionConfirmationDialog` -> `confirmBulkAction()` maps to `promote_now` -> same `runAction()` path.
- Backend route: `POST /capture-inbox/sessions/{capture_session_id}/actions`.
- Backend service: `CaptureInboxService.promote(...)`.
- Review Board entity: `VideoCandidate` table `video_candidates`, created/updated via `CandidateEvaluationService.apply()` after canonical source ingest.
- Duplicate prevention: canonical `SourceVideo` uniqueness by platform/external ID, `VideoCandidate.source_video_id` uniqueness, and new explicit duplicate sync before promotion.

## Handoff Contract

The promotion adapter payload now carries available identity, content, performance, and status fields, including `capture_item_id`, `capture_session_id`, `source_video_external_id`, `source_url`, `video_url`, `profile_url`, `caption`, `title`, `thumbnail_url`, duration, posted fields, estimated views, engagement fields, Reup Score fields, `review_board_status`, and source metadata.

## Duplicate Prevention

`CaptureInboxService.promote()` checks for existing Review Board candidates before ingest. It detects existing canonical videos by promoted/existing source video IDs, aweme/source external ID, or source URL. When a candidate exists, it skips new creation with `already_promoted` and safely marks the Capture Inbox item promoted with the existing candidate ID.

## Eligibility Behavior

Backend eligibility is now centralized for individual and bulk promote. Allowed statuses are `READY`, `ENRICHED`, and `PREVIEW_MISSING`. Items are skipped if already promoted, failed, excluded, duplicate, not ready, missing identity, missing thumbnail, or missing caption/title metadata.

## Bulk Promote Behavior

Bulk Promote continues to reuse the existing `promote_now` action. The API now returns explicit `skipped` and `failed` arrays. The frontend uses backend promote messages for Bulk Promote summaries, refreshes session data, and clears selection after completion.

## Status Sync Behavior

Successful and duplicate-synced promotions mark `CapturedItem.status = PROMOTED`, set promoted foreign keys where available, and write `review_status`, `promoted_at`, `promoted_to_review_board_id`, `review_board_handoff_verified`, `review_board_item_id`, and `review_board_duplicate_detected` into `metadata_json`.

## Validation

Passed:

- `python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status`
- `python -m compileall src scripts`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`
- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/capture-inbox-canonical.test.ts && npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts`

Known pre-existing failure:

- `npm --workspace @reup-douyin/web run test` fails before Capture Inbox tests on Windows path duplication: `apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx`.

## Manual Retest Steps

1. Open `/ops/extensions/douyin/capture-inbox` with a session containing ready and ineligible items.
2. Promote a single ready item and confirm the card becomes promoted with an Open candidate link.
3. Open `/selection/review-board` and confirm the candidate appears once.
4. Try promoting the same item again and confirm no duplicate Review Board item is created.
5. Select multiple visible items including ready, already promoted, and missing metadata rows.
6. Run Bulk Promote and confirm the summary reports promoted and skipped counts.
7. Refresh Capture Inbox and verify promoted badges/status persist.
