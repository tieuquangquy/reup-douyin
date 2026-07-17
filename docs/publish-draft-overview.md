# Publish Draft Overview

Publish draft is the metadata handoff contract for future publish connectors. It sits after final review and before any platform-specific posting integration.

## Purpose

A `PublishDraft` captures:

- source video reference
- approved render output reference
- target platform
- account reference placeholder
- caption
- CTA
- hashtags
- optional planned publish time
- operator notes and platform notes

Phase 1 now includes the first real connector path for Facebook Reels/Page publishing. `PublishDraft` remains the metadata contract; actual external publish executions are recorded as `PublishAttempt` rows.

## Publish-Ready vs Draft Ready

These states are intentionally different:

- `SourceVideo.status = PUBLISH_READY`: media is accepted after final review and can enter publish preparation.
- `PublishDraft.status = READY`: publish metadata has been checked and is ready for a connector or manual publishing step.

Media readiness does not mean caption/CTA/hashtags are ready. Draft readiness does not mean the video was published.

## Current Model

Phase 1 keeps publish preparation in `publish_drafts` rather than introducing separate tables for each small structure.

Canonical structures:

- Publish target: `target_platform`, `platform_account_ref`, `platform_payload_json`
- Caption draft: `caption`, `caption_draft_json`
- CTA draft: `cta_text`, `cta_draft_json`
- Hashtag draft: `hashtags_json`
- Schedule skeleton: `planned_publish_at`, `timezone`, `scheduled_at`, `schedule_json`

This keeps the schema simple while still making each concept explicit.

## Lifecycle

`PublishDraftStatus` supports:

- `DRAFT`: editable metadata, not ready for handoff.
- `READY`: metadata is complete and validated.
- `SCHEDULED`: planned publish time is set, but no real scheduler runs in Phase 1.
- `PUBLISHING`: a publish attempt is active.
- `PUBLISHED`: a canonical publish attempt is confirmed as published.
- `FAILED`: latest attempt failed and there is no canonical success.
- `NEEDS_ATTENTION`: latest publish state is uncertain and needs operator reconciliation.
- `ARCHIVED`: no longer active.

## Creation Policy

A publish draft can be created only when:

- the source video is `PUBLISH_READY`
- the chosen render output is `APPROVED`

`Mark ready` also checks risk gate rules. Critical active warnings block the action unless the operator records `ACCEPT_WITH_WARNING`; high warnings require an operator decision.

If `source_video_id` is supplied, the API resolves the latest render output for that video. If `render_output_id` is supplied, the API uses that exact render.

## API

Phase 1 endpoints:

- `GET /publish-targets`
- `POST /publish-drafts`
- `GET /publish-drafts`
- `GET /publish-drafts/{publish_draft_id}`
- `PATCH /publish-drafts/{publish_draft_id}`
- `POST /publish-drafts/{publish_draft_id}/schedule`
- `POST /publish-drafts/{publish_draft_id}/unschedule`
- `POST /publish-drafts/{publish_draft_id}/mark-ready`
- `POST /publish-drafts/{publish_draft_id}/publish`
- `GET /publish-attempts`
- `GET /publish-attempts/{publish_attempt_id}`
- `GET /publish-drafts/{publish_draft_id}/publish-status`
- `POST /platform-accounts`
- `GET /platform-accounts`

## Future Connector Handoff

Connectors should consume `PublishDraft` only when status is `READY`, then combine it with the approved `RenderOutput` and platform account credentials.

The connector should not regenerate caption, CTA, hashtags, or choose a different render unless explicitly requested by a future workflow.

See also:

- `docs/facebook-reels-connector.md`
- `docs/platform-account-setup-phase1.md`
- `docs/publish-attempt-lifecycle.md`
- `docs/publish-retry-and-idempotency.md`
