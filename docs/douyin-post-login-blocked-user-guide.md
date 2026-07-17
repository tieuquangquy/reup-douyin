# Douyin Post-Login Blocked User Guide

## What Changed

Browser-assisted login no longer treats the first post-login `browser_context_blocked_response` as final proof that the account is blocked.

The app now treats that first signal as retryable when authenticated cookies are present. This matches the real flow better: Douyin may briefly show a challenge/security response immediately after login while the session is still settling.

## Recommended Operator Flow

1. Open `/accounts/douyin`.
2. Click `Connect with browser`.
3. Complete Douyin login in the opened browser window.
4. Keep the browser open while the UI shows login stabilization or validation.
5. If the session enters `Validation retry ready`, click `Retry validation`.
6. Use `Resume current session` if the browser context is still live and the UI offers it.
7. Use `Force restart` only when the live session cannot recover.
8. Use manual session import only when browser-assisted connect remains unavailable.

## Why This Happens

`Login detected` only means the browser has authenticated-looking Douyin cookies. It does not guarantee that Douyin will immediately serve normal authenticated pages to every validation probe.

The first post-login check can be affected by:

- QR login still settling
- challenge or security page shown briefly
- network timing
- a probe page that is stricter than the login page
- Douyin anti-abuse behavior

## Blocked Assignment Rules

- First post-login blocked-like response: retryable, not final.
- Repeated/canonical blocked evidence after retry: account can be marked `BLOCKED`.
- Missing authenticated cookies after stabilization: session is unstable or expired, not a blocked account.
- Successful retry validation: account becomes usable normally.

## What This Does Not Do

- It does not bypass Douyin security pages.
- It does not automate passwords.
- It does not create a second connect flow.
- It does not return raw cookies to the frontend.
- It does not guarantee that every blocked response can recover.

## Troubleshooting

Use `Retry validation` first when login was captured but validation was inconclusive.

Use `Reset browser connect state` only when the UI/session state is stuck and you cannot resume, retry, cancel, or restart normally.
