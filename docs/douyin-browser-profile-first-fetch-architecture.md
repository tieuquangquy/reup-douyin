# Douyin Browser Profile First Fetch Architecture

## Objective

Use the connected Douyin account's persistent local browser profile as the primary local-dev fetch execution path, while preserving the canonical account, ingest, persistence, and candidate-discovery model.

## Why HTTP-First Was Too Fragile

The verified zero-video root cause showed that connected-account HTTP fetch can return a shell/challenge page. That page may include enough scaffolding to look like a profile response, but it does not expose the real video list.

Therefore, HTTP shell parsing is no longer the default connected-account happy path in local development.

## Canonical Pipeline Unchanged

The downstream pipeline remains:

```text
/intake
  -> IntakeDiscoveryService.discover()
  -> DouyinAccountService.build_douyin_adapter()
  -> DouyinLiveFetchClient obtains raw payload
  -> DouyinProfileAdapter.normalize_fetch_payload()
  -> SourceIngestService.ingest_profile()
  -> SourceProfile / SourceVideo / CrawlSession / VideoMetricSnapshot
  -> CandidateEvaluationService
```

No second account model exists.
No second persistence path exists.
No browser-only ingest service exists.

## Execution Path Selection Rules

### Primary: `browser_profile`

Used when:

- the selected/resolved account is a connected Douyin account,
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`,
- the account has persistent profile metadata or an active runtime browser context,
- the profile can be opened/reused.

Behavior:

- open or reuse the persistent profile through `DouyinBrowserContextRegistry`,
- navigate to the target profile,
- collect safe browser artifacts,
- return canonical raw payload for the existing adapter.

### Secondary: `http_html`

Used when:

- no reusable browser profile exists,
- the persistent profile cannot be opened,
- browser profile fetch is explicitly disabled.

### Recovery: `http_then_browser_fallback`

Used when:

- HTTP is attempted,
- HTTP returns shell/challenge/parse-zero classification,
- a browser fetch callback is available.

## Browser-Profile-Backed Fetch Lifecycle

1. `DouyinAccountService.resolve_runtime_config()` resolves account health, cookie, user-agent, and proxy.
2. `DouyinAccountService.build_fetch_client()` creates `DouyinLiveFetchClient` with a browser callback.
3. `DouyinLiveFetchClient.__call__()` tries browser-profile fetch first when configured.
4. `_fetch_profile_via_browser_context()` opens/reuses the persistent browser profile.
5. `DouyinBrowserContextRegistry.fetch_profile_page()` navigates the live browser page and collects:
   - Douyin-related JSON responses,
   - rendered video links,
   - rendered page status metadata.
6. `extract_profile_payload_from_browser_artifacts()` converts artifacts to `{profile, videos, metadata}`.
7. The existing adapter normalizes and the existing ingest service persists.

## Raw Payload Contract

Browser fetch returns the same broad shape as HTTP fetch:

```json
{
  "profile": {},
  "videos": [],
  "metadata": {
    "source": "douyin_browser_profile",
    "fetch_execution_path": "browser_profile",
    "response_shape": "browser_network_payload",
    "parse_strategy": "browser_response_documents"
  }
}
```

If only DOM video links are available, the browser extractor creates minimal video items with `aweme_id`, `share_url`, and `source_video_url`. The canonical adapter still owns normalization.

## Fallback Rules

- Browser profile unavailable -> fallback to HTTP.
- Browser profile classified as challenge/login/parse-zero -> return explicit failure; do not hide it behind HTTP.
- HTTP shell/challenge with browser callback -> attempt browser fallback and record `http_response_classification`.

## Observability

Crawl-session and Intake diagnostics include:

- `fetch_execution_path`
- `fallback_from_execution_path`
- `browser_profile_available`
- `browser_profile_unavailable_reason`
- `browser_fallback_attempted`
- `http_shell_detected`
- `parser_strategy`
- discovered/normalized/persisted counts
- final `fetch_stage_code`

No raw cookies, credential material, or local profile paths are exposed in UI.

## No-Duplication Strategy

The browser profile layer only changes how raw profile/video data is obtained. It does not:

- write `SourceProfile` or `SourceVideo` directly,
- create candidates,
- maintain a second account table,
- bypass `SourceIngestService`.

## Remaining Limits

- A browser profile can still reach a Douyin challenge page.
- If Playwright/profile opening fails, the system falls back to HTTP or returns a classified failure.
- Real profile success requires an actually logged-in and usable local browser profile.
