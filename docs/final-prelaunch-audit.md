# Final Prelaunch Audit

Date: 2026-04-21

## 1. Repo Readiness Overview

`reup-douyin` has a broad local-first Phase 1 pipeline through Step 22:

```text
ingest -> filter/score -> review board -> download/assets -> audio analysis
-> transcript editor -> TTS/subtitle -> render -> final review -> publish draft
-> risk scan -> Facebook publish connector -> reconciliation -> analytics-lite
-> multi-account routing/control plane -> optimization loop
```

The codebase is healthy at compile/test/build level. The main operational blocker found in this pre-launch pass is local PostgreSQL reachability: `DATABASE_URL` points to `localhost:5432`, but this machine did not accept connections during the audit. Full local operation requires PostgreSQL to be running and reachable before migration, seed, worker, and DB-backed API flows can be considered ready.

## 2. Entrypoints And Commands Discovered

Frontend:

- App entry: `apps/web/src/app`
- Dev: `cd apps/web; npm run dev`
- Build: `npm run web:build`
- Tests: `cd apps/web; npm test`
- Typecheck/static check: `npm run typecheck`

Backend API:

- App entry: `apps/api/src/main.py`
- Dev: `cd apps/api; uvicorn src.main:app --reload`
- Swagger: `http://127.0.0.1:8000/docs`
- Migration: `.\scripts\dev-migrate.ps1`
- Seed: `.\scripts\dev-reseed.ps1`

Worker:

- Entry: `apps/worker/src/main.py`
- Dev: `cd apps/worker; python src/main.py`

Operational scripts:

- `npm run doctor`
- `npm run smoke`
- `npm run dev`
- `npm run dev:stop`
- `.\scripts\dev-migrate.ps1`
- `.\scripts\dev-reseed.ps1`

## 3. Issues Found

### Fixed During This Pass

1. Migration and seed scripts could print native command errors but still return success.
   - Cause: PowerShell does not automatically throw on non-zero native process exit codes.
   - Impact: operator could think migration/seed succeeded when DB was unreachable.

2. PostgreSQL connection attempts could hang too long.
   - Cause: no explicit `connect_timeout` in SQLAlchemy/Alembic PostgreSQL connections.
   - Impact: migration/seed/DB sanity checks were slow and unclear when PostgreSQL was down.

3. `dev-doctor` did not check DB reachability.
   - Impact: environment looked healthier than it was; migration/seed failed later.

4. `npm --workspace @reup-douyin/web run lint` was interactive because `next lint` prompted for ESLint setup.
   - Impact: automation could hang or fail during pre-launch checks.

5. API architecture docs still had early-bootstrap language.
   - Impact: docs understated implemented publish/reconciliation/routing/optimization layers.

### Found But Not Fixed As Code

1. Local PostgreSQL is not reachable on `localhost:5432`.
   - This is an environment/service issue, not a code issue.
   - Full local run is blocked until PostgreSQL is started or `apps/api/.env` points at a reachable DB.

2. Real Facebook publish is not verified.
   - Requires `FACEBOOK_PAGE_ACCESS_TOKEN` and has external side effects.

3. `dev-start.ps1` opens separate PowerShell windows.
   - Useful for a local operator, but not ideal for headless CI. This is acceptable for Phase 1.

4. Worker is still a local polling worker with placeholder handlers.
   - This matches Phase 1 local-first scope, but is not production distributed queue infrastructure.

## 4. Fixes Applied

- Added fast PostgreSQL connect timeout for API runtime connections:
  - `apps/api/src/db/session.py`
- Added fast PostgreSQL connect timeout for Alembic migrations:
  - `apps/api/alembic/env.py`
- Added DB reachability to doctor checks:
  - `scripts/dev-doctor.ps1`
- Made migration script fail correctly when Alembic fails:
  - `scripts/dev-migrate.ps1`
- Made seed script fail correctly when seed fails:
  - `scripts/seed-demo.ps1`
- Replaced interactive web lint behavior with non-interactive TypeScript static check:
  - `apps/web/package.json`
  - `apps/web/tsconfig.typecheck.json`
  - root `package.json`
  - `scripts/smoke-check.ps1`
- Decoupled web typecheck from generated `.next/types` so a partial or failed Next build does not break static checks.
- Updated docs to match current code and command behavior:
  - `docs/local-setup.md`
  - `docs/development-workflow.md`
  - `docs/architecture-overview.md`
  - `apps/api/README.md`
- Hardened local start/stop safety:
  - `scripts/dev-start.ps1` refuses to overwrite an existing `.dev/pids.json`
  - `scripts/dev-stop.ps1` verifies the recorded PowerShell command before stopping a PID

Earlier final-release fixes remain in place:

- root npm scripts for `dev`, `dev:stop`, `doctor`, `smoke`, `test`, `typecheck`, `web:build`
- worker entrypoint import validation in smoke/doctor
- Facebook token resolution from process env or `apps/api/.env`
- CSS build warning fix

## 5. Verification Commands Used

