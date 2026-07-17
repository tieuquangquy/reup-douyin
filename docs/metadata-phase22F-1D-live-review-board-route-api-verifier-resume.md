# Phase 22F-1D Live Review Board Route/API Verifier Resume

## Status
- Phase 22F-1D implementation is complete pending final user review.
- Required log doc is `docs/metadata-phase22F-1D-live-review-board-route-api-verifier-log.md`.
- This resume records the exact live route/API/render fix, validation commands, and any caveats for continuation.

## Implemented
- Canonical Review Board routing:
  - `/selection/review-board` renders the single `ReviewBoardPage` implementation.
  - `/selection/review` redirects to `/selection/review-board`.
  - `/review-board` continues redirecting to `/selection/review-board`.
- Frontend 22F-1D diagnostics:
  - Dev-only visible marker exposes `review_board_ui_version = "22F-1D"`, live route pathname, candidates API endpoint, and refresh timestamp.
  - Each card emits hidden serialized 22F-1D render diagnostics from the actual candidate object used for visible score/views rendering.
  - Detail diagnostics include backend `review_candidate_debug` and frontend `frontendVisibleDebug`.
- Backend 22F-1D diagnostics:
  - `GET /candidates` returns list-level `review_board_trace_version: "22F-1D"` and `review_board_api_debug`.
  - Candidate responses include `review_candidate_debug`, `reup_score`, `estimated_views_display`, engagement counts, duration, posted display, aweme id, and capture item id.
- Visible score path:
  - Review Board cards display only `candidate.reup_score` through `reviewCandidateDisplayScore(candidate)`.
  - Raw/internal `candidate.score` remains available for diagnostics and sorting data, but is not used as the visible Review Board score.
- Estimated views path:
  - Review Board cards display `estimated_views_display` first, then canonical min/max/mid fallbacks.
- Self-heal path:
  - Review Board GET hydrates stale candidate/source metadata from Capture Inbox by `capture_item_id`, aweme/source video external id, or source/share URL.
  - Existing review decisions/notes are preserved; the fix updates metadata rather than creating duplicates.

## Live Proof Captured
- Frontend API base source: `apps/web/.env.local` sets `NEXT_PUBLIC_API_BASE_URL=/api`.
- Backend database source: `apps/api/.env` sets `DATABASE_URL=postgresql+psycopg://...@localhost:5432/reup_douyin`.
- This explains why the earlier inspected local SQLite file was empty while the browser/API still had candidates: the running local backend uses PostgreSQL database `reup_douyin`, not that SQLite file.
- Live API command used:
  - `curl -sS --max-time 10 "http://127.0.0.1:8000/candidates?limit=200"`
- Exact aweme `7621110952095665451` live API proof after repair returned raw score `21.05`, visible `reup_score: 42`, `estimated_views_display: "4.1K–20.3K"`, likes/comments/shares `203/7/18`, `duration_text: "17:13"`, and `posted_display: "23:00:00 24/3/2026"`.

## Validation
- Backend:
  - `python -m compileall src`
  - `python -m unittest tests.test_phase22f_review_candidate_contract`
- Web:
  - `npm --workspace @reup-douyin/web run test -- --runInBand`
  - `npm --workspace @reup-douyin/web run typecheck`
  - `npm --workspace @reup-douyin/web run build`

## Files Changed
- `apps/web/src/app/selection/review/page.tsx`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/types/review-board.ts`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/test/review-candidate-metadata.test.ts`
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/api/routes/candidates.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/services/candidate_service.py`
- `apps/api/tests/test_phase22f_review_candidate_contract.py`
- `docs/metadata-phase22F-1D-live-review-board-route-api-verifier-log.md`
- `docs/metadata-phase22F-1D-live-review-board-route-api-verifier-resume.md`

## Caveat
- No browser screenshot was captured in this run. The live proof is from the local running API and from the frontend route/render diagnostics added to the app.
