# douyin-browser-post-login-fix-architecture.md

## Purpose

This fix separates "login was detected" from "the saved account is usable". Douyin browser connect should keep the browser open through stabilization and browser-context validation before allowing the canonical account validation result to finalize the connection.

## Revised Lifecycle

The persisted enum remains compact, but response `phase` can now expose:

- `starting_browser`
- `waiting_for_login`
- `login_detected`
- `stabilizing_auth`
- `validating_session`
- `validation_retry_ready`
- `completed`
- `failed`
- `timed_out`
- `cancelled`

## Post-Login Stabilization

After authenticated cookies are detected:

1. mark session metadata with `browser_connect_phase=login_detected`
2. wait a bounded stabilization window
3. re-check authenticated cookies
4. run a lightweight browser-context prevalidation before closing the browser

The V1 stabilization strategy is deterministic and bounded. It is not a separate browser automation pipeline.

## Validation Before Close

The Playwright browser context performs a prevalidation check before it is closed. This check looks for:

- authenticated cookies still present
- hard block markers such as captcha/security check
- login-wall markers only when authenticated cookies disappeared

The canonical `DouyinAccountService.validate_account()` still runs after account persistence. Browser prevalidation is used as evidence to prevent premature blocked assignment on the first connect-time validation probe.

## Retry Validation

If browser-context prevalidation passed but the first out-of-browser canonical validation returns `blocked_response`, the session becomes retryable instead of finalized as hard blocked.

`POST /douyin-accounts/browser-connect/{id}/retry-validation` reruns canonical validation on the derived account and finalizes the session based on that result.

Response flags added for UI:

- `can_resume_browser_session`
- `can_retry_validation`
- `should_keep_browser_open`
- `validation_attempt_count`

## Resume Browser Session

For V1, resume means the UI reattaches to the backend browser-connect session and polling continues. If the background Playwright browser is still open, validation continues there. The system does not introduce a separate remote browser handle registry.

## Blocked Assignment Rules

- Do not mark blocked at `login_detected`.
- Do not mark blocked after a first early connect-time validation if browser-context prevalidation passed.
- Mark blocked only when browser-context prevalidation indicates a hard block, or when retry/canonical validation still returns `blocked_response`.

## No-Duplication Strategy

- No second account table.
- No second browser connect route family.
- No alternate permanent validator.
- Existing manual import and account validation remain canonical.

## V1 Simplifications

- Browser-context prevalidation is heuristic but bounded and explicit.
- Retry validation reuses saved session cookies, not a persistent browser handle.
- No distributed browser process registry is introduced.
