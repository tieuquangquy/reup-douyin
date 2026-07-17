# Douyin Browser Primary Fetch User Guide

## What Changed

For connected Douyin accounts in local development, `/intake` treats the reusable local browser profile as the primary fetch path.

HTTP fetch is now a secondary fallback when the browser profile or browser runtime is unavailable.

## What Operators Should See

In `/intake`, successful or failed discovery can show:

- `Fetch strategy: Browser profile first`
- `Fetch path: Browser profile`
- `Fetch path: HTTP HTML` if the browser profile was unavailable and HTTP fallback ran
- `HTTP fallback` with a reason when fallback happened

## Recommended Workflow

1. Open `/accounts/douyin`.
2. Reopen and validate the connected account's browser profile.
3. Go to `/intake`.
4. Select that account and run discovery.

## How To Interpret Results

- `Browser profile first` means the app attempted the persistent browser profile before HTTP.
- `Browser profile` means the browser profile produced the final raw payload.
- `HTTP HTML` with HTTP fallback means the browser profile was unavailable and the app degraded to HTTP.
- A blocked/login/parse failure from `Browser profile` means the browser profile itself could not fetch usable profile videos.

## What Remains Unchanged

The same downstream pipeline remains canonical:

- `DouyinAccountConnection`
- `SourceProfile`
- `SourceVideo`
- `CrawlSession`
- `VideoMetricSnapshot`
- `VideoCandidate`

No browser-only ingest pipeline exists.

## Limits

This does not bypass Douyin challenges. It only uses the most reliable local authenticated context first and makes fallback/failure states explicit.
