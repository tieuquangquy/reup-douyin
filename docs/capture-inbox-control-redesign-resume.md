# Capture Inbox Control Redesign Resume

## Task

Refactor only these Capture Inbox controls:

1. Batch actions toolbar
2. Select overlay control on media tiles
3. Ready status chip on media tiles
4. Top image gradient overlay for contrast

## Scope lock

- No extraction/backend/API/data-flow changes.
- No action semantics changes.
- No broader page layout redesign.

## Status

Completed.

## Completed

- Read `AGENTS.md`.
- Audited current control implementation in:
  - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `apps/web/src/components/ops-console/OpsShared.tsx`
  - `apps/web/src/app/globals.css`
  - `apps/web/src/test/capture-inbox.test.ts`
- Wrote docs-first log:
  - `docs/capture-inbox-control-redesign-log.md`
- Refactored batch toolbar into compact command bar with one count anchor and helper text.
- Refactored tile Select overlay into minimal floating checkbox chip.
- Improved Ready chip readability and preserved compact moderation tone.
- Kept subtle top image gradient overlay for contrast.
- Updated focused tests in `apps/web/src/test/capture-inbox.test.ts`.
- Verification passed:
  - `npx tsx apps/web/src/test/capture-inbox.test.ts`
  - `npm run typecheck --workspace apps/web`

## Next steps

None.
