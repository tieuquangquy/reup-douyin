# Phase 22F-1F Canonical Source Metadata Snapshot Log

## Scope
Implemented a Review Board metadata contract that stores a canonical `source_metadata` snapshot from Capture Inbox promotion/hydration paths and makes Review Board responses/adapters prefer that snapshot before legacy flattened fields.

## Audit Notes
- Capture Inbox display is normalized through `CapturedItemResponse` plus frontend helpers in `captureInboxCanonical`, `captureInboxFilterMetadata`, and `captureInboxReupScore`.
- Promote flows enter `CaptureInboxService.promote()` and finish candidate/source-video linking in `_mark_item_promoted_to_review_board()`.
- Duplicate/already-promoted items are reconciled through `_sync_existing_review_board_promotions()` and `_enrich_existing_review_board_candidate_from_capture_item()`.
- Review Board GET hydrates stale candidates through `CandidateEvaluationService._hydrate_stale_candidates_from_capture_inbox()` and maps API fields in `CandidateDetailResponse`.
- Review Board cards read API candidates through `getReviewCandidateMetadata()`.

## Changes
- Added `buildCaptureInboxSourceMetadataSnapshot()` with version `22F-1F`.
- Added `buildCaptureToReviewComparison()` diagnostics for score, estimated views, metrics, posted display, and duration.
- Stored snapshots on candidate/source video metadata during promote and duplicate-promote updates.
- Stored snapshots during Review Board self-heal/backfill hydration without changing candidate status/decision fields.
- Exposed `source_metadata` and `capture_to_review_comparison` in Review Board API response models.
- Updated Review Board frontend types and adapter so `candidate.source_metadata` is the first visible metadata source.
- Updated Phase 22F tests for snapshot priority and fish regression coverage.

## Remaining Verification
Run backend tests/compile, frontend tests/typecheck/build, then backfill existing local candidates and manually retest the fish candidate.
