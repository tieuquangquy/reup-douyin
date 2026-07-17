# Phase 22F-1B Review Board Metadata Trace and Upsert Fix Log

## Summary
Phase 22F-1B traced the real Capture Inbox to Review Board path and found the visible stale metadata was caused by duplicate promote handling. Existing candidates were marked as already promoted and removed from the ingest/evaluation path, so Phase 22F-1A mapping never reached the candidate displayed by Review Board.

## Data Path Traced
1. Capture Inbox UI calls `runCaptureInboxAction()` with `promote_now`.
2. Backend route `POST /capture-inbox/sessions/{capture_session_id}/actions` calls `CaptureInboxService.promote()`.
3. `promote()` selects promotable items.
4. Existing Review Board records are found by source video/candidate lookup.
5. Before this fix, existing records were returned as duplicates and skipped.
6. New records still flow through `_adapter_payload_for_items()` into `SourceIngestService.ingest_profile()`.
7. Candidate evaluation writes `VideoCandidate` records.
8. Review Board API returns `/candidates` using `CandidateDetailResponse`.
9. Frontend route `/selection/review-board` renders `ReviewBoardPage` with `getReviewCandidateMetadata()`.

## Root Cause
`_sync_existing_review_board_promotions()` marked existing candidates as duplicates and appended `already_promoted`, but did not enrich `VideoCandidate.metadata_json` or `SourceVideo.metadata_json`. The displayed candidate therefore retained stale score/date/estimated views metadata.

## Fix
- Added shared backend helper `mapCaptureInboxItemToReviewCandidateMetadata()`.
- Reused the helper for normal promote adapter payloads.
- Changed duplicate promote to idempotent upsert/enrichment.
- Existing candidates now receive latest Capture Inbox metadata and are returned as promoted/updated, not skipped as `already_promoted`.
- Added `candidate_updated_count` to promote results/API response.
- Frontend display score now uses `reupScore` only.

## Tests
- Backend duplicate promote test now verifies existing candidate metadata is enriched.
- Frontend metadata test verifies display score is `reupScore` when candidate score differs.
