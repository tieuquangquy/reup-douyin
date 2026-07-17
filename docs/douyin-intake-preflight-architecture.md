# Douyin Intake Preflight Architecture

## Objective

Before `/intake` starts a real Douyin profile discovery run, verify that the selected/resolved account is fetch-ready and that the preferred browser-profile path can be used or safely degraded.

## Preflight Sequence

```text
/intake
  -> normalize profile URL
  -> resolve selected/default/fallback Douyin account
  -> preflight_fetch_readiness(account)
  -> build account-backed adapter
  -> SourceIngestService.ingest_profile()
  -> CandidateEvaluationService
```

Preflight happens before canonical ingest starts. It does not write `SourceProfile`, `SourceVideo`, or candidates.

## Fetch-Readiness Categories

### `fetch_ready_browser_profile`

- Account health allows live fetch.
- Persistent browser profile/runtime is already active.
- Selected path is `browser_profile`.

### `fetch_ready_after_browser_reopen`

- Account health allows live fetch.
- Persistent browser profile exists but was not active.
- Backend reopened the same saved profile once.
- Selected path is `browser_profile`.

### `fetch_ready_http_fallback`

- Account health allows live fetch.
- Browser profile is unavailable or absent.
- Cookie/User-Agent material exists for HTTP fallback.
- Selected path is `http_html`.

### `fetch_not_ready`

- Account is blocked/invalid/disabled/not usable.
- Or browser profile cannot be reopened and HTTP material is insufficient.
- Intake fails before full discovery starts.

## Auto Reopen Policy

If browser-profile fetch is preferred and account metadata has a saved profile id/path:

1. Inspect current runtime context.
2. If active, pass preflight.
3. If not active, attempt one reopen through `DouyinBrowserContextRegistry.open_profile_for_account()`.
4. If reopen succeeds, proceed with browser-profile fetch.
5. If reopen fails, use HTTP fallback only if session material is usable.

No new profile identity is created during preflight.

## Result Mapping

Successful Intake responses expose:

- `preflight_ran`
- `preflight_result`
- `fetch_readiness_category`
- `selected_fetch_path`
- `browser_reopen_attempted`
- `browser_reopen_result`

Preflight failures return structured API error details under `detail.details.preflight`.

## Canonical Pipeline Unchanged

The actual discovery pipeline remains:

```text
DouyinProfileAdapter
  -> SourceIngestService
  -> SourceProfile / SourceVideo / CrawlSession / VideoMetricSnapshot
  -> CandidateEvaluationService
```

No second fetch or persistence pipeline is introduced.

## Remaining Limits

- Preflight can prove obvious readiness, but it cannot guarantee Douyin will not challenge the actual profile page.
- HTTP fallback can still be less reliable than browser-profile fetch.
- Browser reopen depends on local Playwright/browser runtime availability.
