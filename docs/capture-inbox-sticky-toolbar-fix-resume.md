# Capture Inbox Sticky Toolbar Fix Resume

## Task

UI-only fix for `/extensions/douyin/capture-inbox` in `apps/web`:
1. Sticky/floating batch actions toolbar when `selectedCount > 0`
2. Refined compact Select + Ready tile overlays with better readability

## Scope lock

- No backend/API/schema/capture/extraction changes
- No business-logic semantics changes
- No broad page redesign

## Status

Completed.

## Completed work

- Audited existing batch toolbar placement and tile overlay implementation.
- Confirmed sticky batch command bar behavior in current implementation:
  - conditional rendering when selection > 0
  - sticky/floating placement near active viewport workspace
- Refined Select chip visual treatment for compact, premium state clarity (`Select` / `Selected`).
- Refined Ready chip to compact readable status pill over varied thumbnails.
- Kept subtle top gradient support for overlay legibility.
- Updated focused tests for sticky toolbar and overlay state/readability expectations.
- Verified with focused test + web typecheck.

## Verification

- `npx tsx apps/web/src/test/capture-inbox.test.ts` ✅
- `npm run typecheck --workspace apps/web` ✅

## Files

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/capture-inbox-sticky-toolbar-fix-log.md`
- `docs/capture-inbox-sticky-toolbar-fix-resume.md`
