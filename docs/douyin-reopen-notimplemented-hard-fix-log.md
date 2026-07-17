# douyin-reopen-notimplemented-hard-fix-log.md

## Status

- Root-cause audit complete.
- Architecture document created before implementation.
- Implementation complete.
- Verification complete for compile, backend unit tests via `unittest`, frontend typecheck, direct Playwright persistent-context launch, and direct canonical registry reopen/reattach probe.

## Exact Root Cause

The operator-visible failure is:

```text
profile_reopen_failed
browser_validation_runtime_unavailable
persistent_profile_open_failed:NotImplementedError
```

The exact active code path is:

1. `DouyinAccountService._validate_with_live_browser_context()` detects `no_live_browser_context` for a saved browser-backed account.
2. It calls `DouyinAccountService._ensure_persistent_profile_context()` with `force=True`.
3. `_ensure_persistent_profile_context()` calls `DouyinBrowserContextRegistry.open_profile_for_account()`.
4. `open_profile_for_account()` imports Playwright and calls `sync_playwright().start()`.
5. On Windows, Playwright subprocess startup can raise `NotImplementedError` if the process is using an incompatible event-loop policy/runtime context.
6. The registry catches the exception and returns reason `persistent_profile_open_failed:NotImplementedError`.

The branch causing the visible error is the `except Exception as exc` block in `DouyinBrowserContextRegistry.open_profile_for_account()` after Playwright startup/open attempts. The thrown exception is not a repo-level product stub. It is a Playwright/runtime exception exposed because the registry reopen path does not perform the same Windows runtime setup used by browser-connect capture and runtime probe.

## Is It Called By Reopen, Validate, Or Both?

- Browser-backed `Validate` auto-reopen calls this path through `DouyinAccountService._ensure_persistent_profile_context()`.
- Operator `Reopen profile` starts browser connect for the same account profile. With persistent context enabled, browser-connect delegates to the persistent context registry path for profile opening/capture. The canonical implementation must remain the registry persistent-profile path so both flows share the same runtime behavior.

## Implementation Completed

- Kept `DouyinBrowserContextRegistry.open_profile_for_account()` as the canonical reopen implementation.
- Added Windows Playwright event-loop policy setup before `sync_playwright().start()` in the registry reopen path.
- Hardened `DouyinBrowserContextRegistry.open_login_context_and_capture()` so manual persistent-profile open/capture also applies the policy before Playwright startup.
- Added precise reopen failure classification instead of raw `persistent_profile_open_failed:NotImplementedError`.
- Added first-page acquisition classification as `first_page_closed_early:<ExceptionClass>`.
- Inserted the reopened persistent context into the runtime registry and only returns `reopen_success` after `summary_for_account()` confirms an active record with the same runtime id.
- Preserved Validate continuation through the existing `DouyinAccountService._ensure_persistent_profile_context()` delegation to the canonical registry helper.

## Files Expected To Change

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py` if service-level mapping needs sharper categories
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/api/tests/test_douyin_account_service.py`
- `docs/douyin-reopen-notimplemented-hard-fix-architecture.md`
- `docs/douyin-reopen-notimplemented-hard-fix-log.md`
- `docs/douyin-reopen-notimplemented-hard-fix-resume.md`
- `docs/douyin-reopen-notimplemented-hard-fix-user-guide.md`

## Verification Notes

Commands/results:

- `python -m py_compile apps/api/src/services/douyin_browser_context_registry.py apps/api/tests/test_douyin_browser_connect_service.py apps/api/src/services/douyin_account_service.py apps/api/tests/test_douyin_account_service.py` — passed.
- `npm --prefix apps/web run typecheck` — passed.
- `python -m pytest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_douyin_account_service.py -q` — could not run because this local Python environment does not have `pytest` installed (`No module named pytest`).
- `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_browser_connect_service apps.api.tests.test_douyin_account_service` — passed, 46 tests.
- Direct Playwright persistent-context probe with `ensure_windows_playwright_event_loop_policy()` — passed, created a temporary persistent profile and opened a Chromium persistent context with one page.
- Direct canonical `DouyinBrowserContextRegistry.open_profile_for_account()` probe with a temporary saved profile path — passed:
  - `summary_status=active`
  - `summary_reason=reopen_success`
  - `profile_path_matches=True`
  - `attached_status=active`
  - `attached_same_runtime=True`

The direct registry probe proves the active canonical reopen path can start Playwright on this Windows local environment, launch a persistent profile, reuse the exact supplied saved profile path, insert a runtime record, and reattach `summary_for_account()` to the same runtime id.
