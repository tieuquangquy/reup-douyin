# Douyin Persistent Browser Profile User Guide

## What Changed

Browser-assisted Douyin connect now uses a reusable local browser profile as the primary local-dev path.

The older behavior was fragile because it relied on logging in, capturing cookies, then closing the browser/context. The new behavior keeps a Playwright persistent profile on disk so the same authenticated browser state can be reused for future validation and fetch preparation.

## Operator Flow

1. Open `/accounts/douyin`.
2. Click `Connect with browser`.
3. Complete login in the opened Douyin browser profile.
4. Keep the browser open while validation runs.
5. After success, the account is stored as a normal `DouyinAccountConnection`.
6. Future `Validate`, `Retry validation`, and `/intake` fetch preparation prefer the saved browser profile.
7. If the API process restarts, validation/fetch can reopen the saved profile directory.

## What Is Still Canonical

- `DouyinAccountConnection` remains the persisted source-account model.
- `/intake` still uses the canonical account-backed source ingest path.
- Source persistence still flows through `SourceProfile`, `SourceVideo`, `CrawlSession`, metrics, and candidates.
- Manual session import remains available as fallback.

## Status Labels

- `Live browser attached`: a Playwright context is currently open and linked to the account.
- `Reusable profile saved`: a persistent browser profile exists on disk and can be reopened.
- `No live browser`: no runtime context or saved profile is available.
- `Browser stale` / `Browser closed`: runtime context was no longer usable; reconnect or validate to reopen if a profile exists.

## Reset And Recovery

`Reset browser connect state` clears stuck transient connect sessions. It does not delete saved Douyin accounts and does not delete the persistent profile directory by default.

If a saved profile becomes unusable because Douyin invalidates it, reconnect with browser. The canonical account row stays the same lifecycle owner.

## Local Settings

Relevant API settings:

- `DOUYIN_PERSISTENT_BROWSER_PROFILE_ENABLED=true`
- `DOUYIN_PERSISTENT_BROWSER_PROFILES_ROOT_DIR=./data/browser-profiles/douyin`
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_VALIDATION=true`
- `DOUYIN_PREFER_BROWSER_PROFILE_FOR_FETCH=true`

## Intentional V1 Limits

- No password automation.
- No cloud browser service.
- No profile sync across machines.
- No automatic deletion of profile directories on account delete.
- Fetch still uses the canonical fetch client after refreshing session artifacts from the profile.
