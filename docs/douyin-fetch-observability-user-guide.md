# Douyin Fetch Observability User Guide

## Purpose

This guide explains how operators and developers can read Douyin intake fetch health using the canonical intake pipeline, run-history troubleshooting, and Ops metrics.

The implementation is additive and local-first:

- Canonical ingest path remains unchanged: [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:77) -> [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:47) -> [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88).
- Observability is persisted on existing crawl-session JSON fields, not a new pipeline.

## Where Observability Is Captured

### Adapter-level parse and blocked diagnostics

In [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88), each run now emits:

- `parse_strategy`
- `raw_video_item_count`
- `normalized_video_count`
- `drop_count`
- `drop_reasons`
- `blocked_reason`

Blocked reason normalization is provided by [`_blocked_reason_from_payload()`](apps/api/src/adapters/douyin.py:259).

### Ingest-stage timeline and persistence

In [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:47), stage results and diagnostics are written into crawl-session metadata/summary fields through shared helpers in [`fetch_observability.py`](apps/api/src/services/fetch_observability.py).

### Intake troubleshooting categories

[`IntakeRunHistoryService.troubleshooting_for()`](apps/api/src/services/intake_run_history_service.py:83) now prioritizes structured observability signals, including:

- `FETCH_BLOCKED_AUTH`
- `FETCH_BLOCKED_NETWORK`
- `FETCH_PARSE_SHAPE_CHANGED`
- `PARSE_OR_NORMALIZE_FAILED`

This allows operators to get targeted actions instead of generic failure messages.

## Where To View Fetch Health

## 1) Ops Console summary panel

The Ops homepage now includes a Douyin fetch-health panel in [`OpsHomePage`](apps/web/src/components/ops-console/OpsHomePage.tsx:17), showing:

- recent runs
- blocked runs
- parse warnings
- failed runs
- blocked ratio
- top blocked reasons
- account coverage count

Localized labels are in:

- English [`en.json`](apps/web/src/lib/i18n/en.json:192)
- Vietnamese [`vi.json`](apps/web/src/lib/i18n/vi.json:192)

## 2) Ops metrics API contract

Fetch health is included in [`OperationalMetricsResponse`](apps/api/src/schemas/operations.py:48) via:

- [`FetchHealthSummary`](apps/api/src/schemas/operations.py:38)
- [`FetchHealthReasonCount`](apps/api/src/schemas/operations.py:25)
- [`FetchHealthAccountSummary`](apps/api/src/schemas/operations.py:30)

Aggregation logic is implemented in [`OperationalMetricsService._douyin_fetch_health()`](apps/api/src/services/operational_metrics.py:154).

## 3) Web type contract

Frontend contract mirrors API shape in [`OperationalMetrics`](apps/web/src/types/operations.ts:41), including [`OpsFetchHealthSummary`](apps/web/src/types/operations.ts:31).

## Troubleshooting Playbook

### `login_required` / `challenge_required`

- Reconnect the Douyin account via browser connect.
- Validate account health in account management.
- Retry with explicit healthy account selection.

### `throttled_or_empty` / `network_forbidden`

- Wait before retrying.
- Avoid rapid repeated retries on one profile.
- Prefer a healthy account and calmer network window.

### `unsupported_shape`

- Capture run identifier and parser diagnostics.
- Escalate adapter/parser update.
- Use existing ingested profile fallback where available.

## Verification Snapshot

Validated in this step:

- Web typecheck: `npm --workspace @reup-douyin/web run typecheck`
- API focused tests (unittest):
  - [`test_douyin_adapter.py`](apps/api/tests/test_douyin_adapter.py)
  - [`test_intake_run_history_service.py`](apps/api/tests/test_intake_run_history_service.py)
  - [`test_operational_metrics_helpers.py`](apps/api/tests/test_operational_metrics_helpers.py)
  - [`test_operational_metrics_service.py`](apps/api/tests/test_operational_metrics_service.py)

## Notes

- Historical runs without observability fields are supported; defaults are safe.
- No secret material (cookies/tokens) is written into fetch-observability summaries.
