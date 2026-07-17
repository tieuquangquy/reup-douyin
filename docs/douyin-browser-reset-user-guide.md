# douyin-browser-reset-user-guide.md

## What Reset Does

`Reset browser connect state` is a local recovery action for `/accounts/douyin`.

It cancels active-looking browser-connect attempts that may be stuck in local development:

- starting browser
- waiting for login
- capturing session
- validating session

The backend records those attempts as `CANCELLED` with a `reset_by_operator` error code.

## What Reset Does Not Do

Reset does not:

- delete saved Douyin accounts
- delete validated account connections
- erase account cookies already saved in `DouyinAccountConnection`
- remove browser runtime configuration
- clear manual import data

## When To Use It

Use reset when:

- `/accounts/douyin` appears stuck on an old browser-connect session
- the browser window is gone but the backend still thinks a session is active
- polling keeps showing an old session after local API/browser restarts
- cancel/restart is not enough to recover local development state

Do not use reset as the normal happy path. Prefer:

- `Cancel connect` when you are intentionally stopping the current known session
- `Retry connect` after a terminal failure
- `Force restart` when the current session is visible and you want to start over immediately
- `Reset browser connect state` only when state looks inconsistent or stuck

## UI Flow

1. Open `/accounts/douyin`.
2. If a non-completed browser-connect session is visible, use the recovery actions in the browser connect panel.
3. Click `Reset browser connect state`.
4. Confirm the warning that saved accounts will not be deleted.
5. Start browser connect again.

## Backend Contract

Endpoint:

`POST /douyin-accounts/browser-connect/reset`

Response:

```json
{
  "reset_count": 1,
  "affected_session_ids": ["..."],
  "resulting_state": "CANCELLED",
  "can_start_new": true,
  "warning": null
}
```

## V1 Limits

- Reset is explicit and operator-triggered.
- It terminalizes database session state; it does not track browser process handles separately.
- It is designed for local-development recovery, not account deletion or browser runtime repair.
