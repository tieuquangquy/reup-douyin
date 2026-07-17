# Capture Inbox Sticky Toolbar Fix Log

## 1) What was wrong

- Batch actions toolbar was previously too low in content flow for large selections.
- Operator had to scroll to reach commands after selecting many tiles.
- Select/Ready overlay controls looked bulky and visually unrefined.
- Overlay readability over mixed thumbnails needed a subtle but more intentional contrast layer.

## 2) How toolbar now behaves

- Batch command bar renders only when selection exists (`selectedItems.length > 0`).
- The command bar is sticky/floating near the top of the active workspace (`position: sticky; top: 12px; z-index: 8`).
- It stays reachable while scrolling tile gallery content.
- It keeps one summary count + helper text and concise commands:
  - Promote (primary)
  - Retry (secondary)
  - Exclude (secondary)
  - Delete (destructive)
  - Clear (tertiary)
- Count is not repeated inside individual buttons.

## 3) How overlay controls changed

- Select overlay (top-left): compact chip with state text
  - unselected: `Select`
  - selected: `Selected`
- Added compact indicator glyph and selected-state chip treatment.
- Ready overlay (top-right): compact dark translucent pill, stronger readability, balanced weight.
- Kept/adjusted subtle top gradient scrim for legibility support.

## 4) Files changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/capture-inbox-sticky-toolbar-fix-log.md`
- `docs/capture-inbox-sticky-toolbar-fix-resume.md`

## 5) Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

## 6) Verification result

Passed.

- Capture Inbox focused source-contract tests passed.
- Web typecheck (`tsc --noEmit -p tsconfig.typecheck.json`) passed.
