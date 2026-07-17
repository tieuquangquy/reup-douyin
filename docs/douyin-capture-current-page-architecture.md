# Douyin Current-Page Capture Architecture

## Summary

Douyin intake is being refactored from an automated validation/fetch-first flow to an operator-assisted current-page capture flow.

The system should trust the operator to perform challenge-sensitive actions in a visible managed browser profile, then inspect and import the current page. This minimizes automated navigation and detached HTTP probing while preserving the canonical ingest and review pipeline.

## Primary workflow

1. The operator opens a managed persistent browser profile for a selected `DouyinAccountConnection`.
2. The operator logs in and solves any challenge in that browser.
3. The operator navigates to a target Douyin page manually.
4. The web UI calls API detection for the selected account.
5. The API inspects the current managed browser page without navigation.
6. If the page is supported and capture-ready, the UI allows capture.
7. The API captures page HTML, title, URL, rendered video links, and safe page metadata.
8. The API converts captured artifacts into the existing Douyin adapter payload shape.
9. `SourceIngestService.ingest_profile(adapter_payload_json=...)` persists canonical records.
10. `CandidateEvaluationService.apply()` runs the existing candidate filter path.
11. The review board receives imported results through existing routes and models.

## Scope boundaries

### `apps/web`

Owns operator interaction:

- opening/reopening browser profile;
- showing page classification;
- exposing detect and capture buttons;
- guiding manual login/challenge/load-more actions;
- linking to review board after import.

It must not perform crawling, persistence, or direct database writes.

### `apps/api`

Owns HTTP contracts and orchestration:

- account-scoped current-page detection route;
- account-scoped current-page capture/import route;
- managed runtime lookup;
- page classification;
- adapter payload extraction;
- canonical ingest and candidate pipeline invocation.

It must not leak raw cookies, tokens, local private paths, or browser secrets.

### `apps/worker`

No worker implementation is required for the minimal current-page capture step. If later captures become long-running, they should be converted into durable jobs with retry/resume/cancellation semantics.

## Existing components reused

### Account/runtime model

- `DouyinAccountConnection` remains the persisted account model.
- One account continues to map to one managed persistent browser profile.
- `douyin_browser_context_registry` remains the runtime registry.

### Canonical ingest

The capture service must call:

```text
SourceIngestService.ingest_profile(profile_url=..., adapter_payload_json=...)
```

The adapter payload must match the existing shape accepted by `DouyinProfileAdapter.normalize_fetch_payload()`:

```json
{
  "profile": {
    "sec_uid": "...",
    "nickname": "...",
    "unique_id": "..."
  },
  "videos": [
    {
      "aweme_id": "...",
      "desc": "...",
      "share_url": "https://www.douyin.com/video/...",
      "statistics": {}
    }
  ],
  "metadata": {
    "source": "douyin_current_page_capture",
    "parse_strategy": "current_page_browser_artifacts"
  }
}
```

This preserves canonical persistence:

- `CrawlSession`
- `SourceProfile`
- `SourceVideo`
- `VideoMetricSnapshot`

### Candidate pipeline

After ingest succeeds, capture/import must call `CandidateEvaluationService.apply()` with the resolved `source_profile_id`. This preserves `VideoCandidate` behavior and review-board continuity.

## Page taxonomy

The current page must be classified into exactly one of the following values.

| Page type | Meaning | Capture behavior |
| --- | --- | --- |
| `login_page` | Browser is on login/auth page or login modal dominates page content. | Block capture. Tell operator to log in. |
| `challenge_page` | Browser is on CAPTCHA/verification/security challenge. | Block capture. Tell operator to solve challenge manually. |
| `home_feed_page` | Douyin home/recommend/feed page. | Detect only by default; capture may import visible video links when profile context can be inferred, otherwise ask operator to open a profile. |
| `profile_page` | A Douyin user/profile page. | Supported capture target. |
| `profile_feed_page` | Profile sub-tab/list page with visible videos. | Supported capture target. |
| `video_detail_page` | A single Douyin video page. | Supported only when a usable author/profile identity can be resolved or extracted; otherwise capture-blocked. |
| `unsupported_page` | Non-Douyin page or Douyin page outside supported surfaces. | Block capture. |
| `unknown_page` | Runtime page is readable but heuristics cannot classify it. | Block capture and ask operator to navigate to a profile/feed/video page. |

## Detection design

Detection must:

- retrieve the selected account runtime record;
- verify the managed runtime/page is active;
- recover a usable existing page if needed;
- read current `page.url`, `page.title()`, body text excerpt, and visible video link count;
- classify from current page only;
- return a structured response for UI guidance.

Detection must not:

- call detached HTTP fetch;
- call `fetch_profile_page()`;
- call `validate_account_context()` for the primary path;
- navigate to login/profile/validation URLs;
- scroll automatically;
- run fallback chains.

## Capture design

Capture must:

- run detection first;
- block capture for login/challenge/unsupported/unknown pages;
- read current page artifacts from the managed browser page;
- avoid logging raw HTML, cookies, headers, tokens, or private paths;
- extract profile and video payloads from browser artifacts;
- hand the payload to `SourceIngestService.ingest_profile(adapter_payload_json=...)`;
- run candidate filtering exactly as existing intake does;
- return import summary and next review route.

Capture may:

- use existing parsing helpers for embedded JSON, network documents, and rendered links;
- import the same visible page multiple times, relying on canonical dedupe keys for idempotency;
- allow operator to manually load more content and capture again.

Capture must not:

- auto-navigate to the target profile;
- auto-scroll/load more as part of the primary action;
- call detached HTTP fallback unless explicitly reintroduced as a legacy/debug-only path outside the primary workflow;
- create new downstream tables or duplicate source-video/candidate architecture.

## Readiness model

The current-page readiness gate is intentionally simpler than historical fetch readiness:

- runtime active and attached;
- current page classified;
- page type is capture-supported;
- not login/challenge-blocked;
- enough identity is available to create a canonical profile URL;
- extracted videos are parseable or a true zero-video result is explicitly reported.

Historical account health/preflight may remain visible as diagnostics, but it must not be the primary gate for current-page capture.

## Observability

Log stable identifiers only:

- account id;
- diagnostics id;
- page type;
- crawl session id;
- source profile id;
- counts of links/videos/candidates.

Do not log:

- session cookies;
- auth tokens;
- raw credentials;
- raw private local browser profile paths;
- full HTML payloads;
- raw headers.

## Idempotency and iterative capture

Operators may click capture multiple times after manually loading more content. The system remains safe because:

- profiles dedupe by source platform and external profile id;
- videos dedupe by source platform and video external id;
- metric snapshots are tied to each crawl session;
- candidate upsert is keyed by source video id.

## Failure behavior

- Missing runtime: return action `open_browser_profile`.
- Login page: return action `manual_login_required`.
- Challenge page: return action `solve_challenge_in_browser`.
- Unsupported/unknown: return action `navigate_to_supported_page`.
- No parseable profile identity: return action `open_profile_page`.
- Zero videos on supported profile: allow explicit zero-video import only if identity is present; otherwise block.

## Future extension points

- Durable capture jobs if captures become long-running.
- Distributed browser workers behind the same service contract.
- Object storage for screenshots/debug artifacts, if needed, through storage abstraction.
- More robust page-specific parsers without changing downstream canonical ingest.
