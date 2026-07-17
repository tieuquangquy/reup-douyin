# Phase 22F-1C Review Board Source Trace / Real Path Fix Resume

## Status
Phase 22F-1C implementation is substantially complete in code and targeted validation passed. The remaining gap is manual browser proof against the user's live runtime data, because the local SQLite file inspected in this workspace is empty.

## Files changed
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/lib/reviewCandidateMetadata.ts`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `docs/metadata-phase22F-1C-review-board-source-trace-real-path-fix-log.md`
- `docs/metadata-phase22F-1C-review-board-source-trace-real-path-fix-resume.md`

## Current proof points
- Actual route is `/selection/review-board`; `/review-board` redirects there.
- Actual frontend API helper calls `GET /candidates` through `fetchCandidates()` with `cache: "no-store"`.
- Actual backend endpoint is `apps/api/src/api/routes/candidates.py` `list_candidates()`.
- Actual card render path is `ReviewCandidateCard()` in `apps/web/src/components/review-board/ReviewBoardPage.tsx`.
- Backend candidate responses now carry `review_board_trace_version: "22F-1C"` and `review_candidate_debug`.
- Promote responses now populate `raw_details` with `updated_existing` for duplicate/upserted promotions.

## Validation run
- Failed first attempt: `python -m unittest apps.api.tests.test_phase22f_review_candidate_contract` from repo root could not import `src`.
- Passed: `python -m unittest tests.test_phase22f_review_candidate_contract` from `apps/api`.
- Passed: `python -m compileall src` from `apps/api`.
- Passed: `npm --workspace @reup-douyin/web run test -- --runInBand`.
- Passed: `npm --workspace @reup-douyin/web run typecheck`.

## Remaining manual retest
After starting the real dev stack, promote the Capture Inbox item for aweme `7621110952095665451` again, then open `/selection/review-board` and verify:
- The API payload contains `review_board_trace_version: "22F-1C"`.
- The matching candidate contains `review_candidate_debug.apiEndpoint = "GET /candidates"`.
- The card score displays `42`, not `21.1`, and does not append the aweme id to the score line.
- Est. Views displays `4.1K-20.3K`.
- Likes/comments/shares remain `203 / 7 / 18`.
- Posted display matches `23:00:00 24/3/2026`.

## Known environment notes
- `rg` was unavailable; `findstr` and direct file reads were used.
- `Get-Process` was unavailable in the shell; `tasklist`/`taskkill` were used.
- Node processes were killed and Next cache directories were removed earlier in the phase.
- `apps/api/data/reup_douyin.db` was size 0 with no tables, so live DB proof could not be collected from that file.
