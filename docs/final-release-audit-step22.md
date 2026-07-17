# Final Release Audit After Step 22

Date: 2026-04-21

## 1. Repo State Before Fixes

The project already contained the Phase 1 workflow through Step 22:

- ingest, candidate filtering/scoring, review board
- download/storage/assets and manifest layer
- audio analysis, transcript editor, TTS/subtitle, render preparation
- render engine, final review, publish draft, risk scan
- Facebook Page/Reels connector, publish reconciliation, analytics-lite
- multi-account routing/control plane and feedback-driven optimization

The release audit found that core Python and web logic was healthy, but some local operation wiring was stale:

- Root `package.json` still referenced `pnpm` and a bootstrap-era `dev` script.
- `scripts/smoke-check.ps1` only ran an older subset of web tests and used `npx --package tsx`, which can require network/cache access.
- `scripts/dev-doctor.ps1` did not verify the FastAPI app import and treated workspace dependencies as missing when `node_modules` lived at the repo root.
- Worker startup was only covered by compile checks; a self-review pass found package/script import mode differences that could hide entrypoint breakage.
- `README.md` and workflow docs still described publish connectors as out of scope.
- `apps/api/.env.example` did not document the phase-1 Facebook Page token variable used by `PlatformAccount.token_reference`.
- Facebook publish token lookup only checked process environment even though local setup tells operators to use `apps/api/.env`.
- Next.js production build initially showed an Autoprefixer warning for `align-items: start`.

The repo directory is not currently a Git repository, so this audit could not use `git status` or `git diff` for change review.

## 2. Issues Found

### Run And Script Issues

- Root package manager metadata was inconsistent with the installed npm workspace.
- Root `npm test` did not run the release smoke check.
- Smoke check did not include publish health, publish control, or optimization web tests.
- Smoke check did not run frontend typecheck.
- Doctor script produced an incorrect warning for npm workspaces using a root-level `node_modules`.
- Doctor summary had a PowerShell counting issue when exactly one warning was present.
- Worker entrypoint import was not part of smoke/doctor validation.

### Docs And Env Issues

- README scope statement was stale after the Facebook connector and post-publish layers were added.
- `docs/development-workflow.md` still listed individual legacy web test commands.
- `docs/dev-setup-plan.md` still read like the bootstrap phase was current.
- `docs/local-setup.md` did not mention Facebook Page token readiness.
- API `.env.example` did not include the optional token variable for real Facebook publishing.
- Facebook token resolution could miss tokens configured in `apps/api/.env`.

### Build Issues

- `apps/web/src/app/globals.css` used `align-items: start`, which Next/Autoprefixer warned about during production build.
- Next.js build failed inside the restricted sandbox with `spawn EPERM`; rerunning with normal process-spawn permissions succeeded.

## 3. Fixes Applied

- Updated root `package.json` to npm workspace metadata and practical scripts:
  - `npm run dev`
  - `npm run dev:stop`
  - `npm run doctor`
  - `npm run smoke`
  - `npm test`
  - `npm run web:build`
- Updated `scripts/smoke-check.ps1` to run:
  - Python compile
  - FastAPI app import
  - API unit tests
  - worker entrypoint import
  - full web state-helper test suite
  - web TypeScript typecheck
- Updated `scripts/dev-doctor.ps1` to:
  - accept root workspace `node_modules`
  - verify FastAPI app import
  - verify worker entrypoint import
  - warn when `FACEBOOK_PAGE_ACCESS_TOKEN` is missing
  - correctly count one warning in the summary
- Updated `README.md`, `docs/development-workflow.md`, `docs/local-setup.md`, and `docs/dev-setup-plan.md` to match the current Step 22 project shape.
- Added `FACEBOOK_PAGE_ACCESS_TOKEN` to `apps/api/.env.example` with a no-secrets warning.
- Updated Facebook token resolution so real publish attempts can read the configured token from either the process environment or `apps/api/.env`.
- Added focused token-resolution tests to prevent regressions in real publish setup.
- Made worker imports tolerant of local script execution and explicit entrypoint validation.
- Replaced unsupported CSS alignment values with `flex-start` in `apps/web/src/app/globals.css`.

