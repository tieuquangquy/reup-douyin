# Douyin Browser Watchdog User Guide

## What Changed

Local Douyin Intake now does a lightweight browser-profile watchdog check before deciding whether the selected account is ready for fetch.

If a recent preflight already passed, `/intake` can reuse that short-lived result instead of reopening or rechecking the same browser profile immediately.

## What The Watchdog Checks

The watchdog checks runtime state only:

- active browser profile context,
- stale runtime from idle timeout,
- stale runtime from max lifetime,
- lost/invalid Playwright context,
- missing runtime context.

It does not replace account validation, Douyin fetch validation, or candidate discovery.

## Preflight Cache

Default TTL: 30 seconds.

Only successful preflight results are cached. Failed results are not cached, so fixing an account, reopening a profile, or resetting runtime state can take effect immediately.

Set the TTL with:

```text
DOUYIN_INTAKE_PREFLIGHT_CACHE_TTL_SECONDS=30
```

Use `0` to disable the cache.

## Intake Diagnostics

The `/intake` result can now show:

- `Preflight cache: Reused recent check`
- `Browser watchdog: Browser profile healthy`
- `Runtime state`
- `Runtime reconciled`

These are safe summaries. They do not show cookies, tokens, raw headers, or private profile paths.

## When To Reset Runtime State

Use reset only when the UI still reports stale or invalid runtime state after reopening or validating the account.

Reset clears stuck transient runtime/connect state. It does not delete saved Douyin accounts or the canonical ingest/candidate data.

## Remaining Limits

- A healthy browser runtime can still hit a Douyin challenge page during the real profile fetch.
- The cache is in-memory and clears when the API process restarts.
- The watchdog cannot recover missing browser binaries or broken Playwright installs.
