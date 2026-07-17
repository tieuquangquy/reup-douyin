# Phase 5E-T TargetClosed Revalidate Log

## Status
- completed

## Root cause audit
- Revalidate uses the saved persistent browser profile path through:
  - `DouyinAccountService._ensure_persistent_profile_context(...)`
  - `douyin_browser_context_registry.open_profile_for_account(...)`
  - `douyin_browser_context_registry.validate_account_context(...)`
- The registry already has `get_or_create_live_page(...)`, but `TargetClosedError` can still escape as a hard reopen failure when the first page in the persistent context closes early.
- Current failure shape:
  - reopen path classifies early page close as `first_page_closed_early:TargetClosedError`
  - readiness script maps that to `profile_open_failed`
- This blocks revalidate before it finishes a fresh browser-backed readiness probe on `https://www.douyin.com/`.

## Planned change
- Keep the persistent-profile model.
- Harden live-page recovery so revalidate:
  - ignores a closed first page
  - creates a fresh page if needed
  - retries once when a newly recovered page closes during the validation attempt
  - only returns `profile_open_failed` after recovery fails twice
- Preserve explicit lock/captcha/login classification.

## Files touched
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_douyin_account_service.py`
- `docs/metadata-phase5E-targetclosed-revalidate-log.md`
- `docs/metadata-phase5E-targetclosed-revalidate-resume.md`

## Tests run
- `python -m unittest tests.test_douyin_browser_connect_service tests.test_douyin_account_readiness_script tests.test_douyin_account_service`
- `python -m compileall src scripts`

## Verification result
- Revalidate now always drives browser-backed validation against `https://www.douyin.com/`.
- If the remembered/first page closes early, validation retries once with a fresh page in the same persistent context instead of failing immediately.
- Repeated page-close failure still returns `profile_open_failed`.
- Browser profile lock remains classified separately as `browser_profile_locked`.
