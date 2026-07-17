# Scheduling Skeleton

Scheduling in Phase 1 is persistence-only. It records operator intent but does not enqueue or publish anything automatically.

## Stored Fields

`PublishDraft` stores:

- `planned_publish_at`: intended publish datetime.
- `timezone`: operator-facing timezone label.
- `scheduled_at`: when the draft was marked scheduled.
- `scheduling_notes`: operator notes.
- `schedule_json`: structured schedule metadata.

`schedule_json.status` is currently either `scheduled` or `unscheduled`.

## Status Behavior

Scheduling a draft sets:

- `PublishDraft.status = SCHEDULED`
- `planned_publish_at`
- `timezone`
- `scheduled_at`
- `schedule_json`

Unscheduling clears the planned time and sets status back to:

- `READY` if caption, CTA, hashtag, and target validation passes
- otherwise `DRAFT`

## No Auto Publish In Phase 1

No cron, queue job, or external connector reads `planned_publish_at` yet. That is deliberate. The scheduler abstraction is a future step after social account connectors exist.

## Future Extension

When connectors are added, the scheduler should:

- query `PublishDraft.status = SCHEDULED`
- verify the associated render output is still approved
- verify platform account credentials
- claim due drafts idempotently
- create durable jobs for publish attempts
- record connector response and failure state

The current skeleton keeps enough fields to support that future path without committing to a queue implementation now.
