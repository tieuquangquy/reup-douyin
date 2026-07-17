# Phase 5F Captcha-Aware Hydration Resume

## Current step
- Phase 5F implementation and verification completed.

## Done
- Audited backend hydration flow:
  - `fetch_detail_page(...)`
  - `_fetch_page(...)`
  - `CaptureInboxMetadataHydrationService`
  - hydration command script
- Confirmed the detector should run against detail-page browser artifacts, not in the normalizer.
- Added captcha/block detector.
- Added item/session persistence for captcha-aware hydration failures.
- Added operator-facing hydration script output with `--open-profile` guidance.
- Added focused tests and passed verification.

## In progress
- None.

## Next exact task
- Run the real browser-backed hydration again.
- If captcha is returned, open the saved browser profile, complete verification manually, then rerun hydration and the live Phase 5A-R audit.

## Key files
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
