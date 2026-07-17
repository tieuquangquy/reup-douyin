# Douyin Capture Inbox Final UX User Guide

## Purpose

The Capture Inbox is the local operator staging workspace for Douyin videos captured by the browser extension. It lets an operator inspect captured items, clean up staged records, retry enrichment, promote ready items, and keep noisy staged sessions under control.

## Final Layout

The page has one fixed workflow layout:

- The main area shows captured items as cards.
- The side area shows compact Capture sessions and the item detail drawer.
- On desktop, item details open in a right-side drawer.
- On narrow screens, the same drawer becomes a sheet-like responsive fallback.

## Working With Capture Sessions

Capture sessions appear as compact cards/list rows in the side panel. Each session row has one primary click target for opening the session and one `⋯` overflow menu for session-level actions.

To open a session:

1. Find the session in the Capture sessions list.
2. Click the session body.
3. The item cards update to that session.

To delete a session:

1. Open the session row `⋯` menu.
2. Choose `Delete session`.
3. Confirm the `Delete capture session?` prompt.
4. The staged Capture session and its staged Capture Inbox items are removed from the local inbox.
5. The UI clears selected items, closes any open item details, and opens a fallback session if one remains.

Session delete is intentionally inside the menu so destructive session-level cleanup does not compete with everyday session navigation.

## Working With Item Cards

Each captured item is shown as a visual card with:

- Thumbnail or honest missing-thumbnail placeholder.
- Status badge.
- Selection checkbox.
- Title and caption preview.
- Compact metadata.
- Recommended next action.
- Contextual action buttons.

Use `Open details drawer` or `View more in details` to inspect long text and technical metadata.

## Deleting Items

To delete one staged item:

1. Use the `Delete staged item` action on its card.
2. Confirm the delete prompt.
3. The item disappears from the card list and selected item state is updated.

To delete multiple staged items:

1. Select the item checkboxes.
2. Use `Delete selected` in the batch action bar.
3. Confirm the delete prompt.
4. Deleted items are removed and counts update.

Promoted items are protected from staged item deletion.

## Detail Drawer

The drawer is the canonical item detail view.

It is organized around:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details collapsed / secondary

Long text is compact by default. Use `Show more` to expand a field and `Show less` to collapse it again. Expansion resets when switching to another item.

## Thumbnail Behavior

If a valid thumbnail URL is available, the item card displays it. If not, the card displays `No thumbnail available` and a preview status label. This avoids showing fake or misleading thumbnails.

## Operator Notes

- Use cards for item triage.
- Use the right drawer for detailed inspection.
- Use item delete for staged item cleanup.
- Use session menu delete only when the whole staged capture session should be removed.
- Use batch actions when cleaning up multiple staged items at once.
