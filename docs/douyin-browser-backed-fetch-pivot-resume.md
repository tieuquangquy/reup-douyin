# douyin-browser-backed-fetch-pivot-resume.md

## Current Step

Completed. Browser-profile-backed fetch is now the primary local-dev execution path when a reusable persistent profile exists.

## Done

- Read [`AGENTS.md`](AGENTS.md).
- Audited the canonical intake/discovery path through:
  - [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:99)
  - [`SourceIngestService.ingest_profile()`](apps/api/src/services/source_ingest_service.py:50)
  - [`DouyinProfileAdapter.fetch_profile()`](apps/api/src/adapters/douyin.py:70)
- Audited current Douyin HTTP fetch behavior in [`DouyinLiveFetchClient.__call__()`](apps/api/src/adapters/douyin_live_fetch.py:50).
- Audited persistent browser profile/runtime reuse in:
  - [`DouyinAccountService.resolve_runtime_config()`](apps/api/src/services/douyin_account_service.py:514)
  - [`DouyinAccountService._refresh_session_from_live_browser_context()`](apps/api/src/services/douyin_account_service.py:698)
  - [`DouyinAccountService._ensure_persistent_profile_context()`](apps/api/src/services/douyin_account_service.py:716)
  - [`DouyinBrowserContextRegistry.open_profile_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:320)
- Audited observability and troubleshooting mapping in [`IntakeRunHistoryService.troubleshooting_for()`](apps/api/src/services/intake_run_history_service.py:83).
- Reviewed required architecture/history references:
  - [`docs/douyin-zero-videos-hard-fix-log.md`](docs/douyin-zero-videos-hard-fix-log.md)
  - [`docs/douyin-fetch-observability-architecture.md`](docs/douyin-fetch-observability-architecture.md)
  - [`docs/douyin-persistent-profile-hard-pivot-architecture.md`](docs/douyin-persistent-profile-hard-pivot-architecture.md)
  - [`docs/douyin-persistent-browser-context-architecture.md`](docs/douyin-persistent-browser-context-architecture.md)
- Created [`docs/douyin-browser-backed-fetch-pivot-log.md`](docs/douyin-browser-backed-fetch-pivot-log.md).
- Confirmed the repo already has a partial `browser_fetch` callback path from [`DouyinAccountService`](apps/api/src/services/douyin_account_service.py) into [`DouyinLiveFetchClient`](apps/api/src/adapters/douyin_live_fetch.py).
- Confirmed the current browser-backed path still parses rendered HTML with the old HTTP parser and does not extract browser network JSON or rendered video links.
- Added browser network JSON and rendered video-link collection in [`DouyinBrowserContextRegistry.fetch_profile_page()`](apps/api/src/services/douyin_browser_context_registry.py).
- Added browser-artifact payload extraction in [`extract_profile_payload_from_browser_artifacts()`](apps/api/src/adapters/douyin_live_fetch.py).
- Preserved canonical adapter/ingest/candidate pipeline.
- Propagated `fetch_execution_path` and fallback metadata into crawl-session diagnostics and Intake response/UI.
- Added focused tests for browser primary fetch, classified browser failure, and HTTP fallback when browser profile is unavailable.

## Key Findings

- The canonical ingest/discovery persistence pipeline already exists and should remain unchanged.
- The current account-backed happy path is still HTTP-first because [`DouyinLiveFetchClient.__call__()`](apps/api/src/adapters/douyin_live_fetch.py:50) performs HTML fetch + parse as the main transport.
- Persistent browser profile metadata already exists on the canonical account model, and runtime reuse already exists in [`DouyinBrowserContextRegistry`](apps/api/src/services/douyin_browser_context_registry.py:92).
- Browser is currently used mainly for validation/session refresh/probing, not as the primary fetch transport for profile/video data.

## In Progress

- None.

## Next Exact Task

Run a live operator verification with a real logged-in Douyin persistent profile:

1. Open `/accounts/douyin`.
2. Reopen/validate the connected browser profile.
3. Run `/intake` discovery for the previously failing profile.
4. Confirm the result shows `Fetch path: Browser profile` or an explicit classified browser-profile failure.

## Guardrails

- No second canonical account model.
- No second ingest/discovery persistence path.
- Browser-profile-backed fetch is an execution strategy pivot only.
- Preserve structured diagnostics and explicit failure classification.
- Never log or expose raw cookies/secrets.

## Key Files To Continue

- [`apps/api/src/services/intake_discovery_service.py`](apps/api/src/services/intake_discovery_service.py)
- [`apps/api/src/services/source_ingest_service.py`](apps/api/src/services/source_ingest_service.py)
- [`apps/api/src/services/douyin_account_service.py`](apps/api/src/services/douyin_account_service.py)
- [`apps/api/src/services/douyin_browser_context_registry.py`](apps/api/src/services/douyin_browser_context_registry.py)
- [`apps/api/src/adapters/douyin_live_fetch.py`](apps/api/src/adapters/douyin_live_fetch.py)
- [`apps/api/src/adapters/douyin.py`](apps/api/src/adapters/douyin.py)
- [`apps/api/src/services/intake_run_history_service.py`](apps/api/src/services/intake_run_history_service.py)
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx)
- [`apps/web/src/types/intake.ts`](apps/web/src/types/intake.ts)
- [`docs/douyin-browser-backed-fetch-pivot-log.md`](docs/douyin-browser-backed-fetch-pivot-log.md)
