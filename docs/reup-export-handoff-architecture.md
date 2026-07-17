# Reup Export Handoff Architecture

## Purpose

This slice introduces an explicit boundary between Reup Queue export readiness and downstream publish preparation. Operators can group export-ready queue items into durable Export Packages, inspect package contents, and create Publish Handoff records for manual or future automated publishing workflows.

## Workflow Position

The canonical workflow remains:

1. Extension capture.
2. Capture Inbox staging.
3. Review Board decisioning.
4. Reup Queue downstream preparation.
5. Export Package generation.
6. Publish Handoff inspection.
7. Future publish execution outside this slice.

Export Packages and Publish Handoffs are downstream records. They do not replace Capture Inbox, Review Board, or Reup Queue.

## Domain Model

### Export Package

An Export Package is a durable operator-created grouping of one or more Reup Queue items that are ready for export.

Core fields:

- workspace id.
- status.
- package label.
- operator note.
- package manifest payload.
- diagnostics payload.
- created/exported timestamps.

Expected statuses:

- `DRAFT` for a package created and inspectable by the operator.
- `READY_FOR_HANDOFF` when package contents passed the lightweight readiness checks available in this slice.
- `HANDOFF_CREATED` when at least one Publish Handoff exists for the package.
- `FAILED_NEEDS_ATTENTION` for explicit operator-visible package failures.
- `CANCELLED` for operator-cancelled packages.

### Export Package Item

An Export Package Item links a package to a Reup Queue item and preserves item-level diagnostics.

Core fields:

- export package id.
- reup queue item id.
- source video id.
- video candidate id.
- render output id if available.
- publish draft id if available.
- item status.
- item manifest payload.
- diagnostics payload.

### Publish Handoff

A Publish Handoff is an inspectable record that packages the metadata needed for a human operator or future publish system to proceed. It is not a publish attempt.

Core fields:

- workspace id.
- export package id.
- target platform.
- status.
- handoff payload.
- diagnostics payload.
- operator note.
- created/ready timestamps.

Expected statuses:

- `DRAFT` when created but not marked ready.
- `READY_FOR_OPERATOR` when the handoff is inspectable and ready for manual publishing work.
- `ACCEPTED` when a downstream operator/system has acknowledged it.
- `FAILED_NEEDS_ATTENTION` when required payload data is missing or invalid.
- `CANCELLED` when the handoff is no longer active.

## State Transitions

The minimal explicit queue path becomes:

- `READY_TO_EXPORT` after media-prep handoff.
- `EXPORT_PACKAGE_CREATED` after a package item is successfully created.
- `READY_TO_PUBLISH` after a Publish Handoff is created.
- `PUBLISH_HANDOFF_CREATED` when the handoff record exists and is inspectable.
- `COMPLETED` only when downstream work is known complete.

The implementation should allow these states to be visible in queue filtering and batch eligibility while avoiding hidden side effects.

## Readiness Checks

Export Package creation checks:

- queue item exists.
- queue item is in `READY_TO_EXPORT`.
- item has `READY_FOR_EXPORT` media prep status.
- item is not cancelled or completed.
- duplicate package membership is avoided for active packages.

Publish Handoff creation checks:

- package exists.
- package has at least one item.
- package is not cancelled.
- handoff target platform is explicit.
- payload can be generated without secrets.

Missing render outputs, publish drafts, or media assets should be diagnostics, not hidden blockers unless the requested handoff requires them.

## Batch Result Model

Batch operations return structured results:

- requested count.
- succeeded count.
- skipped count.
- failed count.
- created package id if relevant.
- created handoff id if relevant.
- per-item results containing item id, status, result state, reason code, message, and linked record ids.

The API must not collapse partial failures into a generic error if some selected items succeeded.

## Publish Surface Reuse

Existing Publish Draft and Publish Attempt services remain separate. This slice may link to `publish_draft_id` already present on a queue item, but it must not create publish attempts or trigger external connectors.

A future slice may consume Publish Handoff records to create or update Publish Drafts after stronger render/media requirements are met.

## Observability

Services record safe diagnostics in model fields and return reason codes for operator display. Logs and payloads must not include secrets, auth tokens, cookies, or private absolute paths.

## Verification Status

Implemented and verified with:

- `python -m unittest tests.test_reup_queue_service tests.test_export_handoff_service`.
- `npx tsx apps/web/src/test/reup-queue.test.ts`.
- `npx tsx apps/web/src/test/route-nav.test.ts`.
- `npm run typecheck`.

## Local-First and SaaS-Ready Notes

The package and handoff models are workspace-scoped and explicit. Their manifest payloads are JSON for local-first flexibility, but durable model boundaries keep room for future object storage, distributed workers, and multi-user ownership.
