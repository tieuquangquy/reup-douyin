# Douyin Extension Capture Pivot Architecture

## Summary

The Douyin collection architecture is pivoting from Playwright-managed runtime as the primary path to browser-extension current-tab capture. The operator uses their real Chrome or Edge session, logs in manually, solves any challenge manually, opens the desired Douyin page manually, and asks the extension to detect or capture the current visible tab.

The extension is an input adapter, not a new downstream pipeline. Once the backend receives a safe current-tab payload, it maps the payload into the existing Douyin adapter payload shape and reuses the canonical ingest, metric snapshot, candidate filtering, and review flow.

## Goals

- Make the reliable human-driven browser session the primary Douyin collection path.
- Reduce managed runtime instability from reopen, attach, first-page-close, cooldown, and challenge loops.
- Capture visible current-tab data without raw credential or session export.
- Reuse canonical backend entities and services.
- Keep legacy Playwright-managed paths available only for debug/legacy use.

## Non-goals

- No crawler.
- No automated login.
- No automated challenge solving.
- No auto-navigation probe loop.
- No raw cookie/session/header/local-storage capture.
- No new downstream source/video/candidate persistence architecture.
- No unrelated account health, worker, or publishing rewrite.

## Ownership Boundaries

### Extension

The extension owns current-tab detection and visible DOM extraction from the operator's real browser session.

It may collect:

- Current tab URL.
- Current tab title.
- Page type.
- Safe page metadata.
- Likely profile URL.
- Visible video links/cards.
- Visible captions/titles.
- Visible metrics.
- Minimal diagnostics such as extraction version and item counts.

It must not collect:

- Cookies.
- Authorization headers.
- Local storage/session storage tokens.
- Browser profile paths.
- Raw full HTML dumps.
- Screenshots unless explicitly introduced later with a privacy review.
- Credentials.

### API

The API owns validation, canonical mapping, ingest coordination, candidate filtering, and response contracts.

The API should expose local/dev friendly routes such as:

- `POST /douyin-extension/detect-page`
- `POST /douyin-extension/capture-current-page`

The API must not leak database, queue, worker, or storage internals through these contracts.

### Web

The web app owns operator guidance and review surfaces. It should present extension capture as the primary Douyin collection flow. Managed-runtime controls may remain behind legacy/debug wording only.

## Page Type Detection

The shared page taxonomy for the extension and backend is:

- `login_page`: login or authentication page.
- `challenge_page`: captcha, risk control, verification, blocked/challenge surface.
- `home_feed_page`: general Douyin feed or homepage.
- `profile_page`: profile landing page.
- `profile_feed_page`: profile page with visible video cards/feed items.
- `video_detail_page`: individual Douyin video page.
- `unsupported_page`: a non-Douyin or unsupported Douyin page where capture should not ingest.
- `unknown_page`: Douyin-like page where detection is inconclusive.

Detection should be conservative. Login and challenge pages should produce guidance, not ingest attempts.

## Extension Payload Schema

The extension capture payload should be safe, explicit, and versioned.

Conceptual shape:

```json
{
  "schema_version": "douyin_extension_capture.v1",
  "capture_id": "client-generated-id",
  "captured_at": "2026-04-26T15:00:00Z",
  "page": {
    "url": "https://www.douyin.com/user/...",
    "title": "...",
    "page_type": "profile_feed_page",
    "profile_url": "https://www.douyin.com/user/...",
    "profile_external_id": "MS4wLjAB...",
    "handle": "optional_handle",
    "display_name": "optional display name"
  },
  "profile": {
    "id": "MS4wLjAB...",
    "sec_uid": "MS4wLjAB...",
    "handle": "optional_handle",
    "display_name": "optional display name"
  },
  "videos": [
    {
      "id": "video id when available",
      "source_video_url": "https://www.douyin.com/video/...",
      "title": "visible caption/title",
      "desc": "visible description when available",
      "statistics": {
        "like_count": 123,
        "comment_count": 4,
        "share_count": 5,
        "favorite_count": 6,
        "view_count": null
      }
    }
  ],
  "diagnostics": {
    "extension_version": "0.1.0",
    "visible_video_count": 12,
    "extractor": "content_script_dom_v1"
  }
}
```

