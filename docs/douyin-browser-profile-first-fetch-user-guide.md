# Douyin Browser Profile First Fetch User Guide

## What Changed

For connected Douyin accounts in local development, `/intake` now prefers the account's reusable browser profile instead of starting with fragile HTTP HTML parsing.

## Why

Douyin can return a shell/challenge page to HTTP fetch. That response can look like a profile page but does not expose videos. Browser-profile-first fetch uses the same persistent logged-in profile that the operator uses in `/accounts/douyin`.

## Operator Workflow

1. Open `/accounts/douyin`.
2. Open or reopen the connected account's browser profile.
3. Make sure the account is validated and usable.
4. Go to `/intake`.
5. Select the connected account and run discovery.

## What To Look For In `/intake`

The result panel shows `Fetch path` when available:

- `Browser profile`: primary local-dev path used.
- `HTTP HTML`: fallback path used because no browser profile was usable.
- `HTTP, then browser profile`: HTTP shell/challenge triggered browser fallback.

If discovery still fails, use:

- `Fetch stage`
- `Fetch code`
- `Parser strategy`
- diagnostics id

to identify whether the failure is blocked response, login required, parse zero videos, true zero videos, or filter zero candidates.

## What Did Not Change

- Connected accounts are still `DouyinAccountConnection` records.
- Intake still persists through `SourceProfile`, `SourceVideo`, `CrawlSession`, and `VideoMetricSnapshot`.
- Candidate discovery is unchanged.
- Manual import remains fallback.

## Limitations

- This does not bypass Douyin challenges.
- The browser profile must already be logged in and usable.
- If the local browser profile is stale or locked, fetch may fall back to HTTP or return a classified failure.
