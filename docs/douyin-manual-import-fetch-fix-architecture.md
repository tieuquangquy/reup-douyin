# Douyin Manual Import Fetch Fix Architecture

## Goal

Manual-session-imported Douyin accounts must be first-class inputs to the existing account-backed intake flow. They must not use a separate manual-only discovery pipeline.

## Canonical Flow

1. Operator imports a manual Douyin session in `/accounts/douyin`.
2. API persists a `DouyinAccountConnection`.
3. Runtime session material is normalized into a safe internal Cookie header representation.
4. `/intake` submits `douyin_account_connection_id`.
5. `IntakeDiscoveryService` resolves the selected account through `DouyinAccountService`.
6. `DouyinAccountService` builds the canonical `DouyinProfileAdapter`.
7. `SourceIngestService` runs the canonical ingest/persistence flow using that adapter.
8. Candidate filtering/scoring runs on the canonical persisted `SourceVideo` rows.

## Manual Import Persistence Model

- `DouyinAccountConnection` remains the only persisted account model.
- `session_secret_blob` stores the real session material encoded for local storage.
- API responses expose only `session_cookie_present` and a masked preview.
- `metadata_json.connection_source=manual_import` identifies the account source for operator visibility.

## Session Normalization Rules

Accepted manual inputs:

- Raw `Cookie` header string.
- `Cookie: ...` header line.
- JSON array of browser cookie objects with `name` and `value`.
- JSON object containing `cookies`.
- JSON object containing `headers.Cookie` or `cookie`.

The runtime representation is always a Cookie header string such as `name=value; name2=value2`.

## Validation And Fetch Consistency

- Validation and live fetch both resolve runtime config through `DouyinAccountService`.
- If a manual import is missing usable session material, both validation and fetch must fail with the same class of diagnostic.
- Validation must not mark an account healthy when the runtime fetch client cannot build a usable request.

## Diagnostics

The `/intake` route should expose structured error details:

- `imported_session_missing_cookie`
- `imported_session_invalid`
- `imported_session_missing_user_agent`
- `account_resolution_failed`
- `blocked_response`
- `login_required`
- `parse_failed`
- `zero_videos`
- `filter_zero_candidates`
- `unknown_server_error`

## No-Duplication Strategy

Manual import changes only account runtime normalization and error diagnostics. It does not add a second intake service, second fetch client, or second persistence path.
