# Phase 22F-1C Review Board Source Trace / Real Path Fix Log

## Scope
Implemented Phase 22F-1C only: traced the visible Review Board path, added backend/frontend diagnostics, fixed the real candidate metadata path for promoted Capture Inbox items, and added regression coverage.

## Source-of-truth trace
- Route: `apps/web/src/app/selection/review-board/page.tsx` renders `ReviewBoardPage`.
- Redirect: `apps/web/src/app/review-board/page.tsx` redirects to `/selection/review-board`.
- Data loader: `ReviewBoardPage.loadData()` calls `fetchCandidates(appliedFilters)`.
- API helper: `apps/web/src/lib/api.ts` calls `GET ${API_BASE_URL}/candidates?...` with `cache: "no-store"`.
- Backend endpoint: `apps/api/src/api/routes/candidates.py` `list_candidates()` returns `CandidateDetailResponse`.
- Card renderer: `ReviewCandidateCard()` in `apps/web/src/components/review-board/ReviewBoardPage.tsx` renders `Score {formatScore(reviewCandidateDisplayScore(candidate))}` and the estimated views pill.

## Findings
- The visible `21.1` value is the internal candidate evaluation score written by `CandidateEvaluationService._upsert_candidate()` as `candidate.score = evaluation.score.total_score`.
- The Review Board card must display `reup_score` from capture metadata instead of that internal score.
- Est. Views showed `--` when estimated view metadata was missing from the hydrated candidate payload or the frontend fell through to `formatNumber(null)`.
- No SWR/react-query/localStorage path was found in the inspected Review Board render path; it uses direct fetch and React local state.
- The local `apps/api/data/reup_douyin.db` file is empty, so direct live DB proof for aweme `7621110952095665451` was unavailable in this workspace.

## Changes
- Added `review_board_trace_version = "22F-1C"` and `review_candidate_debug` to `CandidateDetailResponse`.
- Added dev-only frontend marker `data-review-board-trace-version` and detail-panel diagnostics.
- Changed Review Board estimated views handling to prefer canonical estimated views metadata and render `—` when missing.
- Added promote response `raw_details` entries with `action`, `candidate_id`, `metadata_updated`, score, estimated views, metrics, posted display, and `traceVersion`.
- Added regression tests for the backend response contract, promote raw details, frontend API/render source path, score source, and estimated views priority.

## Validation
- `python -m unittest tests.test_phase22f_review_candidate_contract` from `apps/api`: passed.
- `python -m compileall src` from `apps/api`: passed.
- `npm --workspace @reup-douyin/web run test -- --runInBand`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.

## Notes
A failed first backend test invocation from the repo directory reported `ModuleNotFoundError: No module named 'src'`; rerunning from `apps/api` succeeded. A failed first web test run exposed the intended legacy `views_display` fallback removal and the test was updated to use canonical `estimated_views_display`.
