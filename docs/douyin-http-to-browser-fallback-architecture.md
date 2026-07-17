# Douyin HTTP To Browser Fallback Architecture

## Objective

When HTTP profile fetch returns a shell/challenge/login-required/parse-zero response for a connected Douyin account, automatically retry the raw fetch through the reusable browser profile when available.

## Canonical Pipeline Unchanged

Fallback changes only the raw fetch execution strategy:

```text
HTTP raw fetch
  -> classified failure
  -> browser-profile raw fetch
  -> DouyinProfileAdapter.normalize_fetch_payload()
  -> SourceIngestService.ingest_profile()
  -> canonical persistence and candidate discovery
```

No browser-only ingest path is introduced.

## Fallback Trigger Categories

HTTP response classifications that trigger browser fallback:

- `parse_zero_videos`
- `parse_failed`
- `blocked_response`
- `login_required`

Non-triggers:

- `true_zero_videos`
- `filter_zero_candidates`
- account resolution errors
- normalization or persistence errors after valid raw fetch

## Browser Availability Requirement

Fallback requires a browser fetch callback from the connected-account path. That callback is responsible for opening/reusing the persistent browser profile through the canonical browser context registry.

If browser fallback is unavailable or fails, the final error keeps:

- original HTTP classification,
- browser fallback attempt status,
- final browser classification when available.

## Orchestration Flow

1. HTTP fetch runs.
2. HTTP payload is classified by `_finalize_payload()`.
3. If classification raises and the code is a fallback trigger, invoke browser-profile fetch once.
4. If browser fetch succeeds, continue to adapter normalization and canonical ingest.
5. If browser fetch fails, return the browser failure with the HTTP classification attached.

## Implemented Control Point

The fallback lives in `DouyinLiveFetchClient.__call__()`.

The important implementation detail is that HTTP fallback handling must catch `SourceAdapterError` raised by `_finalize_payload(http_html)`. Without that, `parse_zero_videos` and `blocked_response` never reach fallback code because classification stops execution early.

Central policy:

```text
HTTP_TO_BROWSER_FALLBACK_CODES =
  parse_zero_videos
  parse_failed
  blocked_response
  login_required
```

`true_zero_videos` remains a warning and does not trigger browser fallback.

## Diagnostics Fields

Diagnostics include:

- `fetch_execution_path`
- `fallback_from_execution_path`
- `http_response_classification`
- `browser_fallback_attempted`
- `http_shell_detected`
- final `response_classification`

## No-Duplication Strategy

The fallback lives inside `DouyinLiveFetchClient`, the existing transport client. It returns the same raw payload shape and does not write database records directly.
