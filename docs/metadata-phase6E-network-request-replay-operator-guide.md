# Phase 6E Network Request Replay Operator Guide

## Why this comes before modal auto-harvest

- The profile/feed page already loads batch aweme metadata in network responses.
- If those requests can be discovered and replayed in the same browser session, the system can update many captured items without opening every video detail page.
- That is narrower, safer, and faster than per-item detail-page automation.

## Chosen architecture

- Backend browser-side request discovery
- Backend browser-session replay
- Exact `aweme_id` batch update into existing Capture Inbox rows

## Candidate detection rules

A request is considered a candidate only when its response JSON contains aweme-like objects with:

- `aweme_id`
- and at least one of:
  - `statistics`
  - `video`
  - `create_time`
  - `desc`
  - `author`

## Replay strategy

- replay inside the same saved Douyin browser profile
- concurrency `1`
- slow delay between pages
- stop on captcha/login/security block
- match existing `CapturedItem` rows by exact `aweme_id` only

## Safety behavior

- no captcha bypass
- no secret header/cookie persistence
- no duplicate item creation
- no DOM-invented metrics

## Expected operator command

```powershell
cd apps/api
python scripts/discover_and_replay_douyin_profile_requests.py --session-id <capture_session_id> --max-pages 3
```

## Expected follow-up

- rerun the live metadata acceptance audit after successful replay update

## Current live test sequence

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --operator-confirm-ready
python scripts/discover_and_replay_douyin_profile_requests.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740 --max-pages 3
python tests/metadata_phase5a_real_live_audit.py
```

## Expected success signals

- `raw_network_aweme > 0`
- `duration_seconds > 0` when replayed aweme contains `video.duration`
- `view_count > 0` and `like_count > 0` when replayed aweme contains `statistics`
- `performance_status = captured` for at least some matched items
- `processing_fit_status = captured` for at least some matched items

## Status

- implementation complete
