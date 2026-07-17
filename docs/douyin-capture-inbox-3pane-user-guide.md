# Douyin Capture Inbox 3-Pane User Guide

## Purpose

Capture Inbox is where staged Douyin captures are reviewed before they move to Review Board. The page is organized as a 3-pane moderation workspace so operators can move quickly from session selection to item triage to detail inspection.

## Workspace Overview

The page has three main panes:

1. Session Rail on the left
2. Item Worklist in the center
3. Inspector Drawer on the right

The center Item Worklist is the primary workspace.

## Header Actions

Use the compact header actions for common page-level work:

- Refresh: reload sessions and the active session.
- Promote ready: promote all currently ready items in the active session.
- Open Review Board: go to the downstream review board.

## Summary Strip

The summary strip shows counts for the active session:

- Captured
- Ready
- Duplicates
- Needs action
- Failed
- Promoted

Click a summary entry to filter the Item Worklist to that status group.

## Filter Toolbar

Use the toolbar to narrow the workspace:

- Search by caption, video id, or source.
- Filter item status.
- Filter session status when looking for sessions in a specific state.
- Sort by newest, ready first, or needs action first.
- Select visible to bulk-select all rows currently shown.
- Clear filters when you want to return to the default view.

## Session Rail

The left rail lists capture sessions compactly.

Each session row shows:

- session status
- capture time
- profile or source label
- captured count
- ready count
- duplicate count
- failed count

Click a session to load its staged items into the center worklist.

Use the overflow menu for secondary session actions such as deleting a session.

## Item Worklist

The center worklist is designed for fast moderation scanning.

Each row shows:

- selection checkbox
- thumbnail or truthful placeholder
- title/caption snippet
- source/profile line
- short video/source id line
- metadata mini-strip
- status badge
- next action hint
- compact actions

Common row actions:

- Details: open the item in the Inspector Drawer.
- Promote: move a ready item toward Review Board.
- Retry enrich: retry enrichment for incomplete or failed metadata.
- Retry preview: retry preview readiness.
- Exclude: mark an item out of scope.
- Delete staged item: remove the staged item when it should not remain in Capture Inbox.

Long captions are clamped so the worklist stays compact.

## Inspector Drawer

The right pane shows details for the active item.

Open it by choosing Details on a row or by selecting an item action that focuses details.

The inspector contains:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details

Long text is clamped by default. Use Show more and Show less to expand or collapse long fields. Diagnostics and raw details are collapsed by default and should not dominate normal review.

If no item is active, the drawer prompts you to select an item to inspect details.

## Bulk Actions

When one or more rows are selected, the bulk action bar appears.

Bulk actions include:

- Promote selected
- Retry selected
- Exclude selected
- Delete selected
- Clear selection

Bulk actions only apply to eligible items. For example, promoted items should not be deleted from the staged worklist through normal destructive item actions.

## Empty States

When no session exists, the page explains:

- No capture session yet
- Capture a Douyin page with the extension to start staging items here.

When filters hide all rows, the worklist explains:

- No items match this filter.

When nothing is selected for inspection, the inspector explains:

- Select an item to inspect details.

## Data Truthfulness

The workspace should not invent missing data.

Expected placeholders:

- — for unavailable short values
- Pending for readiness or downstream work not complete yet
- Not captured for fields the extension did not capture

If no thumbnail is available, the row shows a placeholder rather than a fake preview.

## Responsive Behavior

Desktop uses the full 3-pane layout.

On narrow screens, panes stack into a single column. The workflow remains the same: choose a session, scan the worklist, inspect details, and act.

## Verification

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
