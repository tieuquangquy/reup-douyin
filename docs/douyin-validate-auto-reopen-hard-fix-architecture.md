# douyin-validate-auto-reopen-hard-fix-architecture.md

## Objective

Make the `/accounts/douyin` Validate action truly recover a saved reusable Douyin browser profile when the live in-memory runtime registry is missing.

For browser-backed accounts with saved profile metadata, Validate must:

1. detect `no_live_browser_context`,
2. reopen the exact saved persistent profile,
3. verify the reopened profile is reattached to the runtime registry for the same account,
4. continue the canonical browser-backed validation probe in that reattached runtime,
5. return runtime-unavailable only after real reopen or attach failure.

## Relevant Chain

- UI action: [`DouyinAccountsPage`](../apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx) calls `validateDouyinAccount()`.
- API route: [`validate_douyin_account()`](../apps/api/src/api/routes/douyin_accounts.py) calls account service validation.
- Service entry: [`DouyinAccountService.validate_account()`](../apps/api/src/services/douyin_account_service.py).
- Browser validation path: [`DouyinAccountService._validate_with_live_browser_context()`](../apps/api/src/services/douyin_account_service.py).
- Reopen helper: [`DouyinAccountService._ensure_persistent_profile_context()`](../apps/api/src/services/douyin_account_service.py).
- Runtime registry reopen: [`DouyinBrowserContextRegistry.open_profile_for_account()`](../apps/api/src/services/douyin_browser_context_registry.py).
- Runtime registry probe: [`DouyinBrowserContextRegistry.validate_account_context()`](../apps/api/src/services/douyin_browser_context_registry.py).

## Saved Profile Versus Live Runtime

A saved profile is durable local profile metadata on the account:

- `browser_profile_id`
- `browser_profile_path`
- `browser_profile_mode`

A live runtime context is process-local Playwright state in the registry. It can disappear after API restart, browser close, idle timeout, or registry invalidation.

Missing live runtime is recoverable when saved profile metadata exists.

## Previous Failure Point

The service could call the reopen helper, but the validation lifecycle did not enforce a full reopen + rebind + retry contract. Specifically:

- `no_live_browser_context` was detected from the registry.
- Reopen could be attempted.
- The service did not explicitly verify that the reopened summary represented an active runtime record for the same account and same saved profile identity.
- If the second validation still returned `no_live_browser_context`, the result collapsed to `browser_validation_runtime_unavailable` without stage-specific evidence.
- Operator diagnostics could say Validate can auto-reopen while the persisted result still showed generic runtime unavailable.

## Hard-Fix Lifecycle

When browser-backed Validate sees `no_live_browser_context` and saved profile metadata exists:

1. Resolve the canonical saved profile identity from account metadata.
2. Mark safe metadata that auto-reopen was attempted.
3. Call the canonical profile reopen helper with `force=True`.
4. Require the reopen summary to be `active` and to include a runtime context id.
5. Verify the summary belongs to the same account.
6. Verify summary profile identity matches the saved profile identity.
7. Re-read registry summary for the account.
8. Require the registry summary to be active with the same runtime context id.
9. Retry `validate_account_context()` in the same request.
10. Mark validation-continuation metadata.
11. Classify the final browser probe result explicitly.

## Runtime Rebind Rules

A reopened runtime is considered attached only if:

- `summary.status == "active"`,
- `summary.runtime_context_id` is present,
- `summary.account_connection_id` equals the account id,
- `summary.browser_profile_id` / `summary.browser_profile_path` match the resolved saved profile identity,
- `summary_for_account(account.id)` returns an active record with the same runtime context id.

If any rule fails, Validate must classify the result as attach failure instead of claiming generic `no_live_browser_context`.

## Result Categories

Browser-backed Validate can record these categories:

- `browser_validation_success`
- `browser_validation_inconclusive`
- `browser_validation_blocked`
- `browser_validation_login_required`
- `captcha_required`
- `profile_reopen_failed`
- `runtime_attach_failed`
- `browser_validation_failed_unknown`
- `browser_validation_profile_unavailable`

`browser_validation_runtime_unavailable` remains an umbrella-compatible status only for cases where the runtime is truly unavailable after a stage-specific reopen or attach failure has been recorded.

## Status Rules

- `browser_validation_success`: set `ACTIVE` / healthy, clear stale error state, refresh cookie and user-agent artifacts from the browser context.
- `browser_validation_inconclusive`: keep retryable warning behavior; do not hard-block.
- `browser_validation_blocked`, `captcha_required`: hard negative browser evidence; block.
- `browser_validation_login_required`: expire the account.
- `profile_reopen_failed`, `runtime_attach_failed`: set invalid/warn-like status with safe stage-specific metadata and reason.
- `browser_validation_failed_unknown`: set invalid/warn-like status when the browser probe returns an unexpected state after a recovered runtime.

## Canonical Constraints

- No second account model.
- No second browser profile model.
- No fresh profile allocation during Validate for an account with saved profile metadata.
- Manual Reopen profile and Validate must share the same canonical reopen helper.
- No raw cookies, tokens, credentials, or private local path dumps in UI/logs.

## Verification Targets

- Saved profile accounts no longer immediately finish as `no_live_browser_context`.
- Validate reuses the exact saved profile id/path.
- Registry summary is active after reopen.
- Validation continues after active reattach.
- Success clears stale invalid/blocked state.
- Inconclusive does not become runtime unavailable.
- Reopen failure and attach failure are distinct.
