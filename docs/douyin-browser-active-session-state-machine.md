# douyin-browser-active-session-state-machine.md

## Purpose

This document defines the V1 backend-owned lifecycle for Douyin browser-assisted connect sessions so stale sessions do not block `/accounts/douyin` indefinitely.

## Canonical Session Model

The canonical persisted model remains `DouyinBrowserConnectSession`.

No second session table, browser pipeline, or frontend-only source of truth is introduced.

## Active States

A session is active-looking when its status is one of:

- `PENDING`
- `LAUNCHING_BROWSER`
- `WAITING_FOR_LOGIN`
- `CAPTURING_SESSION`
- `VALIDATING`

A session is truly active only when it is active-looking and its current phase deadline has not expired.

## Terminal States

Terminal states are:

- `COMPLETED`
- `FAILED`
- `CANCELLED`

Terminal sessions never block a new browser connect attempt.

## Phase Mapping

- `PENDING` / `LAUNCHING_BROWSER` -> `starting_browser`
- `WAITING_FOR_LOGIN` -> `waiting_for_login`
- `CAPTURING_SESSION` -> `capturing_session`
- `VALIDATING` -> `validating_session`
- `COMPLETED` -> `completed`
- `CANCELLED` -> `cancelled`
- `FAILED` -> `failed`

## Stale Rules

V1 stale detection uses backend timestamps only:

- Use `updated_at` as the phase progress timestamp when available.
- Fall back to `started_at` when `updated_at` is unavailable.
- `starting_browser` becomes stale after 60 seconds.
- `waiting_for_login` becomes stale after the session `timeout_seconds` value from metadata.
- `capturing_session` becomes stale after 45 seconds.
- `validating_session` becomes stale after 45 seconds.

When a running-looking session is stale, the backend finalizes it as `FAILED` with a timeout-class error. The response maps those failures to `outcome="timed_out"`.

## Start Behavior

`POST /douyin-accounts/browser-connect/start` follows this order:

1. Check browser runtime readiness.
2. Resolve workspace.
3. Find the latest active-looking session.
4. If stale, finalize it and continue starting a new session.
5. If truly active, return the existing session so the UI can resume/poll it.
6. If none active, create a new session and launch the background browser flow.

## Resume Behavior

Resume does not create a new session. The UI attaches to the backend session id and polls it through the existing `GET /douyin-accounts/browser-connect/{id}` endpoint.

## Cancel Behavior

Cancel moves any non-terminal session to `CANCELLED`, sets `finished_at`, and records a safe operator-facing error code.

## Force Restart Behavior

Force restart explicitly cancels the selected non-terminal session, then starts a new session using the same canonical `start_connect` path.

## UI Mapping

`/accounts/douyin` should show:

- Active healthy session: current status, Resume, Cancel, Force restart, Manual import.
- Stale session: warning, Force restart, Manual import.
- Terminal timed-out/failed/cancelled session: Retry connect and Manual import.
- Completed session: connected account summary and account table refresh.

## V1 Simplifications

- No separate browser process registry is added.
- No distributed heartbeat service is added.
- Staleness is timestamp-based and deterministic.
- Browser process cleanup still relies on the existing cancellation check and Playwright context close behavior.
