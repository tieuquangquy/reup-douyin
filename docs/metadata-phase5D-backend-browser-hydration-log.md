# Phase 5D Backend Browser Hydration Log

## Status
- completed

## Why Phase 5D is needed
- Latest live Phase 5A-R audit still shows `raw_network_aweme = 0/49` and `raw_detail_aweme = 0/49`.
- `raw_dom_snapshot = 49/49`, so time metadata is partially usable, but duration/performance remain absent.
- Extension-side evidence acquisition is still not sufficient as the only metadata source.
- The backend already has a browser-backed Douyin account/runtime path that can be reused for deterministic detail-page hydration.

## Audit findings
- Existing reusable browser/profile runtime lives in `apps/api/src/services/douyin_browser_context_registry.py`.
- Existing profile reopen/preflight orchestration lives in `apps/api/src/services/douyin_account_service.py`.
- Existing browser-backed page fetch path already exists via:
  - `DouyinAccountService._ensure_persistent_profile_context(...)`
  - `douyin_browser_context_registry.fetch_profile_page(...)`
- Existing canonical metadata normalization already exists in `apps/api/src/services/capture_metadata_normalizer.py`.
- Existing Capture Inbox persistence shape already stores:
  - `raw_detail_aweme`
  - `raw_evidence_summary`
  - canonical metadata columns and metadata status fields

## Chosen browser service
- Reuse the managed browser runtime behind `DouyinAccountService` + `douyin_browser_context_registry`.
- Do not introduce a second browser/account execution path.

## Planned implementation
1. Add a backend metadata hydration service for latest/session-scoped captured items.
2. Reuse managed browser profile reopen/preflight before hydration.
3. Fetch each video detail page in the managed runtime.
4. Parse embedded JSON / response documents for exact `aweme_id`.
5. Sanitize and persist `raw_detail_aweme`.
6. Re-run `CaptureMetadataNormalizer`.
7. Persist refreshed canonical duration/performance/status fields.
8. Add a narrow operator script for latest or explicit session hydration.

## Implemented fix
- Added `CaptureInboxMetadataHydrationService` in `apps/api/src/services/capture_inbox_metadata_hydration_service.py`.
- Reused browser-backed preflight/reopen through `DouyinAccountService.preflight_fetch_readiness(...)`.
- Reused managed browser fetch through:
  - `douyin_browser_context_registry.fetch_detail_page(...)`
  - backed by shared `_fetch_page(...)`
- Added recursive exact-id detail parser and bounded sanitizer.
- Reused `CaptureMetadataNormalizer` after `raw_detail_aweme` is attached.
- Added operator script:
  - `apps/api/scripts/hydrate_capture_session_metadata.py`

## Concurrency / timeout
- Requested concurrency flag defaults to `2`.
- Effective browser fetch concurrency is currently `1` because the managed runtime is a single shared Playwright context/page owner and Phase 5D keeps correctness over speculative parallel page races.
- Per-item browser navigation timeout is parameterized and passed into the managed runtime fetch helper.

## Non-goals
- No extension changes.
- No Capture Inbox UI changes.
- No backend metadata normalizer rewrite.
- No backend hydration queue/orchestrator beyond a narrow operator path.

## Files touched
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/scripts/__init__.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5D-backend-browser-hydration-log.md`
- `docs/metadata-phase5D-backend-browser-hydration-resume.md`
- `docs/metadata-phase5D-backend-browser-hydration-architecture.md`

## Tests run
- `python -m unittest tests.test_capture_inbox_metadata_hydration_service tests.test_hydrate_capture_session_metadata_script tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status tests.test_douyin_current_page_capture_service`
- `python -m compileall src scripts`

## Verification
- Focused backend tests passed.
- Compile check passed.
- Browser hydration path is now callable from a backend operator script without any extension/UI changes.

## Live retest steps
1. Start backend with the real local `.env` / PostgreSQL configuration.
2. Ensure a reusable Douyin managed browser profile/account is connected and fetch-ready.
3. Run:
   - `cd apps/api`
   - `python scripts/hydrate_capture_session_metadata.py --session-id <capture_session_id>`
   - or `python scripts/hydrate_capture_session_metadata.py` for latest session
4. Rerun:
   - `python tests/metadata_phase5a_real_live_audit.py`

## Expected live metrics
- `raw_detail_aweme > 0`
- `raw_evidence_summary.has_detail_aweme > 0`
- `duration_seconds > 0` when detail `video.duration` exists
- `view_count / like_count > 0` when detail `statistics` exists
- `performance_status=captured > 0`
- `processing_fit_status=captured > 0`
