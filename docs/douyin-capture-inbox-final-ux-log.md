# Douyin Capture Inbox Final UX Log

## Status

Implementation and verification are complete for the final fixed Capture Inbox UX direction. The change stayed scoped to `/ops/extensions/douyin/capture-inbox` and preserved the local-first, SaaS-ready boundaries in `AGENTS.md`.

## Final UX Direction

The final operator UX is fixed:

- Captured items use a visual card layout.
- Item details open in a right-side detail drawer on desktop.
- Modal/sheet behavior is only the responsive fallback on narrow screens.
- Capture sessions use a compact session card/list.
- Each session card has a `⋯` overflow action menu.
- `Delete session` lives only inside the session overflow menu.
- Item delete lives on item cards and in bulk actions.
- Long text is clamped by default and expands with `Show more` / `Show less`.

No alternate UX option is being evaluated in this task.

## Audit Findings

### Frontend Page

`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` already has the core final UX foundation:

- The page renders `OpsContentGrid`, `OpsMainColumn`, and `OpsSideColumn`.
- Captured items render through `CaptureItemCard` inside `capture-inbox-card-grid`.
- Item details render through `ItemDetailDrawer` in the side column.
- `activeItemId` and `detailDrawerOpen` are separate from checkbox selection.
- Item deletion is routed through `requestDeleteItems()` and `runAction("delete_items")`.
- Bulk deletion is routed through `BatchActionBar` using the same `delete_items` backend action.
- `applyDeletedItems()` removes deleted items, clears checkbox selections, and closes the drawer when the active item is deleted.
- Thumbnail display is centralized in `thumbnailUrlForItem()`.
- Long text uses `CompactText` with `Show more` / `Show less` and expansion reset on item changes.

### Session UI Gap

The current session UI still has a persistent visible `Delete session` button per session row:

- `SessionListPanel` renders `.capture-inbox-session-delete` directly inside each `.capture-inbox-session-row`.
- That conflicts with the final UX direction because session deletion must live inside a compact `⋯` overflow menu only.

Required fix:

- Replace the always-visible session delete button with a compact overflow menu button.
- Keep session open/select behavior separate from menu actions.
- Keep destructive styling on the menu item, not on a large row-level button.

### Detail Drawer Alignment Gap

The detail drawer exists and is compact, but section naming should align with the final structure:

- Existing: `Operator summary`, `Captured text`, `Source and media`, `Readiness`, `Diagnostics and raw details`.
- Final structure should be: `Overview`, `Source / References`, `Metadata`, `Outputs / Downstream artifacts`, `Diagnostics`, and collapsed raw details.

Required fix:

- Keep the same compact drawer model.
- Rename/reorganize sections without introducing a new modal-first pattern.
- Keep raw JSON collapsed and secondary.

### CSS Findings

`apps/web/src/app/globals.css` already supports:

- Responsive card grid.
- Card media and missing-thumbnail placeholder.
- Card title/caption clamping.
- Sticky desktop detail drawer.
- Fixed full-screen narrow-screen drawer fallback.
- Compact text clamping.

Required CSS fix:

- Add overflow menu layout/styles for compact session cards.
- Remove/rework direct `.capture-inbox-session-delete` as a persistent row action.

### Backend Findings

Backend support already exists:

- `DELETE /capture-inbox/sessions/{capture_session_id}` deletes a staged Capture session.
- `CaptureInboxService.delete_session()` logs requested/deleted lifecycle events and deletes the session.
- `delete_items()` still guards promoted items and reconciles counts.

No backend change is currently required unless tests expose a regression.

## Implemented Changes

1. Updated `SessionListPanel` to render compact session cards with a `⋯` overflow menu.
2. Moved `Delete session` into the overflow menu only.
3. Kept `requestDeleteSession()` confirmation and `deleteSession()` state cleanup.
4. Reorganized `ItemDetailDrawer` section titles to the final drawer structure.
5. Preserved existing item card layout and item delete affordances.
6. Preserved thumbnail resolver; audit found no wiring gap requiring code change.
7. Updated focused source tests for the fixed UX direction.
8. Ran web source test and typecheck successfully.

## Verification Results

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Backend files were not changed for this final UX pass, so backend unittest was not rerun.

## Non-Goals

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering implementation.
- No database schema change.
- No queue implementation.
- No auto-publish integration.
- No alternate Capture Inbox UX proposal.
