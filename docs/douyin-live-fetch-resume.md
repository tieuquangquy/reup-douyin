# Douyin Live Fetch Integration Resume

## Current Step

Completed: live Douyin fetch client and `CRAWL_PROFILE` worker handler are wired through the existing ingest/discovery architecture.

## Done

- Read `AGENTS.md`.
- Audited `/intake` API route, intake discovery service, source ingest service, Douyin adapter, canonical ingest models, candidate discovery service, job system, worker runtime, and existing intake/source adapter docs.
- Identified root cause: default Douyin adapter has no fetch client.
- Chosen canonical path: keep `SourceIngestService` as the only persistence path and inject live fetch behind `DouyinProfileAdapter`.
- Created live-fetch log/resume/architecture docs before code changes.
- Added `DouyinLiveFetchClient` using standard-library HTTP and embedded JSON extraction.
- Added adapter registry that injects the live client when `DOUYIN_ENABLE_LIVE_FETCH=true`.
- Added API/worker env examples for live fetch settings.
- Updated `/intake` response and UI summary with fetch mode / existing-profile fallback state.
- Wired `CRAWL_PROFILE/finalize_session` in `JobRunner` to call `SourceIngestService`.
- Verified compile, API tests, web tests, typecheck, build, route smoke, fixture ingest fallback, intake candidate discovery, and worker crawl job execution.

## In Progress

- None for this step.

## Next Exact Task

Add optional `/intake` polling/job mode only if live fetch proves too slow for synchronous local operation, and add a small review-board banner/filter for `?fresh=1` intake results.

## Key Files To Continue

- `apps/api/src/adapters/douyin.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/registry.py`
- `apps/api/src/core/settings.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/job_runner.py`
- `apps/worker/src/handlers/mock_handlers.py`
- `apps/api/.env.example`
- `apps/worker/.env.example`
- `docs/douyin-live-fetch-architecture.md`
- `docs/douyin-live-fetch-log.md`
- `docs/douyin-live-fetch-resume.md`
