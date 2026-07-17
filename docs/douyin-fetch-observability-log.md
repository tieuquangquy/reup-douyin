# Douyin Fetch Observability Log

## Findings

- Canonical live-fetch path already exists and must remain the single ingest pipeline: [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:77) -> [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:39) -> adapter normalize/persist -> candidate evaluation.
- Existing persistence already carries useful diagnostics containers on [`CrawlSession`](apps/api/src/models/ingestion.py:63): `error_code`, `error_message`, `raw_summary_json`, `result_summary_json`, `metadata_json`, `raw_payload_json`.
- Existing intake troubleshooting currently infers categories from coarse status/error heuristics in [`IntakeRunHistoryService.troubleshooting_for()`](apps/api/src/services/intake_run_history_service.py:83).
- Existing ops metrics endpoint [`GET /ops/metrics`](apps/api/src/api/routes/operations.py:15) and service [`OperationalMetricsService.get_metrics()`](apps/api/src/services/operational_metrics.py:28) provide a safe pattern for adding lightweight read-only health slices.
- Adapter-level live fetch currently lacks structured blocked/parse diagnostics classification in [`DouyinProfileAdapter.fetch_profile()`](apps/api/src/adapters/douyin.py:70) and [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88).

## Existing Architecture Inventory

- Ingest orchestration: [`apps/api/src/services/intake_discovery_service.py`](apps/api/src/services/intake_discovery_service.py)
- Canonical persistence: [`apps/api/src/services/source_ingest_service.py`](apps/api/src/services/source_ingest_service.py)
- Douyin adapter boundary: [`apps/api/src/adapters/douyin.py`](apps/api/src/adapters/douyin.py)
- Run history + troubleshooting: [`apps/api/src/services/intake_run_history_service.py`](apps/api/src/services/intake_run_history_service.py)
- Intake API contracts: [`apps/api/src/schemas/intake.py`](apps/api/src/schemas/intake.py), [`apps/web/src/types/intake.ts`](apps/web/src/types/intake.ts)
- Ops metrics baseline: [`apps/api/src/services/operational_metrics.py`](apps/api/src/services/operational_metrics.py), [`apps/api/src/schemas/operations.py`](apps/api/src/schemas/operations.py), [`apps/web/src/types/operations.ts`](apps/web/src/types/operations.ts)
- Ops route shell: [`apps/web/src/app/ops/page.tsx`](apps/web/src/app/ops/page.tsx)

## Decisions Made

- Reuse the canonical ingest path only; no secondary fetch or observability pipeline.
- Represent observability with structured stage diagnostics stored in existing crawl-session summary/metadata JSON fields.
- Keep blocked detection and parse diagnostics at adapter + ingest orchestration boundaries, then expose summarized read models through intake history and ops read-only endpoints.
- Keep dashboard scope lightweight: health summary card/panel in existing Ops console, not a BI subsystem.
- Keep safety constraints strict: never log raw cookies/session token; only store normalized reason/category codes and bounded counters.

## Planned Stage/Result Model (Draft)

- `fetch_stage`: `account_resolution`, `request_dispatch`, `response_classification`, `parse_payload`, `normalize_payload`, `persist_entities`, `candidate_filter`
- `stage_result`: `ok`, `warning`, `blocked`, `failed`, `skipped`
- `blocked_reason`: `login_required`, `challenge_required`, `unsupported_shape`, `throttled_or_empty`, `network_forbidden`
- Parse summary fields: strategy key, raw item count, normalized item count, dropped count, top drop reasons, fallback used.
- Persistence/filter summary fields: upsert counts, snapshot counts, matched/filtered candidate counts.

## Files Touched

- [`docs/douyin-fetch-observability-log.md`](docs/douyin-fetch-observability-log.md)

## Verification Notes

- Audit completed across AGENTS, intake/ingest/adapter/history/ops code paths.
- No implementation changes in this log step.

## Status

In progress for observability implementation plan and docs-first gate.
