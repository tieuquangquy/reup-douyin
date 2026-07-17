# douyin-validate-auto-reopen-architecture.md

## Objective

Fix browser-backed Validate so a Douyin account with a saved reusable browser profile can recover from missing in-memory runtime state. If no live browser context exists, Validate reopens and reattaches the same saved persistent profile, then continues the canonical browser-backed validation probe.

## Saved Profile Versus Live Context

A saved browser profile is durable account metadata and local browser profile storage. It survives API process restarts and is identified by account metadata such as `browser_profile_id` and `browser_profile_path`.

A live browser context is runtime-only registry state held by the API process. It can disappear after API restart, idle timeout, browser close, or invalidation. Missing live context does not mean the saved profile is unusable.

## Previous Root Cause

The Validate endpoint reaches browser-backed validation through [`DouyinAccountService.validate_account()`](../apps/api/src/services/douyin_account_service.py:383), then [`DouyinAccountService._validate_with_live_browser_context()`](../apps/api/src/services/douyin_account_service.py:1114). That method calls [`DouyinBrowserContextRegistry.validate_account_context()`](../apps/api/src/services/douyin_browser_context_registry.py:509). When the registry has no live record, it returns `no_live_browser_context`.

The reopen helper existed in [`DouyinAccountService._ensure_persistent_profile_context()`](../apps/api/src/services/douyin_account_service.py:1236), which calls [`DouyinBrowserContextRegistry.open_profile_for_account()`](../apps/api/src/services/douyin_browser_context_registry.py:358). The fix makes the no-live-context path explicitly auto-reopen and retry validation before returning runtime unavailable.

## Auto-Reopen Validation Flow

1. Validate starts for a browser-backed account.
2. The service checks saved profile metadata.
3. The service asks the registry to validate the account context.
4. If the registry returns `no_live_browser_context` and saved profile metadata exists, the service forces the canonical reopen path with the existing profile identity.
5. The registry opens the persistent profile and records a new runtime entry bound to the same account id.
6. Validate retries the browser-context validation probe in the reattached runtime.
7. The final validation result updates account status, health, and safe metadata.

## Registry Reattachment

The reopened runtime is registered in the browser context registry with:

- the same account id,
- the same resolved profile id/path,
- the new runtime context id,
- active runtime handles,
- last-used/reopen metadata.

This allows Validate, Ready Check, and Intake to observe the same live context after auto-reopen.

## Result Mapping

The browser-backed Validate path uses these result categories:

- `browser_validation_success`
- `browser_validation_inconclusive`
- `browser_validation_blocked`
- `browser_validation_login_required`
- `browser_validation_runtime_reopened`
- `browser_validation_runtime_unavailable`
- `browser_validation_profile_unavailable`

`browser_validation_runtime_reopened` is recorded as safe metadata and shown in diagnostics when the missing runtime was recovered. The final public validation result remains the validation probe outcome after reopen.

## Status Rules

- Reopen succeeds and validation succeeds: set account `ACTIVE` / healthy, clear stale errors, update last successful validation.
- Reopen succeeds and validation is inconclusive: keep retryable warning behavior, not hard blocked.
- Reopen fails: return `browser_validation_runtime_unavailable` with an operator-safe reason.
- Saved profile metadata missing or broken: return `browser_validation_profile_unavailable`.

## UI Diagnostics

The `/accounts/douyin` UI can now show:

- saved reusable browser profile exists,
- no live browser runtime,
- Validate can auto-reopen saved profiles,
- saved profile auto-reopened,
- final browser validation success/inconclusive/blocked/login-required/runtime-unavailable result.

## Canonical Boundaries

This fix does not add a second account model or second browser profile model. It preserves the canonical account row, persistent browser profile metadata, browser-primary Intake strategy, and downstream Intake/discovery pipeline.

## Verification

- Passed: `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service`
- Passed: `npm run typecheck --workspace apps/web`
