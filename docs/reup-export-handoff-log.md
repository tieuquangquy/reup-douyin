# Reup Export Handoff Implementation Log

## Scope

This log tracks the product slice that adds durable Export Package generation, explicit Publish Handoff records, and batch operations for Reup Queue.

## Goals

- Move selected Reup Queue items from `READY_TO_EXPORT` into durable Export Packages.
- Let operators inspect package contents before downstream publish work.
- Create explicit Publish Handoff records without triggering external publish automation.
- Add state-aware batch operations with structured per-item results.
- Preserve the existing extension capture, Capture Inbox, Review Board, and Reup Queue workflow boundaries.

## Non-Goals

- No crawler implementation.
- No video processing or render execution implementation.
- No automated external publishing.
- No replacement review architecture.
- No worker queue implementation for export packaging in this slice.
- No secrets, cookies, or platform credentials in package or handoff payloads.

## Audit Notes

- `READY_TO_EXPORT` currently comes from the Reup Queue `MARK_MEDIA_READY` action when media prep status becomes `READY_FOR_EXPORT`.
- Current `READY_TO_EXPORT` actions are limited to complete, block, or cancel; export package and handoff actions do not exist yet.
- `MediaAssetType.EXPORT_PACKAGE` already exists, but there is no durable Export Package domain model or API.
- Existing publish draft creation requires an approved render output and a source video marked `PUBLISH_READY`; Reup Queue `READY_TO_EXPORT` does not guarantee this.
- The new Publish Handoff must therefore be an inspectable handoff record, not an implicit publish attempt.
- Reup Queue web UI currently supports single-item actions and status filtering only; it has no multi-select or batch result display.

## Planned Implementation Layers

1. Documentation-first architecture and operator guide.
2. Backend enums, models, schemas, service, routes, and migration.
3. Batch Reup Queue service support and API endpoint.
4. Web types and API client methods.
5. Reup Queue multi-select and batch actions.
6. Export Package and Publish Handoff list/detail UI.
7. Tests and verification.

## Verification Log

- `python -m unittest tests.test_reup_queue_service tests.test_export_handoff_service` passed: 8 backend tests covered existing Reup Queue lifecycle behavior plus Export Package creation, Publish Handoff creation, and mixed-eligibility batch action results.
- `npx tsx apps/web/src/test/reup-queue.test.ts` passed: web source checks covered Reup Queue multi-select affordances, batch actions, batch result rendering, package/handoff API methods, and package/handoff page links.
- `npx tsx apps/web/src/test/route-nav.test.ts` passed: route and navigation checks covered the new Export Package and Publish Handoff index/detail routes.
- `npm run typecheck` passed for the web TypeScript project.

## Current Status

- Audit completed.
- Documentation created before implementation.
- Backend models, schemas, services, routes, and migration implemented.
- Reup Queue batch action endpoint implemented with structured partial results.
- Web types, API client methods, Reup Queue batch UI, and package/handoff pages implemented.
- Tests and typecheck passed.
- External publish automation remains out of scope; Publish Handoff records are inspectable manual handoff artifacts only.
