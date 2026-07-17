# Douyin Manual Import Hardening User Guide

## Canonical Runtime Session Shape

Manual-imported accounts are normalized into:

- `Cookie` header string
- `User-Agent`
- optional `proxy_url`

This is the only runtime shape used by the canonical live fetch path.

## Supported Import Formats

You can paste any of these into the manual import session field:

- raw `Cookie` header string
- `Cookie: ...` header line
- JSON cookie array export
- JSON object with:
  - `cookies`
  - `cookie` / `Cookie`
  - `headers.Cookie`
  - `headers.User-Agent`

## What Happens On Import

1. The API parses the imported payload.
2. It extracts a canonical Cookie header string.
3. It resolves a usable User-Agent from:
   - the explicit `User-Agent` field
   - or imported `headers.User-Agent`
4. It persists the normalized account.
5. It immediately runs a lightweight smoke validation.

## Clear Failure Modes

Possible import outcomes:

- `imported_session_missing_cookie`
- `imported_session_missing_user_agent`
- `imported_session_invalid`
- `login_required`
- `blocked_response`
- `usable_for_fetch`

If the account is not actually usable, it is no longer left looking healthy by default.

## Intake Behavior

`/intake` still uses the same canonical account-backed discovery path.

If an imported account is not usable, `/intake` now fails clearly with structured diagnostics instead of falling through a vague server error.

## Remaining Limitations

- A well-formed import can still be unusable if Douyin rejects or expires the session.
- Legacy imported accounts without a stored User-Agent may need one-time repair or reimport.
- No raw cookies are shown in UI responses or diagnostics.
