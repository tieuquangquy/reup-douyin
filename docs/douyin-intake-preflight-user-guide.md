# Douyin Intake Preflight User Guide

## What Changed

`/intake` now checks Douyin account and browser-profile readiness before starting a real discovery run.

This prevents obvious failed runs when:

- the selected account is blocked, invalid, disabled, or expired,
- the reusable browser profile exists but is closed,
- browser-profile fetch is preferred but the runtime is not ready,
- HTTP fallback does not have enough session material.

## What Happens Before Fetch

Preflight runs after account selection and before ingest:

1. Resolve the selected/default/fallback Douyin account.
2. Check account health.
3. Check saved browser profile/runtime state.
4. Auto reopen the saved browser profile once when appropriate.
5. Decide selected fetch path:
   - `browser_profile`
   - `http_html`
6. Start canonical ingest only if fetch is ready.

## Intake Result Fields

The Intake result panel can show:

- `Preflight`
- `Fetch readiness`
- `Browser reopen`
- `Fetch path`
- `Fetch strategy`

## Readiness Categories

- `Browser profile ready`: browser profile was already active.
- `Browser profile reopened`: the saved profile was reopened before fetch.
- `HTTP fallback ready`: browser profile was unavailable, but HTTP fallback is usable.
- `Not fetch-ready`: fetch was blocked before full discovery.

## What To Do If Preflight Fails

- Reopen and validate the account in `/accounts/douyin`.
- Check whether the account is blocked or expired.
- Reset stuck browser runtime state only if local dev state is inconsistent.
- Reimport or reconnect the account if HTTP fallback material is missing.

## What Remains Unchanged

Preflight does not create source profiles, source videos, candidates, or crawl records by itself. The canonical pipeline remains:

```text
DouyinProfileAdapter -> SourceIngestService -> SourceProfile/SourceVideo/CrawlSession -> CandidateEvaluationService
```

## Limitations

Preflight cannot guarantee Douyin will not challenge the actual profile page. It only prevents obviously doomed fetch attempts and reopens the saved browser profile when that is safe.
