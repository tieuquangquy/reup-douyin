# AGENTS.md

This repository is the foundation for `reup-douyin`, a local-first web app that must remain SaaS-ready. Every future change should preserve that direction: one Windows operator in Phase 1, but with clean boundaries for future multi-user, distributed queues, cloud storage, and automated publishing.

## Core Working Rules

- Read the relevant files before editing. Do not assume the current shape of the repo from memory.
- Plan first for any non-trivial change. The plan should identify touched apps/packages, expected files, and explicit non-goals.
- Keep changes scoped to the requested step. Do not implement future product phases early.
- Prefer correctness, maintainability, and observability over speed.
- Do not add dependencies unless they are necessary for the current step and fit the locked stack.
- Follow existing naming and structure once established.
- Do not hardcode business flow into core infrastructure. Infrastructure should expose reusable capabilities; product workflows should compose those capabilities at the application layer.

## Repository Boundaries

### `apps/web`

- Owns the Next.js + TypeScript user interface.
- Handles local operator workflows, review screens, video player UX, checkpoint forms, and API calls.
- Must not perform crawling, video processing, scoring, queue orchestration, or direct database writes.
- Must keep browser-safe configuration separate from server-only secrets.

### `apps/api`

- Owns the FastAPI HTTP boundary.
- Coordinates requests, authentication/authorization when introduced, persistence, validation, and job submission.
- Should expose stable contracts to the web app.
- Must not run long video processing inline in request handlers.
- Must not leak storage, database, queue, or worker implementation details into public API contracts.

### `apps/worker`

- Owns long-running background execution.
- Future jobs include crawl, download, analysis, filtering, scoring, localization steps, rendering, export, and publishing.
- Every long-running job must have explicit state, retry policy, idempotency expectations, error recording, and resume behavior before production use.
- Workers should use abstractions for storage, queue, and external providers so local-first execution can later move to distributed SaaS infrastructure.

### `packages/shared`

- Owns shared types, schemas, constants, and documentation helpers that are safe to use across app boundaries.
- Shared code must stay domain-oriented and dependency-light.
- Do not place app-specific runtime logic here.

### `packages/config`

- Owns shared configuration templates, environment documentation, and cross-app config conventions.
- Must separate local development defaults from production requirements.
- Must not contain secrets.

### `docs`

- Owns technical decisions, architecture notes, setup plans, scope definitions, and operational expectations.
- Docs should be updated when architecture, boundaries, workflows, or environment requirements change.

## Coding Standards

- Use TypeScript for frontend and shared web-facing code.
- Use Python for API and worker services.
- Prefer explicit types, clear module names, and small cohesive files.
- Keep infrastructure abstractions separate from product workflow orchestration.
- Avoid global mutable state except for controlled runtime clients with documented lifecycle.
- Avoid ad hoc string parsing when a typed model, parser, or schema is appropriate.
- Keep local disk paths configurable and never hardcode user-specific absolute paths.
- Treat Windows as the primary Phase 1 runtime; avoid Unix-only assumptions in scripts and docs unless clearly marked.

## Logging Expectations

- Log meaningful lifecycle events, state transitions, retries, and external boundary calls.
- Logs must include stable identifiers where available, such as job id, profile id, video id, export id, or operator id.
- Never log secrets, auth tokens, cookies, raw credentials, or private local paths unless explicitly safe.
- Long-running jobs should emit progress that can later power UI status and resumability.
- Errors should include actionable context without dumping excessive raw payloads.

## Testing Expectations

- Add tests when adding behavior, especially shared schemas, API contracts, job state transitions, storage adapters, queue adapters, and video processing orchestration.
- Prefer focused tests near the code being changed.
- Test idempotency and retry behavior for long-running jobs.
- Test boundary contracts between web/API/worker/shared when contracts are introduced.
- Do not rely on live Douyin, external platforms, or paid services in default test runs.

## Documentation Expectations

- Update `README.md` when repository-level workflows or responsibilities change.
- Update app/package README files when local setup, commands, env vars, or ownership changes.
- Add or update docs for architecture decisions that affect future contributors.
- Keep docs honest: mark planned capabilities as planned, not implemented.
- Capture decision notes for tradeoffs that will matter later.

## Environment And Secrets

- Use `.env.example` files to document required variables.
- Never commit real secrets, tokens, cookies, account credentials, or private storage paths.
- Distinguish browser-exposed variables from server-only variables.
- Local-first defaults should be easy to run on Windows, but production names should not block future SaaS deployment.

## Job And Workflow Principles

- Any job that can take more than a normal HTTP request must be modeled as a durable job.
- Durable jobs must eventually define state, retry, resume, cancellation, and failure handling.
- Job steps should be idempotent where possible.
- Checkpoint-based manual edits must be explicit product states, not hidden side effects.
- Workers should be able to resume from persisted state after a crash or restart.

## Local-First But SaaS-Ready

- Phase 1 may use local disk storage, a single operator, and local services.
- Storage must be accessed through an abstraction so object storage can replace local disk later.
- Queue and database choices target Redis and PostgreSQL even if Phase 1 starts with simple local deployment.
- Do not bake single-user assumptions into data models, API contracts, or job ownership when avoidable.
- Prefer boundaries that can support future multi-user tenancy, distributed workers, cloud storage, and auto publishing.

## Current Bootstrap Non-Goals

- No crawler implementation.
- No video processing implementation.
- No scoring or filtering implementation.
- No database schema.
- No queue implementation.
- No UI/business logic.
- No auto-publish integration.

