# Phase 22F-1B Review Board Metadata Trace and Upsert Fix Resume

## Status
Implemented and ready for validation.

## Files Changed
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `docs/metadata-phase22F-1B-review-board-metadata-trace-upsert-fix-log.md`
- `docs/metadata-phase22F-1B-review-board-metadata-trace-upsert-fix-resume.md`

## Key Finding
Phase 22F-1A fixed mapping for fresh promotions, but existing Review Board candidates were intercepted by `_sync_existing_review_board_promotions()` and skipped as duplicates before the new mapping path ran.

## Implemented Behavior
- Fresh promote uses `mapCaptureInboxItemToReviewCandidateMetadata()` in adapter payload construction.
- Duplicate promote now enriches the existing `SourceVideo` and `VideoCandidate` with latest Capture Inbox metadata.
- Existing Review Board decision/status is preserved because enrichment only updates metadata and score source, not review decisions or status transitions.
- Promote response includes `candidate_updated_count`.
- Frontend display score reads `reupScore` only.

## Validation Already Run
- `python -m compileall apps/api/src/services/capture_inbox_service.py apps/api/src/schemas/capture_inbox.py apps/api/src/api/routes/capture_inbox.py`
- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_capture_inbox_promotion_syncs_existing_review_board_duplicate` from `apps/api`
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_phase22f_review_candidate_contract` from `apps/api`
- `npm --workspace @reup-douyin/web run test -- review-candidate-metadata`

## Remaining Suggested Validation
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`
