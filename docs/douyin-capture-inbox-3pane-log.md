# Douyin Capture Inbox 3-Pane Moderation Workspace Log

## Status

Implemented and verified. The Capture Inbox now uses the final 3-pane moderation workspace with a left Session Rail, center Item Worklist, and right Inspector Drawer.

## Scope

This task refactors the Capture Inbox page into the final chosen 3-pane moderation workspace:

1. Left Session Rail
2. Center Item Worklist
3. Right Inspector Drawer

The page remains a local-first operator workflow in the web app. No crawler, video processing, scoring, queue architecture, publishing, or database schema work is included.

## Audit Findings

### Current Page Structure

The current page already uses a physical three-column grid, but the center column is table-first. The current hierarchy is:

1. page shell with title and header actions
2. compact workflow context strip
3. recommended action banner
4. summary cards
5. filter/search toolbar
6. three-column workspace
7. batch action bar

The workspace is currently labeled as a table workspace and the center section title is "Captured items table". These are legacy artifacts for this task.

### Summary Cards / Toolbar / Filter Flow

Reusable:

- The summary counts already cover Captured, Ready, Duplicates, Needs action, Failed, and Promoted.
- Clicking summary entries already drives the item status filter.
- The toolbar already has search, session status, sort, item status filters, and select visible.

Blockers:

- The shared summary card component renders large cards with descriptions. The new UX needs a compact horizontal summary strip/chip treatment.
- Toolbar copy is useful but slightly too helper-text heavy for the fixed hierarchy.
- There is no clear filters action yet.

### Current Session List Component

Reusable:

- Session selection already loads session details.
- Session rows already expose status, created time, source label, and item counts.
- Session actions already live behind an overflow menu.
- Session delete already reloads or safely clears state.

Blockers:

- The title says "Capture sessions" instead of the rail-oriented "Sessions".
- Count labels are not compact enough for a rail.
- Empty state copy is filter-oriented, not the required "No capture session yet" state.

### Current Item List / Card / Table Component

Reusable:

- Row action derivation is state-aware.
- Thumbnail resolution is already truth-preserving.
- Status and next action helpers exist.
- Selection and focus handlers are already separate.

Blockers:

- The center workspace is a semantic HTML table through the CapturedItemsTable component.
- Class names, tests, and titles explicitly enforce a table workspace.
- The current table is too spreadsheet-like for the final moderation workspace.
- The row structure does not yet expose the required compact source/profile line, short id line, and richer metadata mini-strip.

### Current Detail Drawer / Panel

Reusable:

- The drawer already follows the selected item.
- The drawer closes safely.
- Long text resets expanded state when the selected item changes.
- Overview, Source / References, Metadata, Outputs / Downstream artifacts, Diagnostics, and Raw details are mostly present.

Blockers:

- Diagnostics should be collapsed or visually secondary by default.
- Captured text currently appears as a separate section; the final architecture should fold it into Overview or Raw details unless needed as a compact secondary block.
- Narrow-screen behavior is CSS-stacked, but should be documented as sheet/modal fallback behavior conceptually.

### Selection State Model

Reusable:

- selected item ids and active item id are already independent.
- Filtering does not destroy selected ids.
- Loading a session trims selected ids to items still in that session.
- Deleting active items clears active item and closes the drawer.

Risk:

- When deleting an active item, the current behavior clears the active item instead of advancing to a neighboring item. This is acceptable if documented as safe clear behavior.

### Active Session State Model

Reusable:

- selected session id and selected session detail are synchronized when loading session details.
- Session status filtering reloads session summaries.
- Deleting the active session selects the next available session or clears the workspace.

Risk:

- The list filter and item filter are visually close and need clear labeling so operators understand session status filtering versus item status filtering.

### Delete / Promote / Retry Actions

Reusable:

- Existing action API supports retry enrich, retry preview, promote now, exclude, and delete items.
- Existing delete confirmation protects destructive item and session deletion.
- Existing summary and session count patching avoids stale counts after item deletion.

Blockers:

- Worklist action hierarchy needs visible compact row actions plus overflow for secondary actions.
- Bulk retry label should be simplified to "Retry selected" while still applying retry enrich to retryable selected items unless a preview-specific bulk action is introduced later.

### Thumbnail / Data Availability

Reusable:

- Thumbnail resolution checks canonical fields, aliases, nested metadata, and image-like URLs.
- Empty thumbnail rendering is truthful.

No backend change is planned initially because the current contracts already expose enough data for details, actions, delete, and thumbnail rendering.

### Shared Ops Console Wrappers

Reusable:

- Page shell and console shell should remain.
- Section, metadata list, action row, detail panel, detail section, and batch action bar remain useful.

Blockers:

- Shared summary cards are too large for the compact strip requirement.
- The generic item card is not a fit because the final UX must avoid giant context-card collections.

## Non-Goals

- No backend changes unless implementation proves a required thumbnail/detail field is missing.
- No crawler or media pipeline work.
- No workflow semantic changes.
- No new primary layout alternatives.
- No card-grid-first or table-first main experience.

## Implementation Results

- Replaced the table-first center renderer with `ItemWorklist` and `ItemWorklistRow` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Replaced oversized summary cards with a compact `SummaryStrip` and dense toolbar controls, including Clear filters.
- Refactored session navigation into `SessionRail` with compact count pills and overflow actions.
- Finalized the right-side Inspector Drawer with Overview, Source / References, Metadata, Outputs / Downstream artifacts, collapsed Diagnostics, and collapsed Raw details.
- Preserved the selected item ids / active inspector item id split so checkbox selection does not control drawer identity.
- Kept existing action API semantics for promote, retry enrich, retry preview, exclude, delete items, and session delete.
- Simplified bulk retry copy to `Retry selected` while preserving retry-enrich behavior for retryable selected items.
- Kept existing thumbnail mapping because the current resolver already checks canonical fields, aliases, nested metadata, and image-like URLs.
- Updated `apps/web/src/test/capture-inbox.test.ts` to assert the 3-pane workspace and reject table-first Capture Inbox artifacts.

## Verification

Passed commands:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
