# Phase 22F-1D Live Review Board Route/API Verifier Log

## Scope
- Implemented Phase 22F-1D only: live Review Board route/API verifier, visible diagnostics, backend trace/debug, DB/source proof, and exact aweme repair path.

## Route Canonicalization
- `/selection/review-board` remains the canonical route and renders `ReviewBoardPage`.
- `/review-board` redirects to `/selection/review-board`.
- `/selection/review` now redirects to `/selection/review-board` and does not render a second Review Board component.

## Frontend Diagnostics
- Added dev-only visible marker in `ReviewBoardPage`:
  - `review_board_ui_version = "22F-1D"`
  - `route = {pathname}`
  - `api = GET /candidates`
  - `last refreshed = ...`
- Added per-card `data-review-board-trace-version="22F-1D"` and serialized frontend render debug based on the actual candidate object used to render the card.
- Details diagnostics now include both backend `review_candidate_debug` and frontend `frontendVisibleDebug`.

## Backend/API Diagnostics
- `GET /candidates` now returns `review_board_trace_version: "22F-1D"` at list level.
- Each candidate response now returns `review_board_trace_version: "22F-1D"` and `review_candidate_debug` with visible score source, raw internal score, reup score, priority, estimated views source, metrics, duration, posted display, and raw key lists.
- `review_board_api_debug` includes the API endpoint, frontend API base expectation, backend DB driver/host/path, candidate count, and candidate source.

## Live Source Proof
- `apps/web/.env.local` sets `NEXT_PUBLIC_API_BASE_URL=/api`.
- `apps/api/.env` sets `DATABASE_URL=postgresql+psycopg://...@localhost:5432/reup_douyin`.
- Live API proof command used:
  - `curl -sS --max-time 10 "http://127.0.0.1:8000/candidates?limit=200"`
- Live API returned:
  - `review_board_trace_version: 22F-1D`
  - `backendDatabaseDriver: postgresql+psycopg`
  - `backendDatabaseHost: localhost`
  - `backendDatabasePath: reup_douyin`
  - `candidateCount: 10`

## Exact Aweme Proof
- Live API for aweme `7621110952095665451` returned:
  - `score: 21.05` (raw/internal only)
  - `reup_score: 42`
  - `estimated_views_display: 4.1K-20.3K`
  - `like_count/comment_count/share_count: 203/7/18`
  - `duration_text: 17:13`
  - `posted_display: 23:00:00 24/3/2026`
- Frontend visible score uses `reviewCandidateDisplayScore(candidate)` -> `candidate.reup_score` path, so this renders `Score 42` instead of internal `21.05`/`21.1`.
- Frontend estimated views uses `formatEstimatedViews(metadata)`, so this renders `Est. Views 4.1K-20.3K`.

## Self-Heal
- Review Board GET self-heals stale candidate metadata from Capture Inbox by matching `capture_item_id`, aweme/source video external id, or source/share URL.
- Self-heal updates candidate/source metadata and promotion links without creating duplicates.
- Internal raw `candidate.score` is preserved as raw diagnostic data; visible score uses only `reup_score` priority.

## Validation
- `python -m compileall src` passed.
- `python -m unittest tests.test_phase22f_review_candidate_contract` passed.
- `npm --workspace @reup-douyin/web run test -- --runInBand` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web run build` passed.

## Notes
- The earlier empty SQLite file was not the live browser/API database. The live backend is using PostgreSQL database `reup_douyin` on localhost, which explains why local SQLite inspection did not match browser-visible candidates.
