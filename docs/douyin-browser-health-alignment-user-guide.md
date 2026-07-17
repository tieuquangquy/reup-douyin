# douyin-browser-health-alignment-user-guide.md

## Purpose

Use the browser health alignment details in [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:504) to tell whether an account is truly usable through its reusable browser profile, whether Intake is aligned to that same path, and whether an older blocked state has already been cleared by stronger browser-backed evidence.

This guide explains the new server-computed diagnostics exposed by [`DouyinAccountResponse`](apps/api/src/schemas/douyin_accounts.py:72) and rendered in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:550).

## Where To Look

Open the Douyin accounts screen and expand the **Browser health alignment** section for an account row.

That panel is populated from [`browser_health_alignment`](apps/api/src/schemas/douyin_accounts.py:105), which is computed in [`DouyinAccountService.to_response()`](apps/api/src/services/douyin_account_service.py:873).

## What Each Field Means

### Interactive browser state

This shows whether the reusable profile itself is available.

- `live`: the browser profile is currently attached to a running reusable browser context.
- `saved`: a persistent browser profile is saved for the account, but there is no live runtime attached right now.
- `missing`: no reusable browser profile is currently available for the account.

Interpretation:

- `live` means the operator can expect browser-backed checks and Intake to reuse the currently active profile.
- `saved` means the account is still browser-backed in design, but the operator may need to reopen the saved profile before rerunning validation.
- `missing` means the account has no reusable browser path available and will rely on detached HTTP/session material if that fallback is allowed.

### Automated browser validation

This shows the result of the latest browser-backed validation evidence remembered on the account.

Possible values:

- `passed`: browser-backed validation succeeded.
- `retryable_blocked`: browser validation hit a reusable-context problem that is treated as retryable rather than final account failure.
- `blocked`: browser-backed validation produced blocked evidence.
- `login_required`: the browser path reached a login-required state.
- `unknown`: the account has browser-related context but no clear normalized result yet.
- `not_available`: there is no browser-backed validation evidence available.

Interpretation:

- `passed` is the strongest positive signal for browser-backed accounts.
- `retryable_blocked` means the operator should retry or reopen the reusable profile before treating the account as truly unusable.
- `blocked` and `login_required` are stronger negative signals, but should still be read together with the interactive browser state and path alignment fields.

### Detached HTTP state

This shows the state of fallback session/cookie-based validation that does not depend on the reusable browser runtime.

Possible values:

- `available`: detached HTTP material exists, but browser-backed validation is the effective primary evidence.
- `passed`: detached HTTP validation succeeded.
- `failed`: detached HTTP validation failed.
- `not_applicable`: no detached HTTP path is relevant for the account.

Interpretation:

For browser-backed accounts, this field is diagnostic only. A detached HTTP failure should not be treated as stronger evidence than a successful reusable-browser validation.

### Validation path

This identifies the effective path that produced the current validation judgment.

Possible values:

- `browser_profile`
- `detached_http`
- `unknown`

### Intake path

This identifies the path Intake is expected to use.

Current rule from [`DouyinAccountService.preflight_fetch_readiness()`](apps/api/src/services/douyin_account_service.py:656):

- accounts with a saved browser profile expect `browser_profile`
- accounts without a saved browser profile expect `detached_http`

### Path alignment

This is `Yes` when validation and Intake are using the same effective path family.

Interpretation:

- `Yes` means the current validation evidence matches the path that Intake is expected to use.
- `No` means the operator should treat the account carefully because validation evidence came from a different path than the one Intake expects to run.

### Stale blocked state cleared

When this message appears, browser-backed validation already succeeded strongly enough to clear an older blocked state.

This is the key mismatch-resolution signal for the original bug: a browser-usable account should no longer look blocked just because of weaker older evidence.

### Last browser validation

This shows the most recent browser validation status, reason, and timestamp when those values are available.

Use it to confirm whether the latest reusable-profile evidence is recent and what kind of browser result produced the current summary.

## Common Operator Scenarios

### Scenario 1: Browser profile is usable and alignment is healthy

Typical signs:

- interactive browser state = `live` or `saved`
- automated browser validation = `passed`
- validation path = `browser_profile`
- intake path = `browser_profile`
- path alignment = `Yes`

Meaning:

The account is aligned correctly. Validation and Intake are both centered on the reusable browser profile.

### Scenario 2: The UI used to look blocked, but browser-backed validation fixed it

Typical signs:

- automated browser validation = `passed`
- stale blocked state cleared message is shown
- account status is active again

Meaning:

An older blocked result has already been superseded by stronger browser-backed evidence. The account should be treated as usable again through the reusable browser path.

### Scenario 3: Saved profile exists, but there is no current live runtime

Typical signs:

- interactive browser state = `saved`
- automated browser validation may be `not_available`, `unknown`, or an older value

Meaning:

The reusable profile exists, but there is not an active browser context attached right now. Reopen the saved profile and rerun validation if you need fresh browser-backed evidence.

### Scenario 4: Detached HTTP failed, but browser-backed validation passed

Typical signs:

- automated browser validation = `passed`
- detached HTTP state = `failed` or `available`
- validation path = `browser_profile`

Meaning:

Treat the browser-backed result as stronger evidence. Detached HTTP failure is fallback-only and should not override the reusable-browser health story for this account.

### Scenario 5: Browser validation is retryable, not final

Typical signs:

- automated browser validation = `retryable_blocked`
- interactive browser state = `live` or `saved`

Meaning:

The system encountered a reusable-browser validation obstacle that may clear after reopening or retrying the browser profile. Do not assume the account is permanently blocked from this signal alone.

## Recommended Operator Actions

- If the reusable profile is `saved` but not `live`, reopen the browser profile and rerun validation.
- If browser-backed validation `passed`, prefer that evidence over detached HTTP failures.
- If path alignment is `No`, rerun validation through the reusable browser profile so validation and Intake reflect the same path.
- If browser validation is `retryable_blocked`, retry the browser-backed flow before deciding that the account is blocked.
- If both browser-backed validation and detached HTTP are unavailable, reconnect or reimport the account before using it in Intake.

## What This Change Does Not Mean

- It does not introduce a second account health model.
- It does not change the canonical Intake pipeline.
- It does not make the UI infer account health only from whether a browser window is open.
- It does not expose cookies, tokens, or private profile paths to operators.

## Source Of Truth

The canonical summary comes from the API service layer, not from frontend heuristics:

- schema: [`DouyinBrowserHealthAlignmentSummary`](apps/api/src/schemas/douyin_accounts.py:56)
- response projection: [`DouyinAccountService._browser_health_alignment_summary()`](apps/api/src/services/douyin_account_service.py:933)
- row rendering: [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:550)

That keeps the operator UI aligned with the same server-side evidence that validation and Intake already use.
