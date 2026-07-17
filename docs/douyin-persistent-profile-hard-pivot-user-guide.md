# Douyin Persistent Profile Hard Pivot User Guide

## What Changed

Local Douyin source-account login now uses a persistent browser profile as the primary workflow.

The important rule is:

`one DouyinAccountConnection = one reusable local browser profile`.

This replaces the fragile local-dev behavior where each retry could open a different temporary browser/profile.

## Normal Workflow

1. Open `/accounts/douyin`.
2. For a new source account, use `Connect with browser`.
3. Log in to Douyin in the opened browser. QR login is supported if Douyin shows it.
4. Keep the browser open while the app stabilizes and validates the session.
5. After the account appears in `Connected accounts`, use `Open profile` for future reconnects.

`Open profile` targets the saved account and reuses the same profile directory.

## Reconnect Semantics

For an existing account:

- `Open profile` reopens the same saved browser profile.
- If the API runtime already has that profile open, it reuses the live context.
- If the browser context is not authenticated yet, it waits for login in that same profile.
- It does not create a new temporary browser identity for that account.

## Validation And Fetch

Validation and live fetch prefer the account's persistent profile when available.

Fallback behavior still exists:

- If the live browser context is gone, backend can reopen the saved profile.
- If no profile metadata exists, existing detached session validation can still run.
- Manual session import remains available, but it is no longer the preferred local-dev path.

## Reset And Delete

`Reset browser connect state` clears stuck transient connect attempts. It does not delete saved Douyin accounts and does not delete the persistent profile directory.

`Delete` archives the connected account from active use. Use it only when you no longer want that account available for intake/live fetch.

## Known V1 Limits

- Playwright cannot reliably focus a Chrome window already opened outside the API runtime.
- The persistent browser profile is local machine state. It is not portable cloud account state.
- If Douyin invalidates the login or shows a challenge, the profile may still need manual login/revalidation.
- No password automation or challenge bypass is implemented.
