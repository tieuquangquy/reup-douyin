# Douyin Manual Import Hardening Architecture

## Goal

Manual-imported Douyin accounts must be normalized into the same runtime shape used by the canonical live-fetch path, so `/intake` can use them reliably without a separate manual-only pipeline.

## Canonical Runtime Session Shape

For live fetch, the runtime shape is:

- `session_cookie`: Cookie header string
- `user_agent`: non-empty browser User-Agent string
- `proxy_url`: optional proxy URL

`headers_json` may exist as source material, but the fetch client does not depend on arbitrary header bags as its primary contract.

## Supported Imported Formats

The manual import field may accept:

- raw Cookie header string
- `Cookie: ...` header line
- JSON cookie array export
- JSON object containing:
  - `cookies`
  - `cookie` / `Cookie`
  - `headers.Cookie`
  - `headers.User-Agent`

## Normalization Rules

1. Parse the imported payload.
2. Extract a canonical Cookie header string.
3. Extract a usable User-Agent from:
   - explicit `user_agent`
   - imported `headers.User-Agent`
4. Persist the normalized cookie string in `session_secret_blob`.
5. Persist the resolved User-Agent in `user_agent`.

## Validation Rules

Early validation errors:

- `imported_session_missing_cookie`
- `imported_session_missing_user_agent`
- `imported_session_invalid`

Post-import smoke validation outcomes:

- `usable_for_fetch`
- `login_required`
- `blocked_response`
- `invalid_session`

Only `usable_for_fetch` should allow the account to become healthy/usable for live fetch.

## No-Duplication Strategy

- Manual imports still use `DouyinAccountConnection`.
- `/intake` still resolves accounts through `DouyinAccountService`.
- `DouyinLiveFetchClient` remains the canonical transport.
- `SourceIngestService` remains the canonical ingest persistence path.
