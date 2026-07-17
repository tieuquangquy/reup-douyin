# Douyin Browser Profile First Fetch Log

## Step Name

Make browser-profile-backed profile fetch the primary local-dev strategy for connected Douyin accounts.

## Time Started

2026-04-23T19:29:50+07:00

## Findings

- The canonical `/intake` account-backed path is still:
  - `IntakeDiscoveryService.discover()`
  - `DouyinAccountService.build_douyin_adapter()`
  - `DouyinLiveFetchClient`
  - `DouyinProfileAdapter.normalize_fetch_payload()`
  - `SourceIngestService.ingest_profile()`
  - canonical `SourceProfile`, `SourceVideo`, `CrawlSession`, `VideoMetricSnapshot`, and candidate evaluation.
- Persistent profile identity is already stored on `DouyinAccountConnection.metadata_json` as `browser_profile_id`, `browser_profile_path`, and `browser_profile_mode`.
- `DouyinAccountService.build_fetch_client()` now passes a browser fetch callback into `DouyinLiveFetchClient`.
- `DouyinLiveFetchClient` supports `browser_profile`, `http_html`, and `http_then_browser_fallback` execution paths.
- The previous fragile point was HTTP shell parsing: HTTP could return a shell/challenge page and the old parser path could end as zero videos.

## Current HTTP-First Limitations

- HTTP HTML fetch is easy to challenge or shell-block.
- A shell response can contain enough page scaffolding to look superficially valid.
- Zero videos from a shell response is not the same as a true zero-video profile.
- Browser probing alone improves diagnosis but does not recover data.

## Chosen Browser-Profile-First Strategy

- For connected-account local-dev discovery, prefer the persistent browser profile when `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`.
- Browser-profile fetch reuses/reopens the account's persistent browser profile through the existing registry.
- Browser-profile fetch extracts browser network JSON responses and rendered `/video/` links.
- Raw browser artifacts are converted into the same `{profile, videos, metadata}` shape consumed by the existing adapter.
- HTTP HTML fetch remains a fallback when the browser profile is unavailable.

## Files Touched

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-browser-profile-first-fetch-log.md`
- `docs/douyin-browser-profile-first-fetch-resume.md`
- `docs/douyin-browser-profile-first-fetch-architecture.md`
- `docs/douyin-browser-profile-first-fetch-user-guide.md`

## Verification Notes

- `python -m unittest tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- `python -m compileall src`
- `npm --workspace @reup-douyin/web run typecheck`

Live Douyin profile success still requires an operator-owned logged-in persistent browser profile. The code now makes that profile the primary path; if Douyin still blocks the browser profile, the run should fail with an explicit classified stage/code rather than a vague zero-candidate result.

## Status

completed
