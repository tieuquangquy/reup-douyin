# Douyin Capture Inbox Right-side Sticky Inspector Log

## Decision

Capture Inbox at `/ops/extensions/douyin/capture-inbox` now uses a right-side sticky inspector as the primary desktop detail experience.

The bottom `Item details` block is no longer the desktop primary pattern. A narrow-screen sheet/modal/bottom-sheet fallback is allowed only as responsive fallback.

## Scope

### Touched areas

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- Right-inspector Capture Inbox docs under `docs/`

### Non-goals

- No unrelated page redesign.
- No workflow semantic changes.
- No backend/API changes unless a minimal detail payload gap is proven.
- No thumbnail/media pipeline expansion.
- No reintroduction of bottom details as the desktop primary pattern.

## Audit Findings

### Current page structure

The current Capture Inbox render path keeps header, session ribbon, status strip, and filter toolbar at the top, then renders `MediaTileGallery`, `BatchActionBar`, and `InspectorSheet` sequentially inside `OpsConsolePage`.

Current mount order:

1. `HeaderContext`
2. `SessionRibbon`
3. `StatusStrip`
4. `StudioFilterToolbar`
5. `MediaTileGallery`
6. `BatchActionBar`
7. `InspectorSheet`

Because `InspectorSheet` is mounted after the gallery, it behaves as a bottom details block in normal desktop document flow even though its CSS uses `position: sticky`.

### Current bottom details surface

`InspectorSheet` renders the current bottom detail area. It includes:

- Header with `Details` and `Item details`.
- Close button.
- `OpsDetailPanel` titled `Inspector Sheet`.
- Sections for Overview, Source / References, Metadata, Outputs / Downstream artifacts, Diagnostics, Raw details, action source URLs, and latest raw action details.
- `CompactText` disclosures for long title/caption/detail fields.

This content can be reused, but the component must be renamed/repositioned into a right-side sticky inspector and must not remain as a bottom desktop block.

### Current state flow

The detail state is already mostly clean:

- `activeItemId` is separate from checkbox selection.
- `inspectorSheetOpen` controls whether detail content is open.
- `activeItem` is derived from `selectedSession?.items` by `activeItemId`.
- `openItemDetails(itemId)` sets `activeItemId` and opens the inspector.
- `closeItemDetails()` closes the inspector and clears `activeItemId`.

### Details handlers

Tile detail affordances call `onFocusItem(item.id)`, which maps to `openItemDetails`.

The active item is highlighted through `focused={activeItemId === item.id}` and `.capture-inbox-media-tile.selected`.

### Delete/session correctness

The current implementation already clears stale detail state when:

- selected session load cannot resolve the active item,
- item delete removes the active item,
- session delete removes the active session.

These flows should be preserved while renaming the state to right-inspector terminology where appropriate.

### Detail payload shape

The frontend receives all detail fields needed from existing `CapturedItem` data:

- status, title/caption metadata,
- source/share/thumbnail/preview URLs,
- readiness and downstream fields,
- diagnostics/error fields,
- raw/enrichment/metadata payloads.

No backend/API change is expected.

### Responsive behavior

Current CSS gives `.capture-inbox-inspector-sheet` a sticky position and switches `.capture-inbox-inspector-sheet.open` to fixed bottom-sheet-like behavior under `760px`. Because the component is mounted after the gallery, desktop still behaves like bottom details. The fallback behavior can be reused but must be scoped to the right-inspector class.

### Shared layout/components

Reusable wrappers already exist:

- `OpsContentGrid`
- `OpsMainColumn`
- `OpsSideColumn`
- `OpsDetailPanel`
- `OpsDetailSection`
- `OpsMetadataList`

`OpsSideColumn` is already sticky on desktop and becomes static below `1180px`. It is used by Review Board and Reup Queue for right-side detail panels. Capture Inbox should use the same pattern with Capture-specific right-inspector classes.

### Pieces to remove or avoid

- Sequential bottom mounting of `InspectorSheet` after `BatchActionBar`.
- Desktop bottom detail block behavior.
- `InspectorSheet` naming and `.capture-inbox-inspector-sheet` tests/styles as the desktop primary pattern.
- Duplicate detail surfaces.

## Implementation Completed

1. Kept the top header/ribbon/status/filter areas unchanged.
2. Added a Capture Inbox-specific desktop grid with `capture-inbox-review-workspace`.
3. Put `MediaTileGallery` and `BatchActionBar` in `capture-inbox-review-main`.
4. Reworked `InspectorSheet` into `RightInspector` and mounted it in `capture-inbox-review-side`.
5. Reused the existing detail content sections inside `RightInspector`.
6. Renamed sheet state to `rightInspectorOpen` and preserved active item/delete/session sync behavior.
7. Derived `activeItem` from `visibleItems` and clears the inspector when filters hide the active item.
8. Added CSS for sticky right inspector and independent inspector scrolling.
9. Kept narrow-screen fallback as a fixed sheet only below the responsive breakpoint.
10. Updated tests to assert right-side inspector behavior and reject bottom desktop details as primary.

## Verification Results

Executed from repository root:

- `npx tsx apps/web/src/test/capture-inbox.test.ts` — passed.
- `npm run typecheck --workspace apps/web` — passed.

Confirmed:

- no bottom desktop detail block remains in the Capture Inbox render path,
- the right inspector stays mounted beside the media gallery in desktop layout,
- active item open/close/delete/session/filter behaviors are represented in source tests,
- narrow-screen fixed sheet behavior is retained only as responsive fallback.
