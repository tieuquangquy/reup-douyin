# Douyin Capture Inbox Session Delete / Detail Panel Fix Log

## Objective

Refine `/ops/extensions/douyin/capture-inbox` for two focused UX improvements:

1. Add a safe delete action for Capture sessions from the session sidebar.
2. Redesign the item detail panel so long text is compact, readable, and operator-friendly.

## Scope

Expected touched areas:

- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- API tests if a backend delete endpoint is added

Non-goals:

- No thumbnail/media pipeline changes.
- No workflow semantic changes beyond deleting staged Capture Inbox sessions.
- No full page redesign.
- No crawler, publishing, or promotion behavior changes.

## Audit Findings

### Capture session area

- Session list is rendered by `SessionListPanel` inside `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Session list data comes from `fetchCaptureInboxSessions`, which calls `GET /capture-inbox/sessions`.
- Active session state is held in `selectedSessionId` and `selectedSession`.
- Captured item grid, summary cards, selected item derivation, filters/search/sort, and drawer active item derive from `selectedSession.items`.
- The sidebar rows are currently rendered as one large button per session and expose only open/select behavior.
- Existing backend supports deleting individual staged items through `POST /capture-inbox/sessions/{capture_session_id}/actions` with `delete_items`.
- There is no backend route or service method for deleting a whole Capture Inbox session.
- SQLAlchemy model relationship `CaptureSession.items` uses `cascade="all, delete-orphan"`, so hard deleting a session will delete its staged items as the natural local-first staged-data behavior.
- Session delete must clear or recompute: `sessions`, `totalCount`, `selectedSessionId`, `selectedSession`, `selectedItemIds`, `activeItemId`, `detailDrawerOpen`, `rawDetails`, `sourceUrls`, and summary derived from active session.

### Item detail panel

- The drawer is `ItemDetailDrawer` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Current hero renders full `titleForItem(item)` and full `item.caption`, so long captions can dominate the drawer.
- Raw diagnostics already live in a collapsed section, but the hero and source/metadata sections do not provide a compact scan hierarchy.
- Existing card CSS has clamped title/caption, but there is no reusable show more/show less component for the detail drawer.
- Existing detail drawer CSS has basic panel styling but lacks compact text cards, line clamp controls, and a focused metadata grid.

## Design Decisions

### Session delete

- Add a minimal backend hard-delete endpoint for Capture Inbox sessions using the existing `capture-inbox` route convention: `DELETE /capture-inbox/sessions/{capture_session_id}`.
- Hard delete is appropriate because Capture Inbox sessions are staged local operator data and the ORM already models child items with delete-orphan cascade.
- Use the existing app pattern of `window.confirm` for delete confirmation to stay consistent with item delete and other local operator actions.
- Keep the session row compact: preserve the row as the main open target and add a small `Delete session` action beside it.
- After delete, update local state immediately and reload the session list. If the deleted session was active, select the first remaining session or clear active state when none remain.

### Detail panel compact text

- Restructure the drawer into a scannable hierarchy: header, compact content summary, core metadata, media/readiness, and diagnostics.
- Add a local reusable compact text disclosure for long title/caption/diagnostic-like text.
- Clamp long text by default and reveal with `Show more`; collapse with `Show less`.
- Reset expanded text state when switching active items so one item's expansion does not leak to another.
- Do not hide critical metadata; move dense raw data to existing collapsed diagnostics.

## Planned Verification

- `npm run typecheck --workspace apps/web`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- API tests for Capture Inbox service/routes if backend route/service are changed.

## Final Verification

Completed successfully:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`

## Final Results

- Added `DELETE /capture-inbox/sessions/{capture_session_id}` with service-level hard delete for staged Capture Inbox sessions.
- Added lifecycle logging for session delete request and completion with stable Capture session identifiers.
- Added web API client support for Capture Inbox session deletion.
- Reworked Capture sessions rows so each row has a dedicated open target and a separate destructive `Delete session` action.
- Added confirmation copy headed `Delete capture session?` that explains staged session and staged item removal.
- Session deletion now removes the row locally, decrements total count, clears selected items, clears the active drawer item, closes the drawer, clears raw/source action details, and falls back to another session when possible.
- Redesigned the item detail drawer into compact operator summary, captured text, source/media, readiness, and collapsed diagnostics sections.
- Added reusable `CompactText` disclosure behavior with default clamp, `Show more`, `Show less`, no expansion affordance for short text, and reset-on-item-switch state.
- Updated focused source tests to cover backend route/service, frontend delete action/state cleanup, compact text disclosure, and CSS clamps.
