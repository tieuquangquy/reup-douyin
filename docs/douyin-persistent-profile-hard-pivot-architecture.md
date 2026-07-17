# Douyin Persistent Profile Hard Pivot Architecture

## One Account = One Profile

For local development, a Douyin source account is backed by exactly one persistent local browser profile directory.

`DouyinAccountConnection` remains the canonical persisted account. The profile is stored as account metadata:

- `browser_profile_id`
- `browser_profile_path`
- `browser_profile_mode = persistent_profile`

## Runtime State vs Persisted State

Persisted state:

- Account row
- Account health
- Safe profile id/path metadata
- Captured session artifacts for fallback

Runtime state:

- Playwright context handle
- Active page handle
- Last used/validated timestamps
- Runtime profile lock/availability

Runtime state may disappear on API restart. Persisted profile metadata remains and lets the backend reopen the same `userDataDir`.

## Connect/Reconnect Semantics

New account connect:

1. Create a transient connect session.
2. Create one persistent profile directory.
3. Operator logs in.
4. Persist/update account with that profile identity.

Existing account reconnect:

1. UI sends `account_connection_id`.
2. Backend resolves that account's profile id/path.
3. If live in runtime and authenticated, reuse the existing context.
4. If live in runtime but not authenticated yet, keep that same context open and wait for login there.
5. Otherwise, reopen the same profile directory.
5. Refresh session artifacts and validate using the same account.

Reconnect must not create a different profile for the same account.

## Operator Actions

`/accounts/douyin` exposes two distinct local-dev actions:

- `Connect with browser`: creates a new account-backed browser profile when no account exists yet.
- `Open profile`: targets an existing account and sends `account_connection_id`, so backend reopens/reuses that account's profile.

Force restart preserves the derived account id from the current connect session when one exists. Reset clears stuck runtime connect state, but does not delete the persistent browser profile.

## Retired From Primary Path

- "Reconnect = new temp browser"
- "Profile id = connect session id" for existing accounts
- "Capture cookies then immediately close browser" as the happy path
- Detached cookie-only validation as the first preferred method

These may still exist as fallback/internal compatibility, but not as the operator-facing happy path.

## Validate/Fetch Reuse

Validation/fetch preference:

1. Existing live browser context for the account.
2. Reopen the account's persistent browser profile.
3. Refresh session artifacts from that profile.
4. Fall back to detached session behavior only if no profile is available.

The canonical intake/discovery pipeline remains unchanged.

## V1 Limits

- Playwright cannot always focus an externally opened Chrome window.
- If the profile is locked by a browser outside this API runtime, backend reports/reclaims only when possible.
- The profile is local-machine state, not cloud state.
- No password automation and no challenge bypass.
