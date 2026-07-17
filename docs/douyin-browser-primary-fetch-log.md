# Douyin Browser Primary Fetch Log

## Step Name

Make browser-profile-backed fetch the default primary execution path for connected Douyin accounts in local development.

## Time Started

2026-04-23

## Findings

- `Settings.douyin_prefer_browser_profile_for_fetch` already defaults to `True`.
- `apps/api/.env.example` already sets `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`.
- `DouyinAccountService.build_fetch_client()` always injects a browser fetch callback for connected-account fetch.
- `DouyinLiveFetchClient.__call__()` already attempts browser-profile fetch before HTTP when `prefer_browser_profile` is true.
- HTTP remains available when browser profile fetch reports `browser_profile_unavailable` or `browser_context_unavailable`.
- Existing diagnostics include `fetch_execution_path`, but did not explicitly record the strategy policy or whether HTTP was used as a browser-primary fallback.

## Current Policy

Current connected-account local-dev policy is already functionally browser-first when configuration uses repo defaults:

```text
browser_profile -> HTTP fallback only if browser unavailable
```

## Chosen Browser-Primary Policy

- Browser profile is the default primary path for connected-account fetch.
- HTTP is a secondary fallback when the browser profile/runtime is unavailable.
- Browser-profile classified failures are returned explicitly and are not hidden behind HTTP.
- Canonical downstream ingest/discovery stays unchanged.

## Files Touched

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-primary-fetch-log.md`
- `docs/douyin-browser-primary-fetch-resume.md`
- `docs/douyin-browser-primary-fetch-architecture.md`
- `docs/douyin-browser-primary-fetch-user-guide.md`

## Implementation Notes

- Browser-primary behavior was already the default under repo config.
- Added explicit metadata:
  - `strategy_policy`
  - `primary_execution_path`
  - `final_execution_path_used`
  - `http_fallback_attempted`
  - `http_fallback_reason`
- Propagated these fields through adapter metadata, crawl-session summaries, API response schemas, web types, and `/intake` status UI.
- Kept HTTP fallback available when browser profile/runtime is unavailable.

## Verification Notes

- `python -m unittest tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- `python -m compileall src`
- `npm --workspace @reup-douyin/web run typecheck`

## Status

completed
