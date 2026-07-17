# Douyin Persistent Profile Pivot Architecture

## Goal

Use a persistent local browser profile as the primary local-development strategy for Douyin source accounts.

This reduces repeated QR login and avoids relying on fragile detached cookie-only validation as the main happy path.

## Canonical Model

`DouyinAccountConnection` remains the canonical persisted account model.

The persistent browser profile is a local runtime resource linked from account metadata. It is not a second account table and not a replacement for the canonical account service.

## Profile Strategy

- Each browser-assisted connect creates or reuses a local Playwright persistent profile directory.
- The profile is launched with Playwright `launch_persistent_context`.
- After login, the account stores:
  - `browser_profile_id`
  - `browser_profile_path`
  - `browser_profile_mode = persistent_profile`
- Default profile root: `./data/browser-profiles/douyin`.
- Runtime context handles are kept in memory while the API process is alive.
- If the process restarts, validation/fetch can reopen the same profile directory.

## Connect Flow

1. Operator starts browser connect from `/accounts/douyin`.
2. API launches a persistent local browser profile.
3. Operator logs in once in that browser profile.
4. API captures safe session artifacts from the same profile.
5. API persists/updates `DouyinAccountConnection`.
6. Browser context remains reusable when enabled.

## Validation Flow

Validation preference order:

1. Reuse active live browser context.
2. Reopen persistent browser profile from account metadata.
3. Fall back to detached cookie/session validation.

The validation result mapping remains canonical in `DouyinAccountService`.

## Fetch Flow

Fetch preference is practical V1:

1. Refresh session artifacts from live/reopened persistent browser profile.
2. Continue through the canonical account-backed live fetch client.

This keeps `/intake -> SourceIngestService -> candidate discovery` unchanged.

## Config

- `DOUYIN_PERSISTENT_BROWSER_PROFILE_ENABLED`
- `DOUYIN_PERSISTENT_BROWSER_PROFILES_ROOT_DIR`
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_VALIDATION`
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH`
- Existing live context flags remain supported for runtime reuse.

## Reset And Delete

- Reset browser connect state clears stuck transient connect sessions.
- Reset does not delete persistent profile directories by default.
- Disabling/deleting an account closes any live runtime context for that account.
- Profile deletion is intentionally not automatic in V1.

## Local-Dev Limits

- This is not a cloud browser service.
- Profile paths are local to the machine.
- Browser profile reuse does not bypass Douyin challenges.
- If Douyin invalidates the profile, reconnect is still required.
