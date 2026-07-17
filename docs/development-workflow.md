# Development Workflow

## Before Editing

Read:

- `AGENTS.md`
- the app/package README for the area you are changing
- the relevant docs under `docs/`

Keep changes scoped to the current step. Do not add future product phases early.

## Common Commands

Environment doctor:

```powershell
.\scripts\dev-doctor.ps1
```

Run migrations:

```powershell
.\scripts\dev-migrate.ps1
```

Seed or reseed demo data:

```powershell
.\scripts\dev-reseed.ps1
```

Start/stop local services:

```powershell
.\scripts\dev-start.ps1
.\scripts\dev-stop.ps1
```

API tests:

```powershell
cd apps/api
python -m unittest discover tests
```

API compile:

```powershell
python -m compileall apps\api apps\worker
```

Web state tests:

```powershell
cd apps/web
npm test
npm run typecheck
npm run build
```

`npm test` runs the full current web state-helper suite, including review, transcript editing, final review, publish draft, risk, publish health, publish control, and optimization tests. `npm run build` may need normal process-spawn permissions outside restricted sandboxes.

Repo smoke check:

```powershell
.\scripts\smoke-check.ps1
```

Operational metrics while API is running:

```text
GET /ops/metrics
```

Create a pre-beta pilot report folder:

```powershell
.\scripts\new-pilot-report.ps1 -Name pilot-001
```

## Adding Backend Features

- Add schema changes through Alembic migrations.
- Keep route handlers thin.
- Put domain logic in services.
- Add focused tests for service logic and contract helpers.
- Update docs when lifecycle, state, or API behavior changes.

## Adding Frontend Screens

- Keep API calls in `apps/web/src/lib/api.ts`.
- Keep UI state helpers testable when logic is non-trivial.
- Add components under a feature folder.
- Add loading, empty, and error states.

## Long-Running Work

Any long-running process should be a `Job` with `JobStep` records. Do not run crawl, download, audio, TTS, render, or publish work inline in HTTP handlers.

Retry/resume behavior is documented in `docs/retry-resume-policies.md`.

## Docs Expectations

If a change affects setup, demo, lifecycle, pipeline behavior, or debugging, update docs in the same change.

For pre-beta validation changes, also update:

- `docs/pre-beta-test-plan.md`
- `docs/operator-pilot-workflow.md`
- `docs/issue-taxonomy-and-triage.md`
- `docs/go-no-go-criteria.md`
