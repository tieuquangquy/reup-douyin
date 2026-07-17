# Douyin Hard Reset Log

## Audit Findings

- The canonical downstream pipeline is usable and should remain unchanged:
  `DouyinProfileAdapter -> SourceIngestService -> SourceProfile/SourceVideo/CrawlSession/VideoMetricSnapshot -> CandidateEvaluationService`.
- Browser-profile fetch already exists through:
  - `DouyinAccountService.build_fetch_client()`
  - `DouyinLiveFetchClient(browser_fetch=...)`
  - `DouyinBrowserContextRegistry.fetch_profile_page()`
  - `extract_profile_payload_from_browser_artifacts()`
- The remaining reliability problem is policy and primary-path clarity:
  - preflight still allows `fetch_ready_http_fallback` for connected accounts when browser profile is missing/unavailable,
  - `DouyinLiveFetchClient` can still silently degrade from browser-profile primary to HTTP fallback on browser unavailability,
  - `/accounts/douyin` still exposes manual import as a fallback surface in the same page,
  - previous docs and UI still mention HTTP fallback as a normal readiness category.
- The strongest root cause remains the same: HTTP HTML fetch often receives shell/challenge surfaces, so it is not a reliable primary discovery method.
- Manual import remains useful for diagnostics but is not reliable enough to be the main operator path.

## Chosen Primary Path

For local development, the primary path is now:

1. create/open a connected Douyin account with a persistent local browser profile,
2. login through that profile,
3. validate using that same profile,
4. run `/intake` using browser-profile-backed fetch,
5. feed the browser-extracted raw payload into the existing canonical ingest/discovery pipeline.

## Legacy Paths Demoted

- Manual session import is legacy/troubleshooting only.
- HTTP HTML fetch is legacy fallback only, disabled by default for connected-account Intake.
- HTTP fallback may be explicitly re-enabled with `DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE=true`.

## Files Touched

- `apps/api/src/core/settings.py`
- `apps/api/.env.example`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_run_history_service.py`
- `apps/api/tests/test_douyin_account_preflight.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-hard-reset-log.md`
- `docs/douyin-hard-reset-resume.md`
- `docs/douyin-hard-reset-architecture.md`
- `docs/douyin-hard-reset-user-guide.md`

## Implementation Decisions

- `DouyinLiveFetchClient` no longer allows legacy HTTP fallback by default.
- `DouyinAccountService.build_fetch_client()` passes the explicit setting
  `DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE`, which defaults to `false`.
- Intake preflight now fails with `browser_profile_required` when a connected
  account lacks a reusable browser profile and legacy HTTP fallback is disabled.
- Intake preflight now fails with `browser_profile_unavailable` when the saved
  profile cannot be reopened and legacy HTTP fallback is disabled.
- Browser profile fetch now waits briefly and scrolls the rendered profile page
  before extracting browser network JSON and rendered `/video/` links.
- Fetch observability now carries `legacy_http_fallback_allowed`.
- `/accounts/douyin` no longer promotes manual import from active runtime status.
  Manual import remains collapsed as legacy troubleshooting only.
- `/intake` wording now labels HTTP execution/readiness as legacy fallback.

## Verification Notes

- Passed focused API tests:
  `python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_live_fetch tests.test_douyin_account_service`
- Passed API compile:
  `python -m compileall src`
- Passed web typecheck:
  `npm --workspace @reup-douyin/web run typecheck`
- Passed full smoke:
  `npm run smoke`
- Runtime route smoke passed:
  - `GET http://localhost:3000/accounts/douyin -> 200`
  - `GET http://localhost:3000/intake -> 200`
  - `GET http://localhost:8000/docs -> 200`
  - `GET http://localhost:8000/douyin-accounts -> 200`
- Live account inventory showed one active account, but it did not have a
  reusable browser profile attached. Therefore a real logged-in Douyin
  browser-profile discovery run could not be completed in this pass without
  operator login/reconnect.

## Status

Completed for code, policy, docs, tests, and local route smoke.

Remaining live-operation requirement: create or reopen a browser-profile-backed
Douyin account from `/accounts/douyin`, complete login in that profile, then run
`/intake` against a real profile. The rebuilt primary path will require that
profile and will fail early with `browser_profile_required` or
`browser_profile_unavailable` instead of silently using HTTP shell parsing.