Passed:

```powershell
python -m compileall apps\api apps\worker
```

```powershell
cd apps/api
python -m unittest discover tests
```

Result: 77 tests passed.

```powershell
npm run smoke
```

Result: passed. Includes Python compile, API import, API tests, worker import, web tests, and web typecheck.

```powershell
npm run typecheck
```

Result: passed.

```powershell
npm --workspace @reup-douyin/web run lint
```

Result: passed. This now runs the non-interactive TypeScript static check.

```powershell
npm run web:build
```

Result: passed. Next.js production build completed successfully.

```powershell
npm run dev:stop
```

Result: passed with no PID file present. This verifies the stop command exits cleanly when no local stack is running.

```powershell
cd apps/api
python -c "from src.main import app; print(app.title); print(len(app.routes))"
```

Result: passed, app title `reup-douyin API`, 96 routes.

```powershell
cd apps/worker
python -c "import sys, runpy; sys.path.insert(0, 'src'); runpy.run_path('src/main.py', run_name='__worker_import_check__'); print('worker import ok')"
```

Result: passed.

Failed as expected because PostgreSQL is not reachable:

```powershell
npm run doctor
```

Result: 1 fail, 1 warn.

- Fail: `DATABASE_URL is not reachable`
- Warn: `FACEBOOK_PAGE_ACCESS_TOKEN` is not configured

```powershell
.\scripts\dev-migrate.ps1
```

Result: failed correctly with PostgreSQL connection timeout.

```powershell
.\scripts\dev-reseed.ps1
```

Result: failed correctly with PostgreSQL connection timeout.

## 6. Final Commands For Local Operation

Install dependencies:

```powershell
cd apps/api
pip install -e .

cd ..\worker
pip install -e .

cd ..\web
npm install
```

Prepare env files:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
Copy-Item apps/worker/.env.example apps/worker/.env
```

Edit `apps/api/.env` so `DATABASE_URL` points to a running PostgreSQL database.

Run checks:

```powershell
npm run doctor
npm run smoke
npm run web:build
```

Run DB setup after `doctor` passes:

```powershell
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
```

Start services:

```powershell
npm run dev
```

Stop services:

```powershell
npm run dev:stop
```

If `npm run dev` refuses to start because `.dev/pids.json` already exists, run `npm run dev:stop` first. The stop script validates the recorded command before stopping a process to avoid stale-PID mistakes.

Manual service commands:

```powershell
cd apps/api
uvicorn src.main:app --reload
```

```powershell
cd apps/worker
python src/main.py
```

```powershell
cd apps/web
npm run dev
```

## 7. Recommended First-Run Sequence

1. Start PostgreSQL locally and ensure the database/user in `apps/api/.env` exists.
2. Copy env files if missing.
3. Run:

```powershell
npm run doctor
```

4. If doctor passes, run:

```powershell
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
```

5. Run:

```powershell
npm run smoke
npm run web:build
```

6. Start the apps:

```powershell
npm run dev
```

7. Open:

- Web: `http://localhost:3000`
- API Swagger: `http://127.0.0.1:8000/docs`
- API metrics: `http://127.0.0.1:8000/ops/metrics`

8. For real Facebook publish attempts, configure `FACEBOOK_PAGE_ACCESS_TOKEN` in the shell environment or `apps/api/.env` before publishing.

## 8. Known Limitations Accepted For V1

- PostgreSQL must be provided by the local operator; there is no bundled database service.
- Redis remains a target for future distributed queueing; Phase 1 uses a local polling worker.
- Worker handlers are still placeholder-oriented for many pipeline jobs.
- Real Douyin crawling, production STT/TTS/OCR providers, and final external publish verification are not part of default tests.
- Facebook Page/Reels is the only real connector foundation; TikTok/YouTube remain out of scope.
- Analytics-lite and optimization hints are operator-assist heuristics, not autopilot.
- OAuth onboarding is not production-grade; phase-1 account setup uses manual token references.

## 9. Risks Not Fixed Because They Are Too Large

- Replacing local worker polling with Redis-backed distributed queues.
- Full production OAuth/account onboarding.
- Full media provider integration for STT/TTS/OCR and real render quality benchmarking.
- Multi-user auth/permissions.
- Deep analytics, engagement sync, comments/inbox, or social CRM.
- End-to-end live Facebook publish verification without operator-provided credentials and explicit side-effect approval.

## 10. Final Assessment

Assessment: **CAUTION for full local run until PostgreSQL is reachable; GO for code/build/test readiness.**

The repo is substantially easier to run and debug than before:

- smoke/build/typecheck pass
- web build passes
- API and worker imports are checked
- migration/seed scripts now fail correctly instead of silently succeeding
- DB unreachable is now surfaced in `doctor`
- docs now match current commands and current feature scope more closely

The only current blocker for a full local run is environment-level: PostgreSQL at `DATABASE_URL` is not reachable from this machine. Once PostgreSQL is running and `npm run doctor` passes, proceed with migration, seed, start, and demo flow.
