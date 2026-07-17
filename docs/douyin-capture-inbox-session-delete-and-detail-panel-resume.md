# Douyin Capture Inbox Session Delete / Detail Panel Fix Resume

## Current Status

Implementation and verification are complete. Capture Inbox now supports staged Capture session deletion and a compact item detail drawer with long-text disclosure controls.

## Root Causes Identified

### Missing session delete UX

The Capture sessions sidebar renders each session row as a single open/select button. There is no row-level delete affordance and no backend Capture Inbox session delete endpoint. Deleting individual staged items exists, but deleting an entire staged session requires a dedicated route and frontend state cleanup.

### Detail panel wall-of-text

The item detail drawer renders the full title and caption directly in the hero. Long captured text can consume most of the drawer height before the operator reaches source, readiness, media, or diagnostics metadata. Card text is clamped, but the drawer lacks show more/show less controls and a compact hierarchy.

## Implemented Fix

- Added backend hard delete for Capture Inbox sessions using `DELETE /capture-inbox/sessions/{capture_session_id}`.
- Added web API client support for deleting a Capture Inbox session.
- Added a compact session row action area with separate open/select and `Delete session` controls.
- Confirmed deletion with clear `Delete capture session?` copy before calling the API.
- After deletion, the page removes the deleted session from local state, clears selection/drawer/raw action state, and falls back to another session or an empty state.
- Redesigned `ItemDetailDrawer` into compact operator summary, captured text, source/media, readiness, and collapsed diagnostics sections.
- Added a compact text disclosure component for long title, caption, description, transcript, notes, and raw text candidates.
- Reset compact text expansion when switching active items.

## Verification Results

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`

## Final Results

The requested UX improvements are complete. Session deletion is implemented across backend, API client, sidebar UI, confirmation, local state sync, and tests. The item detail panel is compact by default, keeps diagnostics collapsed at the bottom, and exposes explicit `Show more` / `Show less` controls for long operator-facing text.
