# Alpha Readiness Review

Date: 2026-04-17

## Overall Readiness

The repo is structurally ready for internal alpha development and demo with seeded data. It is not ready for unattended production use or real platform publishing.

Current readiness: **alpha foundation ready, real-world provider integration still high risk**.

## Strengths

1. Clear monorepo boundaries between web, API, worker, shared packages, and docs.
2. Durable job and job step model exists before heavy pipelines.
3. Media storage abstraction exists, so local disk is not hardcoded everywhere.
4. Domain lifecycle enums are explicit across source video, candidates, jobs, media, render, publish, and risk.
5. Review checkpoints are visible: review board, transcript editor, final review, publish draft.
6. Risk scan is honest about heuristic limits and records operator decisions.
7. Docs now include setup, demo, runbooks, and alpha checklist.
8. Tests cover many service/state helpers without live external services.
9. Seed fixture enables demo without live Douyin or media providers.
10. Pipeline outputs use manifests, reducing guesswork between stages.

## Weaknesses And Technical Debt

1. Several pipelines use placeholder/mock providers; real provider integration will expose new failure modes.
2. Frontend tests are helper-level, not full component/browser tests.
3. API tests are mostly unit/service tests, not database integration tests.
4. Seeded media files are placeholder bytes, not real playable video.
5. Worker runtime is local polling, not Redis-backed distributed queue.
6. No auth, account model, or multi-user ownership yet.
7. Publish scheduling is persistence-only.
8. Risk scan is heuristic and metadata-driven.
9. Logging exists by convention, but structured log coverage is uneven.
10. Some docs from early bootstrap may still understate how much has been implemented.

## Risk Areas

### Architecture

The architecture is appropriately layered for alpha. The main risk is accumulating route/service coupling as features grow. Keep controllers thin and continue adding focused services.

### Backend

Schema breadth is now large. Migration discipline matters. Before alpha, run migrations from an empty database at least once.

### Frontend

Screens are pragmatic and desktop-first. Main risk is lack of browser-level tests for long operator sessions.

### Worker Pipeline

Worker is the highest operational risk. It can run skeleton jobs, but real concurrency, idempotency, and crash recovery need testing with actual long-running handlers.

### Data Model

The data model is SaaS-ready enough for alpha. User/auth/billing are intentionally absent, which is fine for Phase 1 but should not be bolted on casually later.

### Error Handling

Domain-specific error codes exist in many places. Gaps remain around consistent UI presentation and logs for nested provider errors.

### Logging

Logging expectations are documented. Alpha should verify logs include job id, source video id, render id, and publish draft id in real failure paths.

### Docs

Docs are now usable for onboarding. Keep them updated aggressively because the pipeline is broad.

### Developer Experience

Seed and smoke scripts reduce friction. Dependency installation still depends on local Python/Node toolchains and PostgreSQL being configured correctly.

### Test Coverage

Good for deterministic helpers. Weak for database integration, API route tests, and browser UI behavior.

## Fix Before Alpha

1. Run `alembic upgrade head` on a clean local database.
2. Run `scripts/seed-demo.ps1` against that database.
3. Confirm seeded final review and publish draft screens load in browser.
4. Confirm `GET /risk-flags` and `GET /publish-drafts` return seed data.
5. Validate worker starts with local env and does not crash on startup.
6. Add real sample media files if visual playback demo is required.

## Can Wait Until Post-Alpha

1. Real publish connectors.
2. OAuth/social account linking.
3. Redis queue backend.
4. Cloud object storage.
5. Browser automation tests.
6. Multi-user auth and roles.
7. Advanced moderation/legal workflow.

## Internal Alpha Launch Checklist

- [ ] Migrations run cleanly from empty database.
- [ ] Seed demo data is loaded.
- [ ] API, web, and worker start locally.
- [ ] Review board shows candidates.
- [ ] Transcript editor opens seeded segments.
- [ ] Final review opens seeded render.
- [ ] Publish draft page opens seeded draft.
- [ ] Risk scan can run and decision can be saved.
- [ ] Runbooks are available to operator/dev.
- [ ] Known placeholder limitations are communicated.

## Priority Fix Order

1. Clean database migration verification.
2. Realistic playable demo media.
3. Worker startup and failure logging check.
4. API route smoke checks for primary screens.
5. Browser-level smoke test for review board -> final review -> publish draft.
6. Provider integration hardening when real tools are selected.
