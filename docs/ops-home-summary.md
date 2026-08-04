# Ops Home Summary

`GET /ops/home-summary` is the canonical read model for the Ops Console Home page.

## Purpose

The browser previously composed operational metrics, publish health, and the publish control queue independently. That made priority rules a frontend concern and produced three freshness timestamps. The summary endpoint now owns the composition and returns one stable contract for the Home control tower.

## Authorities

- `OperationalMetricsService`: durable jobs, render state, open risk, failure signatures, and Douyin fetch health.
- `PublishHealthService`: seven-day publish outcomes and reconciliation state.
- `ControlQueueService`: account health and publishing assignment queues.

The endpoint does not mutate jobs, drafts, risk decisions, accounts, or publishing state.

## Response sections

- `overall`: one status, headline, detail, and critical/warning totals.
- `freshness`: summary time plus each source authority timestamp.
- `kpis`: compact decision metrics with canonical display values and deep links.
- `action_items`: non-zero issues ordered by severity and impact.
- `job_health`: type/status counts, failure rate, and observed step duration.
- `account_health`: hold/cooldown, seven-day outcomes, load, and recent error context.
- `publish_trend`: seven-day publish outcome series.
- `failure_signatures`: ranked job and publishing error categories.
- `fetch_health`: recent run summary, account breakdown, and blocked reasons.
- `operational_status`: compact job/output/publish/account/fetch boundary states.
- `queue_health`: backlog age, running lock coverage, busy-worker signals, retries, failures, and manual-review load.
- `dependencies`: observed API/database/storage/FFmpeg signals plus explicit `not_observed` states for dependencies without a safe canonical probe.
- `storage_capacity`: local storage headroom without exposing the configured private path.

## Decision rules

- Zero-count action rows are omitted.
- A publish window with zero attempts is `No activity`, not `0% success`.
- Critical actions produce `blocked`; warnings produce `needs_attention`.
- `critical_count` and `warning_count` count distinct signals, not affected rows, so overlapping job/render/risk conditions are not presented as unique incidents.
- Tables are sorted by operational severity before volume.
- Publish and account authorities are scoped to the authenticated workspace.
- Publish-control totals are calculated independently from the bounded detail list.

## Current limitations

- The summary exposes oldest backlog age, but not last failure time or P50/P95 duration.
- API/database readiness means the current summary queries completed; it is not an independent synthetic availability check.
- Redis, idle-worker heartbeat, and AI provider health remain `not_observed` until dedicated registries/probes exist.
- Storage capacity is read-only. A storage read/write synthetic probe is still pending.
- Publishing is currently summarized for Facebook Reels; a cross-platform aggregate is planned when more connectors are introduced.
