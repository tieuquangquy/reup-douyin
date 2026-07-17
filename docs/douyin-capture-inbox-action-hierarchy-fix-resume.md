# Douyin Capture Inbox Action Hierarchy Fix Resume

## Current task

Normalize Capture Inbox action hierarchy, icon usage, labels, and action presentation so the page behaves like a first-class sibling of Review Board and Reup Queue.

## Required docs

- `docs/douyin-capture-inbox-action-hierarchy-fix-log.md`
- `docs/douyin-capture-inbox-action-hierarchy-fix-resume.md`
- `docs/douyin-capture-inbox-action-hierarchy-fix-user-guide.md`

## Status

Completed.

## Audit completed

Relevant files reviewed:

- `AGENTS.md`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/app/globals.css`

## Key decisions

- Capture Inbox uses the shared Ops action hierarchy already present in Review Board and Reup Queue.
- Button tone is the hierarchy mechanism: primary, default/secondary, subtle link-style, and danger.
- No icon library is currently used in the audited sibling workflows.
- No new icon dependency was added.
- The compact `⋯` overflow affordance remains only for Capture session row menus.

## Code changes completed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - Imported `OpsActionRow`.
  - Made `Promote ready items` explicitly primary.
  - Changed active status filters from `selected` to `primary` to match Reup Queue.
  - Rendered item card contextual actions through shared `OpsActionRow`.
  - Standardized card detail affordances as `Details`.
  - Standardized contextual detail action as `Details` for all statuses.
  - Standardized failed retry as `Retry enrich`.
  - Kept `Delete staged item`, `Delete selected`, and `Delete session` labels.
  - Kept `Exclude` and `Exclude selected` as destructive actions.
  - Kept `Show more` / `Show less` as tertiary text controls.

- `apps/web/src/test/capture-inbox.test.ts`
  - Added assertions for shared `OpsActionRow` on item cards.
  - Added assertions for primary header CTA and primary active filters.
  - Added assertions that old duplicate labels are removed.
  - Added assertions that destructive actions remain distinct.
  - Added assertion preventing noisy icon plumbing without a shared icon system.

## Verification run

Passed:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Output:

```text
capture inbox UX redesign, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Remaining inconsistencies

- Reup Queue top toolbar still has some default-styled primary workflow buttons. Capture Inbox was normalized locally without changing sibling pages.
- No broad icon normalization was implemented because no shared icon system exists in the audited workflows.
