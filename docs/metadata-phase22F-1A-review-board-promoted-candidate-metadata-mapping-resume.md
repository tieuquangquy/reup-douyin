# Phase 22F-1A Review Board Promoted Candidate Metadata Mapping Resume

## Status
Implemented. Validation still needs to be run.

## Files Changed
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `docs/metadata-phase22F-1A-review-board-promoted-candidate-metadata-mapping-log.md`
- `docs/metadata-phase22F-1A-review-board-promoted-candidate-metadata-mapping-resume.md`

## What Changed
- Promote mapping now preserves canonical Capture Inbox metadata and aliases needed by Review Board.
- Candidate API response hydrates canonical fields and aliases from candidate/source metadata.
- API response uses promoted `reup_score` as the exposed `score` when available.
- Review Board display now uses promoted Reup Score instead of recalculated candidate score.
- Aweme ID is no longer concatenated beside the score on the Review Board card.
- Estimated views and posted display prefer captured display strings before fallbacks.

## Audit Findings
- Individual and bulk promote both use `promote_now` with `item_ids`; backend mapping is shared.
- `CandidateEvaluationService.apply()` recalculates `candidate.score`, explaining Score 42 becoming 21.1.
- The Review Board score eyebrow appended external ID, explaining the aweme beside score.
- Estimated views were vulnerable to alias gaps across promote/API/frontend.
- Posted date could change when the UI formatted `posted_at` instead of using captured `posted_display`.

## Validation To Run
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_phase22f_review_candidate_contract tests.test_capture_inbox_metadata_status`
- `cd apps/api && python -m compileall src scripts`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`

## Known Limitations
- Existing old candidates only show fields that are available in their stored metadata/source record; missing metrics remain missing rather than being synthesized.
