# Douyin Capture Inbox 3-Pane Resume

## Current Task

Refactor the Capture Inbox route into the final chosen 3-pane moderation workspace:

- left Session Rail
- center Item Worklist
- right Inspector Drawer

This is the final primary UX model for Capture Inbox. Do not reintroduce card-grid-first or table-first primary layouts.

## Current Status

Implementation and verification are complete. The Capture Inbox route now uses the final 3-pane moderation workspace as the primary UX model.

## Completed

- Read AGENTS.md.
- Audited the current Capture Inbox page, CSS, and focused test.
- Created the required 3-pane log, resume, architecture, and user guide docs before implementation.
- Replaced the old table-first center workspace with a compact media-row Item Worklist.
- Refactored capture sessions into a compact Session Rail.
- Finalized the Inspector Drawer with collapsed Diagnostics and Raw details.
- Preserved and verified selection, active item, session switching, delete, promote, retry, bulk action, and empty-state sync behavior.
- Kept thumbnail mapping unchanged because the existing resolver was sufficient.
- Updated the focused Capture Inbox source test for 3-pane expectations.
- Ran focused source verification and web typecheck successfully.

## Key Findings

Reusable pieces:

- Existing session loading and deletion flow.
- Existing selected item ids and active item id separation.
- Existing action API wiring for promote, retry enrich, retry preview, exclude, delete items.
- Existing summary count derivation.
- Existing thumbnail resolution.
- Existing detail drawer long-text expansion reset.
- Existing batch action bar pattern.

Replace or refactor:

- CapturedItemsTable table-first center renderer.
- capture-inbox table-specific CSS.
- table workspace labels and tests.
- oversized summary cards.
- session list copy and empty state.
- row structure so it becomes a compact media-rich worklist row.

## Required Next Steps

No implementation steps remain for this task. Future work should stay scoped and must not reintroduce a card-grid-first or table-first primary Capture Inbox layout.

## Files Changed

Web files:

- apps/web/src/components/capture-inbox/CaptureInboxPage.tsx
- apps/web/src/app/globals.css
- apps/web/src/test/capture-inbox.test.ts

Docs:

- docs/douyin-capture-inbox-3pane-log.md
- docs/douyin-capture-inbox-3pane-resume.md
- docs/douyin-capture-inbox-3pane-architecture.md
- docs/douyin-capture-inbox-3pane-user-guide.md

Backend files did not change. Existing contracts were sufficient for details, actions, delete, and thumbnail rendering.

## Guardrails

- Keep the 3-pane moderation workspace as the primary model.
- Avoid giant cards, raw text dumps, debug-page visual treatment, and spreadsheet-like main tables.
- Keep Capture Inbox as a staging/review workflow only.
- Preserve local-first and SaaS-ready boundaries.
- Do not add dependencies unless required.

## Verification Results

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace apps/web`
