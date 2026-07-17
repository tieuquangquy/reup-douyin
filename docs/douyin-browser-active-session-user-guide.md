# douyin-browser-active-session-user-guide.md

## Purpose

This guide explains how `/accounts/douyin` behaves when a browser-assisted connect session is already active, stale, cancelled, or timed out.

## What Changed

Previously, starting browser connect could fail with:

`active_session_exists: A browser connect session is already running (...) Cancel it before retrying.`

That was a dead end when the UI no longer knew the session id. The page now asks the backend for the active session and gives the operator explicit recovery actions.

## Normal Flow

1. Open `/accounts/douyin`.
2. Click `Connect with browser`.
3. A real local browser opens on Douyin.
4. Login or scan QR in that browser.
5. The UI polls the backend session.
6. When cookies are captured and validated, the account appears in the connected accounts table.

## If A Session Is Already Running

The page shows a browser connect status card with:

- current phase
- session age
- remaining seconds when known
- stale reason if the backend finalized it as stale
- action buttons

Available actions:

- `Resume current session`: attach to the existing backend session and keep polling.
- `Cancel connect`: mark the current session as `CANCELLED`.
- `Force restart`: cancel the selected running session, then start a new canonical session.
- `Open manual import`: use cookie import fallback without changing the browser session.

## If The Previous Session Is Stale

The backend finalizes stale running-looking sessions as `FAILED` with a timeout-class error. Stale sessions do not block a new session indefinitely.

The UI shows the stale state and allows retry or force restart.

## Backend Rules

Running-looking statuses are:

- `PENDING`
- `LAUNCHING_BROWSER`
- `WAITING_FOR_LOGIN`
- `CAPTURING_SESSION`
- `VALIDATING`

Terminal statuses are:

- `COMPLETED`
- `FAILED`
- `CANCELLED`

Terminal sessions never block a new browser connect.

## V1 Limits

- Stale detection is timestamp-based.
- There is no distributed browser process registry.
- Cancel/restart uses the existing DB session state and the Playwright loop checks that state.
- Manual import remains the fallback when local browser runtime is unavailable.
