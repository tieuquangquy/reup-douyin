# Local Setup

This guide targets Phase 1 local development on Windows.

## Prerequisites

- Python matching `apps/api/pyproject.toml`
- Node.js for `apps/web`
- PostgreSQL reachable from the API
- Optional local ffmpeg for real render runs

## Environment Files

Copy examples:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
Copy-Item apps/worker/.env.example apps/worker/.env
```

Important variables:

- `DATABASE_URL`: PostgreSQL connection for API and worker.
- `LOCAL_STORAGE_ROOT`: local disk storage root for media assets.
- `NEXT_PUBLIC_API_BASE_URL`: browser-facing API URL, usually `http://localhost:8000`.
- `FACEBOOK_PAGE_ACCESS_TOKEN`: optional for normal local demo; required only for real Facebook Page/Reels publish attempts when a `PlatformAccount` references this token name. It can be set in the shell environment or in `apps/api/.env`.

## Install Dependencies

API:

```powershell
cd apps/api
pip install -e .
```

Web:

```powershell
cd apps/web
npm install
```

## Local Doctor

From repo root:

```powershell
.\scripts\dev-doctor.ps1
```

The doctor checks env files, Python/Node/npm, web dependencies, ffmpeg availability, storage write access, API dependency imports, **Playwright import/browser binary/launch readiness for browser-assisted Douyin connect**, PostgreSQL reachability through `DATABASE_URL`, FastAPI app import, worker entrypoint import, Facebook publish-token readiness, and whether the API server is reachable.

## Migrations

From repo root:

```powershell
.\scripts\dev-migrate.ps1
```

## Seed Demo Data

From repo root:

```powershell
.\scripts\seed-demo.ps1
```

The seed is intended to be idempotent for the alpha demo profile/video identifiers.

Equivalent convenience wrapper:

```powershell
.\scripts\dev-reseed.ps1
```

## Run Apps

Start API, web, and worker in separate PowerShell windows:

```powershell
.\scripts\dev-start.ps1
```

Stop services started by that script:

```powershell
.\scripts\dev-stop.ps1
```

`dev-start` refuses to overwrite an existing `.dev/pids.json`; run `dev-stop` first if a previous local stack is still recorded. `dev-stop` verifies the recorded PowerShell command before stopping a PID, which avoids killing an unrelated process if a stale PID was reused.

Manual commands remain valid:

- API: `cd apps/api; uvicorn src.main:app --reload`
- Web: `cd apps/web; npm run dev`
- Worker: `cd apps/worker; python src/main.py`

## Smoke Check

From repo root:

```powershell
.\scripts\smoke-check.ps1
```

This runs Python compile, API app import, API unit tests, **Playwright launch smoke in API runtime**, worker entrypoint import, frontend state-helper tests, and frontend typecheck. Run `npm --workspace @reup-douyin/web run build` before release packaging or when verifying Next.js build output.

## Operational Metrics

When the API is running, open:

```text
GET /ops/metrics
```

Use it to inspect job backlog, failure categories, step durations, asset reuse, render status, publish draft status, and open risk severity counts.
