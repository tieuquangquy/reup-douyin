# Douyin Account Health User Guide

## Health States
- `HEALTHY`: ready for live fetch.
- `STALE`: still usable, but validate soon.
- `EXPIRING_SOON`: still usable, but revalidate before important intake runs.
- `INVALID`: session is incomplete or validation failed.
- `EXPIRED`: Douyin appears to require login again.
- `BLOCKED`: Douyin returned a block/captcha/security signal.
- `DISABLED`: operator disabled the account.
- `UNKNOWN`: account has not been validated yet.

## Manual Validate vs Auto Revalidate
Manual validate checks one account immediately from `/accounts/douyin`.

Auto revalidate queues a job:
- validate one account in the worker, or
- sweep due/stale accounts.

Both paths call the same backend validation service.

## Buttons
- `Validate`: runs validation immediately through the API request.
- `Revalidate`: queues a worker job for that account.
- `Queue health sweep`: queues a worker job for all due/stale accounts.
- `Disable`: blocks the account from live fetch.

## Intake Behavior
`/intake` allows live fetch with:
- `HEALTHY`
- `STALE`
- `EXPIRING_SOON`

`/intake` blocks or warns before live fetch for:
- `INVALID`
- `EXPIRED`
- `BLOCKED`
- `DISABLED`
- `UNKNOWN`

## Security Notes
- Raw cookies are not shown in the UI.
- Raw cookies are not logged.
- Error messages are safe summaries.
- V1 storage is local-first, not production secret vaulting.
