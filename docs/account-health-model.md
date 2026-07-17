# Account Health Model

Account health is deterministic and operator-readable. It is not a black-box score.

## Statuses

- `HEALTHY`: no recent failures or reconciliation blockers.
- `DEGRADED`: some recent failures, reconciliation backlog, or lower success rate.
- `UNHEALTHY`: repeated failures, too much reconciliation backlog, or very low recent success rate.
- `HELD`: account is inactive, manually held, or in cooldown.

## Inputs

The phase 1 health model uses:

- `PlatformAccount.status`
- `is_on_hold`
- `cooldown_until`
- publish attempts in the last 7 days
- success rate
- failed attempts
- reconciliation-needed attempts
- currently assigned and scheduled drafts

## Routing Use

Health affects routing score:

- `HEALTHY`: strong boost
- `DEGRADED`: small boost with warnings
- `UNHEALTHY`: blocked
- `HELD`: blocked

This prevents drafts from being recommended to accounts that are currently failing or under manual hold.

## Limits

The model does not know Facebook quota limits unless the operator encodes them manually through hold/cooldown or future routing rules. It is designed to be simple enough to debug during local operation.

