# Douyin Current-Page Capture Log

## Purpose

This log tracks the refactor from automated, probe-heavy Douyin intake toward an operator-assisted managed-browser workflow. The primary happy path is now planned as:

1. Open or reopen the managed browser profile for a `DouyinAccountConnection`.
2. Let the operator log in, solve challenges, and navigate manually inside that same persistent profile.
3. Detect the current visible Douyin page without navigating away.
4. Capture/import visible current-page data from that same managed browser context.
5. Hand the extracted payload to the canonical ingest and candidate pipeline.

## Audit summary

### Repository rules read

- `AGENTS.md` was read before implementation.
- Relevant constraints applied:
  - keep `DouyinAccountConnection` as the account model;
  - keep one account mapped to one persistent managed browser profile;
  - do not create a second downstream discovery architecture;
  - preserve local-first and SaaS-ready boundaries;
  - keep long-running/side-effect-heavy work out of request handlers unless it remains small and explicit;
  - never log or expose raw secrets.

### Current backend audit

- `apps/api/src/services/douyin_browser_context_registry.py`
  - Existing `validate_account_context()` can navigate to a `validation_url` and calls `_prevalidate_record_context()`, which itself can navigate to the login URL. This must not be the new primary gate for current-page capture.
  - Existing `fetch_profile_page()` uses the managed runtime, but it auto-navigates to `profile_url` and auto-scrolls. It can remain as legacy/debug behavior, but the current-page happy path must not call it.
  - Useful runtime seams already exist: `_record_for_account()`, `_ensure_usable()`, `_page_for_record()`, page `content()`, page `title()`, page `url`, DOM link extraction, and same-context response artifact collection patterns.
- `apps/api/src/services/intake_discovery_service.py`
  - Existing `ready_check()` resolves accounts and runs `preflight_fetch_readiness()`, which is too probe-heavy for the requested primary flow.
  - Existing `discover()` normalizes a submitted profile URL, resolves accounts, runs preflight, builds a live fetch adapter, then dispatches fetch. This remains useful for legacy fallback/existing flows, but current-page capture should add a new entrypoint that already has browser-derived profile URL/data.
- `apps/api/src/services/source_ingest_service.py`
  - `ingest_profile(..., adapter_payload_json=...)` is the correct canonical import seam. It creates/updates `CrawlSession`, `SourceProfile`, `SourceVideo`, and `VideoMetricSnapshot` without requiring a detached live fetch.
- `apps/api/src/adapters/douyin.py`
  - `DouyinProfileAdapter.normalize_fetch_payload()` accepts payloads shaped as `{ profile|user, videos|aweme_list, metadata }`.
  - Captured current-page data should produce that shape.
- `apps/api/src/adapters/douyin_live_fetch.py`
  - Existing extraction helpers can parse embedded render JSON, network documents, and rendered video links.
  - Some helper behavior is reusable, but the live fetch client itself represents the old detached HTTP/probe model and must not be the primary current-page orchestrator.
- `apps/api/src/services/candidate_service.py`
  - Candidate creation remains downstream of ingest through `CandidateEvaluationService.apply()`.

### Current frontend audit

- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
  - Already has account-level actions for open/reopen managed browser profile, validate, challenge actions, reset runtime, and use in intake.
  - It should gain first-class current-page actions: detect current page, capture current page/profile, and show page classification/import outcome.
- `apps/web/src/components/intake/IntakePage.tsx`
  - Current UI centers on pasted profile URL, ready check, validate selected account, and run now.
  - It should support the current-page capture path and make the review board continuation unchanged after import.
- `apps/web/src/lib/api.ts` and `apps/web/src/types/douyin-accounts.ts`
  - Need typed clients and response/request types for current-page detection/capture endpoints.

## Architecture decision for this refactor

The new primary workflow will add a browser-current-page layer instead of replacing canonical ingest/candidate services.

- New current-page detection/capture service will live in `apps/api`.
- The service will use only the managed live Playwright page associated with the selected `DouyinAccountConnection`.
- Detection must not call detached HTTP fetch, must not auto-navigate to login/profile URLs, and must not run broad probe/fallback chains.
- Capture may read current page URL/title/HTML/DOM links and optional browser-visible artifacts, then convert to the existing adapter payload shape.
- Import will call `SourceIngestService.ingest_profile(adapter_payload_json=...)`.
- Candidate creation will continue through `CandidateEvaluationService.apply()`.

## Page taxonomy

The implementation will classify the current page as one of:

- `login_page`
- `challenge_page`
- `home_feed_page`
- `profile_page`
- `profile_feed_page`
- `video_detail_page`
- `unsupported_page`
- `unknown_page`

## Planned implementation steps

1. Add schemas for current-page detection/capture contracts.
2. Add a current-page service that classifies the active managed page without navigation.
3. Add capture/import orchestration that creates adapter-compatible payloads and calls canonical ingest.
4. Add API routes under the account boundary.
5. Add web types/API client helpers.
6. Add minimal account/intake UI actions.
7. Add backend and frontend-focused tests.
8. Run verification and update this log with results.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering rewrite.
- No database schema rewrite.
- No queue implementation for this minimal capture action.
- No auto-publish integration.
- No new downstream discovery architecture.

## Implementation summary

Implemented current-page capture as an account-scoped operator workflow:

- Added no-navigation managed browser snapshots in `apps/api/src/services/douyin_browser_context_registry.py`.
- Added current-page taxonomy, detection, guidance, capture/import orchestration, and canonical ingest handoff in `apps/api/src/services/douyin_current_page_capture_service.py`.
- Added account-scoped API contracts and routes in `apps/api/src/schemas/douyin_accounts.py` and `apps/api/src/api/routes/douyin_accounts.py`:
  - `GET /douyin-accounts/{account_id}/current-page`
  - `POST /douyin-accounts/{account_id}/current-page/capture`
- Added web request/response types and API helpers in `apps/web/src/types/douyin-accounts.ts` and `apps/web/src/lib/api.ts`.
- Added operator actions and current-page result display to `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`.
- Updated English and Vietnamese UI copy in `apps/web/src/lib/i18n/en.json` and `apps/web/src/lib/i18n/vi.json`.
- Added focused tests in `apps/api/tests/test_douyin_current_page_capture_service.py`.

## Verification log

- `python -m unittest tests.test_douyin_current_page_capture_service` from `apps/api`: passed, 5 tests.
- `npm run typecheck` from `apps/web`: passed.
- `python -m py_compile src\\services\\douyin_browser_context_registry.py src\\services\\douyin_current_page_capture_service.py src\\schemas\\douyin_accounts.py src\\api\\routes\\douyin_accounts.py` from `apps/api`: passed.
- `python -m unittest tests.test_douyin_adapter tests.test_douyin_current_page_capture_service tests.test_intake_discovery_service` from `apps/api`: passed, 32 tests.

One combined verification command was interrupted by the tool before completion, then rerun as smaller commands successfully.
