# Reup Export Handoff Resume Notes

## Resume Point

The Export Package, Publish Handoff, and Reup Queue batch operations slice is implemented and verified. Future work should continue from the durable package/handoff records and the explicit Reup Queue states rather than assuming hidden publish automation.

## Current Boundary

A Reup Queue item reaches export readiness when an operator runs `MARK_MEDIA_READY` and selects media prep status `READY_FOR_EXPORT`. That transition sets the queue status to `READY_TO_EXPORT`.

This slice added explicit downstream records and states instead of hiding work behind existing single-item actions. Package creation moves eligible items to `EXPORT_PACKAGE_CREATED`; handoff creation moves linked items to `PUBLISH_HANDOFF_CREATED` and creates an inspectable manual handoff payload.

## Implemented Backend Changes

- Added enums for Export Package status, Publish Handoff status, and batch action names.
- Added models for Export Package, Export Package Item, and Publish Handoff.
- Added migration `0024_reup_export_handoff` after `0023_reup_queue_lifecycle`.
- Added schemas for package creation, package detail/list, handoff creation/detail/list, and batch results.
- Added a service that validates eligibility, creates durable records, and returns safe diagnostics.
- Added API routes for package and handoff list/detail/create operations.
- Added a Reup Queue batch action route that reuses existing single-item lifecycle validation where appropriate.

## Implemented Web Changes

- Added export/handoff TypeScript response types.
- Added API client functions for packages, handoffs, and batch actions.
- Added Reup Queue multi-select, state-aware batch controls, and batch result display.
- Added links from Reup Queue items to created packages/handoffs when available.
- Added package list/detail pages and handoff list/detail pages.
- Updated navigation and route tests for the new operator surfaces.

## Verification Completed

- Backend tests passed for:
  - creating an Export Package from eligible `READY_TO_EXPORT` queue items;
  - rejecting or skipping ineligible queue items;
  - creating Publish Handoff from a package without publishing externally;
  - mixed-eligibility batch operations returning structured partial results.
- Web checks passed for:
  - Reup Queue multi-select and batch labels;
  - batch result rendering;
  - package and handoff route/page/API-client presence.
- Route/navigation checks passed for the new operator pages.
- Web TypeScript typecheck passed.

## Known Constraints

- Do not call external publishing connectors.
- Do not create `PublishAttempt` records in this slice.
- Do not require actual media files to exist locally in tests.
- Do not expose local private paths or secrets in logs, UI, or payload previews.
- Keep local-first data structures compatible with future distributed workers and object storage.
