# Phase 5D Backend Browser Hydration Resume

## Current step
- Phase 5D implementation and focused verification completed.

## Done
- Read live Phase 5A-R acceptance result showing `raw_network_aweme = 0/49` and `raw_detail_aweme = 0/49`.
- Audited existing backend browser/profile runtime path.
- Identified canonical reuse points:
  - `DouyinAccountService._ensure_persistent_profile_context(...)`
  - `douyin_browser_context_registry.fetch_profile_page(...)`
  - `CaptureMetadataNormalizer`
  - `CaptureInbox` persistence model
- Added backend hydration service.
- Added browser detail fetch wrapper on the managed runtime registry.
- Added operator script for latest or explicit capture session hydration.
- Added focused parser/service/script tests.
- Ran focused backend verification.

## In progress
- none

## Next exact task
- Run live hydration on a real managed Douyin browser profile, then rerun `metadata_phase5a_real_live_audit.py`.

## Key files
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/capture_metadata_normalizer.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
