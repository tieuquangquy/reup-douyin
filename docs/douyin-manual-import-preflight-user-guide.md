# Douyin Manual Import Preflight User Guide

## What This Adds

Manual-imported Douyin accounts now expose a compact preflight result before you use them in `/intake`.

For imported accounts, `/accounts/douyin` now shows:

- last preflight result
- short reason
- recommended next action
- detected import format
- cookie strength
- last preflight check time

No raw cookie values are shown.

## Preflight Categories

- `usable_for_fetch`
  - The imported session passed fetch preflight.
  - You can use this account in `/intake`.

- `imported_session_missing_cookie`
  - No valid Cookie header could be extracted.
  - Reimport a full Cookie header or cookie export.

- `imported_session_cookie_parse_failed`
  - The pasted JSON cookie export could not be parsed.
  - Reimport valid JSON or paste a raw Cookie header.

- `imported_session_missing_user_agent`
  - The imported session is missing a usable User-Agent.
  - Reimport the session with the browser User-Agent used by the signed-in request.

- `imported_session_cookie_too_thin`
  - The import parsed, but it does not contain strong authenticated Douyin cookies.
  - Reimport a fuller logged-in cookie export.

- `login_required`
  - The import parsed, but Douyin still redirects to login.
  - Reimport a fresh logged-in session or reopen a browser-backed profile and validate again.

- `blocked_response`
  - Douyin rejected this session with a blocked/challenge-style response.
  - Retry from a different network/proxy or use a browser-backed account.

- `validation_transport_error`
  - Validation could not reach Douyin reliably.
  - Check proxy/network and validate again.

- `parse_failed`
  - Douyin responded, but the imported session did not pass fetch preflight cleanly.
  - Reimport a stronger session or use a browser-backed account.

- `unknown_validation_failure`
  - Validation failed, but the reason was not classified more precisely.
  - Retry validation, then reimport if the result repeats.

## How Operators Should Use It

1. Import the session in `/accounts/douyin`.
2. Read the preflight result immediately after save.
3. If the preflight result is not `usable_for_fetch`, fix the import before using `/intake`.
4. Use the row-level `Validate` action after repairing the session.
5. Only use `Use in intake` when the account is clearly fetch-usable.

## What Remains Limited

- Real Douyin validation still depends on live network and anti-bot conditions.
- A session can move from usable to blocked later; preflight is a bounded readiness check, not a permanent guarantee.
- Browser-backed profiles remain the more stable path when manual cookie exports are repeatedly blocked.
