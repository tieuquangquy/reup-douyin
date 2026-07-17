# Douyin Intake Account Selection User Guide

## What Changed
`/intake` now uses backend-canonical account resolution for live fetch and can automatically fallback to a healthier usable Douyin account when needed.

## Account Health and Usability
Usable for intake live fetch:
- `HEALTHY`
- `STALE`
- `EXPIRING_SOON`

Not usable for intake live fetch:
- `INVALID`
- `EXPIRED`
- `BLOCKED`
- `DISABLED`
- `UNKNOWN`

## Operator Behavior
- You can choose a specific account in `/intake`.
- If your selected account is usable, intake uses it.
- If your selected account is unusable, intake automatically switches to the best usable account and shows a fallback notice.
- If no usable account exists, intake blocks live fetch and directs you to `/accounts/douyin`.

## Selection Explainability
Intake status/result now indicates:
- which account you selected,
- which account was actually used,
- whether fallback happened,
- why fallback was applied.

## Recommended Operator Actions
1. Keep at least one validated `HEALTHY` account as default.
2. Revalidate `STALE`/`EXPIRING_SOON` before critical runs.
3. If intake reports no usable account, open `/accounts/douyin` and validate or reconnect an account.

## Safety Notes
- Backend is final authority for account resolution.
- Session secrets remain hidden in UI/API responses.
- Fallback is explicit, not silent.
