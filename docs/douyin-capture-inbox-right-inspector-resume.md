# Douyin Capture Inbox Right-side Sticky Inspector Resume

## Current Objective

Refactor `/ops/extensions/douyin/capture-inbox` so item details move from the bottom details block into a right-side sticky inspector.

This is the finalized desktop detail UX. Do not keep bottom details as the primary desktop pattern.

## Required Order

1. Audit current bottom details implementation.
2. Docs first.
3. Create/finalize right-side inspector layout container.
4. Move/rework current detail content into right-side inspector.
5. Remove/demote bottom details from desktop.
6. Wire active item / open / close / switch behavior.
7. Fix sticky/scroll behavior.
8. Add/update tests.
9. Run verification.
10. Update docs.

## Audit Completed

Relevant files reviewed before implementation:

- `AGENTS.md`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/test/capture-inbox.test.ts`

## Implementation Baseline

Capture Inbox now renders the details surface in a right-side sticky inspector beside the main gallery:

- `capture-inbox-review-main`
  - `MediaTileGallery`
  - `BatchActionBar`
- `capture-inbox-review-side`
  - `RightInspector`

The active detail component and styles are named for the right inspector:

- `RightInspector`
- `rightInspectorOpen`
- `.capture-inbox-right-inspector`

The previous bottom `InspectorSheet` desktop primary pattern has been removed.

## Reusable Pieces

Preserve:

- `activeItemId`
- derived active item lookup from loaded session items
- `openItemDetails`
- `closeItemDetails` behavior, renamed if useful
- stale active item cleanup on session load/delete/item delete
- current detail sections
- `CompactText`
- `OpsDetailPanel`, `OpsDetailSection`, `OpsMetadataList`
- media tile active styling

## Implementation Checklist

- Completed: desktop workspace grid with main content and right inspector columns.
- Completed: detail component moved into the right column.
- Completed: `InspectorSheet` reworked into `RightInspector`.
- Completed: `inspectorSheetOpen` renamed to `rightInspectorOpen`.
- Completed: `Select an item to inspect details.` empty state remains visible in the right inspector.
- Completed: close/reopen behavior preserved.
- Completed: active item highlight preserved.
- Completed: inspector closes/clears when active item disappears after delete or session changes.
- Completed: filtering clears the inspector when the active item is no longer visible.
- Completed: narrow-screen fallback remains fixed sheet/bottom-sheet behavior only below breakpoint.
- Completed: tests assert right-side inspector and reject bottom primary detail behavior.

## Verification Results

Run from repository root on Windows:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts
npm run typecheck --workspace apps/web
```

Both commands passed.

## Guardrails

- Do not add dependencies.
- Do not change backend unless a minimal missing field is proven.
- Do not change Capture Inbox workflow semantics.
- Do not keep duplicate desktop detail surfaces.
- Do not reintroduce bottom details as the desktop primary pattern.
