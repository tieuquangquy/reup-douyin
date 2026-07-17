# Current Status

## Implemented

- Monorepo skeleton and runtime boundaries for web, API, worker, extension, shared/config packages.
- Next.js operator UI with many routes: intake, review board, capture inbox, Douyin accounts, extension setup/manager, production/editing/publishing surfaces.
- FastAPI API with routers for source ingest, Douyin accounts, Douyin extension capture, capture inbox, review/candidate flow, jobs, audio/TTS/render/publish/risk/analytics.
- SQLAlchemy models and Alembic migrations for profiles, crawl sessions, source videos, metric snapshots, capture inbox, queues, publishing, and later workflow surfaces.
- Douyin profile adapter that can normalize fixture/live payloads into source profiles/videos.
- Browser extension whole-profile harvest implementation with state machine, profile scanner, readiness checks, calibration, backend flush, and tests.
- Docker Compose for postgres, redis, api, worker, and web.

## Partially Implemented

- Douyin import has multiple paths:
  - API live/fixture ingest via `/source-profiles/ingest`.
  - Extension-driven capture inbox ingest via `/douyin-extension/*`.
  - Douyin account/browser connect via `/douyin-accounts/*`.
- Worker exists but is still a local polling skeleton with mock handlers, not a mature Redis-backed distributed queue consumer.
- Video processing surfaces exist as foundations, but the audit did not verify a complete real rewrite/TTS/subtitle/render/remove-text pipeline.
- API source ingest currently runs synchronously in the HTTP request; architecture docs say long-running crawls should become jobs.

## Appears Missing Or Risky

- Clear single canonical product path from `Scan Profile` to reviewable videos is not obvious because extension capture inbox and source ingest are both present.
- Real live Douyin fetch depends on env/browser/session settings and is disabled by default (`DOUYIN_ENABLE_LIVE_FETCH=false` default in settings).
- No default safe live-crawl reproduction was performed; using real Douyin would require owner-approved session/cookie/browser profile decisions.
- `rg` is unavailable on this Windows environment, so searches used PowerShell.
- The repo has unusual zero-byte files/directories with quoted names such as `'caption'`, `'like_count'`, `'share_count'`, and API quoted artifacts. They were not modified.

## Commands Run

- `pwd; ... rg --files ...` failed because `pwd`/Unix syntax was not available in cmd.
- `cd && dir /a && rg --files ...` partially succeeded for top-level listing, failed because `rg` is not installed.
- `powershell -NoProfile -Command "Get-ChildItem ..."` for inventory/searches succeeded.
- `npm run` succeeded and listed scripts.
- Environment inspection listed variable names only from `.env`/`.env.example` files; no secret values were printed.

## Local Startup Status

- `npm run dev` was not started during this audit to avoid opening persistent PowerShell windows and modifying runtime state.
- Based on scripts, local dev expects:
  - API: `uvicorn src.main:app --reload` from `apps/api`
  - Web: `npm run dev` from `apps/web`
  - Worker: `python src/main.py` from `apps/worker`
- Docker production-like stack exposes web on `${WEB_PORT:-3000}` and keeps API internal behind web/upstream config.

## Important Environment Variables Observed

Variable names observed include:

- Core: `APP_ENV`, `DATABASE_URL`, `LOCAL_STORAGE_ROOT`, `LOG_LEVEL`, `CORS_ALLOWED_ORIGINS`
- Auth: `API_AUTH_REQUIRED`, `JWT_SECRET_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`
- Web/API: `NEXT_PUBLIC_API_BASE_URL`, `API_HOST`, `API_PORT`, `WEB_PORT`
- Douyin: `DOUYIN_ENABLE_LIVE_FETCH`, `DOUYIN_SESSION_COOKIE`, `DOUYIN_USER_AGENT`, `DOUYIN_PROXY_URL`, `DOUYIN_FETCH_MAX_VIDEOS`, `DOUYIN_PERSISTENT_BROWSER_PROFILE_ENABLED`, `DOUYIN_REUSE_LIVE_BROWSER_FOR_FETCH`, `DOUYIN_SECRET_ENCRYPTION_KEY_REF`
- Worker/queue: `REDIS_URL`, `WORKER_ID`, `WORKER_CONCURRENCY`, `WORKER_POLL_INTERVAL_SECONDS`
- Publishing: `FACEBOOK_PAGE_ACCESS_TOKEN`
