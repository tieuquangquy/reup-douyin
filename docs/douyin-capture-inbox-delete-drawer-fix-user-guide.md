# Douyin Capture Inbox Delete / Drawer Fix User Guide

## What This Fix Covers

This fix makes Capture Inbox deletion and item details interactions reliable for the local operator workflow.

## Expected Delete Behavior

After deleting one staged item:

- The item disappears from the current grid.
- Summary cards update from the remaining active-session items.
- The shown item count updates through the existing filter/search derivation.
- The selected count removes the deleted id.
- The session sidebar row updates its item counts.
- If the deleted item was open in the drawer, the drawer closes safely.

After deleting multiple staged items:

- All deleted ids returned by the backend disappear.
- Batch selection is cleaned up.
- Existing search/filter/sort choices remain applied to the remaining items.
- Empty states appear normally if the current filter has no remaining matches.

Promoted items are still protected by the backend and skipped from deletion.

## Expected Details Drawer Behavior

- `Open details drawer`, `Details`, card media click, and `View more in details` all open the same drawer for the exact clicked item.
- Clicking another card's detail action switches the drawer to that item.
- `Close details` closes the drawer without changing batch selection.
- Checkbox selection does not implicitly open the drawer.
- If the active drawer item is deleted, the drawer closes rather than silently showing a different item.

## Operator Notes

Deletion remains explicit and uses the existing confirmation prompt. If no items match the active filter after deletion, use `All` or clear search to review remaining items.

## Verified Behavior

The web implementation was verified with:

- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

## Limitations

This fix does not change Capture Inbox workflow semantics, thumbnail/media handling, promotion, crawler behavior, backend storage design, or backend API response shapes.
