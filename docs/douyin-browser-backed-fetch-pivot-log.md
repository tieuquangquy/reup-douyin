# douyin-browser-backed-fetch-pivot-log.md

## Step Name

Pivot local-dev Douyin profile discovery from HTTP-first parsing to browser-profile-backed fetch as the primary strategy.

## Time Started

2026-04-23

## Scope

- [`apps/api`](apps/api)
- [`apps/web`](apps/web)
- relevant local-runtime helpers in [`apps/worker`](apps/worker) if needed
- connected-account fetch path for [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx) and [`/intake`](apps/web/src/components/intake/IntakePage.tsx)
- required architecture references:
  - [`docs/douyin-zero-videos-hard-fix-log.md`](docs/douyin-zero-videos-hard-fix-log.md)
  - [`docs/douyin-fetch-observability-architecture.md`](docs/douyin-fetch-observability-architecture.md)
  - [`docs/douyin-persistent-profile-hard-pivot-architecture.md`](docs/douyin-persistent-profile-hard-pivot-architecture.md)
  - [`docs/douyin-persistent-browser-context-architecture.md`](docs/douyin-persistent-browser-context-architecture.md)

## Findings

### 2026-04-23 follow-up audit

The repo already contains a partial browser-backed pivot:

- [`DouyinAccountService.build_fetch_client()`](apps/api/src/services/douyin_account_service.py) passes a `browser_fetch` callback into [`DouyinLiveFetchClient`](apps/api/src/adapters/douyin_live_fetch.py).
- [`DouyinLiveFetchClient`](apps/api/src/adapters/douyin_live_fetch.py) can prefer `browser_profile` and record `fetch_execution_path`.
- [`DouyinBrowserContextRegistry.fetch_profile_page()`](apps/api/src/services/douyin_browser_context_registry.py) reuses the persistent browser context and returns rendered HTML/page metadata.

Remaining gaps found in this audit:

- Browser-backed fetch still feeds rendered HTML into the HTTP embedded-JSON parser only.
- Browser network JSON responses and rendered `/video/` links are not extracted into canonical raw video payloads.
- `fetch_execution_path` and fallback metadata are not fully propagated through [`DouyinProfileAdapter`](apps/api/src/adapters/douyin.py) into crawl-session summaries.
- Failed crawl-session summaries do not consistently preserve fetch execution path diagnostics.
- [`/intake`](apps/web/src/components/intake/IntakePage.tsx) shows fetch stage/code but not the actual execution path used.

### Canonical pipeline already exists and should be preserved

Current canonical path is still:

- [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:99)
- [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50)
- [`DouyinProfileAdapter.fetch_profile()`](apps/api/src/adapters/douyin.py:70)
- persistence into canonical ingest entities
- candidate filtering through the existing intake pipeline

No second persistence pipeline is needed.

### Exact fetch decision point

The intake account-backed fetch decision currently happens in [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:183):

1. resolve selected/resolved Douyin account
2. build account-backed adapter via [`DouyinAccountService.build_douyin_adapter()`](apps/api/src/services/douyin_account_service.py:556)
3. pass that adapter into [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50)

### Persistent browser profile availability already exists

Reusable persistent-profile metadata already exists in the canonical account model and runtime helper layer:

- [`browser_profile_id`](apps/api/src/services/douyin_browser_context_registry.py:36)
- [`browser_profile_path`](apps/api/src/services/douyin_browser_context_registry.py:37)
- persistent profile reopen flow in [`DouyinBrowserContextRegistry.open_profile_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:320)
- account-side reuse hook in [`DouyinAccountService._ensure_persistent_profile_context()`](apps/api/src/services/douyin_account_service.py:716)

### Current limitation: fetch is still HTTP-first on the happy path

Even when persistent profile reuse is enabled, the current happy path still ends in [`DouyinLiveFetchClient.__call__()`](apps/api/src/adapters/douyin_live_fetch.py:50), which:

1. does HTTP HTML fetch
2. parses embedded payloads from HTML
3. uses browser probing mainly for classification when HTML shell/zero-video response appears

This means local-dev profile discovery still depends on the fragile HTTP-first response path even when a reusable browser profile exists.

### Browser-backed capability exists but is not yet the primary fetch transport

The current code already reuses browser context/profile for:

- validation in [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:632)
- session refresh in [`DouyinAccountService._refresh_session_from_live_browser_context()`](apps/api/src/services/douyin_account_service.py:698)
- persistent profile reopening in [`DouyinBrowserContextRegistry.open_profile_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:320)

