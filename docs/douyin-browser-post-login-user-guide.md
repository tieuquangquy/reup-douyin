# douyin-browser-post-login-user-guide.md

## What Changed

Browser-assisted Douyin connect now treats login detection as an intermediate state, not as proof that the account is ready.

After login is detected, the browser stays open while the session stabilizes and validation runs.

## Operator Flow

1. Open `/accounts/douyin`.
2. Click `Connect with browser`.
3. Login or scan QR in the Douyin browser window.
4. Keep the browser open while the UI shows:
   - `Login detected`
   - `Stabilizing login`
   - `Validating session`
5. Close the browser only after the UI says the account connection completed.

## Retry Validation

If login was captured but the first validation is not conclusive, the UI can show `Retry validation`.

Use this before reconnecting from scratch. It reruns canonical validation against the derived account session and avoids forcing a new login immediately.

## Blocked Accounts

The system should not mark an account blocked just because login was detected or because the first connect-time validation probe was too early.

Blocked is only final when:

- browser-context post-login validation sees a hard block signal, or
- retry/canonical validation still returns a blocked response.

## Resume Browser Session

`Resume current session` reattaches the UI to the backend browser-connect session. If the local Playwright browser is still open, the backend flow continues from its current phase.

## V1 Limits

- Resume does not create a persistent remote browser handle registry.
- Browser-context prevalidation is a bounded heuristic, used only to reduce false blocked states.
- Canonical account validation still lives in `DouyinAccountService`.
