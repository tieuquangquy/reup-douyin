# Phase 5E TargetClosed Revalidate Fix Log

## Status
- completed

## Exact root cause
- Persistent-profile open/revalidate already uses page recovery helpers, but the open/revalidate path still classified some early page-close cases too aggressively.
- When the first page in a persistent context closed early, the flow could bubble up `TargetClosedError` as:
  - `first_page_closed_early:TargetClosedError`
- That made revalidate fail even though:
  - the context itself could still be usable
  - another existing page might still be alive
  - or a fresh page could be created safely after a short retry

## Behavior before
- `revalidate` could fail on the first closed page.
- operator-facing code mapping was still too generic for:
  - profile lock
  - repeated `TargetClosedError`

## Planned implementation
1. Add explicit `get_or_create_live_page(...)` helper semantics.
2. Retry page recovery more robustly before failing the whole reopen/revalidate.
3. Keep persistent-context failure classifications actionable:
   - `browser_profile_locked`
   - `profile_open_failed`
   - `manual_login_required`
   - `captcha_required`

## Files touched
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `docs/metadata-phase5E-target-closed-revalidate-fix-log.md`
- `docs/metadata-phase5E-target-closed-revalidate-fix-resume.md`

## Behavior after
- Persistent-profile revalidate/open no longer assumes the first page stays alive.
- The registry now:
  - reuses a live preferred page if present
  - reacquires another existing live page if the remembered page is closed
  - creates a fresh page if no live page exists
  - retries page recovery more robustly before failing
- Operator-facing revalidate errors now distinguish:
  - `browser_profile_locked`
  - `profile_open_failed`
  - `manual_login_required`
  - `captcha_required`

## Tests run
- `python -m unittest tests.test_douyin_account_readiness_script tests.test_hydrate_capture_session_metadata_script tests.test_douyin_browser_connect_service`
- `python -m compileall src scripts`

## Verification result
- Focused tests passed.
- Live revalidate no longer failed with `first_page_closed_early:TargetClosedError`.
- Current real environment now reaches `captcha_required`, which is the correct next blocking state after page recovery succeeds.
