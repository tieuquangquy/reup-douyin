# Douyin Capture Inbox Right-side Sticky Inspector Architecture

## Purpose

Capture Inbox is an operator triage surface for Douyin extension captures. The previous bottom detail block forced operators to scroll away from the item gallery to inspect details. The right-side sticky inspector fixes this by keeping details visible beside the item gallery on desktop.

## Why Bottom Details Is No Longer Desktop Pattern

Bottom details is inefficient for real triage because:

- details are disconnected from the gallery/list item being reviewed,
- operators must scroll through many media tiles before seeing details,
- switching between items requires unnecessary vertical navigation,
- long detail content competes with the item browsing flow.

Desktop Capture Inbox must therefore use a persistent right-side inspector. Bottom sheet/modal behavior is allowed only as a narrow-screen fallback.

## Chosen UX Model

### Desktop

The top controls remain full width:

1. Compact header
2. Header context
3. Session Ribbon
4. Status Strip
5. Studio filter toolbar

The main workspace is split into:

- left/main column: media tile gallery and batch actions,
- right/sidebar column: sticky item inspector.

Suggested proportions:

- main content: about 68-72%,
- inspector: about 28-32%.

The right inspector is visible on desktop, uses sticky positioning, and may scroll internally when its content is long.

### Narrow screens

The inspector can collapse into a fixed sheet/bottom-sheet style. This is a responsive fallback only, not the desktop primary pattern.

## Component Design

### Reworked detail component

`InspectorSheet` was reworked into the right-side inspector component `RightInspector`.

It should reuse existing structured detail content:

1. Overview
2. Source / References
3. Metadata
4. Outputs / Downstream artifacts
5. Diagnostics
6. Raw details

Diagnostics and raw details remain collapsed/secondary.

### Layout container

Capture Inbox introduces a Capture-specific workspace wrapper:

- `capture-inbox-review-workspace`
- `capture-inbox-review-main`
- `capture-inbox-review-side`
- `capture-inbox-right-inspector`

This avoids forcing unrelated `OpsContentGrid` proportions while still following the same right-column pattern used by Review Board and Reup Queue.

## State Model

Implemented state:

- `activeItemId`: id of the item currently inspected.
- `rightInspectorOpen`: whether the inspector is open.
- `activeItem`: derived from loaded session items and `activeItemId`.
- `visibleItems`: client-filtered gallery items.

State flow:

1. Tile `Details` or thumbnail/title click calls `openItemDetails(item.id)`.
2. `openItemDetails` sets `activeItemId` and opens the right inspector.
3. Clicking a different item replaces `activeItemId`; the same inspector updates in place.
4. Close clears open state and active id.
5. Deleting the active item clears active id and closes the inspector.
6. Switching sessions clears or re-resolves active item from loaded session items.
7. Filtering behavior: if the active item is no longer in `visibleItems`, close/clear the inspector. This keeps the inspector aligned with the currently visible triage set.

There should be no conflicting detail state such as separate selected item and active detail item sources of truth.

## Action Hierarchy

Tile actions remain compact. The inspector may show the same status, next action, source links, and structured metadata near the top, but must avoid flooding the top with too many buttons.

Primary operator actions remain governed by existing action handlers:

- promote,
- retry enrich,
- retry preview,
- exclude,
- delete staged item,
- open candidate/source links.

No workflow semantic changes are introduced.

## Sticky / Scroll Behavior

Desktop CSS should ensure:

- the inspector column is `position: sticky` under the top controls,
- the inspector has a bounded max height, such as `calc(100vh - 120px)`,
- detail content scrolls inside the inspector,
- parent containers do not clip sticky positioning,
- the main gallery scroll remains independent in normal page flow.

## Old Layout Pieces Removed

The implementation removed or replaced:

- sequential bottom render of `InspectorSheet` after gallery/batch actions,
- `.capture-inbox-inspector-sheet` as the desktop primary class,
- tests that describe the detail surface as a bottom Inspector Sheet,
- desktop expectation that details are below the item gallery.

## Testing Strategy And Verification

Focused source tests verify:

- `RightInspector` exists and is rendered in a right-side workspace column.
- `MediaTileGallery` remains in the main workspace column.
- Details handlers open/update the right inspector.
- Close clears active detail state.
- Active item styling remains tied to `activeItemId`.
- Delete/session reload cleanup still closes stale inspector state.
- Filtering clears the inspector when the active item leaves `visibleItems`.
- Long text is clamped and expandable through `CompactText`.
- Responsive fallback uses fixed sheet behavior only under a narrow breakpoint.
- Bottom details block is no longer the primary desktop detail surface.

Verification passed with:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