But it does not yet use browser-rendered page extraction as the primary profile/video fetch transport for canonical ingest.

## Current HTTP-First Limitations

- HTTP fetch can return challenge/shell responses that still look superficially parseable.
- HTML shell parsing remains the main happy path in local dev.
- Browser probing currently improves classification, but not successful data acquisition.
- A reusable persistent browser profile may exist while discovery still fails on the HTTP transport path.

## Chosen Direction

- Keep one canonical account model and one canonical ingest/discovery pipeline.
- Pivot the execution strategy, not the product architecture.
- When a selected/resolved Douyin account has a reusable persistent browser profile/context, prefer browser-profile-backed fetch as the primary local-dev path.
- Keep HTTP fetch as secondary fallback when browser-backed fetch is unavailable.
- Preserve explicit observability for execution path, stage outcomes, and classified failures.

## Files Touched

- [`apps/api/src/services/douyin_browser_context_registry.py`](apps/api/src/services/douyin_browser_context_registry.py)
- [`apps/api/src/adapters/douyin_live_fetch.py`](apps/api/src/adapters/douyin_live_fetch.py)
- [`apps/api/src/services/douyin_account_service.py`](apps/api/src/services/douyin_account_service.py)
- [`apps/api/src/adapters/douyin.py`](apps/api/src/adapters/douyin.py)
- [`apps/api/src/services/source_ingest_service.py`](apps/api/src/services/source_ingest_service.py)
- [`apps/api/src/services/intake_discovery_service.py`](apps/api/src/services/intake_discovery_service.py)
- [`apps/api/src/schemas/intake.py`](apps/api/src/schemas/intake.py)
- [`apps/api/tests/test_douyin_live_fetch.py`](apps/api/tests/test_douyin_live_fetch.py)
- [`apps/web/src/types/intake.ts`](apps/web/src/types/intake.ts)
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json)
- [`docs/douyin-browser-backed-fetch-pivot-log.md`](docs/douyin-browser-backed-fetch-pivot-log.md)
- [`docs/douyin-browser-backed-fetch-pivot-resume.md`](docs/douyin-browser-backed-fetch-pivot-resume.md)
- [`docs/douyin-browser-backed-fetch-pivot-architecture.md`](docs/douyin-browser-backed-fetch-pivot-architecture.md)
- [`docs/douyin-browser-backed-fetch-pivot-user-guide.md`](docs/douyin-browser-backed-fetch-pivot-user-guide.md)

## Implementation Decisions

- Completed the existing `browser_fetch` seam instead of adding a second discovery pipeline.
- Browser-profile-backed fetch now collects browser network JSON documents and rendered DOM `/video/` links.
- Browser artifacts are converted into the same raw `{profile, videos, metadata}` shape consumed by [`DouyinProfileAdapter.normalize_fetch_payload()`](apps/api/src/adapters/douyin.py).
- Browser-profile classified failures no longer fall through to HTTP just to hide the browser failure.
- HTTP fallback is reserved for browser-profile unavailability; HTTP shell/challenge can still trigger browser fallback when a browser callback exists.
- Crawl-session and Intake responses now preserve `fetch_execution_path` and `fallback_from_execution_path`.

## Verification Notes

- Audit confirms this should be completed as an execution-strategy improvement inside the existing account-backed adapter path.
- No product pipeline split is needed.
- `python -m unittest tests.test_douyin_live_fetch tests.test_intake_discovery_service` passed.
- `python -m compileall src` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- Live Douyin success with a real logged-in profile was not re-run in this pass because it requires the operator's active local browser profile/session.

## Status

completed
