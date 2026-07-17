# Phase 22F-1F Canonical Source Metadata Snapshot Resume

## What This Phase Does
Phase 22F-1F stops one-off Review Board field repairs by creating a canonical Capture Inbox `source_metadata` snapshot and making Review Board use it first.

## Important Files
- `apps/api/src/services/capture_inbox_service.py`: snapshot builder, comparison diagnostic, promote storage.
- `apps/api/src/services/candidate_service.py`: Review Board self-heal/backfill hydration from Capture Inbox.
- `apps/api/src/schemas/candidates.py`: API response fields and source-metadata priority.
- `apps/api/src/api/routes/capture_inbox.py`: promote raw detail trace and snapshot flags.
- `apps/web/src/types/review-board.ts`: `source_metadata` and comparison types.
- `apps/web/src/lib/reviewCandidateMetadata.ts`: frontend metadata adapter priority.
- `apps/api/tests/test_phase22f_review_candidate_contract.py`: backend contract/fish regression.
- `apps/web/src/test/review-candidate-metadata.test.ts`: frontend adapter/fish regression.

## Expected Fish Result
For aweme `7622664109737250084`, Review Board should show the Capture Inbox snapshot values: Score `42`, estimated views `3.7K-18.3K`, likes `183`, comments `12`, shares `13`, duration `13:37`, and the best preserved posted display from Capture Inbox metadata.

## Validation Commands
- `cd apps/api && python -m unittest tests.test_phase22f_review_candidate_contract`
- `cd apps/api && python -m compileall src`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`

## Manual Retest
1. Backfill Review Board candidates from Capture Inbox.
2. Open Review Board and locate candidate `68084b15-10c7-4c00-ba43-9c1e50eb3e15` / aweme `7622664109737250084`.
3. Confirm the card reads from `source_metadata` and no longer falls back to internal `candidate.score` or stale source-video fields.
