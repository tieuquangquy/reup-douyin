# Douyin Capture Inbox Kanban User Guide

## Purpose

Capture Inbox is the staging console for Douyin items captured by the browser extension. The Kanban Moderation Board helps an operator quickly decide which items are ready to promote, which need action, which are duplicates, which failed, and which have already moved downstream.

## Basic Flow

1. Open Capture Inbox.
2. Choose the active capture session from the Session Ribbon.
3. Review the KPI strip to understand the active session.
4. Use search, filters, and sorting to narrow the board.
5. Work column by column:
   - promote ready items
   - retry items that need enrichment or preview
   - review duplicates
   - retry or exclude failed items
   - confirm promoted items moved downstream
6. Select one or more cards for batch actions.
7. Open a card detail to inspect it in the bottom Inspector Sheet.

## Session Ribbon

The Session Ribbon appears near the top of the page. Each session chip shows compact counts and status. Select a session to load its captured items.

Use the overflow menu on a session to open or delete it. Deleting a session removes the session and staged items after confirmation.

## KPI Strip

The KPI strip summarizes the active session. Click a KPI to filter the board by that workflow state.

Typical KPIs are:

- Captured
- Ready
- Duplicates
- Needs action
- Failed
- Promoted

## Filter Toolbar

Use the toolbar to search captions, video IDs, and source URLs. You can also filter sessions by status, sort items, select all visible items, or clear filters.

## Board Columns

The board groups items by state:

- Ready: items eligible for promotion to Review Board.
- Needs action: items requiring enrichment or preview retry.
- Duplicates: items that appear to duplicate existing/captured content.
- Failed: items that failed capture/enrichment and need retry or exclusion.
- Promoted: items already sent downstream.
- Excluded / Other: visible when those items exist in the current view.

Each column may provide state-aware actions for eligible items.

## Moderation Cards

Each card is intentionally compact. It shows the information needed to triage:

- selection checkbox
- thumbnail or honest no-thumbnail placeholder
- status
- title/caption snippet
- source/video id
- small metadata chips
- next action
- quick actions

Long captions and raw data are kept out of cards to preserve scanning speed.

## Bottom Inspector Sheet

Open item details from a card to inspect richer data in the bottom sheet. The sheet preserves the board behind it so you do not lose context.

The sheet includes overview details, source links, metadata, downstream artifacts, diagnostics, and raw details. Long text is collapsed by default and can be expanded.

## Batch Actions

Select cards, then use batch actions for eligible items:

- Promote selected ready items.
- Retry selected retryable items.
- Exclude selected non-promoted items.
- Delete selected non-promoted staged items.

Only eligible selected items are changed by each batch action.

## Data Truthfulness

If a thumbnail is unavailable, Capture Inbox shows a no-thumbnail placeholder. It does not fabricate thumbnails or imply media is ready when the captured data does not support that claim.

## Safety Notes

- Session delete and item delete require confirmation.
- Promoted items are protected from delete/exclude actions in the UI.
- Capture Inbox does not run crawling or video processing directly in the page.

## Verification

The implemented Kanban UX was verified with:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Both commands passed. No API tests were required because this change did not modify API files.
