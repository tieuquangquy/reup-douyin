# douyin-browser-backed-fetch-pivot-architecture.md

## Objective

Make browser-profile-backed fetch the **primary local-dev execution strategy** for connected Douyin accounts when a reusable persistent browser profile exists, while preserving the **same canonical ingest and candidate-discovery pipeline**.

## Problem Statement

The current local-dev happy path is still effectively HTTP-first:

1. [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:99) resolves a Douyin account.
2. [`DouyinAccountService.build_douyin_adapter()`](apps/api/src/services/douyin_account_service.py:556) builds an adapter-backed fetch client.
3. [`DouyinLiveFetchClient.__call__()`](apps/api/src/adapters/douyin_live_fetch.py:50) performs HTML fetch + parser extraction as the main fetch transport.
4. Browser use is currently secondary:
   - session refresh,
   - validation,
   - rendered-page probing for diagnostics.

This remains fragile in local dev because Douyin can return challenge/shell responses on the HTTP path even when the same connected account’s persistent browser profile is reusable.

## Canonical Path That Must Stay Unchanged

The downstream pipeline remains canonical and unchanged:

```text
/intake
  -> IntakeDiscoveryService.discover()
  -> SourceIngestService.ingest_profile()
  -> DouyinProfileAdapter.fetch_profile()/normalize_fetch_payload()
  -> SourceProfile + SourceVideo + CrawlSession + VideoMetricSnapshot
  -> CandidateEvaluationService.apply()
```

No browser-only persistence path is introduced.
No second account model is introduced.
No second discovery pipeline is introduced.

## Existing Reusable Building Blocks

### Canonical account model

[`DouyinAccountConnection`](apps/api/src/models/source_accounts.py) already remains the canonical connected-account record.

### Persistent browser profile metadata

Account metadata already carries persistent-profile identity such as:

- `browser_profile_id`
- `browser_profile_path`
- `browser_profile_mode = persistent_profile`

This is already used by [`DouyinAccountService._ensure_persistent_profile_context()`](apps/api/src/services/douyin_account_service.py:716).

### Runtime context/profile reuse

[`DouyinBrowserContextRegistry`](apps/api/src/services/douyin_browser_context_registry.py:92) already supports:

- reopening a persistent account profile,
- keeping a runtime browser context active,
- refreshing cookies/user-agent,
- account validation against browser context.

This means the missing piece is not account architecture, but **fetch transport selection and extraction strategy**.

## Chosen Pivot Strategy

### Policy

For local development account-backed fetch:

1. If the selected/resolved Douyin account has a reusable persistent browser profile/context, prefer **browser-profile-backed fetch**.
2. If no reusable browser profile is available, fall back to the current HTTP-based fetch path.
3. If browser-backed fetch fails with a classified issue, return an explicit stage/code instead of a vague no-candidate outcome.
4. The result still flows through the existing adapter normalization and canonical ingest persistence path.

### Execution paths

#### A. Primary path: `browser_profile`

Used when:

