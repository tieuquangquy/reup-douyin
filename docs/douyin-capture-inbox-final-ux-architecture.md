# Douyin Capture Inbox Final UX Architecture

## Scope

This note documents the final Capture Inbox UX architecture for `/ops/extensions/douyin/capture-inbox`.

The implemented change is frontend-focused. Existing backend API boundaries remain valid:

- `apps/web` owns the operator UI and API calls.
- `apps/api` owns HTTP routes and persistence.
- The web app must not write directly to the database.

## UI Composition

### Page Shell

The Capture Inbox page uses the shared Ops Console layout primitives:

- `OpsConsoleShell`
- `PageShell`
- `OpsConsolePage`
- `OpsContentGrid`
- `OpsMainColumn`
- `OpsSideColumn`
- `OpsSection`
- `OpsBatchActionBar`
- `OpsDetailPanel`
- `OpsDetailSection`

This preserves consistent operator navigation and avoids a one-off layout.

### Main Column: Captured Item Cards

Captured items are presented as cards in `capture-inbox-card-grid`.

Each item card is responsible for:

- Thumbnail or missing-thumbnail placeholder.
- Status badge.
- Selection checkbox.
- Explicit detail drawer affordance.
- Clamped title and caption.
- Compact metadata strip.
- Next-action text.
- Contextual item actions.

Item delete stays on the item card through the contextual `Delete staged item` action. It must not move to session menus.

### Side Column: Sessions and Detail Drawer

The side column contains:

1. Capture session compact list.
2. Item detail drawer.

The session list must use compact session cards/list rows with a `⋯` overflow menu. The session row's primary body selects/opens the session. The overflow menu owns secondary/destructive actions.

`Delete session` appears only inside the session menu and keeps destructive styling.

The detail drawer remains the canonical item detail surface on desktop. On narrow screens, existing CSS switches the open drawer to a fixed full-screen sheet-like fallback.

## State Model

The page separates three concepts:

- Selected session: `selectedSessionId` and `selectedSession`.
- Selected items for bulk actions: `selectedItemIds`.
- Active item details: `activeItemId` and `detailDrawerOpen`.

This separation prevents checkbox selection from controlling the detail drawer.

## Delete Flows

### Session Delete

1. Operator opens the session row `⋯` menu.
2. Operator chooses `Delete session`.
3. UI shows explicit `Delete capture session?` confirmation.
4. Web calls `deleteCaptureInboxSession(captureSessionId)`.
5. Backend route `DELETE /capture-inbox/sessions/{capture_session_id}` calls `CaptureInboxService.delete_session()`.
6. Frontend removes the session locally, decrements total count, clears selected items, clears active item, closes drawer, clears raw/source details, and loads a fallback session if needed.

### Item Delete

Per-item delete and bulk delete both use the `delete_items` action.

- Card delete calls `requestDeleteItems([item.id])`.
- Bulk delete calls `requestDeleteItems(selectedItemIds)`.
- Backend skips promoted items.
- Frontend uses affected ids from the response to update item lists, aggregate counts, selection, and drawer state.

## Detail Drawer Structure

The final drawer structure is:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details collapsed / secondary

Long operator-facing text uses `CompactText` and is clamped until expanded.

## Thumbnail Strategy

Thumbnail rendering stays centralized in `thumbnailUrlForItem()`.

Resolution order prioritizes canonical and common aliases:

- `thumbnail_url`
- `poster_url`
- `poster`
- `cover_url`
- `cover`
- `origin_cover`
- `dynamic_cover`
- `animated_cover`
- `thumb_url`
- `thumbnail`
- `image_url`
- `image`
- `url_list`

Fallback behavior stays honest: if no safe image-like URL is available, the card renders `No thumbnail available` rather than a fake image.

## Verification

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

Backend files were not changed for this final UX pass.

## Non-Goals

- No changes to crawling.
- No changes to video processing.
- No changes to scoring/filtering.
- No changes to queue/database architecture.
- No alternate Capture Inbox UX mode.
