# Reup Pipeline Dashboard Log

## Purpose

Track implementation of the top-level operator dashboard for the end-to-end `reup_douyin` workflow:

Capture -> Review -> Reup Queue -> Export Package -> Publish Handoff -> Publish progress.

The dashboard is an operator command view, not a developer diagnostics page. It summarizes pipeline health, backlog, blockers, recent movement, and next actions while preserving the existing canonical stage surfaces.

## Implementation Plan

1. Audit current pipeline surfaces, API routes, models, schemas, services, and available counts.
2. Create required planning and operating docs before implementation.
3. Define a focused API aggregation contract for dashboard summary data.
4. Implement aggregation support in `apps/api` without moving workflow logic into the web app.
5. Implement the `/ops/pipeline` page in `apps/web` using the Ops Console Design System.
6. Add stage visualization, attention panels, recent activity, and quick links into canonical surfaces.
7. Add tests for aggregation, page structure, links, attention model, and design-system adoption.
8. Run verification and record results.

## Audit Notes

### Repository and boundaries

- `AGENTS.md` confirms `apps/web` owns UI only and must not perform crawling, video processing, queue orchestration, or direct database writes.
- `apps/api` owns FastAPI contracts, persistence-facing aggregation, validation, and stable HTTP boundaries.
- Long-running jobs remain worker-owned; this dashboard only summarizes persisted state and links to existing surfaces.
- Existing Ops Console Design System primitives are available in `apps/web/src/components/ops-console/OpsShared.tsx`.

### Current operator surfaces

- Capture Inbox: `/ops/extensions/douyin/capture-inbox`
- Review Board: `/selection/review-board` and legacy `/review-board`
- Reup Queue: `/selection/reup-queue`
- Export Packages: `/publishing/export-packages`
- Publish Handoffs: `/publishing/publish-handoffs`
- Publish drafts/progress: `/publishing/drafts`, `/ops/publish-health`, `/ops/publish-attempts`, `/ops/reconciliation`

### Existing backend routes

- Capture Inbox routes expose sessions/items with total counts and status filters.
- Candidate routes expose candidate lists but currently no total count or status aggregation in the public response.
- Reup Queue routes expose items with total count and status filtering.
- Export Package and Publish Handoff routes expose list totals but no status filtering.
- Publish Draft and Publish Attempt routes expose list endpoints with status filters but no total count in response.

### Data model availability

- Capture session/item models store status, reconciliation counts, timestamps, errors, and promoted candidate references.
- Candidate model stores status, score, priority, evaluated timestamps, and source video relation.
- Reup Queue model stores lifecycle status, media prep status, blocked/held/failed timestamps, action timestamps, error fields, export references, and publish draft references.
- Export Package model stores status, item count, ready/failed/cancelled timestamps, diagnostics, and handoff relation.
- Publish Handoff model stores status, target platform, ready/accepted/failed/cancelled timestamps, payload, and diagnostics.
- Publish Draft and Publish Attempt models store draft/attempt statuses, publish lifecycle timestamps, reconciliation flags, external publication status, and safe summary fields.

## Aggregation Direction

A dedicated API aggregation endpoint is preferred over browser-side fan-out because:

- Some existing endpoints do not return total counts.
- Some list routes lack status filters.
- The dashboard needs consistent stage status, attention severity, and recent activity across multiple tables.
- `apps/web` must remain UI-only and should not infer database-level workflow semantics.

Proposed endpoint:

- `GET /ops/pipeline-dashboard`

Proposed service:

- `PipelineDashboardService` in `apps/api/src/services/pipeline_dashboard_service.py`

Proposed route:

- `apps/api/src/api/routes/pipeline_dashboard.py`

Proposed schema:

- `apps/api/src/schemas/pipeline_dashboard.py`

## Status

- Audit: complete.
- Docs: created before implementation and updated after verification.
- API aggregation: complete.
- Web dashboard: complete.
- Tests: complete.
- Verification: complete for focused API and web checks.

## Implemented Files

### API

- `apps/api/src/schemas/pipeline_dashboard.py`
- `apps/api/src/services/pipeline_dashboard_service.py`
- `apps/api/src/api/routes/pipeline_dashboard.py`
- `apps/api/src/main.py`
- `apps/api/tests/test_pipeline_dashboard_service.py`

### Web

- `apps/web/src/types/operations.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/operator-routes/PipelineDashboardPage.tsx`
- `apps/web/src/app/ops/pipeline/page.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/test/reup-pipeline-dashboard.test.ts`
- `apps/web/src/test/route-nav.test.ts`
- `apps/web/package.json`

## Verification Log

- `python -m pytest apps/api/tests/test_pipeline_dashboard_service.py`
  - Result: failed because `pytest` is not installed in the active Python 3.11 environment.
- `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_pipeline_dashboard_service`
  - Result: passed, 2 tests.
- `npx tsx apps/web/src/test/reup-pipeline-dashboard.test.ts`
  - First result: failed because the source-level test expected every canonical quick link literal in the page source while some links were API-provided. The page was updated with a canonical href map.
  - Final result: passed.
- `npx tsx apps/web/src/test/route-nav.test.ts`
  - Result: passed.
- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`
  - Result: passed.
