# Reup Pipeline Dashboard Architecture

## Overview

The Reup Pipeline Dashboard is a read-only operator command surface for the end-to-end workflow:

Capture -> Review -> Reup Queue -> Export Package -> Publish Handoff -> Publish progress.

It summarizes health, progress, bottlenecks, blockers, and recommended next actions while preserving existing stage ownership.

## Boundary Decisions

### Web boundary

`apps/web` owns presentation only:

- Render `/ops/pipeline`.
- Fetch one dashboard summary contract from `apps/api`.
- Render stage cards, pipeline visualization, attention panels, recent activity, and quick links.
- Reuse Ops Console Design System primitives.

`apps/web` must not:

- Query the database directly.
- Run long-running work.
- Infer storage/queue/publish internals beyond the API contract.
- Trigger publish attempts automatically.

### API boundary

`apps/api` owns aggregation:

- Query stage tables.
- Normalize stage status into an operator-safe dashboard model.
- Count backlogs and failures.
- Produce recent activity rows from safe metadata and timestamps.
- Avoid raw secrets, tokens, cookies, credentials, and private local paths.

### Worker boundary

`apps/worker` remains unchanged. The dashboard does not introduce background jobs.

## Proposed API Contract

Endpoint:

- `GET /ops/pipeline-dashboard`

Top-level response fields:

- `generated_at`
- `overall_status`
- `headline`
- `summary_metrics`
- `stages`
- `attention_items`
- `recent_activity`
- `quick_links`

### Dashboard status model

Use a small operator-facing status model:

- `healthy`: stage is moving and no blocking backlog is detected.
- `needs_attention`: stage has backlog, warnings, or operator action required.
- `blocked`: stage has failed records or unresolved blocked work.
- `quiet`: stage has no recent activity and no active backlog.
- `in_progress`: stage has active work moving through it.

The status model is separate from persistence enums. It does not rewrite canonical stage status meanings.

### Stage model

Each stage should include:

- `key`
- `label`
- `description`
- `status`
- `primary_count`
- `primary_label`
- `secondary_count`
- `secondary_label`
- `metrics`
- `attention_count`
- `href`
- `next_action`

Stage keys:

- `capture`
- `review`
- `reup_queue`
- `export_package`
- `publish_handoff`
- `publish_progress`

### Attention model

Each attention item should include:

- `id`
- `severity`: `info`, `warning`, or `critical`
- `stage_key`
- `title`
- `detail`
- `count`
- `href`
- `recommended_action`

Attention should highlight operator-actionable conditions, such as failed capture items, approved candidates not queued, queue failures, packages ready for handoff, handoffs waiting for operator acceptance, and publish attempts needing reconciliation.

### Recent activity model

Each recent activity item should include:

- `id`
- `stage_key`
- `title`
- `detail`
- `occurred_at`
- `href`

Activity sources should be safe, high-level lifecycle changes derived from timestamps such as `created_at`, `updated_at`, `ready_at`, `failed_at`, `accepted_at`, `published_at`, or attempt status timestamps.

## Aggregation Sources

### Capture stage

Tables:

- `capture_sessions`
- `captured_items`

Useful fields:

- `CaptureSession.status`
- `CaptureSession.created_at`
- `CaptureSession.ready_item_count`
- `CaptureSession.promoted_item_count`
- `CaptureSession.failed_item_count`
- `CapturedItem.status`
- `CapturedItem.error_code`
- `CapturedItem.error_message`
- `CapturedItem.promoted_video_candidate_id`

### Review stage

Table:

- `video_candidates`

Useful fields:

- `VideoCandidate.status`
- `VideoCandidate.score`
- `VideoCandidate.priority`
- `VideoCandidate.created_at`
- `VideoCandidate.updated_at`

Approved but not queued requires checking for missing `reup_queue_items.video_candidate_id`.

### Reup Queue stage

Table:

- `reup_queue_items`

Useful fields:

- `status`
- `media_prep_status`
- `blocked_reason`
- `blocked_at`
- `held_at`
- `failed_at`
- `last_error_code`
- `last_error_message`
- `queued_at`
- `started_at`
- `completed_at`
- `updated_at`

### Export Package stage

Tables:

- `export_packages`
- `export_package_items`

Useful fields:

- `ExportPackage.status`
- `ExportPackage.item_count`
- `ExportPackage.ready_at`
- `ExportPackage.failed_at`
- `ExportPackage.cancelled_at`
- `ExportPackage.created_at`
- Relationship to publish handoffs.

### Publish Handoff stage

Table:

- `publish_handoffs`

Useful fields:

- `status`
- `target_platform`
- `ready_at`
- `accepted_at`
- `failed_at`
- `cancelled_at`
- `created_at`
- `updated_at`

### Publish progress stage

Tables:

- `publish_drafts`
- `publish_attempts`

Useful fields:

- `PublishDraft.status`
- `PublishDraft.ready_at`
- `PublishDraft.scheduled_at`
- `PublishDraft.published_at`
- `PublishDraft.current_publication_status`
- `PublishDraft.last_publish_synced_at`
- `PublishAttempt.status`
- `PublishAttempt.reconciliation_required`
- `PublishAttempt.reconciliation_status`
- `PublishAttempt.started_at`
- `PublishAttempt.finished_at`
- `PublishAttempt.error_code`
- `PublishAttempt.error_message`

## UX Architecture

The `/ops/pipeline` page should use existing Ops Console primitives:

- `OpsConsoleShell`
- `PageShell`
- `OpsWorkflowContext`
- `OpsNextActionBanner`
- `OpsSummaryCards`
- `OpsItemCard`
- `OpsDetailPanel`
- `OpsDetailSection`
- `OpsMetadataList`
- `OpsStatePanel`
- `OpsActionRow`

Dashboard-specific layout can use existing panel/card classes from `apps/web/src/app/globals.css` and add minimal scoped classes only if required.

## Observability and Safety

- Aggregation should return stable counts and IDs only where useful for navigation.
- Error summaries must be actionable without dumping raw payloads.
- No raw secrets, tokens, cookies, account credentials, or private local paths should be returned.
- The endpoint should be read-only.

## Testing Strategy

API tests should validate:

- Empty database returns quiet/empty dashboard safely.
- Failed capture/queue/publish records create attention items.
- Approved candidates without queue items are counted.
- Export packages and handoffs readiness counts are correct.
- Response contract is stable.

Web tests should validate:

- `/ops/pipeline` route exists.
- Page uses Ops Console Design System primitives.
- Stage labels and canonical links are present.
- Attention and recent activity sections are present.
- API client function and types are wired.
