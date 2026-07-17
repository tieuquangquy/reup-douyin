# Douyin Hard Reset User Guide

## Primary Workflow

1. Open `/accounts/douyin`.
2. Use **Create browser profile** to create a connected account.
3. Login to Douyin in the opened browser profile.
4. Keep/reopen that same browser profile for future validation and Intake runs.
5. Use **Use in intake** on the connected account.
6. Run discovery from `/intake`.

## What Changed

The main workflow now expects a reusable local browser profile. HTTP cookie scraping and manual cookie import are not the normal path.

## Legacy Manual Import

Manual import is still available under troubleshooting for diagnostics or emergency fallback. It is not recommended for reliable local discovery.

## HTTP Fallback

HTTP fallback is disabled by default for connected-account Intake. Enable only when intentionally debugging legacy behavior:

```text
DOUYIN_ALLOW_LEGACY_HTTP_FALLBACK_FOR_INTAKE=true
```

Do not enable this for normal local discovery. It can reproduce the old
HTML-shell/challenge behavior.

## Browser Profile Fetch Behavior

When `/intake` uses a connected account, the API:

1. checks account health,
2. checks the saved browser profile,
3. reopens that same profile if needed,
4. fetches the target Douyin profile through the browser context,
5. waits briefly and scrolls the page so lazy-loaded video data can appear,
6. sends extracted profile/video data into the existing ingest pipeline.

## If Intake Fails

The failure should say which stage failed:

- `browser_profile_required`
- `browser_profile_unavailable`
- `login_required`
- `blocked_response`
- `parse_zero_videos`
- `parse_failed`

Do not tune candidate filters until the fetch stage has actually returned videos.

## Current Local Verification State

The code, tests, and routes are verified. A live real-profile discovery still
requires an account that has a reusable browser profile attached and is logged
in. If `/intake` says `browser_profile_required`, go back to `/accounts/douyin`
and create/reopen the profile for that account.

## What Remains External

Douyin can still challenge or block a logged-in browser profile. The app now reports that explicitly instead of pretending the profile has no videos.
