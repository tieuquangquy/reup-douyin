# Phase 22F-1A Review Board Promoted Candidate Metadata Mapping Log

## Audit
- Individual Promote: `CaptureInboxPage.tsx` calls `runCaptureInboxAction(..., { action: "promote_now", item_ids: [...] })` for card actions and Promote ready.
- Bulk Promote: `CaptureInboxPage.tsx` maps selected eligible items to the same `promote_now` action and `item_ids`; no separate backend mapper exists.
- Backend endpoint: `apps/api/src/api/routes/capture_inbox.py` routes `promote_now` to `CaptureInboxService.promote()`.
- Backend creation path: `CaptureInboxService.promote()` builds adapter payload, calls `SourceIngestService.ingest_profile()`, then `CandidateEvaluationService.apply()`.
- Storage: canonical video metadata is stored in `SourceVideo.metadata_json`; promoted review metadata is copied into `VideoCandidate.metadata_json`.
- API mapper: `CandidateDetailResponse` hydrates top-level fields from candidate/source metadata.
- Frontend adapter/component: `getReviewCandidateMetadata()` normalizes API fields for `ReviewBoardPage.tsx`.

## Root Cause
- Review Board card displayed `candidate.score`, which is recalculated by `calculate_reup_score_v1()` during candidate evaluation, not the Capture Inbox `reup_score`.
- Review Board card appended `source_video_external_id` in the score eyebrow, causing `SCORE 21.1 · aweme_id`.
- Estimated views could be missing because not all Capture Inbox aliases (`estimated_views_text`, `estimated_views`, aliases) were mapped through promote/API/frontend.
- Posted display could shift because Review Board fell back to formatting `source.posted_at` when `posted_display` was absent.

## Mapping Fixed
- Promote payload now sets `source = douyin` and `source_module = capture_inbox` while preserving aweme/source/video/profile/caption/description/thumbnail/duration/posted/estimated views/engagement/Reup Score fields.
- Douyin adapter now stores 22F-1A canonical fields and metadata quality flags in source metadata.
- API response now exposes canonical fields plus compatibility aliases: `thumbnail`, `posted`, `duration`, `views_display`, `views_mid`, `likes`, `comments`, `shares`.
- Frontend adapter now returns camelCase normalized fields while preserving snake_case compatibility used by existing code.

## Score Handling
- API aliases `score` to `reup_score` when promoted metadata includes it.
- Review Board display uses `reviewCandidateDisplayScore()`, which prefers Capture Inbox `reupScore` and falls back to candidate score only for legacy records.

## Estimated Views Handling
- Promote mapping checks canonical and legacy estimated-view fields before falling back to `view_count_text`.
- Review Board formats estimated views from display text first, then min/max range, then mid/view count.

## Posted Date Handling
- Promote/API/frontend preserve `posted_display` and prefer it over formatted timestamps.
- `posted_text_raw` is carried for diagnostics and legacy compatibility.

## Zero/Null Handling
- Numeric fields use first-present/nullish semantics, preserving explicit `0` and leaving missing values null.
- Frontend display keeps missing values as `--`/`Not captured`; no fake zeros are introduced.

## Duplicate Prevention
- Existing Phase 22F duplicate prevention by source video and `capture_item_id` remains in `CaptureInboxService.promote()`.
- Duplicate detected items are synced to Review Board references and skipped before canonical ingest.

## Tests
- Updated backend promote mapping assertions in `test_douyin_extension_capture_service.py`.
- Updated API response contract assertions in `test_phase22f_review_candidate_contract.py`.
- Updated frontend metadata adapter assertions in `review-candidate-metadata.test.ts`.
