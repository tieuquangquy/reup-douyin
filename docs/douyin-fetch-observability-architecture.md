# Douyin Fetch Observability Architecture

## Scope

This step adds fetch observability for Douyin intake by extending the **existing canonical live-fetch pipeline** and exposing lightweight read models for operators.

Canonical path remains:

```text
/intake -> POST /intake/discover
  -> IntakeDiscoveryService.discover()
  -> SourceIngestService.ingest_profile()
  -> DouyinProfileAdapter fetch/normalize
  -> CrawlSession + SourceProfile + SourceVideo + VideoMetricSnapshot
  -> CandidateEvaluationService.apply()
```

No duplicate fetch pipeline is introduced.

## Goals

- Detect and classify blocked fetch responses with stable reason codes.
- Emit parse diagnostics (strategy, counts, drop reasons, fallback usage).
- Persist stage/result diagnostics in canonical crawl-session fields.
- Expose lightweight health aggregation for intake troubleshooting and Ops view.

## Non-Goals

- No crawler redesign.
- No queue/platform rewrite.
- No external observability stack.
- No secrets/raw cookies stored in logs.

## Diagnostic Data Model

### Stage timeline

Each crawl run has stage outcomes recorded in bounded JSON, keyed by stage:

- `account_resolution`
- `request_dispatch`
- `response_classification`
- `parse_payload`
- `normalize_payload`
- `persist_entities`
- `candidate_filter`

Each stage contains:

- `result`: `ok | warning | blocked | failed | skipped`
- `code`: stable machine code (for example `blocked.login_required`)
- `message`: safe, operator-facing short detail
- `ts`: optional timestamp
- `metrics`: small numeric payload (counts/durations)

### Blocked classification

Adapter/ingest classifies blocked outcomes into normalized reasons:

- `login_required`
- `challenge_required`
- `unsupported_shape`
- `throttled_or_empty`
- `network_forbidden`

These reasons map to canonical `error_code` patterns and stage result `blocked`.

### Parse diagnostics

Parse stage captures:

- parsing strategy key/name
- raw item count
- normalized item count
- dropped item count
- bounded top drop reasons
- fallback parser used (boolean)

## Persistence Strategy (No-Duplication)

Use existing [`CrawlSession`](apps/api/src/models/ingestion.py:63) JSON columns:

- `raw_summary_json`: source-level fetch/parse details
- `result_summary_json`: ingest and candidate/filter totals
- `metadata_json`: stage diagnostics and classification tags

No new table is required in this step.

## API Read Models

### Intake run history/troubleshooting

Enhance existing mapping in [`IntakeRunHistoryService.troubleshooting_for()`](apps/api/src/services/intake_run_history_service.py:83):

- Prioritize stage-based categories over coarse status-only heuristics.
- Distinguish blocked fetch vs parse-failed vs normalize/persist-failed vs filter-zero.
- Provide concrete recommended actions based on `blocked_reason` and parse metrics.

### Ops health endpoint

Extend ops domain by adding a read-only live-fetch health summary under existing ops API surface (same pattern as [`get_operational_metrics()`](apps/api/src/api/routes/operations.py:16)) with:

- recent crawl totals (window-limited)
- blocked count + ratio
- parse failure count + ratio
- zero-video normalized count
- top blocked reasons
- per-account health slice

## UI Integration

Add a lightweight panel into existing Ops console route [`OpsPage`](apps/web/src/app/ops/page.tsx:4):

- high-level health cards (success/blocked/parse failure)
- top blocked reasons list
- per-account table (recent success %, blocked %, parse issues)

No custom charting framework required.

## Contract and Type Strategy

- Add schema(s) in API ops/intake schema modules.
- Mirror types in web [`operations.ts`](apps/web/src/types/operations.ts:18) and intake types if troubleshooting payload shape evolves.
- Keep fields optional/backward compatible where appropriate.

## Testing Strategy

- Adapter classification unit tests for blocked reason mapping.
- Ingest diagnostics unit tests for stage/result persistence.
- Intake run history tests for category/action mapping with new signals.
- Ops aggregation tests for counts/ratios/reason ranking.
- API contract tests for new endpoint payload shape.

## Security and Logging

- Never persist raw session cookies or credential material.
- Keep messages sanitized and bounded.
- Include stable identifiers only when safe (`crawl_session_id`, `douyin_account_connection_id`, `source_profile_id`).

## Rollout Notes

- Default behavior remains compatible with current intake flow.
- Observability fields are additive and safe for partial availability.
- Dashboard must tolerate absent diagnostics for historical runs.
