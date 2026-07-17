# Douyin Live Fetch Integration Log

## Findings

- `/intake` submits `POST /intake/discover`.
- `POST /intake/discover` calls `IntakeDiscoveryService.discover()`.
- `IntakeDiscoveryService` resolves a Douyin profile identity, reuses an existing `SourceProfile` when present, otherwise calls `SourceIngestService.ingest_profile()`.
- `SourceIngestService` persists canonical `CrawlSession`, `SourceProfile`, `SourceVideo`, and `VideoMetricSnapshot` rows, then intake applies `CandidateEvaluationService`.
- The root failure is `SourceIngestService` defaulting to `DouyinProfileAdapter()` without a fetch client. `DouyinProfileAdapter.fetch_profile()` raises `adapter_fetch_failed` with: `Douyin network fetch client is not configured; inject a fetch client or worker handler`.
- Existing fallback exists only for dev/test callers that pass `adapter_payload_json` to `/source-profiles/ingest`, or for `/intake` when the profile is already ingested.
- Worker infrastructure has a `CRAWL_PROFILE` job template, but the worker currently uses placeholder handlers and no real crawl handler.

## Existing Architecture Inventory

- Adapter boundary: `apps/api/src/adapters/douyin.py`, `apps/api/src/adapters/types.py`.
- Ingest persistence: `apps/api/src/services/source_ingest_service.py`.
- Intake orchestration: `apps/api/src/services/intake_discovery_service.py`.
- Candidate discovery: `apps/api/src/services/candidate_service.py`, `candidate_filter.py`, `filter_presets.py`.
- Durable job foundation: `apps/api/src/services/job_service.py`, `job_runner.py`, `job_templates.py`.
- Local worker runtime: `apps/worker/src/runtime.py`, `apps/worker/src/main.py`.
- Canonical entities reused: `SourceProfile`, `CrawlSession`, `SourceVideo`, `VideoMetricSnapshot`, `VideoCandidate`.

## Decisions Made

- Keep `/intake` synchronous for Phase 1 local-first UX because current API already performs ingest and candidate discovery synchronously.
- Implement live Douyin fetch behind the existing `DouyinProfileAdapter` fetch-client seam.
- Do not create a second intake/crawl persistence pipeline.
- Add a real worker handler for `CRAWL_PROFILE` that calls `SourceIngestService`, but keep `/intake` on the existing sync path for now.
- Preserve fallback mode:
  - Existing ingested profile can still be used by `/intake`.
  - `/source-profiles/ingest` can still accept `adapter_payload_json` for dev/test payload normalization.
  - If live fetch is disabled or Douyin blocks the request, API returns a clear, actionable error.

## Files Touched

- `apps/api/src/adapters/douyin.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/registry.py`
- `apps/api/src/core/settings.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/job_runner.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/tests/test_douyin_adapter.py`
- `apps/api/.env.example`
- `apps/worker/.env.example`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/types/intake.ts`
- `docs/douyin-live-fetch-architecture.md`
- `docs/douyin-live-fetch-log.md`
- `docs/douyin-live-fetch-resume.md`
- `docs/douyin-ingest-flow.md`
- `docs/source-adapter-architecture.md`
- `docs/worker-runtime-overview.md`
- `docs/job-system-overview.md`
- `docs/intake-screen-api-map.md`
- `docs/intake-screen-log.md`
- `docs/intake-screen-resume.md`

## Verification Notes

- `python -m compileall apps/api/src apps/worker/src` passed.
- `PYTHONPATH=apps/api python -m unittest discover apps/api/tests` passed: 80 tests.
- `npm --workspace @reup-douyin/web test` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- Restarted the web dev server after build and smoke-checked `/`, `/intake`, `/review-board`, `/ops`, `/source-videos/test-id/transcript-editor`, `/source-videos/test-id/final-review`, and `/source-videos/test-id/publish`.
- API smoke: `GET /docs` and `GET /filter-presets` returned 200.
- API route inventory confirmed `/intake/discover`, `/source-profiles/ingest`, `/crawl-sessions`, `/candidates`, and `/jobs`.
- Adapter registry smoke confirmed live mode creates `DouyinLiveFetchClient`, and disabled mode keeps `fetch_client=None`.
- Fallback disabled-live path now returns a clear 502 message telling the operator to enable `DOUYIN_ENABLE_LIVE_FETCH=true`, ingest a dev payload, or use an already-ingested profile.
- Canonical fallback smoke:
  - `POST /source-profiles/ingest` with fixture payload completed with 2 videos.
  - `POST /intake/discover` on the same profile returned `used_existing_profile=true`, `fetch_mode=existing_profile`, and 2 matched candidates.
  - `GET /candidates` returned candidate rows.
- Worker smoke:
  - Created a high-priority `CRAWL_PROFILE` job with fixture payload.
  - Ran one `LocalPollingWorker.run_once()`.
  - Job completed with progress 100 and a crawl session id.

## Status

Completed for this step.
