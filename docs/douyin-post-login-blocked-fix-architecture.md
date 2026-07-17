# Douyin Post-Login Blocked Fix Architecture

## Problem

Douyin browser-assisted login can succeed visually, but the first authenticated probe may still see a transient security/challenge page. The previous flow treated that single signal as a hard `post_login_blocked` failure.

## Revised Post-Login Sequence

1. Start browser connect through the canonical backend service.
2. Wait for authenticated Douyin cookies.
3. Enter `login_detected`.
4. Run bounded stabilization while the browser remains open.
5. Run browser-context prevalidation.
6. If prevalidation passes, continue to normal validation.
7. If prevalidation is blocked-like but cookies are present, keep the result as retryable evidence and continue to canonical account validation.
8. If canonical validation is still blocked-like during initial connect, mark the connect session `validation_retry_ready`.
9. Operator can retry validation using the same canonical account/session path.
10. Only repeated/canonical blocked evidence marks the account `BLOCKED`.

## Blocked Assignment Rules

- `login_detected` never means connected.
- `browser_context_blocked_response` from the first post-login probe is not enough to mark an account `BLOCKED`.
- Initial connect-time browser-context blocked results are stored as retryable diagnostics.
- A retry/canonical validation may mark `BLOCKED` after repeated blocked evidence.
- Login-required or missing cookies remains a session-stability failure, not a blocked account.

## Retry And Resume

- `validation_retry_ready` keeps the session visible in `/accounts/douyin`.
- UI should show `Retry validation` and `Resume current session` when backend capability flags allow it.
- Persistent browser context mode keeps the live browser context available for retry when possible.

## No-Duplication Strategy

This fix does not add a second browser connect or validation pipeline. It changes classification and sequencing inside:

- the existing Playwright capture/runtime layer
- the existing `DouyinBrowserConnectService`
- the existing `DouyinAccountService`

`DouyinAccountConnection` remains the canonical persisted account model.

## Intentional V1 Limits

- No password automation.
- No bypass of Douyin challenge pages.
- No guarantee that every challenge can be resolved by retry.
- Retry is a controlled operator action, not an autopilot loop.