## Backend Canonical Mapping

The backend maps the extension payload into the existing `DouyinProfileAdapter.normalize_fetch_payload(...)` raw payload shape:

```json
{
  "profile": {
    "id": "...",
    "sec_uid": "...",
    "handle": "...",
    "display_name": "..."
  },
  "videos": [
    {
      "id": "...",
      "source_video_url": "...",
      "title": "...",
      "desc": "...",
      "statistics": {
        "like_count": 123,
        "comment_count": 4,
        "share_count": 5,
        "favorite_count": 6,
        "view_count": null
      }
    }
  ],
  "metadata": {
    "fetch_execution_path": "browser_extension_current_tab",
    "primary_execution_path": "browser_extension_current_tab",
    "final_execution_path_used": "browser_extension_current_tab",
    "strategy_policy": "operator_current_tab_extension",
    "http_fallback_attempted": false,
    "parse_strategy": "extension_visible_dom_v1",
    "profile_payload_present": true,
    "video_candidate_count": 12,
    "extension_capture_id": "...",
    "extension_page_type": "profile_feed_page"
  }
}
```

Then the backend calls:

```python
SourceIngestService(db).ingest_profile(
    profile_url=profile_url,
    workspace_id=workspace_id,
    source_platform=SourcePlatformEnum.DOUYIN,
    crawl_mode="extension_current_tab_capture",
    adapter_payload_json=adapter_payload_json,
)
```

After ingest, the backend applies the existing candidate flow:

```python
CandidateEvaluationService(db).apply(
    source_profile_id=source_profile_id,
    config=filter_config,
    persist=True,
)
```

## Canonical Entities

Extension capture must reuse:

- `SourceProfile`: one source profile per platform/external id.
- `SourceVideo`: one source video per platform/external video id.
- `CrawlSession`: one import/capture session with metadata and counts.
- `VideoMetricSnapshot`: one metrics snapshot per video and crawl session.
- `VideoCandidate`: created/updated by the existing candidate evaluation service.

## Iterative Capture Behavior

The operator may capture the same profile/page multiple times as they scroll or revisit it.

Expected behavior:

- Each backend capture creates or updates a `CrawlSession` summary.
- Existing profiles/videos are updated by canonical external ids.
- New videos are inserted.
- Metric snapshots are recorded for the capture run.
- Candidate evaluation runs against the profile and upserts matching candidates.
- The API returns created/updated/candidate counts so the UI/extension can show actionable feedback.

## Login and Challenge Handling

Login and challenge handling is manual by design.

If the extension detects `login_page` or `challenge_page`, the response should explain:

- The operator must complete login or challenge in the browser.
- No backend ingest was attempted.
- No cookies or credentials are needed by the app.
- The operator should retry detect/capture after the target page is visible.

## Legacy Playwright Demotion

The Playwright-managed browser path remains isolated as legacy/debug. It can still be useful for diagnostics or future controlled experiments, but it is not the primary collection architecture.

UI requirements:

- Main Douyin guidance should describe extension install, manual login, manual navigation, detect, capture, and import.
- Managed browser controls should use legacy/debug wording.
- Ready checks and account health should not imply that managed browser automation is required for the primary extension flow.

## Observability

Backend logs and metadata should include stable identifiers when available:

- capture id
- crawl session id
- source profile id
- source video ids/counts
- page type
- extension version

Do not log raw HTML, cookies, auth headers, local storage, credentials, or private browser paths.

## Testing Strategy

Backend tests should cover:

- page type validation and unsupported/login/challenge behavior,
- safe payload mapping into adapter payload shape,
- canonical ingest call with `adapter_payload_json`,
- candidate evaluation call after ingest,
- repeated capture/idempotency summary behavior using mocked services,
- no secret fields accepted or echoed.

Extension tests should cover pure parsing helpers where practical without live Douyin.

Frontend tests/typecheck should verify that primary guidance points to extension capture and legacy paths are demoted.
