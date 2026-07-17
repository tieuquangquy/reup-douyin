# Douyin Capture Inbox Media-first Triage Studio User Guide

## Overview

Capture Inbox is the review surface for Douyin items captured by the browser extension. The Media-first Triage Studio helps an operator scan captures visually, inspect details without losing gallery context, and send ready items forward to the Review Board.

The page is intentionally thumbnail-first and compact. It is not a Kanban board, data table, card wall, or debug console.

## Page Areas

### Compact Header

The header identifies the page as `Capture Inbox` and summarizes the purpose: review captured Douyin items before sending them forward.

Primary actions:

- `Refresh` reloads sessions and the active session.
- `Promote ready` promotes ready items from the active session.
- `Open Review Board` navigates to the downstream review surface.

### Session Ribbon

The Session Ribbon shows recent capture sessions as compact horizontal chips. Use it to switch between captures.

Each session includes compact context such as status, item count, and profile/source hint when available.

Session overflow actions:

- `Open session` activates that session.
- `Delete session` removes the session and safely resets gallery, status metrics, selection, and inspector state if needed.

### Status Strip

The Status Strip shows compact metric pills:

- Captured
- Ready
- Duplicates
- Needs action
- Failed
- Promoted

Clicking a pill filters or highlights that item status. These are lightweight triage controls, not dashboard cards.

### Flat Filter Toolbar

Use the toolbar to narrow the gallery quickly:

- Search captured title, caption, author, source, metadata, IDs, and diagnostics text.
- Filter by session status.
- Filter by item status.
- Sort by ready-first, newest, or needs-action-first.
- Toggle:
  - `Only actionable`
  - `Only with thumbnail`
  - `Hide duplicates`

The toolbar is intentionally flat and calm, avoiding heavy admin-form styling.

### Media-first Tile Gallery

The gallery is the main workspace. Tiles prioritize thumbnails so the operator can scan visually.

Each tile should provide:

- Thumbnail or truthful `No thumbnail` placeholder.
- Status badge.
- Short title/source/caption preview.
- Compact metadata chips.
- Selection checkbox.
- Details action.
- Contextual next actions such as promote, retry, exclude, or delete.

Use `Details` or click/select a tile to open the bottom Inspector Sheet.

### Bottom Inspector Sheet

The Inspector Sheet is the secondary detail surface. It appears below the gallery in the normal page flow and behaves like a bottom sheet on smaller screens.

Sections:

- Overview
- Source
- Metadata
- Outputs
- Diagnostics
- Raw details

Long captions, descriptions, and raw text use disclosure controls so the page does not become a wall of text.

### Batch Action Bar

When one or more items are selected, the batch action bar appears.

Available actions:

- Promote selected ready items.
- Retry selected items.
- Exclude selected items.
- Delete selected items.
- Clear selection.

## Common Workflows

### Review a new capture session

1. Open Capture Inbox.
2. Select the newest session in the Session Ribbon.
3. Scan thumbnails in the tile gallery.
4. Use Status Strip pills to focus on ready, duplicate, failed, or needs-action items.
5. Open Details for uncertain items.
6. Promote ready items or retry failed/missing-preview items.

### Find actionable work

1. Enable `Only actionable`.
2. Optionally enable `Hide duplicates`.
3. Sort by `Needs action first`.
4. Retry or exclude items as needed.

### Focus on visual captures only

1. Enable `Only with thumbnail`.
2. Scan the gallery thumbnails.
3. Open Details for items that need more context.

### Delete a session safely

1. Open the session overflow menu in the Session Ribbon.
2. Choose `Delete session`.
3. Confirm the browser prompt.
4. Capture Inbox will remove the session, choose a safe fallback active session, clear deleted selections, close stale inspector details, and refresh visible metrics.

### Delete selected items safely

1. Select one or more tiles.
2. Use the batch action bar `Delete selected` action.
3. Confirm the browser prompt.
4. The gallery, selected IDs, session counts, and Inspector Sheet synchronize automatically.

## Data Truthfulness

Thumbnails are only shown when a real captured thumbnail URL or image-like payload URL is available. If there is no valid thumbnail, the tile uses a clear placeholder and does not invent media.

Raw metadata remains available in the inspector for diagnostics, but it is not the primary operator surface.

## Empty States

If there are no sessions, Capture Inbox tells the operator to capture a Douyin page with the extension to start triaging items.

If filters hide all items, clear filters or disable toggles to return to the full gallery.

If a selected item disappears after delete or session changes, the inspector closes rather than showing stale details.

## Verification Status

The implemented Media-first Triage Studio has passed the focused Capture Inbox source test and the web TypeScript typecheck.
