# Development Setup Plan

This document captures the original bootstrap setup path. It is retained as historical context; current runnable commands live in `docs/local-setup.md` and `docs/development-workflow.md`.

## Planned Local Prerequisites

- Windows development machine.
- Node.js and npm for the web workspace.
- Python for API and worker services.
- PostgreSQL for persistence.
- Redis for queues.
- Local disk directory for Phase 1 storage.

## Environment Files

Create local `.env` files from:

- `apps/web/.env.example`
- `apps/api/.env.example`
- `apps/worker/.env.example`

Do not commit real `.env` files.

## Planned Service Responsibilities

- Run `apps/web` as the local operator UI.
- Run `apps/api` as the HTTP service.
- Run `apps/worker` as the background job executor.
- Run PostgreSQL and Redis locally for Phase 1 development when persistence and queue work begins.

## Bootstrap Work That Has Since Been Completed

- Next.js application files.
- FastAPI application entrypoint.
- Python worker entrypoint.
- Python package setup for API and worker services.
- Test runners for API and web state helpers.
- Database migrations and domain models.
- Job, queue-adjacent, storage, media, publish, routing, and optimization foundations.

## Bootstrap Guardrail

Do not implement crawler, queue, schema, storage adapter, or UI business logic as part of this bootstrap. Those belong to later focused steps with their own plan and tests.
