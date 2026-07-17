# Phase 17AC Capture Inbox session items log

## Scope
Implement Phase 17AC only: ensure Capture Inbox displays video items inside V2-created Capture Inbox sessions, with clear diagnostics for empty and filtered states, and expose item linkage in finalized-harvest response.

## Changes made
- Extended finalized harvest response payload with item linkage fields:
  - `ok`
  - `capture_inbox_item_id`
  - `source_video_external_id`
  - `metadata_status`
  - `item_created_or_updated`
- Extended backend service summary dataclass to propagate the same fields.
- Ensured reconcile/commit runs on matched finalized harvest flows even when no item-level mutation is detected (`matched_count > 0` path), to keep session counters/status current.
- Added extension-side response typing and trace diagnostics:
  - Parses `capture_inbox_item_id`, `source_video_external_id`, `metadata_status`, `item_created_or_updated`
  - Emits `backend_success_but_no_item_id` warning summary when backend success response omits item id.
- Added Capture Inbox UI diagnostics panel:
  - `Loaded items: X`
  - `Hidden by filters: Y`
  - Empty-session guidance: `No items in this session yet.` with reasons.
  - Filtered-empty guidance: `Items exist but are hidden by filters.`
- Updated tests across API/web/extension to lock the new contract and UI messaging.

## Notes
- V2 Open behavior already called session detail load path (`onSelect -> selectSession -> loadSession -> fetchCaptureInboxSession`); Phase 17AC work focused on visibility diagnostics and finalized-response linkage.
- View handling remains honest (`Views —`) when trusted view count is unavailable; estimated views remain clearly labeled as `Est. Views`.
