# Douyin Capture Inbox 3-Pane Architecture

## Decision

Capture Inbox uses a 3-pane moderation workspace as its final primary UX model.

The primary layout is:

1. Left pane: Session Rail
2. Center pane: Item Worklist
3. Right pane: Inspector Drawer

This replaces the table-first workspace as the main experience. Card-grid-first and table-first layouts are no longer primary models for Capture Inbox.

## Product Goal

Capture Inbox is an operations triage surface for staged Douyin captures. It should feel like a moderation inbox where an operator can quickly scan sessions, select staged items, inspect details, and perform state-aware actions before promotion to Review Board.

It must not feel like a debug page, form page, generic database table, raw text dump, or oversized context-card collection.

## Page Hierarchy

### Compact Header

Responsibilities:

- Present the page identity: Capture Inbox.
- Explain the page purpose: Stage captured Douyin items before review.
- Keep high-value actions right-aligned and compact.

Primary header actions:

- Refresh
- Promote ready
- Open Review Board

The source profile link is not a primary page-level action. It belongs in the selected session/item context or inspector.

### Summary Strip

Responsibilities:

- Show compact item counts for the active session.
- Act as item status quick filters.
- Stay horizontal and low-height on wide screens, wrapping only when necessary.

Summary entries:

- Captured
- Ready
- Duplicates
- Needs action
- Failed
- Promoted

The summary strip should avoid long helper descriptions and oversized cards.

### Filter Toolbar

Responsibilities:

- Search by caption, video id, source, or status.
- Filter item status.
- Filter session status where useful.
- Sort the worklist.
- Select visible rows.
- Clear filters when non-default filters are active.

The toolbar must remain dense and readable.

## Main Workspace

### Left Pane: Session Rail

Responsibilities:

- Navigate capture sessions.
- Show compact session status.
- Show compact counts.
- Keep session actions in an overflow menu.

The rail is intentionally narrow. Sessions are not the visual center of the page.

Rail row structure:

- status badge
- created time
- compact session label
- compact counts for captured, ready, duplicate, failed
- overflow actions: open session, delete session

Empty state:

- Title: No capture session yet
- Detail: Capture a Douyin page with the extension to start staging items here.
- Actions may include Refresh and Open extension setup if an appropriate target exists.

### Center Pane: Item Worklist

Responsibilities:

- Serve as the main operator workspace.
- Support fast scan, select, sort, filter, and action.
- Render compact media-rich rows rather than cards or spreadsheet tables.

Worklist row structure:

1. selection checkbox
2. compact 16:9 thumbnail or truthful placeholder
3. title/caption block clamped to 2 lines
4. source/profile line clamped to 1 line when needed
5. short id line for video/source identifiers
6. metadata mini-strip
7. status badge
8. next action hint
9. compact row actions

Metadata mini-strip should include the best available values for:

- duration
- posted date
- views
- likes
- comments
- preview readiness
- media readiness

Truthful placeholders must be used when data is absent:

- —
- Pending
- Not captured

Row action hierarchy:

- Primary: Promote, Retry when it is the main recovery action
- Secondary: Details, Retry enrich, Retry preview, Open source
- Destructive: Delete staged item, Exclude
- Tertiary: View raw, Copy id, minor utilities

The row may show the most relevant actions directly and place secondary actions in overflow where appropriate.

### Right Pane: Inspector Drawer

Responsibilities:

- Show selected item details.
- Update when another row is selected.
- Close safely.
- Clear or safely advance when the active item is deleted.

Inspector sections:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details

Diagnostics should be collapsed or visually secondary by default. Raw details should remain collapsed by default.

No active selection empty state:

- Select an item to inspect details.

## Long Text Rules

Worklist:

- title and caption clamp to 2 lines
- source line clamps to 1 line if needed
- ellipsis is required for overflow
- rows must not grow into giant cards because of long text

Inspector:

- summary text clamps to 4-5 lines by default
- Show more / Show less reveals long text
- switching rows resets or safely manages expanded state
- raw and diagnostics full text are allowed only in secondary or collapsed containers

## State Model

### Active Session

- selected session id identifies the rail selection.
- selected session detail owns the currently displayed items.
- switching sessions loads details, prunes selected item ids, and clears invalid active item state.

### Worklist Selection

- selected item ids are independent of the active inspector item.
- selecting checkboxes enables the bulk action bar.
- opening Details sets the active item and opens the inspector.

### Deletion

- deleting an item removes it from session detail and session summary counts.
- deleting selected items clears removed ids from selected item ids.
- deleting the active item clears the inspector or safely advances if implemented later.
- deleting the active session loads the next available session or shows the no-session state.

### Promote / Retry / Exclude

- promote and retry actions use existing Capture Inbox action contracts.
- successful actions reload the current session to preserve canonical backend state.
- delete action can patch local state immediately after confirmed backend success.

## Responsive Rules

Desktop is primary:

- left rail: narrow
- center worklist: dominant
- right inspector: moderate width

Narrow screens:

- panes may stack vertically, or the inspector may become a sheet/modal fallback.
- the conceptual model remains Session Rail, Item Worklist, Inspector Drawer.
- the worklist stays the main task surface.

## Why Other Layouts Are No Longer Primary

Card-grid-first is not primary because it makes sessions/items feel like oversized content cards and slows moderation scanning.

Table-first is not primary because it makes the main surface feel like a generic database table or spreadsheet. Capture Inbox needs compact media-rich rows with visible thumbnails, status, next action hints, and concise item context.

The 3-pane model best matches the actual operator workflow: choose a session, scan staged items, inspect one item, then act.

## Backend Impact

No backend changes were required. Existing web/API contracts support:

- session listing
- session detail
- session delete
- item actions
- item delete
- item detail payloads
- thumbnail candidate exposure

Backend changes should still be considered only if a future scoped task proves a required field is missing.

## Implemented Components

The implemented web page now uses these page-local components in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`:

- `SummaryStrip` for compact active-session summary filters.
- `FilterSearchRow` for dense search, item status filter, session status filter, sort, select visible, and clear filters.
- `SessionRail` for left-pane session navigation and session overflow actions.
- `ItemWorklist` and `ItemWorklistRow` for compact media-rich moderation rows.
- `ItemDetailDrawer` for the right-side Inspector Drawer.
- `CompactText` for long-text clamp and Show more / Show less behavior.
- `BatchActionBar` for selected-row bulk actions.

## Verification

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
