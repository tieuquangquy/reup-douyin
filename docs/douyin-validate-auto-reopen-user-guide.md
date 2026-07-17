# douyin-validate-auto-reopen-user-guide.md

## What Changed

Validate for browser-backed Douyin accounts now auto-reopens the saved reusable browser profile when the live browser runtime is missing. Operators no longer need to manually click Reopen profile before every Validate attempt.

## Saved Profile Versus Live Runtime

A saved browser profile is durable local profile storage linked to the account. It can remain available after the API restarts.

A live browser runtime is the currently attached in-memory browser context. It can disappear after restart, browser close, timeout, or registry loss.

Missing live runtime does not automatically mean the saved profile is bad. Validate now tries to recover from the saved profile first.

## Validate Flow

1. Operator clicks Validate in `/accounts/douyin`.
2. If a live browser context exists, Validate uses it.
3. If no live browser context exists but a saved reusable profile exists, Validate auto-reopens that same saved profile.
4. The reopened browser context is registered for the same account.
5. Validate continues the browser-backed validation probe in that reopened profile.
6. The final account health reflects the browser validation result.

## Result Meanings

- `browser_validation_success`: the reopened or live browser profile validated successfully; stale invalid/blocked state is cleared.
- `browser_validation_runtime_reopened`: Validate recovered the missing live runtime from the saved profile, then continued validation. This is recorded as metadata and UI diagnostics.
- `browser_validation_inconclusive`: the profile was reached, but the browser probe could not prove success or hard failure. This remains retryable/warning-like.
- `browser_validation_blocked`: the browser profile itself showed blocked/challenge evidence.
- `browser_validation_login_required`: the profile needs login again.
- `browser_validation_runtime_unavailable`: the saved profile could not be reopened or the runtime stayed unavailable after the reopen attempt.
- `browser_validation_profile_unavailable`: no usable saved profile metadata exists.

## Operator Notes

- If `/accounts/douyin` shows `Reusable browser profile saved; Validate can auto-reopen it`, clicking Validate should attempt recovery automatically.
- The manual Reopen profile control remains useful for direct operator control, but it is not required before Validate in the common saved-profile case.
- If Validate still returns runtime unavailable, the saved profile could not be opened or attached by the local browser runtime.
- If Validate returns login required, reopen the browser profile and log in again.

## What Stayed Canonical

The same account row, same saved browser profile metadata, same runtime registry, and same browser-primary Intake path remain canonical. No second account model or second browser profile model was added.
