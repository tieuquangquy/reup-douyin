# Douyin Account Health Architecture

## Health Model
Douyin account health is a deterministic projection over:

- `DouyinAccountConnection.status`
- `last_validated_at`
- `last_successful_validation_at`
- `last_validation_status`
- `last_error_code`
- `last_error_message`
- `next_validation_due_at`

V1 health states:

- `HEALTHY`: active session validated recently.
- `STALE`: active session is usable, but validation is older than the freshness window.
- `EXPIRING_SOON`: active session is still usable, but validation age is beyond the warning window.
- `INVALID`: validation failed or session is incomplete.
- `EXPIRED`: validation saw login-required/expired markers.
- `BLOCKED`: validation saw blocking, captcha, rate limit, or security markers.
- `DISABLED`: operator disabled the connection.
- `UNKNOWN`: no validation signal yet.

## Expiry And Staleness Strategy
Provider-derived expiry is not reliable in the current implementation, so V1 uses a documented heuristic:

- Fresh window: 24 hours after successful validation.
- Warning window: 6 days after successful validation.
- `HEALTHY`: active and last successful validation is within 24 hours.
- `STALE`: active and last successful validation is older than 24 hours but not beyond 6 days.
- `EXPIRING_SOON`: active and last successful validation is older than 6 days.
- `EXPIRED`: only set when validation sees login-required/expired markers, not from time alone.

`expires_at` stays optional unless a reliable provider signal becomes available.

## Validation Normalization
Existing validation is still canonical.

Normalized statuses:

- `valid`
- `invalid_session`
- `expired_session`
- `blocked_response`
- `login_required`
- `missing_session`
- `proxy_failure`
- `transport_error`
- `unknown_error`

Validation writes latest account status and latest health summary fields. UI and intake read the safe projection.

## Auto Revalidate Lifecycle
V1 supports two run-now flows:

1. Validate one account:
   - API enqueues `VALIDATE_DOUYIN_ACCOUNT`.
   - Worker calls `DouyinAccountService.validate_account`.
   - Job result stores safe validation summary.

2. Revalidate due accounts:
   - API enqueues `REVALIDATE_STALE_DOUYIN_ACCOUNTS`.
   - Worker finds accounts with `next_validation_due_at <= now`, missing validation, or warning health.
   - Worker validates each due account through the same service.

There is no separate validation pipeline.

## Intake Gating Integration
Policy:

- `HEALTHY`: usable.
- `STALE`: usable with warning.
- `EXPIRING_SOON`: usable with warning.
- `INVALID`, `EXPIRED`, `BLOCKED`, `DISABLED`, `UNKNOWN`: not usable for live fetch.

The API still requires canonical account status to be active for live fetch. The UI surfaces health warnings before submit.

## No-Duplication Strategy
This step does not add:

- a second account model
- a second validation implementation
- a separate intake/live-fetch pipeline
- a validation history table
- a scheduler platform

## V1 Limitations
- Expiry warning is heuristic unless provider expiry is later extracted from session artifacts.
- Auto revalidate is queueable/run-now; real periodic scheduling is a later worker/ops step.
- Validation remains a lightweight network marker check, not a full production Douyin account health proof.
- V1 stores only latest health summary, not a full validation event history.
