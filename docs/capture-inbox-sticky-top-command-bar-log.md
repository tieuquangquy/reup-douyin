# Capture Inbox Sticky Top Command Bar Log

## 1) Root cause of previous bottom-bound behavior

The batch actions bar was still mounted **after** the tile gallery inside `capture-inbox-review-main`.

- Component order previously:
  1. `MediaTileGallery`
  2. `BatchActionBar`
- Even with `position: sticky`, sticky only takes effect from the element’s normal flow position.
- Because the bar’s normal position was below the gallery block, operator still had to scroll down before the sticky bar became reachable.

This is why it felt bottom-bound despite sticky CSS being present.

## 2) New placement strategy

Mount `BatchActionBar` near the top of main workspace flow, directly above tile gallery content.

New order in `capture-inbox-review-main`:
1. `BatchActionBar`
2. `MediaTileGallery`

Behavior remains selection-gated (`selectedItems.length > 0`) and command content unchanged.

## 3) Sticky behavior rules

- Bar is hidden when selected count is zero.
- Bar appears immediately at top workspace area once selection exists.
- Bar remains sticky while scrolling gallery content.
- Keep one count anchor + helper text.
- Keep concise commands and hierarchy:
  - Promote (primary)
  - Retry (secondary)
  - Exclude (secondary)
  - Delete (destructive)
  - Clear (tertiary)

## 4) Files changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/capture-inbox-sticky-top-command-bar-log.md`
- `docs/capture-inbox-sticky-top-command-bar-resume.md`

## 5) Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

## 6) Verification result

Passed.

- Capture Inbox focused source-contract test passed.
- Web typecheck (`tsc --noEmit -p tsconfig.typecheck.json`) passed.
