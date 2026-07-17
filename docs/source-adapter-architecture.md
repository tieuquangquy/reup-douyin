# Source Adapter Architecture

Source adapters isolate platform-specific crawl and payload parsing from core ingest persistence. The goal is to add TikTok, Kuaishou, Xiaohongshu, or other short-video sources later without rewriting database ingest logic.

## Adapter Contract

Each adapter must provide:

- `source_platform`
- `validate_profile_url(profile_url)`
- `normalize_profile_identity(profile_url)`
- `fetch_profile(profile_url)`

The adapter returns both raw payload and normalized payload. Raw payload is for debugging and parser evolution. Normalized payload is the only data shape the ingest service should persist into canonical tables.

## Current Adapter

`DouyinProfileAdapter` supports:

- Douyin URL validation.
- Profile identity extraction from `/user/{id}`, `sec_uid`, or `@handle` style URLs.
- Mapping mocked or injected fetch payloads into normalized profile, video, and metric snapshot types.

The configured default adapter can inject `DouyinLiveFetchClient` when `DOUYIN_ENABLE_LIVE_FETCH=true`. The live client fetches public profile HTML and extracts embedded JSON payloads; it does not bypass captcha, login, or platform protection. If Douyin omits payloads or blocks the request, callers should use an existing ingested profile or dev fixture payload.

## Error Categories

```text
invalid_url
unsupported_profile
adapter_fetch_failed
normalization_failed
persistence_failed
rate_limited
```

These codes are written to `crawl_sessions.error_code` when ingest fails.

## Adding A New Platform

1. Add a platform enum if needed.
2. Implement `SourceAdapter`.
3. Return `NormalizedSourceProfile`, `NormalizedSourceVideo`, and `NormalizedMetricSnapshot`.
4. Register the adapter in `SourceIngestService`.
5. Add URL validation and normalization tests.

Core ingest should not contain platform-specific parsing.
