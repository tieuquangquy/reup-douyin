# intake-run-history-architecture.md

## Scope
Add operator-facing intake run history, run comparison, and failed-fetch troubleshooting on `/intake` using existing canonical ingestion models and services.

## Goals
- Provide fast read-only visibility into recent intake runs.
- Help operators compare two runs for the same profile/url context.
- Provide deterministic troubleshooting categories and next actions for failed or degraded runs.
- Keep UX action-oriented: quick actions should prefill intake form, not execute hidden automation.

## Canonical Source Of Truth

### Reused Entities
- `CrawlSession` in `apps/api/src/models/ingestion.py`
- `SourceProfile` in `apps/api/src/models/ingestion.py`
- `SourceVideo` in `apps/api/src/models/ingestion.py`

### Reused Orchestration
- `SourceIngestService.ingest_profile()` in `apps/api/src/services/source_ingest_service.py`
- `IntakeDiscoveryService.discover()` in `apps/api/src/services/intake_discovery_service.py`

No new run-tracking tables are introduced.

## Data Reuse Strategy (No Duplication)
- Run history rows are projections of `CrawlSession` + optional joined `SourceProfile`.
- Compare view computes deltas from two existing `CrawlSession` records.
- Troubleshooting signals are derived from persisted session fields:
  - `status`
  - `error_code`
  - `error_message`
  - count fields
  - `metadata_json` / `result_summary_json` (when available)
- Any missing troubleshooting context should be stored in existing session metadata channels, not separate tracking entities.

## API Design (Read-Only Summary Contracts)
Add minimal endpoints under intake route module (`apps/api/src/api/routes/intake.py`):

- `GET /intake/runs`
  - Query: workspace_id (optional), limit (default small), profile_url or profile_id optional filters.
  - Returns compact run list items for side panel.

- `GET /intake/runs/{crawl_session_id}`
  - Returns run detail with normalized troubleshooting summary + quick-action hints.

- `GET /intake/runs/compare`
  - Query: left_run_id, right_run_id.
  - Returns pair summary + deterministic deltas (status, duration, discovered/created/updated, candidate totals where available, error changes).

The contracts belong in `apps/api/src/schemas/intake.py`.

## Service Layer Design
Introduce a dedicated read service (new file planned):
- `apps/api/src/services/intake_run_history_service.py`

Responsibilities:
- Query and shape run summaries from canonical models.
- Build compare deltas from two sessions.
- Map troubleshooting categories from deterministic rules.
- Produce operator quick-action recommendations as structured payloads.

Non-responsibilities:
- No ingestion writes.
- No queue/job orchestration.
- No hidden retry side effects.

## Troubleshooting Mapping (Deterministic)
Primary categories (v1):
- `ACCOUNT_UNUSABLE`: account health/status gate or known account-related error codes.
- `AUTH_EXPIRED`: cookie/session invalid or auth-expired style error signals.
- `PROFILE_NOT_FOUND_OR_PRIVATE`: profile access/visibility failures.
- `RATE_LIMIT_OR_ANTIBOT`: rate-limit/challenge indications.
- `NETWORK_OR_TIMEOUT`: timeout/network transport failures.
- `UNKNOWN_FAILURE`: fallback.

Each category emits:
- `category`
- `severity`
- `why`
- `recommended_actions[]` (prefill/runbook-oriented)

## Web UI Design (`/intake`)
Add side-panel blocks in `apps/web/src/components/intake/IntakePage.tsx`:
- Run history list (recent runs, compact status, timestamp, profile hint).
- Compare runs panel (select two runs and inspect deltas).
- Troubleshooting panel (for selected run, shows category + actions).

UX principles:
- Do not introduce dashboard complexity.
- Quick actions only fill current intake form fields (profile url, account, force_live_fetch toggles, filter hints).
- Preserve existing status/guidance/productivity panels.

## Type/API Client Additions
- Extend `apps/web/src/types/intake.ts` with run list/detail/compare/troubleshooting response types.
- Extend `apps/web/src/lib/api.ts` with intake run-history fetch helpers.

## Testing Plan
- API/service tests:
  - New focused tests for run list, run detail, compare delta correctness, troubleshooting mapping determinism.
  - Route-level behavior for query validation and not-found handling.
- Web tests:
  - Intake page render/wiring for run history blocks.
  - Compare interaction and troubleshooting display.
- Keep tests local/offline, no external Douyin dependencies.

## Non-Goals (V1)
- No BI-style analytics dashboard.
- No new persistence model for run history.
- No automatic retry job execution from UI actions.
- No crawler/video processing redesign.

## Compatibility And Boundaries
- Follows `AGENTS.md` ownership:
  - API: stable read contracts + orchestration boundary.
  - Web: operator workflows and presentation only.
  - Shared logic remains dependency-light.
- Maintains local-first execution while keeping SaaS-ready boundaries by preserving canonical entities and clean API contracts.