## 4. Verification Commands Used

Run from repo root unless otherwise noted.

```powershell
python -m compileall apps\api apps\worker
```

Result: passed.

```powershell
cd apps/api
python -m unittest discover tests
```

Result: passed, 77 tests.

```powershell
cd apps/web
npm test
```

Result: passed all web state-helper tests:

- review board
- transcript editor
- final review
- publish draft
- risk
- publish health
- publish control
- optimization

```powershell
cd apps/web
npm run typecheck
```

Result: passed.

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

```powershell
.\scripts\smoke-check.ps1
```

Result: passed.

```powershell
.\scripts\dev-doctor.ps1
```

Result: passed with 0 failures and 1 expected warning because `FACEBOOK_PAGE_ACCESS_TOKEN` is not set.

```powershell
cd apps/web
npm run build
```

Result: passed when run with normal process-spawn permissions. It fails inside the restricted sandbox with `spawn EPERM`, which is an execution environment limitation rather than a project build failure.

## 5. Acceptable Remaining Issues For V1

- `FACEBOOK_PAGE_ACCESS_TOKEN` is not set in the local environment or `apps/api/.env`. This is acceptable for non-publish demos and tests, but real Facebook publish attempts require it.
- Live Facebook publish was not executed during this audit to avoid external side effects.
- Live migrations and seed scripts were not executed against the local database during this audit to avoid mutating the operator's current DB state. The scripts were inspected and the API/runtime/test layer was verified.
- The API server was already running locally and responded during doctor checks. If it is stopped, doctor will warn instead of fail.
- `docs/continuation-handoff.md` still records older `npx --package tsx` commands as historical handoff notes. Current runnable commands are now documented in `docs/development-workflow.md`.

## 6. Not Fixed Because Too Large Or Risky

- No schema or migration changes were made in this pass. Current model semantics for current/latest render, canonical publish success, reconciliation, account routing, and optimization were left intact because tests passed and a release audit should not rewrite business lifecycle behavior without a targeted migration plan.
- No job orchestration rewrite was attempted. Existing retry/resume/reconciliation policies are documented and covered by focused tests, but production-grade distributed queue semantics remain a future hardening area.
- No UI redesign was attempted. Existing operator screens build successfully and state-helper tests pass.
- No second platform connector, deep analytics, social inbox, or autopilot automation was added.

## 7. Recommended Local Operation Commands

Install dependencies:

```powershell
cd apps/api
pip install -e .

cd ..\..\apps\worker
pip install -e .

cd ..\..\apps\web
npm install
```

Prepare local environment:

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
Copy-Item apps/worker/.env.example apps/worker/.env
```

Run readiness checks:

```powershell
npm run doctor
npm test
npm --workspace @reup-douyin/web run build
```

Run migrations and seed demo data when ready to mutate the local DB:

```powershell
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
```

Start and stop local services:

```powershell
npm run dev
npm run dev:stop
```

Manual service commands:

```powershell
cd apps/api
uvicorn src.main:app --reload

cd apps/web
npm run dev

cd apps/worker
python src/main.py
```

Important local URLs:

- Web: `http://localhost:3000`
- API Swagger: `http://127.0.0.1:8000/docs`
- API health/ops metrics: `http://127.0.0.1:8000/ops/metrics`

## 8. Final Go/No-Go Assessment

Status: **Go for local V1 dry-run and operator demo, with controlled external publishing**.

The repo is ready for local operation at the code/build/test level:

- Python compile passes.
- API unit tests pass.
- FastAPI app imports successfully.
- Worker entrypoint imports successfully.
- Web state tests pass.
- Web typecheck passes.
- Next.js production build passes outside the restricted sandbox.
- Doctor and smoke scripts now reflect the current project shape.

Conditions before a real publish run:

- Configure a valid Facebook Page access token through `FACEBOOK_PAGE_ACCESS_TOKEN` in the process environment or `apps/api/.env`, matching the chosen `PlatformAccount.token_reference`.
- Run migrations and seed/demo commands intentionally against the target local database.
- Use risk gates and publish reconciliation views during real publishing.
- Do not treat analytics-lite or optimization hints as autonomous decisioning; they are operator-assist heuristics.
