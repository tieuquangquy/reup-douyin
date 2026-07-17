# Douyin HTTP To Browser Fallback Log

## Step Name

Automatic fallback from HTTP shell/challenge responses to browser-profile-backed fetch.

## Time Started

2026-04-23

## Findings

- Connected-account discovery is assembled in `DouyinAccountService.build_fetch_client()` and executed by `DouyinLiveFetchClient`.
- Browser-profile-backed fetch already exists as a callback passed into the same live fetch client.
- The downstream pipeline remains canonical: `DouyinProfileAdapter -> SourceIngestService -> SourceProfile/SourceVideo/CrawlSession -> CandidateEvaluationService`.
- HTTP response classifications already include `parse_zero_videos`, `parse_failed`, `blocked_response`, `login_required`, and `true_zero_videos`.
- Current fallback orchestration is placed after `_finalize_payload(http_html)`.
- `_finalize_payload(http_html)` raises `SourceAdapterError` for non-warning classifications, so the existing fallback block is skipped for key triggers like `parse_zero_videos` and `blocked_response`.

## Current Orchestration Points

- HTTP fetch: `DouyinLiveFetchClient.fetch_html()`
- HTTP classification: `DouyinLiveFetchClient._finalize_payload()`
- Browser profile fetch: `DouyinAccountService._fetch_profile_via_browser_context()`
- Browser context reuse: `DouyinBrowserContextRegistry.fetch_profile_page()`
- Canonical ingest: `SourceIngestService.ingest_profile()`

## Chosen Fallback Triggers

HTTP classifications that should trigger browser fallback when a browser callback is available:

- `parse_zero_videos`
- `parse_failed`
- `blocked_response`
- `login_required`

Non-trigger:

- `true_zero_videos`

## Files Touched

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `docs/douyin-http-to-browser-fallback-log.md`
- `docs/douyin-http-to-browser-fallback-resume.md`
- `docs/douyin-http-to-browser-fallback-architecture.md`
- `docs/douyin-http-to-browser-fallback-user-guide.md`

## Implementation Notes

- Moved HTTP fallback handling into the `SourceAdapterError` path raised by `_finalize_payload(http_html)`.
- Added centralized `HTTP_TO_BROWSER_FALLBACK_CODES`.
- Added `_should_browser_fallback_from_http()` and `_fetch_with_browser_fallback()` in `DouyinLiveFetchClient`.
- Fallback runs at most once and only when a browser fetch callback exists.
- If browser fallback succeeds, the final payload uses `fetch_execution_path = http_then_browser_fallback`.
- If browser fallback fails, the final error payload includes both:
  - `http_response_classification`
  - browser final `response_classification`

## Verification Notes

- `python -m unittest tests.test_douyin_live_fetch`
- `python -m unittest tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- `python -m compileall src`
- `npm --workspace @reup-douyin/web run typecheck`

## Status

completed
