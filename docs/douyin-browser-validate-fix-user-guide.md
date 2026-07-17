# douyin-browser-validate-fix-user-guide.md

## What Changed

The Validate action for Douyin accounts now treats the saved browser profile as the primary evidence source. When an account has a reusable browser profile, Validate reopens or reuses that same persistent profile and records browser-specific results instead of letting detached HTTP fallback dominate the account state.

## Validate Result Meanings

- `browser_validation_success`: The saved browser profile produced strong usable-account evidence. The account is set to active/healthy and old blocked errors are cleared.
- `browser_validation_inconclusive`: Validate reached the saved browser profile, but the browser probe could not prove success or a hard block. This is a warning/retry state, not hard blocked.
- `browser_validation_blocked`: The browser context itself showed challenge/security/block markers.
- `browser_validation_login_required`: The saved browser profile no longer has authenticated Douyin cookies or lands on login.
- `browser_validation_runtime_unavailable`: A saved profile exists, but the local browser runtime/context could not be opened or used.
- `browser_validation_profile_unavailable`: No saved browser profile is available for browser-backed validation.
- `browser_validation_failed_unknown`: Reserved for browser validation failures that cannot be classified more specifically.

## Operator Workflow

1. Open `/accounts/douyin`.
2. Confirm the account shows a saved reusable browser profile.
3. Click Validate.
4. Read the Browser health alignment panel:
   - `Browser validation succeeded` means the saved profile is usable and the account can be active again.
   - `Browser validation inconclusive` means the profile was reached, but the result is retryable and should not be treated as hard blocked.
   - `Browser validation blocked` means the browser profile itself showed block/challenge evidence.
   - `Login required` means reopen the profile and sign in again.
5. Use the account from Intake only after browser validation succeeds or after the account health indicates it is usable.

## Before And After

Before this fix, a browser-backed account could reach its saved profile but return an `uncertain` browser probe. That result fell through to detached HTTP validation, and detached HTTP failure could leave the account blocked.

After this fix, browser-backed accounts record explicit browser validation categories. A fresh browser validation success clears stale blocked state. An inconclusive browser result remains retryable/warning-level and does not become hard blocked merely because detached HTTP would fail.

## Edge Cases

- A visible browser window alone is not success. The validation probe still needs authenticated cookies plus non-login/non-challenge browser evidence.
- Inconclusive validation can happen during transient navigation timeouts, changing Douyin page structure, or incomplete page signals.
- Login-required and blocked results are still hard negative browser-backed evidence when observed in the browser context.
- Detached HTTP remains available only as a fallback path for non-browser-backed cases or weaker diagnostics; it does not override fresh browser success.
