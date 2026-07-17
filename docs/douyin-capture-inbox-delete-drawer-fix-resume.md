# Douyin Capture Inbox Delete / Drawer Fix Resume

## Current Status

Implementation and web verification are complete. Backend code was not changed because the audited delete endpoint already returns affected deleted ids and an updated session aggregate.

## Root Causes Identified

### Delete / count sync

The active item grid and summary are derived from `selectedSession.items`, while the session sidebar uses the separate `sessions` list. Delete currently patches some of these structures optimistically and then refetches. The optimistic patch only updates part of the sidebar/session aggregate, so counts can be stale before the refetch completes or if the refetch targets stale session state.

### Details drawer reliability

The detail drawer uses `focusedItemId` and `detailDrawerOpen`, but `focusedItemId` also changes during checkbox selection. This couples selection/focus with drawer activation and can create states where a card appears focused but the drawer is closed. Deleted active items can also be replaced by a fallback item during reload instead of closing deterministically.

## Implemented Fix

- Introduced canonical drawer active identity with `activeItemId`.
- Used a single `openItemDetails` handler for all card media, explicit drawer, view-more, and contextual details affordances.
- Kept selection toggles from opening or changing drawer active item.
- Added `buildSummaryFromItems` and `patchSessionCounts` so optimistic deletion patches active session counts, detail reconciliation, and sidebar aggregates from the same remaining item list.
- Removed deleted ids from checkbox selection immediately.
- Closed the drawer when its active item is deleted.
- Preserved drawer open state only when the same active item still exists after authoritative reload.
- Captured the action session id before mutation and refreshed that exact session after the API response.

## Verification Plan

Run:

- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

No backend verification is expected unless backend code changes.

## Final Results

Verification passed:

- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

Touched implementation files:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`

Touched docs:

- `docs/douyin-capture-inbox-delete-drawer-fix-log.md`
- `docs/douyin-capture-inbox-delete-drawer-fix-resume.md`
- `docs/douyin-capture-inbox-delete-drawer-fix-user-guide.md`
