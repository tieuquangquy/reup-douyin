# Reup Queue UX Redesign Log

## Status

Implemented and verified. This document was created before UI implementation to record the audit, intended scope, implementation notes, and verification results for the Reup Queue operator-first redesign.

## Request

Redesign the Reup Queue UI/UX to match the operator-first design system introduced for Douyin Capture Inbox, so the workflow feels consistent:

Capture Inbox -> Review Board -> Reup Queue -> Export Package -> Publish Handoff.

## Scope

Touched areas expected for this slice:

- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/test/reup-queue.test.ts`
- `docs/reup-queue-ux-redesign-log.md`
- `docs/reup-queue-ux-redesign-resume.md`
- `docs/reup-queue-ux-redesign-architecture.md`
- `docs/reup-queue-ux-redesign-user-guide.md`

API changes are not expected. The current Reup Queue API already exposes statuses, media prep state, lifecycle timestamps, source video context, available actions, metadata, and batch operations needed for the UI redesign.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering implementation.
- No new database schema or queue implementation.
- No automatic publishing.
- No hidden publish automation from Publish Handoff.
- No changes to the durable lifecycle or backend state machine unless a UI-blocking issue is discovered.
- No rewrite of unrelated Review Board, Capture Inbox, Export Package, or Publish Handoff pages.

## Audit findings

### Current Reup Queue strengths

- The page already loads Reup Queue items with `fetchReupQueueItems`.
- Existing operator actions use `runReupQueueAction` and preserve backend-owned lifecycle decisions.
- Existing batch actions use `runReupQueueBatchAction`, including Export Package and Publish Handoff creation.
- Items are already grouped into work buckets.
- The detail panel already keeps raw queue JSON behind a collapsed disclosure.
- Export Package and Publish Handoff identifiers are already discoverable through item metadata.

### Current UX gaps

- The page still uses older `review-board` / `board-header` layout classes instead of the newer Capture Inbox operator workspace hierarchy.
- Summary cards are passive metrics rather than clickable work filters.
- Filtering is status-select-only; there is no search row, filter chip row, or operator sort mode.
- Main item cards expose technical queue fields in the collapsed list, including raw bucket names, blocked reason, package ids, handoff ids, and timestamps.
- Next action is visible but not prominent enough to guide an operator.
- Export Package and Publish Handoff readiness is present but not summarized as a clear operational state.
- Batch operations are functional but not sticky or state-aware in the same way as Capture Inbox.
- Detail panel is useful but should be split into semantic sections: Overview, Queue lifecycle, Source / Review context, Media prep, Export Package, Publish Handoff, Diagnostics.
- Empty/missing metadata should use honest operator labels such as `Pending`, `Not packaged`, `No handoff`, `Not prepared yet`, and `Needs action`.

## Design direction

The Reup Queue redesign should adopt the Capture Inbox operator-first pattern:

1. Header with concise workflow context and primary/secondary CTAs.
2. Recommended next action banner.
3. Clickable summary cards mapped to operator work states.
4. Filter/search/sort row.
5. Two-column workspace with list on the left and details on the right.
6. Simplified cards that show only operationally relevant information.
7. Contextual item actions based on backend-provided available actions and item state.
8. Sticky batch action bar that keeps selected-item operations close to the operator.
9. Detail panel with technical diagnostics collapsed.

## Implementation notes

Implemented in `apps/web/src/components/reup-queue/ReupQueuePage.tsx` without API changes.

Key changes:

- Replaced the older `review-board` / `board-header` page hierarchy with the shared `OpsConsoleShell` and `PageShell` structure used by the newer operator workspace pages.
- Added workflow context showing `Capture Inbox -> Review Board -> Reup Queue -> Media prep -> Export Package -> Publish Handoff`.
- Added a recommended next action banner derived from current queue counts.
- Replaced passive summary metrics with clickable summary cards for:
  - all queue work;
  - ready to process;
  - waiting for media;
  - waiting for metadata;
  - processing;
  - ready to export;
  - ready to publish;
  - failed;
  - completed;
  - cancelled.
- Added search by title/caption, source identifiers, candidate id, package id, handoff id, next action, and failure text.
- Added operator sort modes: Newest, Ready first, Needs attention first, Export ready first.
- Simplified collapsed queue cards to focus on title/source, status badge, queue stage, next action, export readiness, and handoff readiness.
- Added contextual card actions for details, source links, Export Package links, Publish Handoff links, export selection, and diagnostics.
- Reworked the detail panel into semantic sections:
  - Overview;
  - Queue lifecycle;
  - Source / Review context;
  - Media prep status;
  - Export Package;
  - Publish Handoff;
  - Operator processing actions;
  - Diagnostics / failure reasons.
- Kept raw queue JSON behind a collapsed `View raw queue details` disclosure.
- Converted batch operations into a sticky state-aware batch action bar.
- Preserved existing explicit batch actions, including `CREATE_EXPORT_PACKAGE` and `CREATE_PUBLISH_HANDOFF`.
- Added explicit UI copy that publish automation is not triggered from Reup Queue.
- Replaced ambiguous empty values with honest labels such as `Pending`, `Not packaged`, `No handoff`, `Not prepared yet`, and `No worker job attached yet`.

Updated `apps/web/src/test/reup-queue.test.ts` to assert the new operator-first hierarchy, search/sort/filter controls, summary cards, detail panel sections, sticky batch bar, export/handoff visibility, and publish automation safety copy.

## Verification plan

Run after implementation:

- `npx tsx apps/web/src/test/reup-queue.test.ts`
- `npm run typecheck`

Run route navigation checks if navigation or route references change:

- `npx tsx apps/web/src/test/route-nav.test.ts`

## Verification results

Passed:

- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`
- `npx tsx apps/web/src/test/reup-queue.test.ts`
- `npm run typecheck`

`npx tsx apps/web/src/test/route-nav.test.ts` was not required because no navigation configuration or route files were changed.
