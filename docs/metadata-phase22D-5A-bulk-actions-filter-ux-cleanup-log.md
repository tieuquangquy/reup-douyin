# Phase 22D-5A - Bulk Actions Filter UX Cleanup Log

## Scope

Phase 22D-5A separates Capture Inbox filtering controls from selection and bulk action controls. The work is limited to frontend Capture Inbox UX labels/grouping, source-inspection tests, and documentation.

## Audit

- Studio filters component: `StudioFilterToolbar` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Bulk toolbar component: `BatchActionBar` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Duplicated control before cleanup: `Select visible` appeared in both `StudioFilterToolbar` and `BatchActionBar`.
- Current `Select visible` handler: `selectVisibleItems()`, which maps the current `visibleItems` to item ids and stores them in `selectedItemIds`.
- Current `Clear filters` handler: inline `onClearFilters` passed into `StudioFilterToolbar`; it resets status/search/session status/metadata/sort/preset/quick filters/hide duplicates.
- Current `Clear selection` handler: `clearSelection`, passed into `BatchActionBar` as `onClear`.

## UX Decision

`Select visible` was removed from Studio filters because it is a selection command, not a filter. Studio filters now stay focused on narrowing and sorting the visible result set: item status, metadata status, session status, sort, search, quick filters, and `Clear filters`.

The Bulk toolbar remains the only place for selecting visible cards and running batch actions. This keeps selection count, selection clearing, and action eligibility in one local command surface.

## Changes

- Renamed Studio filter toggle group from `Studio toggles` to `Quick filters`.
- Removed `Select visible` from `StudioFilterToolbar` props and JSX.
- Kept `Only actionable`, `Only with thumbnail`, `Hide duplicates`, and `Clear filters` in Studio filters.
- Renamed Bulk toolbar `Clear` to `Clear selection`.
- Updated Bulk toolbar selected-state copy:
  - `0 selected`: `Select visible items or tick cards to enable bulk actions.`
  - `>0 selected`: `Bulk actions apply only to selected items.`
- Added a `Select visible` title clarifying scope: `Select visible applies to the current filtered view.`
- Kept Results summary above `BatchActionBar`.
- Kept Smart Presets as filters, outside the Bulk toolbar.

## Clear Behavior

- `Clear filters` resets filter state only: status filter, search query, session status, metadata filter, sort, active preset, quick-filter toggles, and duplicate hiding.
- `Clear selection` resets selected item ids only via the existing selection clear handler.

## Select Visible Scope

`Select visible` remains scoped to `visibleItems`, so it respects all active filtering layers, including Smart Presets and Advanced filters. No filtering logic or backend action behavior was changed.

## Tests Run

- `npx tsx src/test/capture-inbox.test.ts` from `apps/web` - passed.
- `npm --workspace @reup-douyin/web run typecheck` - passed.
- `npm --workspace @reup-douyin/web run build` - passed.
- `npm --workspace @reup-douyin/web run test` - failed on the known pre-existing Review Board path issue: `apps/web/apps/web/src/components/review-board/ReviewBoardPage.tsx`.

## Notes

- An initial direct `node --loader ts-node/esm apps/web/src/test/capture-inbox.test.ts` command failed because `ts-node` is not installed at the workspace root. The project test runner uses `tsx`, so validation continued with `npx tsx` from `apps/web`.
- Full web tests still fail before reaching Capture Inbox because the Review Board test resolves a duplicated Windows path. This was not changed in Phase 22D-5A.
