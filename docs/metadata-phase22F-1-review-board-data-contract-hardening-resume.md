# Phase 22F-1 Review Board Data Contract Hardening Resume

## Status
Phase 22F-1 implementation is complete pending final validation and report.

## Implemented
- Audited Capture Inbox to Review Board promotion before changing behavior.
- Hardened backend promotion payload mapping and Douyin adapter metadata preservation.
- Preserved source metadata on candidate upsert.
- Added Review Board response-level canonical aliases with lazy metadata hydration.
- Added duplicate prevention by `capture_item_id`, with existing checks for `source_video_external_id` and `source_url` retained.
- Added frontend Review Board metadata adapter and switched Review Board display/sort paths to use it.
- Added backend and frontend tests for canonical field mapping and zero/null behavior.

## Important Files
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/candidate_service.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/lib/reviewBoardState.ts`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `apps/web/package.json`

## Validation To Run
- `python -m unittest tests.test_douyin_extension_capture_service tests.test_phase22f_review_candidate_contract` from `apps/api`.
- `python -m compileall src scripts` from `apps/api`.
- `npm --workspace @reup-douyin/web run test` from repo root.
- `npm --workspace @reup-douyin/web run typecheck` from repo root.
- `npm --workspace @reup-douyin/web run build` from repo root.

## Manual Retest
1. Capture a Douyin profile/video into Capture Inbox where metrics include estimated views, likes, comments, shares, duration, posted text, thumbnail, and Capture Reup Score.
2. Promote the item to Review Board.
3. Open Review Board and confirm the card shows `Est. Views`, likes, comments, and shares from captured metadata.
4. Confirm unavailable metrics show `--`, not `0`.
5. Confirm explicit source-provided zero remains visible as `0`.
6. Confirm thumbnail, posted date/text, duration, and Capture Reup Score are present when captured.
7. Promote the same capture/source again and confirm it is treated as already promoted rather than creating a duplicate candidate.