- a selected/resolved connected account exists, and
- persistent profile metadata exists, and
- the backend can open/reuse that profile via [`DouyinBrowserContextRegistry.open_profile_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:320) or an active runtime record.

Behavior:

- open/reuse the persistent browser profile/context,
- navigate to the requested Douyin profile,
- wait for meaningful render readiness,
- extract canonical raw profile/video payload,
- pass that payload into the same [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88) and [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50) pipeline.

#### B. Secondary path: `http_html`

Used when:

- no reusable browser profile exists, or
- browser-backed fetch is unavailable because runtime/profile open fails before a browser-backed attempt is possible.

Behavior:

- keep the current HTTP HTML fetch + parser path through [`DouyinLiveFetchClient`](apps/api/src/adapters/douyin_live_fetch.py:39).

#### C. Recovery path: `http_then_browser_fallback`

Used when:

- HTTP HTML returns shell/challenge-like or parse-zero-videos outcome, and
- a reusable browser profile is available.

Behavior:

- preserve diagnostics that HTTP path saw shell/challenge,
- automatically retry using browser-profile-backed fetch,
- if browser-backed fetch succeeds, complete canonical ingest,
- if browser-backed fetch fails, return explicit classified failure with both execution-path signals recorded.

## Canonical Service Addition

Add a canonical helper/service for browser-backed fetch, for example:

- `DouyinBrowserProfileFetchService`

Responsibilities:

- reuse or reopen the persistent local browser profile for a connected account,
- navigate to the target profile URL,
- wait for page render readiness,
- extract profile/video payload from browser-rendered state,
- return a raw payload compatible with [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88),
- return structured metadata describing execution path and fallback/diagnostic state.

Non-responsibilities:

- no direct persistence,
- no candidate generation,
- no second account abstraction,
- no second ingest service.

## Raw Payload Compatibility Contract

The browser-backed fetch helper should return the same broad payload shape already consumed by [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py:88):

- `profile`
- `videos`
- `metadata`

Additional metadata should include:

- `fetch_execution_path`
- `response_shape`
- `response_classification`
- `parser_strategy`
- `browser_profile_reused`
- `browser_profile_id` when safe
- `browser_runtime_context_id` when safe
- optional `fallback_from_execution_path`

This lets browser-backed fetch act as a transport substitution rather than a pipeline fork.

## Implemented Browser Artifact Extraction

Browser-profile-backed fetch now collects three safe runtime artifact classes:

- Douyin-related browser network JSON responses.
- Rendered DOM links matching `/video/`.
- Rendered HTML/page title/page URL metadata for challenge/login classification.

[`extract_profile_payload_from_browser_artifacts()`](apps/api/src/adapters/douyin_live_fetch.py) converts those artifacts into the existing adapter raw payload shape:

```text
{
  profile: {...},
  videos: [...],
  metadata: {
    source: "douyin_browser_profile",
    fetch_execution_path: "browser_profile",
    response_shape: "browser_network_payload" | "browser_rendered_links" | "browser_rendered_shell" | ...,
    parse_strategy: "browser_response_documents" | "browser_dom_video_links" | "browser_rendered_html",
    response_classification: optional
  }
}
```

When only rendered video links are available, the helper creates minimal canonical video payloads with the video id and source URL. Those still flow through [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py), so persistence and candidate discovery remain unchanged.

## Fallback Policy Implemented

- `browser_profile` is tried first when `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true` and the account-backed client has a browser callback.
- If the browser profile is unavailable, the client falls back to `http_html`.
- If browser-profile fetch reaches a classified challenge/login/parse-zero failure, that failure is returned as the primary result instead of being hidden behind HTTP fallback.
- If HTTP fetch sees shell/challenge-like failure and a browser callback exists, the client tries `http_then_browser_fallback`.

## Integration Seam

### Recommended pivot point

The cleanest pivot point is the account-backed fetch transport layer inside [`DouyinAccountService`](apps/api/src/services/douyin_account_service.py:514), because that is where:

- account health is checked,
- runtime/session artifacts are refreshed,
- fetch client strategy is assembled before intake injects it into the adapter.

Likely implementation pattern:

- enrich runtime config with browser-profile/runtime availability metadata,
- build a composite fetch client that can:
  - prefer browser-profile-backed fetch,
  - fall back to HTTP fetch when unavailable,
  - preserve structured execution-path diagnostics.

### Why not pivot in ingest or candidate discovery?

[`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50) should remain transport-agnostic and canonical.

[`CandidateEvaluationService.apply()`](apps/api/src/services/candidate_service.py) should remain unchanged because candidate discovery is downstream of fetch/normalize/persist.

## Observability Requirements

The new fetch flow must explicitly show:

- `fetch_execution_path`:
  - `browser_profile`
  - `http_html`
  - `http_then_browser_fallback`
- stage outcomes
- parser strategy used
- discovered video count
- persisted video count
- matched candidate count
- explicit failure code/stage when browser-backed or HTTP-backed fetch fails

These signals should continue to live inside canonical crawl-session summary/metadata fields as described by [`docs/douyin-fetch-observability-architecture.md`](docs/douyin-fetch-observability-architecture.md).

## Failure Classification Rules

Preserve and extend the existing explicit classes:

- `blocked_response`
- `parse_zero_videos`
- `true_zero_videos`
- `filter_zero_candidates`
- other existing canonical account/session errors

Additional requirement:

- if HTTP path gets shell/challenge and browser fallback is attempted, diagnostics must record both:
  - HTTP shell/challenge-like result,
  - browser-backed fallback attempt/outcome.

## UI Contract Impact

[`/intake`](apps/web/src/components/intake/IntakePage.tsx) should be able to show concise operator-facing messaging for:

- browser-backed fetch used,
- HTTP shell/challenge triggered browser fallback,
- specific fetch failure rather than ambiguous no-candidate result.

This is an additive contract update, not a workflow redesign.

## Non-Goals

- No crawler redesign.
- No review/publish pipeline rewrite.
- No cloud browser service.
- No second canonical account model.
- No second canonical ingest/discovery persistence path.
- No raw cookie/session exposure to logs or UI.

## Verification Plan

Minimum verification after implementation:

1. A previously failing real profile with videos succeeds via browser-backed fetch, **or** the failure is now explicitly classified.
2. Persistent browser profile is actually reused when present.
3. Canonical downstream persistence and candidate flow remain intact.
4. No duplicate discovery pipeline is introduced.
5. Intake/operator surfaces can distinguish fetch-path outcome from genuine zero-candidate filtering.

## Resolved Implementation Choices

- Browser-backed fetch now extracts browser network JSON first, then rendered DOM video links, with rendered HTML metadata kept for classification.
- Browser-profile-first is used when the account-backed fetch client has a browser callback and `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`.
- HTTP remains a fallback only when the browser profile is unavailable or when HTTP needs to recover through browser fallback.
- Operator-safe observability exposes execution path, parser strategy, browser context status/reason, and counts. It does not expose raw cookies or local profile paths.
