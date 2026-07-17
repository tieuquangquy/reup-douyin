# Douyin Capture Inbox Table Workspace Architecture

## Decision

Capture Inbox uses a table-based operator workspace as the official primary layout. The card-grid layout is no longer the primary item layout because operators need dense scanning, quick filtering, batch selection, row-level actions, and stable side-by-side details.

## Scope

### In Scope

- Capture Inbox UI refactor in `apps/web`.
- Capture Inbox-specific CSS.
- Focused source tests for the table workspace.
- Documentation updates.

### Out of Scope

- New crawler behavior.
- Video processing or scoring.
- Queue implementation changes.
- Database schema changes.
- New dependencies.
- Unrelated Ops Console page redesigns.
- A second layout architecture or card-grid primary fallback.

## Page Regions

### 1. Compact Header

The page shell keeps a concise title, subtitle, and primary workflow actions only:

- Promote ready items
- Open source profile when available
- Refresh session
- Go to Review Board

### 2. Compact Workflow Context Strip

The former large workflow context block is replaced by a compact key/value strip. It shows essential context without pushing the table below the fold:

- Workflow path
- Profile or source context
- Session status
- Captured time
- Total capture sessions

### 3. Summary Cards

Summary cards stay clickable and set the item status filter:

- Captured
- Ready
- Duplicates
- Needs action
- Failed
- Promoted

The cards summarize the selected session, not all sessions.

### 4. Filter/Search Toolbar

The toolbar is the operator control row for the workspace:

- Search by caption, video ID, source, or status
- Session status select
- Sort select
- Item status filter buttons
- Select visible control

Session status filtering reloads the session list. Item status filtering applies to the selected session table.

### 5. Three-Column Workspace

Desktop layout uses a Capture Inbox-specific grid:

- Left: compact Capture Sessions panel
- Center: captured-items table
- Right: item detail drawer

This page intentionally does not use the shared two-column `OpsContentGrid` as its main workspace because the selected design requires three fixed operator regions.

## Table Columns

The captured-items table columns are:

1. Select
2. Thumbnail
3. Title / Caption
4. Status
5. Source
6. Metadata
7. Next action
8. Actions

Rows are compact, keyboard/click friendly, and use one canonical Details action to open the right drawer.

## Session Panel Behavior

The left panel lists sessions as compact rows with:

- status badge
- timestamp
- short session label
- captured/ready/duplicate/failed counts
- compact overflow menu

The overflow menu includes:

- Open session
- Delete session

Deleting a session keeps the existing confirmation and fallback session behavior.

## Detail Drawer Behavior

The right drawer remains independent from row checkbox selection. The active item id controls the drawer. Closing the drawer clears the active item.

Required detail sections:

1. Overview
2. Captured text
3. Source / References
4. Metadata
5. Outputs / Downstream artifacts
6. Diagnostics
7. Raw details

Raw details stay collapsed by default.

## Batch Action Behavior

The sticky batch action bar appears only when items are selected. It shows selected count, clear selection, promote selected, retry enrich selected, exclude selected, and delete selected. Eligibility counts remain truthful and promoted items are skipped for delete/exclude.

## Thumbnail And Metadata Truthfulness

The table renders a thumbnail only when a trustworthy image-like URL exists. The resolver prioritizes canonical `thumbnail_url`, then known poster/cover aliases from raw and metadata payloads, then image-like nested values. It does not turn video URLs or source page URLs into fake thumbnails.

Missing data is rendered explicitly as Not captured, Pending, or Not analyzed yet.

## Responsive Fallback

- Desktop: three-column workspace.
- At `1180px` and below: the Capture Inbox workspace collapses to one column, and the left/right workspace regions stop using sticky positioning.
- The table keeps dense desktop columns with horizontal overflow fallback so operators can still inspect all table fields without hiding truthful data.

## Why Card Grid Is No Longer Primary

The previous card-grid layout was useful for visual browsing, but it does not scale for operations that require scanning many staged records, comparing statuses, selecting batches, and acting quickly. A data table is the better primary layout for staging work because it makes status, source, metadata, next action, and row actions visible in aligned columns.

## Verification

The implementation was verified with the focused Capture Inbox source test and the web TypeScript typecheck:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```
