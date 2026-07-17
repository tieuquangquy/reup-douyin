# Douyin Live Runtime Attach Fix Log

## Purpose

Track the fix for browser-backed Douyin validation and post-challenge recovery when the saved persistent browser profile is already open, logged in, and manually verified, but validation fails because the remembered first page was closed.

## Scope

Touched areas planned for this fix:

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/schemas/douyin_accounts.py` if additional safe diagnostics are needed
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py` or focused registry tests if required
- `apps/web/src/types/douyin-accounts.ts` and account UI/i18n only if new public diagnostics are surfaced

Non-goals:

- No new Douyin crawler.
- No video processing implementation.
- No queue/database schema changes.
- No new browser profile allocation for existing saved accounts.
- No bypass of manual Douyin verification.

## Audit Findings

### Current fatal path

The registry currently treats first-page acquisition failure during saved profile open as fatal:

```python
try:
    page = context.pages[0] if context.pages else context.new_page()
except Exception as exc:
    raise DouyinBrowserContextError(f"first_page_closed_early:{exc.__class__.__name__}") from exc
```

This means a saved profile can be open and valid, but if the first page target has closed at the moment validation/reopen logic inspects it, the whole profile open path reports `first_page_closed_early:TargetClosedError`.

### Current stale page validation path

`validate_account_context` currently validates through `record.page` directly:

```python
if validation_url:
    record.page.goto(validation_url, wait_until="domcontentloaded", timeout=20_000)
status, reason = self._prevalidate_record_context(context=record.context, page=record.page)
```

If `record.page` is stale or closed while `record.context` is still usable, the exception path invalidates the entire runtime:

```python
except Exception as exc:
    self._mark_invalid(record, f"browser_context_error:{exc.__class__.__name__}")
```

That violates the desired behavior because a closed page is recoverable inside the same live browser context.

### Current validate ordering

`DouyinAccountService._validate_with_live_browser_context` currently calls `_ensure_persistent_profile_context` before direct validation:

```python
self._ensure_persistent_profile_context(account, purpose="validation")
result = douyin_browser_context_registry.validate_account_context(account.id, validation_url=validation_url)
```

This can force the reopen/profile-open branch before attempting to attach to the existing live runtime and reacquire a page in the same context.

## Implementation Plan

1. Add registry-level page reacquisition that keeps the same `_ContextRecord.context` and only replaces `record.page`.
2. Make validation call the page reacquisition path before navigation/prevalidation.
3. Make profile open use the same page selection/create helper instead of failing on the first closed page.
4. Change account validation ordering to validate/attach first, then reopen the same saved profile only when no usable live context exists.
5. Record safe diagnostics for page reacquisition and reopen fallback.
6. Add tests for:
   - closed remembered page recovered by existing page,
   - closed remembered page recovered by new page in same context,
   - missing runtime triggers same saved profile reopen,
   - profile open does not allocate a different saved profile,
   - Mark challenge solved uses the same canonical validation path.

## Progress

- 2026-04-26: Audited registry and account service failure paths.
- 2026-04-26: Created mandatory planning/log docs before implementation.
- 2026-04-26: Implemented same-context page reacquisition for validation, profile reopen, and browser-profile fetch.
- 2026-04-26: Changed account validation to attach to an existing live runtime first and reopen only when the runtime/context is truly missing or unusable.
- 2026-04-26: Exposed safe runtime attach/page recovery diagnostics in API schema, web types, and account UI/i18n.
- 2026-04-26: Added focused tests for attach-first validation, page reacquisition, same-context new page creation, and saved-profile reopen fallback.

## Verification

Focused backend tests passed:

```cmd
set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service apps.api.tests.test_douyin_browser_connect_service
```

Web typecheck passed after schema/type/UI changes:

```cmd
npm run typecheck --workspace apps/web
```

## Final Status

Complete. Validation and post-challenge recovery now prefer the existing live runtime/context, recover from closed remembered pages inside the same context, and reopen only the same saved persistent profile when no usable live runtime exists. Safe diagnostics now distinguish runtime attach, page reacquisition, same-context new page creation, reopen-required, reopen-success, and attach-failed cases.
