# Douyin HTTP To Browser Fallback User Guide

## What Changed

If HTTP profile fetch returns a shell/challenge-style classified failure, the system can automatically retry through the connected account's reusable browser profile.

## Trigger Conditions

Browser fallback is attempted for HTTP classifications:

- `parse_zero_videos`
- `parse_failed`
- `blocked_response`
- `login_required`

It is not attempted for:

- `true_zero_videos`
- `filter_zero_candidates`
- account resolution failures
- persistence failures

## What Operators See

In `/intake`, the fetch path can show:

- `HTTP, then browser profile` when automatic fallback won,
- `Browser profile` when browser-profile-first was used directly,
- `HTTP HTML` when no browser profile path was available.

If both HTTP and browser attempts fail, the final fetch code stays explicit. Diagnostics retain the original HTTP classification under `http_response_classification`.

## What Remains Canonical

Fallback changes only how raw profile/video payload is obtained. The same downstream path persists and evaluates:

- `SourceProfile`
- `SourceVideo`
- `CrawlSession`
- `VideoMetricSnapshot`
- `VideoCandidate`

## Limitations

This does not bypass Douyin challenges. If the reusable browser profile also reaches a challenge page, the run fails with a classified `blocked_response` or related fetch code.
