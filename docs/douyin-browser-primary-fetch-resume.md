# Douyin Browser Primary Fetch Resume

## Current Step

Completed: browser-primary policy is explicit in fetch diagnostics, API response, `/intake` UI, and docs.

## Done

- Audited current config defaults.
- Audited `DouyinAccountService.build_fetch_client()`.
- Audited `DouyinLiveFetchClient.__call__()`.
- Confirmed browser-profile-backed fetch is already attempted first under local defaults.
- Added strategy-policy diagnostics through API and web surfaces.
- Added tests covering browser-primary success and HTTP fallback when browser profile is unavailable.
- Verified API tests, API compile, and web typecheck.

## In Progress

- None.

## Next Exact Task

Run a live connected-account discovery and confirm `/intake` shows:

- `Fetch strategy: Browser profile first`
- `Fetch path: Browser profile`
- or, if browser profile is unavailable, `Fetch path: HTTP HTML` with HTTP fallback detail.

## Key Files To Continue

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/tests/test_douyin_live_fetch.py`

## Guardrails

- Keep one canonical account model.
- Keep one canonical ingest/discovery pipeline.
- Keep HTTP fallback available when browser runtime/profile is unavailable.
- Do not log cookies or local private paths.
