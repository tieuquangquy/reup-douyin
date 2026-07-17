# Architecture Overview

`reup-douyin` is designed as a local-first product with SaaS-ready boundaries. Phase 1 runs on a personal Windows machine for one operator, but the repository layout avoids assumptions that would block later multi-user, distributed, or cloud-hosted operation.

## High-Level Shape

```text
apps/web       -> operator UI
apps/api       -> FastAPI HTTP boundary and orchestration
apps/worker    -> long-running background execution
packages/shared -> shared contracts, schemas, constants, docs helpers
packages/config -> config templates and conventions
docs           -> architecture, setup, and scope notes
```

## Runtime Direction

- Frontend: Next.js + TypeScript.
- API: FastAPI + Python.
- Worker: Python.
- Database target: PostgreSQL.
- Queue target: Redis.
- Storage Phase 1: local disk through an abstraction.
- Future storage: object storage behind the same abstraction.

## Boundary Decisions

The web app owns UI and operator interaction only. It calls the API and does not directly run crawlers, processors, or storage writes.

The API owns HTTP contracts, validation, persistence coordination, and future job submission. Long-running work must be submitted as jobs instead of running inline in request handlers.

The worker owns long-running execution. Any crawl, download, analysis, scoring, processing, rendering, export, or publish workflow should be modeled with durable state, retries, resume behavior, and observable progress.

Shared packages hold contracts and config conventions, not hidden application workflows.

## Decision Note

This structure uses separate `apps` and `packages` directories because the product has three distinct runtime surfaces: UI, HTTP API, and background jobs. Keeping them separate from the start reduces coupling and makes it easier to introduce multi-user auth, distributed workers, cloud storage, and deployment-specific packaging later.

Local disk is accepted for Phase 1 because it is practical for one Windows operator. It must still be accessed behind a storage abstraction so the later move to object storage does not force product workflow rewrites.

PostgreSQL and Redis remain the target infrastructure choices. The current repo has PostgreSQL-oriented models, migrations, and local worker/job orchestration; Redis-backed distributed queueing is still a future replacement for the local polling worker.

## Current Phase 1 Foundation

The repo now contains a broad local-first alpha foundation:

- database models and migrations for the core domain
- job and job-step orchestration
- source ingest adapter shape
- filtering, candidate scoring, and review board UI
- media storage/download abstractions and asset manifests
- audio analysis, transcript, translation draft, TTS, subtitle, render-prep, and render foundations
- transcript editor, final review, publish draft, and risk warning UI/API surfaces
- Facebook Page/Reels publish connector, publish attempt reconciliation, analytics-lite, publish control, and optimization hints
- seed data, runbooks, smoke checks, and operational metrics

The implementation still intentionally avoids connector platforms beyond Facebook Reels, production OAuth onboarding, distributed queue infrastructure, cloud storage, multi-user auth, billing, deep analytics, social inbox workflows, and legal/compliance automation.

## Local Operations

For pre-beta local operation, use:

- `scripts/dev-doctor.ps1` for environment checks
- `scripts/dev-migrate.ps1` for migrations
- `scripts/dev-reseed.ps1` for demo data
- `scripts/dev-start.ps1` and `scripts/dev-stop.ps1` for local processes
- `GET /ops/metrics` for backlog, failure, duration, asset, render, publish, and risk summaries
