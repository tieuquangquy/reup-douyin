# Intake Screen Log

## Step

Create `/intake` screen for Douyin profile intake + candidate discovery.

## Time Started

2026-04-22 Asia/Bangkok

## Findings

- `apps/web` uses Next.js App Router.
- `/intake` already exists, but it is a lightweight placeholder page and is not a real Douyin profile intake workflow.
- Operator navigation already has breadcrumb/i18n keys for Intake, but the Operator sidebar does not expose `/intake` as a primary entry.
- Review board data is loaded from `GET /candidates`; applying a preset uses `POST /candidates/filter/apply`.
- Existing canonical review route is `/selection/review-board`; legacy `/review-board` redirects there.
- Backend source ingest domain already exists:
  - `POST /source-profiles/ingest`
  - `GET /source-profiles`
  - `GET /source-profiles/{profile_id}/videos`
  - `GET /crawl-sessions`
- Backend candidate discovery/filter domain already exists:
  - `GET /filter-presets`
  - `POST /candidates/filter/preview`
  - `POST /candidates/filter/apply`
- `DouyinProfileAdapter` can validate/normalize Douyin profile URLs, but live fetch is not configured unless a fetch client or worker handler is added later.

## API / Domain Found

- `SourceProfile`, `SourceVideo`, `CrawlSession`, and `VideoMetricSnapshot` live in `apps/api/src/models/ingestion.py`.
- `VideoCandidate` and review status live in `apps/api/src/models/review.py`.
- Candidate filtering/reup score logic lives in:
  - `apps/api/src/services/candidate_filter.py`
  - `apps/api/src/services/candidate_service.py`
  - `apps/api/src/services/filter_presets.py`
  - `apps/api/src/services/reup_score.py`
- Frontend API client lives in `apps/web/src/lib/api.ts`.

## Decisions Made

- Add a thin `POST /intake/discover` backend endpoint instead of making the UI orchestrate ingest + candidate filter separately.
- Keep business logic in a service layer and reuse `SourceIngestService` plus `CandidateEvaluationService`.
- Discovery strategy:
  - Normalize/validate the Douyin profile URL.
  - If the source profile already exists, apply the candidate filter to existing source videos.
  - If the source profile does not exist, attempt the existing ingest service, then apply the candidate filter.
  - If Douyin live fetch is not configured, return a clear API error rather than inventing fake candidates.
- `/intake` success flow should show a summary and provide an `Open Review Board` link to `/review-board?fresh=1`.
- Add `/intake` to Operator Studio navigation and home quick launch.

## Files Touched

- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/main.py`
- `apps/web/src/app/intake/page.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/operatorHomeState.ts`
- `apps/web/src/types/intake.ts`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/intake.test.ts`
- `apps/web/src/test/operator-home.test.ts`
- `apps/web/src/test/route-nav.test.ts`
- `apps/web/package.json`
- `docs/intake-screen-log.md`
- `docs/intake-screen-resume.md`
- `docs/intake-screen-api-map.md`

## Verification Notes

- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web test` passed.
- `python -m compileall apps/api/src` passed.
- `npm --workspace @reup-douyin/web run build` passed and generated `/intake`.
- FastAPI app route inventory confirms `/intake/discover` is included.
- Live smoke:
  - `GET http://localhost:3000/intake` returned 200.
  - `GET http://localhost:3000/selection/review-board` returned 200 after restarting the stale web listener.
  - `GET http://localhost:3000/review-board` returned 200 and resolved to `/selection/review-board`.
  - `GET http://localhost:3000/optimization` returned 200.
  - `GET http://localhost:3000/ops` returned 200.
  - `GET http://127.0.0.1:8000/docs` returned 200.
  - `GET http://127.0.0.1:8000/filter-presets` returned 200.
  - `POST http://127.0.0.1:8000/intake/discover` with invalid URL returned 422.

## Known Remaining Rough Edges

- Live Douyin fetching now has a minimal HTML fetch client behind the adapter boundary, but it must be enabled with `DOUYIN_ENABLE_LIVE_FETCH=true` and may still need cookie/proxy support if Douyin blocks public profile payloads.
- `/intake` does not auto-redirect after success; it shows the summary and an explicit Review Board link to keep errors/no-candidate states visible.
- The frontend form covers the requested time/views/likes filters plus preset; advanced filter fields remain in review board/API surfaces.

## Status

Completed.
