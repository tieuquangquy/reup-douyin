# Phase 5E TargetClosed Revalidate Fix Resume

## Current step
- Phase 5E TargetClosed revalidate fix completed and verified.

## Done
- Audited:
  - `DouyinAccountService._ensure_persistent_profile_context(...)`
  - `DouyinAccountService.preflight_fetch_readiness(...)`
  - `DouyinBrowserContextRegistry`
  - `douyin_account_readiness.py`
- Confirmed `TargetClosedError` is raised from persistent-context page recovery/open logic.
- Added stronger live-page recovery via `get_or_create_live_page(...)`.
- Updated operator-facing revalidate failure mapping.
- Passed focused tests.
- Verified live revalidate now progresses past `first_page_closed_early` and currently fails at `captcha_required` instead.

## In progress
- None.

## Next exact task
- Operator should:
  - open the profile
  - complete captcha/login if needed
  - rerun `--revalidate`
  - rerun hydration

## Key files
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
