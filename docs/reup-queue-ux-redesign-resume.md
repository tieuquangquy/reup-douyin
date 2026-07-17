# Reup Queue UX Redesign Resume Notes

## Current state

The Reup Queue UX redesign is in progress. This document is created before implementation so the work can be resumed safely without losing context.

## User intent

Create a Reup Queue workspace that feels consistent with the redesigned Douyin Capture Inbox and supports the full operator workflow:

Capture Inbox -> Review Board -> Reup Queue -> Export Package -> Publish Handoff.

The page must remain an operator workspace, not a technical queue dump.

## Files to prioritize

- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/test/reup-queue.test.ts`
- `docs/reup-queue-ux-redesign-log.md`
- `docs/reup-queue-ux-redesign-architecture.md`
- `docs/reup-queue-ux-redesign-user-guide.md`

Useful pattern reference:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

Useful type/API references:

- `apps/web/src/types/reup-queue.ts`
- `apps/web/src/types/export-handoff.ts`
- `apps/web/src/lib/api.ts`

## Audit completed

Relevant files have been read:

- `AGENTS.md`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/test/reup-queue.test.ts`
- `apps/web/src/types/reup-queue.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

## Implementation approach

1. Keep existing API calls and backend-owned lifecycle intact.
2. Add local UI-only state for:
   - operator filter;
   - search query;
   - sort mode;
   - focused item;
   - selected item ids.
3. Replace passive status summary metrics with clickable operator summary cards.
4. Add recommended next action banner derived from visible queue counts.
5. Convert the list into simplified cards.
6. Move raw/technical details into semantic right-panel sections and collapsed diagnostics.
7. Convert the batch operation panel into a sticky, state-aware batch action bar.
8. Keep Export Package and Publish Handoff links visible but operator-friendly.
9. Update source tests to assert the new UX structure.
10. Run verification and update the log.

## Important constraints

- Do not trigger publishing from the UI.
- Do not hide backend state or available actions; present them in operator language.
- Do not hardcode user-specific paths.
- Do not add dependencies.
- Do not implement future SaaS or worker behavior in this UI slice.

## Expected verification

- `npx tsx apps/web/src/test/reup-queue.test.ts`
- `npm run typecheck`

Optional if routes/navigation change:

- `npx tsx apps/web/src/test/route-nav.test.ts`
