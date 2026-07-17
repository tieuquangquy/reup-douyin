# Douyin Capture Inbox Redesign Architecture

## Product workflow

The end-to-end workflow is:

1. Capture Inbox: operator cleans up and promotes captured Douyin items.
2. Review Board: operator reviews canonical VideoCandidate records.
3. Reup Queue: approved candidates wait for downstream reup work.
4. Publish/Export: rendering, final review, draft preparation, routing, and publish control continue through existing downstream modules.

## Capture Inbox architecture

Capture Inbox keeps its current persistence:

- CaptureSession represents one extension capture operation.
- CapturedItem represents one staged captured row.

The redesigned UI should project these technical records into operator concepts:

- Session Summary: captured count, usable count, duplicate count, pending count, failed count, promoted count, and next action.
- Work Buckets: ready for review, needs enrichment, preview missing, duplicate, excluded, promoted, failed.
- Item Detail Panel: source IDs, URLs, readiness reasons, promotion links, safe raw payload, and error information.

The API can add projection fields without changing ingestion persistence. Raw diagnostics remain safe and are only shown in detail views.

## Review Board boundary

Review Board remains backed by canonical VideoCandidate rows. Capture Inbox promotion creates/reuses SourceProfile, SourceVideo, CrawlSession, VideoMetricSnapshot, and VideoCandidate records. Review Board must not read CapturedItem rows directly and must not duplicate review state.

Approved review decisions are represented by VideoCandidate status APPROVED. Rejected decisions remain VideoCandidate status REJECTED. Existing status transitions are preserved.

## Reup Queue architecture

Reup Queue is a durable downstream queue linked to canonical records:

- workspace_id: tenant/local workspace boundary.
- video_candidate_id: canonical reviewed candidate.
- source_video_id: canonical source video.
- status: queue lifecycle state.
- bucket: operator-facing derived or stored queue bucket.
- priority: sort and operator triage.
- job_id: optional future processing job link.
- publish_draft_id/render_output_id: optional downstream references when they exist.
- idempotency: one active queue item per workspace/candidate.

Initial statuses should be lightweight and explicit:

- READY_FOR_PROCESSING: candidate is approved and queued.
- WAITING_FOR_MEDIA: media/download prerequisites are missing.
- WAITING_FOR_METADATA: metadata preparation is incomplete.
- PROCESSING: background work is running or reserved.
- READY_TO_EXPORT: processing result is ready for export/final review.
- READY_TO_PUBLISH: export/final review has made media publish-ready.
- FAILED_NEEDS_ATTENTION: operator action is required.
- COMPLETED: downstream work is complete.
- CANCELLED: operator removed the item from active work.

This queue does not implement processing itself. It exposes durable work state and can reference jobs as workers are introduced.

## API contract

Recommended endpoints:

- GET /reup-queue/items: list queue items with optional status/bucket filters.
- POST /reup-queue/enqueue-candidates: enqueue approved VideoCandidate IDs idempotently.
- POST /reup-queue/items/{item_id}/actions: hold, retry, cancel, or mark completed in future slices.

Review Board can call enqueue after approval, or the candidate status update endpoint can enqueue approved candidates when requested by a request flag. To avoid hidden side effects, the response should expose created/existing queue counts.

## UI architecture

Capture Inbox main list should prioritize operator answers:

- What was captured?
- What is usable?
- What is duplicate?
- What is pending?
- What failed?
- What should I do next?

Review Board should add a clear action for approved items: Send to Reup Queue. If approval and queueing happen together, copy must state that approved candidates were queued.

Reup Queue page should group items by bucket and show next action for each item without exposing raw infrastructure details.

## Observability and safety

- Logs should include stable IDs: queue item id, candidate id, source video id, job id when present.
- Do not log secrets, cookies, credentials, or private local paths.
- Queue transitions should be idempotent and retry-safe.
- Missing media/metadata should be represented honestly as waiting states, not fake readiness.
