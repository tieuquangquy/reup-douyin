# Capture Inbox Sticky Toolbar + Overlay Polish Resume

## Task

Capture Inbox UI polish (`apps/web` only):
1. Sticky/floating batch actions command bar when selection exists
2. Refined Select overlay chip on media tiles
3. Refined Ready status chip on media tiles
4. Subtle top gradient support for legibility

## Scope lock

- No backend/API/schema/extractor/capture flow changes
- No selection or action semantics changes
- No broad page/workflow redesign

## Status

Completed.

## Completed

- Read `AGENTS.md` before implementation.
- Audited current implementation in:
  - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `apps/web/src/app/globals.css`
  - `apps/web/src/test/capture-inbox.test.ts`
- Created docs-first files:
  - `docs/capture-inbox-sticky-toolbar-overlay-polish-log.md`
  - `docs/capture-inbox-sticky-toolbar-overlay-polish-resume.md`
- Updated sticky/floating batch command bar behavior:
  - renders only when `selectedItems.length > 0`
  - remains sticky inside Capture Inbox content workspace
  - keeps single selected-count anchor and concise command labels
- Refined Select overlay into compact chip with explicit state labels:
  - unselected: `Select`
  - selected: `Selected`
- Refined Ready chip readability into compact dark translucent pill.
- Kept subtle top overlay gradient for readability support.
- Updated focused tests for sticky mode + overlay compact states.
- Verification passed:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts`
  - `npm run typecheck --workspace apps/web`

## Next steps

None.
