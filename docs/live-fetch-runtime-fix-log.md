# Live Fetch Runtime Fix Log

## Findings

- API settings loader is `apps/api/src/core/settings.py` using `pydantic-settings` with `env_file=".env"`.
- `scripts/dev-start.ps1` starts API from `apps/api`, so API reads `apps/api/.env`.
- Worker runtime imports the same API settings and `scripts/dev-start.ps1` starts it from `apps/worker`, so worker reads `apps/worker/.env`.
- Canonical env var for live fetch is `DOUYIN_ENABLE_LIVE_FETCH`.
- Adapter registry checks `settings.douyin_enable_live_fetch` and injects `DouyinLiveFetchClient` only when true.
- `apps/api/.env` did not include `DOUYIN_ENABLE_LIVE_FETCH`, so runtime used default `False`.
- `apps/worker/.env` did not include `DOUYIN_ENABLE_LIVE_FETCH`, so worker runtime also used default `False`.
- `.env.example` files already documented the variables, but kept live mode disabled by default.

## Current Runtime Root Cause

The live fetch client exists and is wired, but local runtime env files do not enable it. The `/intake` error is caused by runtime config resolving `douyin_enable_live_fetch=False`, which leaves `DouyinProfileAdapter.fetch_client=None`.

## Config Values Expected

- `DOUYIN_ENABLE_LIVE_FETCH=true`
- `DOUYIN_USER_AGENT` present; default browser UA is acceptable.
- `DOUYIN_SESSION_COOKIE` optional, empty by default. May be required if Douyin blocks public profile payloads.
- `DOUYIN_PROXY_URL` optional, empty by default. May be required for network/region/rate-limit issues.
- `DOUYIN_FETCH_TIMEOUT_SECONDS=15`
- `DOUYIN_FETCH_MAX_VIDEOS=50`

## Decisions Made

- Enable live fetch in local `.env` for both API and worker.
- Keep `.env.example` default disabled so fresh clones can still run demo/fallback without accidental live Douyin calls.
- Do not hardcode cookie/proxy/session secrets.
- Preserve existing fallback paths: existing profile reuse and dev fixture payload ingest.

## Files Touched

- `apps/api/.env`
- `apps/worker/.env`
- `docs/live-fetch-runtime-fix-log.md`
- `docs/live-fetch-runtime-fix-resume.md`
- `docs/live-fetch-runtime-next-steps.md`

## Verification Notes

- API settings load from `apps/api`:
  - `douyin_enable_live_fetch=True`
  - adapter registry creates `DouyinLiveFetchClient`
  - cookie present: false
  - proxy present: false
- Worker settings load through `apps/worker/src/api_path.py`:
  - `douyin_enable_live_fetch=True`
  - adapter registry creates `DouyinLiveFetchClient`
  - cookie present: false
  - proxy present: false
- Restarted API on port 8000 from `apps/api` so it reads updated `apps/api/.env`.
- API smoke:
  - `GET /docs` returned 200.
  - `GET /filter-presets` returned 200.
- Live-mode runtime smoke:
  - `POST /intake/discover` for a not-yet-ingested Douyin profile URL no longer returns the disabled fetch-client error.
  - The request used `fetch_mode=live_or_fixture_ingest`, `used_existing_profile=false`, and created a `crawl_session_id`.
  - The synthetic profile URL produced zero candidates, which is expected for a test/non-real profile and is not a config failure.
- Fallback verification:
  - `POST /source-profiles/ingest` with fixture payload completed with 2 videos.
  - `POST /intake/discover` for that existing profile returned `used_existing_profile=true`, `fetch_mode=existing_profile`, `matched=2`, `total=2`.
  - `GET /candidates` returned candidate rows.
- Web smoke:
  - `/intake` returned 200.
  - `/review-board` returned 200.
  - `/ops` returned 200.

## Status

Completed for this step.
