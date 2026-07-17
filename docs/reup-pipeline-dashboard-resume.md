# Reup Pipeline Dashboard Resume

## Current Goal

Implement a top-level operator dashboard for the full `reup_douyin` workflow so operators can see pipeline health and progress across:

Capture -> Review -> Reup Queue -> Export Package -> Publish Handoff -> Publish progress.

## Required Route

Use `/ops/pipeline` as the top-level operator dashboard route.

## Non-Goals

- Do not create a second workflow architecture.
- Do not replace Capture Inbox, Review Board, Reup Queue, Export Package, Publish Handoff, or Publish progress surfaces.
- Do not trigger crawling, video processing, rendering, scoring, queue orchestration, or publishing from the dashboard.
- Do not expose secrets, raw tokens, cookies, credentials, or unsafe local paths.
- Do not hardcode single-user assumptions into API contracts if avoidable.

## Completed So Far

- Read `AGENTS.md` and confirmed repository boundaries.
- Audited current web routes for pipeline stages.
- Audited existing API routes for Capture Inbox, Candidates, Reup Queue, Export Package / Publish Handoff, and Publish progress.
- Audited relevant schemas, models, services, and enums for count/status/timestamp availability.
- Created required docs before implementation.

## Important Files Already Audited

- `AGENTS.md`
- `apps/api/src/main.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/api/routes/candidates.py`
- `apps/api/src/api/routes/reup_queue.py`
- `apps/api/src/api/routes/export_handoff.py`
- `apps/api/src/api/routes/publish.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/schemas/reup_queue.py`
- `apps/api/src/schemas/export_handoff.py`
- `apps/api/src/schemas/publish.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/models/review.py`
- `apps/api/src/models/reup_queue.py`
- `apps/api/src/models/export_handoff.py`
- `apps/api/src/models/publish.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/services/candidate_service.py`
- `apps/api/src/services/reup_queue_service.py`
- `apps/api/src/services/export_handoff_service.py`
- `apps/api/src/services/publish_service.py`
- `apps/api/src/publish/services/publish_attempt_service.py`
- `apps/api/src/enums/__init__.py`
- `apps/web/src/lib/api.ts`
- Existing stage pages and Ops Console shared components under `apps/web/src/components`

## Implemented Steps

1. Added API schemas for pipeline dashboard summary, stage cards, attention items, recent activity, and quick links.
2. Added `PipelineDashboardService` with database aggregation queries.
3. Added `GET /ops/pipeline-dashboard` route and included it from `apps/api/src/main.py`.
4. Added web types and `fetchPipelineDashboard()` API client.
5. Created `apps/web/src/components/operator-routes/PipelineDashboardPage.tsx`.
6. Created `apps/web/src/app/ops/pipeline/page.tsx`.
7. Added tests:
   - API aggregation unit test.
   - Web dashboard source-level test.
   - Route/nav test updates for the new navigation link.
8. Ran focused verification and updated the log.

## Expected Dashboard Sections

- Header with health status and last refresh time.
- Pipeline summary strip.
- Stage-by-stage progress visualization.
- Stage cards for Capture, Review, Reup Queue, Export, Handoff, Publish.
- Attention / blocker panel.
- Recent activity feed.
- Quick actions / drill-down links to canonical surfaces.
- Clean loading, empty, and error states.

## Expected Metrics

- Captures in last 24h.
- Capture items ready for promotion.
- Capture failures.
- Review-ready backlog.
- Approved candidates not yet queued.
- Reup Queue active backlog.
- Queue items waiting for media or metadata.
- Queue failures needing retry or operator attention.
- Export-ready backlog.
- Export packages ready for handoff.
- Publish handoffs ready for operator.
- Publish drafts ready/scheduled/publishing/published.
- Publish attempts active/failed/needing reconciliation.

## Verification Completed

- `python -m pytest apps/api/tests/test_pipeline_dashboard_service.py`
  - Failed because `pytest` is not installed in the active Python 3.11 environment.
- `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_pipeline_dashboard_service`
  - Passed.
- `npx tsx apps/web/src/test/reup-pipeline-dashboard.test.ts`
  - Passed after correcting the dashboard source to expose canonical href constants.
- `npx tsx apps/web/src/test/route-nav.test.ts`
  - Passed.
- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`
  - Passed.
