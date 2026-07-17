# Intake 500 Root Cause Architecture

## Goal

`/intake` must never collapse a canonical Douyin discovery failure into a generic unexplained 500 when the system can classify the failing stage.

## Canonical Discovery Path

1. `/intake` posts `IntakeDiscoverRequest`.
2. `IntakeDiscoveryService` normalizes the profile URL.
3. If live fetch is needed, it resolves a `DouyinAccountConnection`.
4. `DouyinAccountService` builds the canonical `DouyinProfileAdapter`.
5. `SourceIngestService` runs canonical ingest persistence.
6. `CandidateEvaluationService` filters and scores discovered videos.
7. Response returns either:
   - success summary
   - or a structured classified error

## Structured Error Boundary

The discovery path should return classified failures with:

- `code`
- `message`
- `stage`
- `diagnostics_id`

Suggested stage values:

- `normalize_profile_input`
- `resolve_account`
- `build_fetch_client`
- `dispatch_live_fetch`
- `classify_response`
- `normalize_payload`
- `persist_entities`
- `candidate_filtering`
- `unknown`

## Error Category Principles

Preferred error codes:

- `account_resolution_failed`
- `imported_session_invalid`
- `missing_required_headers`
- `missing_user_agent`
- `fetch_client_construction_failed`
- `login_required`
- `blocked_response`
- `parse_failed`
- `normalize_failed`
- `persistence_failed`
- `zero_videos`
- `zero_candidates`
- `unknown_server_error`

## Manual Import Compatibility

Manual-imported accounts must still use:

- `DouyinAccountConnection`
- `DouyinAccountService.resolve_runtime_config`
- `DouyinProfileAdapter`
- `SourceIngestService`

They do not get a separate fetch pipeline. The only special handling is runtime normalization of imported cookie material into a usable Cookie header string.

## Diagnostics Id

- Success runs already have `crawl_session_id`.
- Failure responses should include `diagnostics_id`.
- Backend logs should reference the same id and the failing stage.
