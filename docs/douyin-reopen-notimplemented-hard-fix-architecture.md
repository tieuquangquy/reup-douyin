# douyin-reopen-notimplemented-hard-fix-architecture.md

## Objective

Eliminate `persistent_profile_open_failed:NotImplementedError` from the active Douyin persistent browser profile reopen path.

The fix must make both operator `Reopen profile` and browser-backed `Validate` auto-reopen use the same canonical saved-profile reopen implementation, attach a live runtime record, and continue validation after successful reopen.

## Exact Root Cause

The active Validate auto-reopen path is:

1. `DouyinAccountService._validate_with_live_browser_context()` detects `no_live_browser_context`.
2. `DouyinAccountService._ensure_persistent_profile_context()` resolves saved `browser_profile_id` / `browser_profile_path` metadata.
3. `DouyinBrowserContextRegistry.open_profile_for_account()` opens the saved persistent profile.
4. `open_profile_for_account()` calls `sync_playwright().start()` and then `launch_persistent_context()`.

The failing branch is `DouyinBrowserContextRegistry.open_profile_for_account()` before/around Playwright startup. The registry reopen method did not call the Windows Playwright event-loop policy setup that already exists in the browser-connect runtime path.

On Windows, Playwright subprocess startup can raise `NotImplementedError` when run under an incompatible event-loop policy/runtime context. The registry catch block then collapsed that exception to:

```text
persistent_profile_open_failed:NotImplementedError
```

This is not an intentional product stub in the registry. It is an unsupported runtime branch caused by missing environment/runtime setup in the canonical reopen helper.

## Saved Profile Identity Model

One Douyin account owns one canonical saved persistent profile identity:

- `browser_profile_id` identifies the reusable local profile.
- `browser_profile_path` identifies the concrete local profile directory.
- If one field is missing, `DouyinBrowserContextRegistry.profile_identity_for_account()` derives the canonical pair.
- Reopen must use that pair and must not allocate a new profile for an existing browser-backed account.

## Canonical Reopen Lifecycle

The canonical reopen helper is `DouyinBrowserContextRegistry.open_profile_for_account()`.

Lifecycle:

1. Ensure persistent browser profiles are enabled.
2. Resolve canonical profile id/path with `profile_identity_for_account()`.
3. If a live record exists for the same account/profile, return its summary.
4. If a live record exists for a different profile, close it as a mismatch.
5. Prepare the local Playwright runtime for Windows before starting Playwright.
6. Start Playwright.
7. Launch a persistent Chromium context against the exact saved profile path.
8. Acquire or create the first page.
9. Insert a `_ContextRecord` for the same account/profile into the runtime registry.
10. Return `reopen_success` only after `summary_for_account()` sees an active record.

## Runtime Reattach Lifecycle

A successful reopen must create a live registry record with:

- the same `account_connection_id`,
- the same `browser_profile_id`,
- the same `browser_profile_path`,
- a live Playwright context/page,
- an active `runtime_context_id`.

Consumers such as Validate, Ready Check, and Intake should read the same registry record after reopen.

## Shared Reopen Logic

Both flows must share `DouyinBrowserContextRegistry.open_profile_for_account()`:

- Operator `Reopen profile` starts a browser-connect session for an existing account profile, which uses the persistent context registry path when persistent browser context is enabled.
- Browser-backed `Validate` auto-reopen calls `DouyinAccountService._ensure_persistent_profile_context()`, which delegates to `DouyinBrowserContextRegistry.open_profile_for_account()`.

The fix keeps the backend/runtime as the source of truth. UI may display backend diagnostics, but must not invent success.

## Failure Categories

The reopen path should distinguish:

- `reopen_not_supported_current_runtime`: Playwright/runtime support is unavailable for the current local environment.
- `browser_launch_failed`: browser launch failed for a non-lock, non-runtime-support reason.
- `profile_locked_by_existing_process`: saved profile is locked or already in use.
- `persistent_profile_open_failed`: generic persistent-profile open failure when no sharper category applies.
- `first_page_closed_early`: context opened but first page acquisition failed or closed early.
- `runtime_attach_failed`: browser opened but registry attach/same-profile validation failed.
- `reopen_success`: live runtime record attached to the same account/profile.

## Environment Runtime Support Model

The supported Phase 1 local backend is Python Playwright synchronous API using a persistent Chromium context on Windows.

Before Playwright startup in every active browser path, the backend must apply the Windows Playwright event-loop policy setup. Unsupported or missing runtime dependencies should fail explicitly as support/setup categories, not as raw `NotImplementedError` in operator diagnostics.

## Verified Implementation

The implementation now applies runtime policy setup in both persistent browser registry entrypoints:

- `DouyinBrowserContextRegistry.open_profile_for_account()` for canonical saved-profile reopen and Validate auto-reopen.
- `DouyinBrowserContextRegistry.open_login_context_and_capture()` for browser-connect persistent open/capture.

`open_profile_for_account()` now reports `reopen_success` only after a live `_ContextRecord` is inserted and `summary_for_account()` confirms that the same account is attached to the same runtime id. A direct local probe verified that the helper opens a temporary persistent Chromium profile, reuses the exact profile path, returns `reopen_success`, and reattaches the registry to the same runtime id.

## Non-Goals

- No crawler implementation.
- No video processing implementation.
- No new account model.
- No new browser profile allocation for existing browser-backed accounts.
- No raw cookies, credentials, tokens, or private profile paths in UI/logs beyond already-safe local diagnostics.
