# Douyin Capture Inbox Table Workspace User Guide

## Purpose

Capture Inbox is the staging workspace for Douyin captures. Use it to review captured videos, identify items that need follow-up, retry incomplete records, exclude duplicates, delete staged items, and promote ready items to Review Board.

## Workspace Layout

The page is organized as a table-based operator workspace:

1. Compact header with primary actions.
2. Compact workflow context strip.
3. Clickable summary cards.
4. Search/filter toolbar.
5. Left Capture Sessions panel.
6. Center captured-items table.
7. Right item detail drawer.
8. Sticky batch action bar when rows are selected.

## Select A Session

Use the Capture Sessions panel on the left to choose a capture session. Each row shows the session status, capture time, short session label, and item counts.

Open the overflow menu for session actions:

- Open session
- Delete session

Deleting a session removes local staged session data and staged items. Promoted Review Board records are not deleted.

## Filter And Search

Use the toolbar to narrow the workspace:

- Search by caption, video ID, source, or status.
- Filter sessions by session status.
- Filter items by summary card or item status buttons.
- Sort by ready first, needs action first, or newest.
- Select all currently visible rows.

## Read The Table

Each row represents one captured item. Columns show:

- selection checkbox
- truthful thumbnail or No thumbnail placeholder
- title/caption
- operator status
- source/video ID
- metadata such as duration, posted time, and engagement
- next action
- row actions

## Row Actions

Common row actions include:

- Details
- Promote
- Retry enrich
- Retry preview
- Exclude
- Delete staged item
- Open candidate for promoted items

Destructive actions require confirmation or remain visually destructive.

## Details Drawer

Click Details, the thumbnail, or the row title area to open the item drawer. The drawer shows overview, captured text, source links, metadata, downstream outputs, diagnostics, and collapsed raw details.

The drawer is separate from checkbox selection. Selecting rows for batch actions does not change the active detail item.

## Batch Actions

When rows are selected, the sticky batch action bar appears with:

- selected count
- Promote selected
- Retry enrich selected
- Exclude selected
- Delete selected
- Clear selection

Only eligible items are changed. Promoted items are skipped for destructive staged-item deletion.

## Missing Data

The workspace does not fake thumbnails or metadata. Missing values are shown as Not captured, Pending, No thumbnail, or Not analyzed yet.

## Verified Implementation

The table workspace implementation has been verified with the focused Capture Inbox source test and the web TypeScript typecheck:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```
