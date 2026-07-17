# Douyin Capture Inbox Media-first Triage Studio Resume

## Current Objective

Refactor `/ops/extensions/douyin/capture-inbox` into a Media-first Triage Studio.

This is the final chosen primary UX direction for Capture Inbox. Do not propose or restore card-grid-first, table-first, Kanban-first, or 3-pane-first primary layouts.

## Required Order

1. Audit
2. Docs first
3. Build compact header + Session Ribbon + Status Strip
4. Build flat filter toolbar
5. Refactor item area into media-first tile gallery
6. Finalize bottom Inspector Sheet
7. Wire selection / delete / promote / retry / sync
8. Fix thumbnail mapping only if minimally needed
9. Add/update tests
10. Run verification
11. Update docs

## Audit Completed

Relevant files reviewed before implementation:

- `AGENTS.md`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/capture-inbox.ts`

## Current Implementation Baseline

The Capture Inbox UI is now implemented as the Media-first Triage Studio. The previous Kanban primary workspace, Kanban source tests, and Kanban CSS artifacts have been replaced by a compact Status Strip, flat Studio filter toolbar, media tile gallery, and Media-first source tests.

Reusable pieces that should be preserved:

- `loadSessions`
- `loadSession`
- `selectSession`
- `deleteSession`
- `applyDeletedItems`
- `runAction`
- `runBatchAction`
- `openItemDetails`
- `closeItemDetails`
- `buildSummary`
- `patchSessionCounts`
- `thumbnailUrlForItem`
- metadata/detail helper functions
- current action labels and state transition semantics

## Next Step

The Media-first Studio implementation and verification are complete. Future changes should preserve this primary UX model and should not restore Kanban/table/card-grid/3-pane primary layouts.

## Implementation Checklist

- Completed: replaced `KpiStrip` with `StatusStrip`.
- Completed: replaced Kanban board rendering with a media-first tile gallery.
- Completed: replaced `FilterSearchRow` copy and shape with a flat Studio toolbar.
- Completed: added toolbar toggles:
  - Only actionable
  - Only with thumbnail
  - Hide duplicates
- Completed: added filter state and visible item logic for the toggles.
- Completed: replaced `ModerationCard` with a compact media tile component.
- Completed: kept gallery visible above the bottom inspector.
- Completed: kept batch action bar visible when items are selected.
- Completed: preserved delete/session sync correctness.
- Completed: updated tests to assert media-first behavior and reject Kanban-first primary artifacts.

## Verification Commands

Completed from repository root on Windows:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts
npm run typecheck --workspace apps/web
```

Both commands passed.

## Known Guardrails

- Do not add dependencies.
- Do not alter backend unless a minimal missing field is proven.
- Do not introduce new workflow semantics.
- Do not fake thumbnails.
- Do not expose raw/debug content as the primary item surface.
- Do not make the inspector a right drawer as the primary desktop pattern.
