# Douyin Live Runtime Attach Fix Resume

## Current Goal

Fix browser-backed Douyin validation and post-challenge recovery so that an already open saved browser profile is reused safely even when the originally remembered first page has been closed.

## User-Visible Problem

The operator has already opened the saved Douyin browser profile, logged in, and solved the visible challenge. Validation and `Mark challenge solved` still report runtime failures such as:

- `profile_reopen_failed`
- `browser_validation_runtime_unavailable`
- `first_page_closed_early:TargetClosedError`

Diagnostics may say the same saved browser profile was reused, but challenge recheck remains unresolved because validation does not successfully attach to the live browser runtime/page.

## Required Runtime Hierarchy

1. Prefer existing live runtime/context for the saved account/profile.
2. If the old page is closed, reacquire a usable active page from the same context.
3. If no active page is usable, create a new page in the same context.
4. Only reopen the same saved persistent profile if the live runtime/context is truly missing or dead.
5. Never create a new browser profile for this recovery path.

## Audited Root Causes

### Registry page acquisition during profile open

`apps/api/src/services/douyin_browser_context_registry.py` uses `context.pages[0] if context.pages else context.new_page()` and converts failures to `first_page_closed_early:<ExceptionClass>`. A `TargetClosedError` at this point currently fails reopen rather than trying another page or a fresh page in the same context.

### Registry validation uses stale `record.page`

`validate_account_context` navigates and prevalidates using `record.page`. If that page is closed but the context remains alive, validation catches the exception and calls `_mark_invalid`, closing the entire context.

### Account service validates after ensure/reopen

`apps/api/src/services/douyin_account_service.py` calls `_ensure_persistent_profile_context` before `validate_account_context`, so the validate path can reopen/fail before a direct attach/reacquire attempt.

## Files To Continue With

- `apps/api/src/services/douyin_browser_context_registry.py`
  - Add same-context page acquisition helper.
  - Use helper in `open_profile_for_account`.
  - Use helper in `validate_account_context`.
  - Consider using helper in `fetch_profile_page` for consistency.
  - Extend `DouyinBrowserContextValidationResult` with safe diagnostics.

- `apps/api/src/services/douyin_account_service.py`
  - Reorder `_validate_with_live_browser_context` to validate existing runtime first.
  - Reopen same saved profile only after `no_live_browser_context`, stale, invalid, closed, or equivalent true runtime loss.
  - Preserve exact saved profile identity checks.
  - Store safe metadata for attach/page reacquisition/reopen outcome.

- `apps/api/tests/test_douyin_account_service.py`
  - Update existing auto-reopen tests to expect attach-first behavior.
  - Add tests for no reopen when existing live validation succeeds.

- `apps/api/tests/test_douyin_browser_connect_service.py` or a focused registry test file
  - Add tests for page reacquisition behavior if feasible with fakes.

## Suggested Next Step

Implement registry-level page reacquisition first, then adjust account validation ordering. After each layer, add focused tests and run the targeted backend test command.

## Final Status

Complete. The fix was implemented and verified on 2026-04-26.

Implemented behavior:

- Existing live Douyin runtime/context is attempted before any reopen.
- Closed/stale remembered pages are replaced by another usable page in the same context when possible.
- If no usable page exists, a new page is created in the same live context.
- The same saved persistent profile is reopened only when the live runtime/context is missing or unusable.
- A different browser profile is not allocated for this recovery path.
- `Validate`, `Mark challenge solved`, and challenge recheck share the same browser-backed validation path.
- Safe diagnostics now include runtime attach status and page recovery status.

Verification passed:

```cmd
set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service apps.api.tests.test_douyin_browser_connect_service
```

```cmd
npm run typecheck --workspace apps/web
```
