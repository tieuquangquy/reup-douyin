# Douyin Capture Inbox Final UX Resume

## Current Status

Implementation and verification are complete. `AGENTS.md` was read, the current Capture Inbox implementation was audited, docs-first planning was written before implementation, and the final fixed UX direction is now implemented.

## Fixed UX Direction

The selected UX is final and singular:

- Captured items are cards.
- The item detail surface is a right-side drawer on desktop.
- Narrow screens use a sheet-like fallback only as responsive behavior.
- Capture sessions are compact session cards/list rows.
- Session row actions are hidden behind a `⋯` menu.
- Session delete is available only inside the session `⋯` menu.
- Item delete remains on the item card and in bulk actions.
- Long text is clamped by default with `Show more` / `Show less`.

## Audit Summary

### Already aligned

- Capture Inbox route renders the shared Capture Inbox page.
- Main item list already uses a card grid.
- Item cards already show thumbnails, fallback placeholder, title, caption, metadata, next action, and contextual actions.
- Item delete already exists on cards through `Delete staged item`.
- Bulk delete already exists through `Delete selected`.
- Detail drawer state is separate from checkbox selection.
- Deleting the active item closes the drawer and clears stale active state.
- Long text already uses `CompactText` and resets expansion when switching items.
- Thumbnail resolution already checks canonical and alias fields in deterministic order.
- Backend session delete and item delete already exist.

### Implemented in this pass

- Replaced the persistent visible session delete button with a compact `⋯` menu.
- Ensured `Delete session` lives inside that menu only.
- Added menu styles and updated tests so the final UX cannot regress to the old large delete button.
- Aligned drawer section titles/content with the required final structure.
- Re-ran focused web checks successfully.

## Important Existing Behavior To Preserve

- `requestDeleteSession()` must keep the explicit `Delete capture session?` confirmation.
- `deleteSession()` must remove the deleted session, decrement total count, clear selected item ids, clear active item id, close the drawer, clear raw/source detail state, and load a fallback session if needed.
- `requestDeleteItems()` must keep explicit confirmation for staged item deletion.
- `applyDeletedItems()` must remove deleted items from active session state, sidebar aggregate counts, selection state, and drawer state.
- Promoted item delete must remain disabled/skipped.

## Verification Results

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Backend files were not changed for this final UX pass, so backend unittest was not rerun.

## Resume Point

No resume work remains for this task. The final UX implementation is complete and verified.
