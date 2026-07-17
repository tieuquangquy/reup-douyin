# Phase 22D-5 Bulk Actions Capture Inbox Log

## Audit
- Frontend cards live in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` through `MediaTileGallery` and `MediaTile`.
- Tile identity, selection, focus, and backend actions use backend captured item `item.id`.
- Individual actions remain: Promote uses `promote_now`, Re-check uses `re_evaluate_intake`, Delete uses `delete_items`, and promoted items show Open candidate plus Details.
- Existing backend endpoint `POST /capture-inbox/sessions/{capture_session_id}/actions` already accepts multiple `item_ids`.
- Backend delete currently hard-deletes non-promoted `CapturedItem` rows and skips promoted items.
- Backend promotion accepts selected IDs but promotes only eligible ready-like items; frontend keeps promote eligibility to READY/ENRICHED to match existing card UX.

## Implementation
- Added visible-item scoped bulk selection state with `lastSelectedAt` and `selectionScope = "visible_items"`.
- Bulk toolbar now sits below the filter count line and includes Select visible, Clear, Promote, Re-check, and Delete.
- Added `getBulkActionEligibility(items, selectedIds)` for selected, promotable, recheckable, deletable, blocked, and reasons-by-item.
- Bulk Re-check now uses `re_evaluate_intake`, matching individual Re-check instead of enrichment retry.
- Bulk delete uses a custom modal, not `window.confirm`, and warns that non-promoted staged rows are hard-deleted.
- Bulk actions send only eligible visible selected item IDs and show compact partial-success summaries.

## Validation Notes
- Frontend typecheck passed after implementation.
- Backend was not changed because existing batch-capable action endpoint covers Phase 22D-5 behavior.
