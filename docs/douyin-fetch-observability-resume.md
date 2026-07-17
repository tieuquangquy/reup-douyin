# Douyin Fetch Observability Resume

## Current Step

Docs-first observability specification and audit are completed; implementation is next.

## Done

- Completed cross-cut audit required by [`AGENTS.md`](AGENTS.md):
  - canonical intake/ingest/adapter/history/ops paths
  - existing live-fetch docs and account-health docs
  - web intake + ops integration surfaces
- Confirmed extension points without duplicating pipeline:
  - [`CrawlSession`](apps/api/src/models/ingestion.py:63) diagnostics JSON fields
  - [`IntakeRunHistoryService.troubleshooting_for()`](apps/api/src/services/intake_run_history_service.py:83)
  - [`OperationalMetricsService`](apps/api/src/services/operational_metrics.py:24) + [`/ops`](apps/api/src/api/routes/operations.py:8)
- Created docs-first artifacts:
  - [`docs/douyin-fetch-observability-log.md`](docs/douyin-fetch-observability-log.md)
  - [`docs/douyin-fetch-observability-architecture.md`](docs/douyin-fetch-observability-architecture.md)
  - [`docs/douyin-fetch-observability-resume.md`](docs/douyin-fetch-observability-resume.md)

## In Progress

- Implement canonical stage/result diagnostic model and no-duplication mapping in API ingest flow.

## Next Exact Task

1. Add typed diagnostic helpers/constants in API service/adapter layer.
2. Emit blocked classification and parse metrics during adapter fetch/normalize.
3. Persist diagnostics into crawl-session summary/metadata fields in ingest service.
4. Extend run-history troubleshooting to consume these diagnostics.
5. Add read-only ops fetch-health aggregation endpoint and web panel.
6. Add/adjust tests and run verifications.

## Key Files To Continue

- [`apps/api/src/adapters/douyin.py`](apps/api/src/adapters/douyin.py)
- [`apps/api/src/services/source_ingest_service.py`](apps/api/src/services/source_ingest_service.py)
- [`apps/api/src/services/intake_run_history_service.py`](apps/api/src/services/intake_run_history_service.py)
- [`apps/api/src/services/operational_metrics.py`](apps/api/src/services/operational_metrics.py)
- [`apps/api/src/api/routes/operations.py`](apps/api/src/api/routes/operations.py)
- [`apps/api/src/schemas/operations.py`](apps/api/src/schemas/operations.py)
- [`apps/web/src/lib/api.ts`](apps/web/src/lib/api.ts)
- [`apps/web/src/types/operations.ts`](apps/web/src/types/operations.ts)
- [`apps/web/src/app/ops/page.tsx`](apps/web/src/app/ops/page.tsx)
- [`apps/web/src/components/ops-console`](apps/web/src/components/ops-console)

## Risks / Watchouts

- Keep diagnostics additive and backward compatible for historical runs.
- Avoid high-cardinality payloads in JSON summaries.
- Do not leak secret session material in any logs or response payloads.
