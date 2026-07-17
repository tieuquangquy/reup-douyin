# Douyin Capture Inbox Kanban Log

## Scope

Refactor the Capture Inbox page into the final Kanban Moderation Board UX. This replaces the prior 3-pane-first desktop model as the primary Capture Inbox experience.

## Required Order

1. Audit the current Capture Inbox implementation.
2. Create Kanban documentation before implementation.
3. Build compact header, Session Ribbon, and KPI strip.
4. Build filter toolbar.
5. Refactor the item area into Kanban board columns.
6. Finalize compact moderation cards.
7. Finalize bottom Inspector Sheet.
8. Wire selection, delete, promote, retry, sync, active session, and empty states.
9. Fix thumbnail mapping only if minimally required.
10. Update tests.
11. Run verification.
12. Update docs with final results.

## Audit Findings

- Current page is a completed 3-pane baseline, not the requested final Kanban UX.
- Current reusable state and API behavior can remain:
  - session list/detail loading
  - active session selection
  - selected item ids
  - active item id
  - action execution through Capture Inbox API
  - delete session flow
  - item deletion state sync
  - summary derivation from items
  - thumbnail candidate resolution
  - metadata helpers and compact text expansion
- Current primary layout must be replaced:
  - `SessionRail` becomes a horizontal Session Ribbon.
  - `SummaryStrip` becomes a compact KPI strip with filter behavior.
  - `FilterSearchRow` must stop referring to a worklist and become board controls.
  - `ItemWorklist` and `ItemWorklistRow` become Kanban columns and compact moderation cards.
  - `ItemDetailDrawer` becomes a bottom Inspector Sheet.
  - `.capture-inbox-workspace` and worklist/drawer CSS must no longer define the primary desktop layout.
- Existing API contracts are sufficient for this refactor. No backend changes are planned unless verification reveals a minimal thumbnail/status issue.
- Existing tests currently enforce the obsolete 3-pane model and must be rewritten for the Kanban model.

## Implementation Notes

- The board groups visible items by operator workflow states:
  - Ready
  - Needs action
  - Duplicates
  - Failed
  - Promoted
  - Excluded / other, when relevant
- Item cards remain compact and truthful:
  - no fabricated thumbnails
  - placeholder shown when no thumbnail is available
  - long text is clamped with explicit expansion in the Inspector Sheet
- Bottom Inspector Sheet preserves board context and replaces the right drawer as the primary detail pattern.
- Existing API contracts were sufficient; no backend changes were required.
- Thumbnail mapping was already adequate for this refactor and remains based on deterministic canonical/alias/nested image candidates.

## Verification Results

- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npm run typecheck --workspace apps/web` passed.
- API tests were not run because no API files were changed.

## Status

- Audit completed.
- Docs-first step completed.
- Kanban Moderation Board implementation completed.
- Session Ribbon, KPI strip, board controls, Kanban columns, compact moderation cards, and Inspector Sheet are implemented.
- Selection, item delete, session delete, promote, retry, exclude, column action, batch action, active session, and empty-state wiring are preserved through the existing Capture Inbox action model.
- Focused Kanban source test and web typecheck passed.
