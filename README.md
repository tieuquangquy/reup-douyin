# reup-douyin

`reup-douyin` is a local-first web app for a single Windows operator in Phase 1. The long-term product goal is to help an operator import Douyin profile links, crawl videos, filter and score candidates worth reuploading, review them in a UI, run semi-automated Vietnamese localization, edit at important checkpoints, and export videos for multiple platforms.

The repository is intentionally scaffolded as SaaS-ready from the start. Phase 1 can run locally, but boundaries are designed for future multi-user access, distributed workers, Redis-backed queues, PostgreSQL persistence, cloud object storage, and auto publishing.

## Repository Architecture

```text
apps/
  web/        Next.js + TypeScript frontend
  api/        FastAPI HTTP service
  worker/     Python background worker
packages/
  shared/     Shared schemas, types, constants, and docs helpers
  config/     Shared config templates and environment conventions
docs/         Architecture, scope, and setup documentation
```

## App And Package Responsibilities

- `apps/web`: operator-facing UI only. It should call the API and never own crawling, processing, scoring, queue orchestration, or direct database writes.
- `apps/api`: FastAPI boundary for request handling, validation, persistence coordination, and future job submission. It should not execute long-running processing inline.
- `apps/worker`: background execution for future crawl, processing, scoring, localization, export, and publishing jobs. Long-running jobs must be durable, retryable, resumable, and observable.
- `packages/shared`: cross-boundary shared contracts, schemas, constants, and documentation helpers. It should stay dependency-light and avoid app-specific runtime logic.
- `packages/config`: shared environment examples, config conventions, and templates. It must never contain real secrets.
- `docs`: technical decisions, setup plans, scope boundaries, and future operational notes.

## Phase 1 Scope

Phase 1 targets one local Windows operator and focuses on building a reliable foundation for the eventual workflow:

- Input Douyin profile links.
- Crawl and collect candidate videos.
- Filter and score videos for reupload potential.
- Review candidates through a UI card/player workflow.
- Run semi-automated Vietnamese localization and processing.
- Allow manual edits at important checkpoints.
- Export videos for multiple target platforms.

The Reup Queue `Start auto` action is now bound to the content-addressed V24
controlled-pilot recipe. Durable Download/Audio/Translate/TTS/OCR/Render jobs carry
the same recipe reference through retry/resume and stop fail-closed if its evidence
changes. Final Review and Manual Export remain operator gates; external publishing
is not triggered by this path.

The current alpha foundation includes local-first implementations for ingest, filtering/scoring, review, media assets, transcript editing, TTS/subtitle preparation, render, final review, publish draft preparation, risk warnings, Facebook Page/Reels publishing, publish reconciliation, analytics-lite, publication metric snapshots/growth summaries, a durable metrics collector job, an adaptive cadence scheduler, a network-free local adapter, a fail-closed Facebook Reels insights adapter with controlled-live preflight, and Meta OAuth Page onboarding with encrypted local credentials. Facebook publishing also has Page-level concurrency, warm-up, cadence, failure and cooldown/hold guardrails. Live Meta App Review/verification, TikTok/YouTube connectors, attribution/revenue analytics, social inbox/comment workflows, hosted vault/KMS integration and automatic scheduler activation remain intentionally out of scope.

## Development Direction

- Use Next.js + TypeScript in `apps/web`.
- Use FastAPI + Python in `apps/api`.
- Use Python in `apps/worker`.
- Target PostgreSQL for persistence.
- Target Redis for queueing.
- Use local disk storage in Phase 1 through an abstraction that can later move to object storage.
- Keep long-running work out of HTTP request handlers.
- Keep product workflows separate from reusable infrastructure.

## Environment Files

Each runtime app has an example environment file:

- `apps/web/.env.example`
- `apps/api/.env.example`
- `apps/worker/.env.example`

Copy these to local `.env` files when real runtime setup begins. Do not commit secrets.

## Documentation

Start with:

- `docs/architecture-overview.md`
- `docs/local-setup.md`
- `docs/development-workflow.md`
- `docs/demo-flow.md`
- `docs/alpha-test-checklist.md`
- `docs/alpha-readiness-review.md`
- `docs/local-operator-guide.md`
- `docs/pre-beta-readiness.md`
- `docs/pre-beta-test-plan.md`
- `docs/operator-pilot-workflow.md`
- `docs/bug-bash-plan.md`
- `docs/go-no-go-criteria.md`
- `docs/facebook-reels-connector.md`
- `docs/facebook-reels-insights-adapter-v1.md`
- `docs/platform-account-setup-phase1.md`
- `docs/publish-attempt-lifecycle.md`
- `docs/publish-retry-and-idempotency.md`
- `docs/publish-connector-hardening.md`
- `docs/publish-health-dashboard.md`
- `docs/multi-account-scaling-phase1.md`
- `docs/feedback-driven-optimization.md`

Contributors and agents should also read `AGENTS.md` before making changes.

Recent extension cleanup notes:

- `docs/extension-cleanup-changelog.md`

## Extension Test Guardrails

The repository includes lightweight guardrails for `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts` to protect assertion diagnostics without changing runtime behavior.

What the guardrail checks:

- missing final assertion message strings in the highest-risk workflow regions
- exact duplicate assertion statements after whitespace normalization
- optional changed-file scope warnings for conservative cleanup passes

Local commands:

```powershell
npm run extension:test:guardrails
npm run extension:test:guardrails:warn
npm run extension:test:guardrails:strict
```

Current rollout stage:

- default `extension:test:guardrails` runs in soft mode
- warn mode always exits `0` and is safe for immediate adoption in local workflows
- strict mode exits non-zero on blocking findings and is intended for later CI enforcement once the signal remains low-noise

Recommended adoption path:

1. Start with `npm run extension:test:guardrails:warn` during local cleanup work.
2. Use the default soft mode in focused pre-PR validation for extension test maintenance.
3. Move CI to `extension:test:guardrails:strict` only after the file stays clean and the warnings remain actionable.

No repository CI workflow was added in this phase because the repo currently has no existing `.github/workflows` entry point; keeping rollout script-first avoids introducing a new blocking pipeline prematurely.

## Alpha Demo

After configuring API environment and running migrations, seed demo data from the repo root:

```powershell
.\scripts\seed-demo.ps1
```

Run focused smoke checks:

```powershell
.\scripts\smoke-check.ps1
```

For local pre-beta operation, use:

```powershell
.\scripts\dev-doctor.ps1
.\scripts\dev-migrate.ps1
.\scripts\dev-reseed.ps1
.\scripts\dev-start.ps1
```

Stop services started by `dev-start`:

```powershell
.\scripts\dev-stop.ps1
```

Create a pilot report folder from templates:

```powershell
.\scripts\new-pilot-report.ps1 -Name pilot-001
```
