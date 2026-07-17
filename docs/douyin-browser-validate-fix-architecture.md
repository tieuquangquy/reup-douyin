# douyin-browser-validate-fix-architecture.md

## Objective

Fix browser-backed Validate so a saved Douyin browser profile is validated inside the same reusable persistent profile/runtime that Intake expects to use. Strong positive browser evidence must clear stale blocked state. Inconclusive browser evidence must be recorded explicitly and must not fall through to detached HTTP as if the browser profile were hard-blocked.

## Browser-Backed Validation Lifecycle

1. The operator clicks Validate in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:293).
2. The web app calls the API Validate endpoint through [`validateDouyinAccount()`](apps/web/src/lib/api.ts:247).
3. [`validate_douyin_account()`](apps/api/src/api/routes/douyin_accounts.py:230) calls [`DouyinAccountService.validate_account()`](apps/api/src/services/douyin_account_service.py:383).
4. Browser-backed validation is attempted before detached HTTP validation through [`DouyinAccountService._validate_with_live_browser_context()`](apps/api/src/services/douyin_account_service.py:1114).
5. For an account with saved `browser_profile_id` or `browser_profile_path`, validation reopens or reuses that same persistent profile using [`DouyinAccountService._ensure_persistent_profile_context()`](apps/api/src/services/douyin_account_service.py:1224).
6. The runtime probe runs inside the account-bound context through [`DouyinBrowserContextRegistry.validate_account_context()`](apps/api/src/services/douyin_browser_context_registry.py:509).
7. Browser-backed results are mapped immediately. Saved-profile accounts that produce a browser result do not continue into detached HTTP fallback during that Validate action.

## Same-Profile Requirement

Validate must not allocate a fresh browser profile for an existing saved-profile account. The account metadata carries the canonical `browser_profile_id` and/or `browser_profile_path`; validation passes those exact values into [`open_profile_for_account()`](apps/api/src/services/douyin_browser_context_registry.py:358). This matches the browser-primary Intake path, which also reuses the account-bound persistent profile before browser-backed fetch.

## Evidence Collection Rules

Positive browser evidence must come from the browser context itself, not from merely seeing a profile path on disk.

Strong positive evidence includes:

- authenticated Douyin cookies still present in the persistent browser context,
- navigation to a known Douyin page succeeds without login/challenge markers,
- browser page content/title/url do not indicate login or security challenge,
- meaningful Douyin page/profile/video-like markers are visible when available,
- cookie/user-agent artifacts can be refreshed from the same browser runtime.

Weak or inconclusive evidence includes:

- navigation timeout while authenticated cookies remain present,
- page content temporarily unavailable,
- runtime opens but cannot produce a conclusive page probe,
- browser context available but page probe result is `uncertain`.

## Result Categories

Browser validation maps to explicit categories:

- `browser_validation_success`
- `browser_validation_inconclusive`
- `browser_validation_blocked`
- `browser_validation_login_required`
- `browser_validation_runtime_unavailable`
- `browser_validation_profile_unavailable`
- `browser_validation_failed_unknown`

The former operator state “No conclusive browser result yet” is treated as `browser_validation_inconclusive`, not as hard blocked browser evidence.

## Status Overwrite Precedence

- `browser_validation_success` sets the account to `ACTIVE`, clears stale blocked/error state, updates `last_successful_validation_at`, and records strong browser evidence.
- `browser_validation_inconclusive` records a retryable warning state and does not allow detached HTTP fallback failure to dominate browser-profile-backed accounts during the same Validate action.
- `browser_validation_blocked` and `browser_validation_login_required` are hard negative browser-backed results and can justify blocked/expired-like account state.
- `browser_validation_runtime_unavailable` is warning/invalid for saved-profile accounts because the profile exists but the local runtime could not produce validation evidence.
- Detached HTTP remains fallback-only for non-browser-backed accounts and must not outrank a fresh positive browser-backed result.

## UI Diagnostics

The `/accounts/douyin` browser health alignment UI distinguishes:

- saved or live reusable browser profile,
- browser validation succeeded,
- browser validation inconclusive,
- browser validation blocked,
- login required,
- detached HTTP material/failure,
- Validate/Intake path alignment.

## Canonical Boundaries

The canonical account model, account row, Intake/discovery pipeline, and browser-primary fetch strategy remain unchanged. This fix strengthens validation execution and evidence mapping around the existing canonical account record.

## Verification

- Focused backend tests verify browser success clears stale blocked state, inconclusive does not fall through to detached HTTP, and validation reopens the exact saved profile identity.
- Frontend typecheck verifies the updated `/accounts/douyin` wording and i18n references.
