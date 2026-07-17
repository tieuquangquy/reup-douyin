# Reup Queue Lifecycle Architecture

## Summary

This slice makes Reup Queue an explicit operational workspace downstream of Review Board approval. It adds deterministic state transitions, operator actions, and a narrow media-prep handoff while preserving the existing local-first and SaaS-ready boundaries.

## System Boundaries

```text
Extension capture -> Capture Inbox -> Review Board -> Reup Queue -> Media prep handoff -> Future export/publish
```

- Extension capture owns browser-side capture.
- Capture Inbox owns raw/staged captured items.
- Review Board owns canonical candidate review through `VideoCandidate`.
- Reup Queue owns approved downstream work tracking.
- Worker/job infrastructure owns future long-running processing.
- Publish control remains a future downstream consumer.

## Data Model Approach

Use the existing `ReupQueueItem` as the lifecycle record. Add narrow lifecycle/media-prep fields on that record:

- `media_prep_status`: textual sub-state for media handoff readiness.
- `media_prep_notes`: safe operator-visible notes.
- `media_ready_at`: timestamp for explicit media readiness.
- `blocked_reason`: safe reason shown in UI.
- `blocked_at`: timestamp for blocked state.
- `held_at`: timestamp for hold/pause state.
- `failed_at`: timestamp for explicit failure state.
- `last_action`: last operator/system action applied.
- `last_action_at`: timestamp for the last action.
- `last_action_note`: safe operator note for the action.

The existing `metadata_json` remains available for non-contractual supplementary details, but operator-critical lifecycle fields should be first-class columns.

## Lifecycle State Semantics

- `READY_FOR_PROCESSING`: item is approved and waiting for operator/worker start.
- `WAITING_FOR_MEDIA`: item cannot proceed until source media is attached/downloaded/confirmed.
- `WAITING_FOR_METADATA`: item has media but still needs caption/language/metadata preparation.
- `PROCESSING`: item is actively being prepared or handed to a durable job.
- `READY_TO_EXPORT`: media preparation is complete enough for future export.
- `READY_TO_PUBLISH`: retained for future publish-ready compatibility; not automatically reached by this slice.
- `FAILED_NEEDS_ATTENTION`: item failed or is manually blocked in a way that requires operator decision.
- `COMPLETED`: downstream work is done.
- `CANCELLED`: operator explicitly removed item from active downstream work.

## Operator Action Model

Actions are explicit API calls. Each action validates the current state, updates first-class fields, records the last action, and returns the updated item with available next actions.

Allowed actions:

- `START_PROCESSING`
- `MARK_MEDIA_READY`
- `MARK_BLOCKED`
- `HOLD`
- `RESUME`
- `RETRY`
- `CANCEL`
- `MARK_COMPLETED`

Actions do not perform long-running work inline. When future worker integration is added, an action may create or attach a durable job, but this slice only records the handoff-ready state.

## Media-Prep Handoff

Media preparation is modeled as an explicit queue item sub-state, not as hidden processing. The operator can mark media ready only when prerequisites are known. The action stores safe notes and advances the item toward metadata prep or export readiness.

This slice ends at `READY_TO_EXPORT`. Future slices can consume that state to create render outputs, export packages, publish drafts, or worker jobs.

## API Surface

Expected API additions:

- `GET /reup-queue/items/{item_id}`: item detail.
- `POST /reup-queue/items/{item_id}/actions`: apply one lifecycle action.

Existing endpoints remain:

- `GET /reup-queue/items`
- `POST /reup-queue/enqueue-candidates`

The list response should expose `total_count`, `limit`, and `offset` consistently.

## UI Surface

The Reup Queue page should show:

- queue grouping by lifecycle bucket,
- selected item detail,
- available actions only for the current state,
- safe blocked/failed/hold reasons,
- media-prep readiness,
- linked job/render/publish IDs when present,
- source link and existing downstream editor links,
- raw technical details behind a disclosure.

## Observability

Service actions should log lifecycle transitions with stable identifiers:

- queue item id,
- workspace id,
- candidate id,
- source video id,
- action,
- from status,
- to status.

Logs must not include secrets, raw credentials, or private local paths.

## Future Extension Points

- Attach `Job` records for actual media download, analysis, render prep, or export.
- Use `MediaAsset` records for source video, derived audio, transcript, subtitles, and export packages.
- Promote `READY_TO_EXPORT` items into render/export workflows.
- Promote future `READY_TO_PUBLISH` items into publish control.
