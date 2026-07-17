# Capture Inbox Sticky Toolbar + Overlay Polish Log

## 1) Problem summary

This task is intentionally narrow to `apps/web` Capture Inbox UI polish only.

Current operator pain points:
- Batch actions command bar is present but not sticky, so when many items are selected the operator may need to scroll to reach it.
- Tile top overlay controls (Select + Ready) are functional but visually bulky and not refined enough for a media-first moderation surface.
- Overlay legibility support should remain subtle and must not darken thumbnails heavily.

Strict non-goals:
- No backend/API/schema/extraction/capture logic changes.
- No selection semantics changes.
- No broader page workflow or layout redesign.

## 2) Sticky toolbar behavior target

When `selectedCount > 0`:
- Render batch actions as a sticky/floating command bar inside Capture Inbox content area.
- Keep one selected-count anchor (`N selected`) and one helper line (`Only eligible items will be affected.`).
- Keep concise buttons only: `Promote`, `Retry`, `Exclude`, `Delete`, `Clear`.
- Preserve hierarchy:
  - Promote = primary
  - Retry/Exclude = secondary
  - Delete = destructive
  - Clear = tertiary/ghost

When `selectedCount === 0`:
- Command bar does not render.

Implementation direction:
- Sticky top placement within Capture Inbox review workspace, with safe `top` offset and z-index that does not conflict with global header.
- Rounded, light elevation, compact spacing, readable contrast.

## 3) New overlay design target

Select chip (top-left):
- Smaller compact floating chip.
- Unselected text: `Select`.
- Selected text: `Selected`.
- Clear selected/unselected visual distinction, but still lightweight.

Ready chip (top-right):
- Compact readable status pill.
- Stronger contrast across bright/dark thumbnails.
- Balanced visual weight relative to Select chip.

Top gradient support:
- Keep/add subtle top gradient to improve chip readability.
- Must stay light and media-first.

## 4) Files planned

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/capture-inbox-sticky-toolbar-overlay-polish-log.md`
- `docs/capture-inbox-sticky-toolbar-overlay-polish-resume.md`

## 5) Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`

## 6) Verification result

Passed.

- Capture Inbox focused source-contract test passed.
- Web typecheck (`tsc --noEmit -p tsconfig.typecheck.json`) passed.
