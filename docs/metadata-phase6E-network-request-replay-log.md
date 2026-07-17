# Phase 6E Network Request Replay Log

## Previous blocker

- Capture Inbox live items had `raw_dom_snapshot` only.
- `raw_network_aweme` and `raw_detail_aweme` stayed at zero in live audits.
- Per-video detail hydration was already implemented, but it remained operationally weak because browser context availability and block/captcha surfaces made one-detail-page-per-item unreliable.

## Audit findings

### Extension

- `apps/extension-douyin-capture/src/pageNetworkHook.ts` intercepts fetch/XHR and extracts aweme-like objects.
- It does **not** persist a replayable request template with:
  - request URL
  - method
  - body
  - cursor params
  - safe replay headers
- That makes extension-side request replay incomplete for Phase 6E.

### Backend browser context

- `apps/api/src/services/douyin_browser_context_registry.py` already has:
  - persistent browser profile open/reuse
  - authenticated browser-session navigation
  - response JSON capture during page navigation via `_fetch_page(...)`
- That is the safest place to discover candidate feed/profile requests and replay them with the same browser session.

### Backend normalization/update path

- `CaptureMetadataNormalizer` already converts `raw_network_aweme` into:
  - `duration_seconds`
  - `view_count`
  - `like_count`
  - `comment_count`
  - `share_count`
- Existing `CapturedItem` persistence already stores `raw_network_aweme` and evidence summaries.

## Chosen architecture

- Backend browser-side request discovery plus backend browser-session replay.
- Flow:
  1. open/reuse saved browser profile context
  2. load Douyin profile/feed page
  3. inspect network response JSON bodies
  4. detect candidate aweme-list requests by response body
  5. replay best request inside the same browser session
  6. paginate slowly if cursor fields are present
  7. batch update existing `CapturedItem` rows by exact `aweme_id`
  8. reuse `CaptureMetadataNormalizer`

## Non-goals

- no captcha bypass
- no extension-side request replay store
- no frontend Capture Inbox redesign
- no new normalizer path
- no per-video detail-page requirement

## Files expected

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/capture_inbox_request_replay_service.py`
- `apps/api/scripts/discover_and_replay_douyin_profile_requests.py`
- focused backend tests

## Status

- Audit complete
- Implemented backend browser-side discovery and replay

## Implemented behavior

- `douyin_browser_context_registry._fetch_page(...)` now returns in-memory `response_records` with:
  - safe request URL
  - request method
  - sanitized replay headers
  - bounded request body
  - parsed response JSON
- `douyin_browser_context_registry.replay_request(...)` now replays a captured request inside the same live browser context with `credentials: "include"`.
- `CaptureInboxRequestReplayService` now:
  - ensures browser context before discovery
  - detects candidate aweme-list requests from response JSON bodies
  - replays the strongest candidate
  - paginates slowly with cursor mutation when available
  - batch updates existing `CapturedItem` rows by exact `aweme_id`
  - reuses `CaptureMetadataNormalizer`

## Safety behavior

- request headers are sanitized before replay persistence/use
- query-string secret markers are stripped from operator-visible summaries
- replay stops on captcha/login/security wall markers
- unmatched `aweme_id` values are ignored
- no duplicate `CapturedItem` rows are created

## Tests run

- `python -m unittest tests.test_capture_inbox_request_replay_service tests.test_discover_and_replay_douyin_profile_requests_script`
- `python -m unittest tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_hydration_service`
- `python -m compileall src scripts`

## Verification result

- focused request replay tests passed
- existing normalizer/hydration tests passed
- compile check passed
