# Capture Inbox Sticky Top Command Bar Resume

## Task

Refactor only the Capture Inbox batch actions area into a true sticky top command bar.

## Scope lock

- UI-only (`apps/web`) batch toolbar behavior
- No overlay redesign in this task
- No backend/API/data-flow/semantics changes

## Status

Completed.

## Audit summary

- Root cause found: batch bar was mounted after gallery content, so sticky started too low in flow.
- Sticky CSS existed, but placement in component tree made it late-reachable.

## Completed steps

1. Moved `BatchActionBar` mount above `MediaTileGallery` in main workspace column.
2. Kept sticky command bar behavior and existing action hierarchy/labels.
3. Updated focused tests for top/workspace mount behavior.
4. Ran focused test + web typecheck.
5. Finalized docs with verification.

## Verification

- `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅
- `npm run typecheck --workspace apps/web` ✅
