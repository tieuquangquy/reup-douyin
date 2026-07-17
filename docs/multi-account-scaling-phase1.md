# Multi-Account Scaling Phase 1

Step 21 scales depth on the first real connector, Facebook Reels/Page publishing. It does not add TikTok, YouTube, CRM, or a large scheduler.

## Strategy

Phase 1 uses manual assignment as the source of control:

- `PlatformAccount` represents one publishable Page/account.
- `PublishDraft.assigned_platform_account_id` records the intended Page before publish.
- Routing services compute recommendations from account health, account priority, assignment load, and optional routing rules.
- Operator override is always allowed, but overrides are recorded as `OVERRIDDEN` with metadata.

This keeps the system operationally useful without hiding decisions inside automation.

## Data Additions

`PlatformAccount` now includes:

- `priority`
- `is_on_hold`
- `hold_reason`
- `cooldown_until`
- `allowed_niches_json`
- `routing_notes`

`PublishDraft` now includes:

- `assigned_platform_account_id`
- `assignment_status`
- `assigned_at`
- `assigned_reason`
- `assigned_by`
- `assignment_metadata_json`

`PublishRoutingRule` stores lightweight rule definitions:

- `match_json` for deterministic match conditions
- `action_json` for recommend/exclude/manual-review actions
- `priority` for evaluation order

## Phase 1 Limits

- No cross-platform routing.
- No ML routing.
- No automatic queue publisher.
- No enterprise quota/rate-limit engine.
- No multi-user approval ownership.

The goal is to let one operator route and rebalance drafts across multiple Facebook Pages with clear health and backlog visibility.

