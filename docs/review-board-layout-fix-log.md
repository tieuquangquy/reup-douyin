# Review Board Layout Fix Log

## Scope

Fix the broken `selection/review-board` layout in `apps/web` so the page renders under one correct app shell, removes duplicated sidebars, and aligns the Review Board surface with the shared Ops Console workflow layout already used by Capture Inbox, Reup Queue, Export Package, and Publish Handoff surfaces.

## Audit findings before implementation

### Files inspected

- `AGENTS.md`
- `apps/web/src/app/selection/review-board/page.tsx`
- `apps/web/src/app/review-board/page.tsx`
- `apps/web/src/components/operator-routes/OperatorReviewBoardPage.tsx`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/components/app-shell/AppShell.tsx`
- `apps/web/src/components/app-shell/OperatorStudioShell.tsx`
- `apps/web/src/components/app-shell/OpsConsoleShell.tsx`
- `apps/web/src/components/app-shell/Sidebar.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/test/review-board.test.ts`

### Exact broken route composition

The active route `apps/web/src/app/selection/review-board/page.tsx` currently renders `OperatorReviewBoardPage`.

`OperatorReviewBoardPage` wraps `ReviewBoardPage` in `OperatorStudioShell`.

`ReviewBoardPage` already wraps its page content in `OpsConsoleShell`.

Both shell components render `AppShell`, and `AppShell` always renders `Sidebar`. `Sidebar` labels the `operator` surface as `Operator Studio` and the `ops` surface as `Ops Console`.

That creates this runtime hierarchy:

```text
/selection/review-board
└─ OperatorReviewBoardPage
   └─ OperatorStudioShell
      └─ AppShell(surface="operator")
         └─ Sidebar("Operator Studio")
         └─ ReviewBoardPage
            └─ OpsConsoleShell
               └─ AppShell(surface="ops")
                  └─ Sidebar("Ops Console")
                  └─ Review Board content
```

### Root cause

The duplicated left navigation is caused by nested route/page shells, not by CSS. The `selection/review-board` route adds the legacy Operator Studio shell around a Review Board component that already owns its intended Ops Console shell.

### Current Review Board layout issues

Inside the existing single Review Board content area, `ReviewBoardPage` still uses legacy intake wrappers:

- `intake-layout`
- `intake-form`
- `intake-side`

Capture Inbox and Reup Queue have already been migrated to shared Ops Console layout primitives:

- `OpsConsolePage`
- `OpsContentGrid`
- `OpsMainColumn`
- `OpsSideColumn`
- `OpsSection`
- `OpsToolbarGroup`

Review Board should reuse those same primitives so workflow surfaces share width, spacing, content hierarchy, toolbar behavior, candidate/list region, and side detail panel structure.

## Implementation plan

1. Fix route composition first by making `selection/review-board` render the Review Board under exactly one shell.
2. Keep Review Board under `OpsConsoleShell`, because it is now part of the shared operator workflow surfaces that connect Capture Inbox, Review Board, Reup Queue, Export Package, and Publish Handoff.
3. Remove the legacy Operator Studio wrapper from this route path.
4. Refactor Review Board content from legacy intake layout wrappers into shared Ops Console layout primitives.
5. Preserve candidate loading, filtering, status transitions, bulk actions, detail panel behavior, and Reup Queue enqueue behavior.
6. Add source tests that guard against nested shells and legacy layout regressions.
7. Run focused web typecheck and Review Board tests.

## Implementation notes

Implemented after the required docs-first step:

- `apps/web/src/app/selection/review-board/page.tsx` now imports and renders `ReviewBoardPage` directly.
- `ReviewBoardPage` remains the owner of `OpsConsoleShell`, so `/selection/review-board` has exactly one `AppShell` and one `Sidebar`.
- `ReviewBoardPage` now wraps its content in `OpsConsolePage` and uses `OpsContentGrid`, `OpsMainColumn`, `OpsSideColumn`, and `OpsSection` for the candidate list plus detail panel structure.
- `ReviewFilterBar` now uses `OpsToolbarGroup` for filter action grouping.
- Legacy Review Board layout wrappers `intake-layout`, `intake-form`, and `intake-side` were removed from the Review Board page.
- Candidate loading, filters, keep/reject/in-review transitions, detail panel focus, bulk actions, and approved candidate enqueue behavior were preserved.

## Verification log

Command run from the repository root:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/review-board.test.ts
```

Result:

```text
> typecheck
> tsc --noEmit -p tsconfig.typecheck.json

review-board state tests passed
```

Verification passed. Source tests now guard against the duplicate-shell regression by asserting the route renders `ReviewBoardPage` directly and does not reference `OperatorReviewBoardPage` or `OperatorStudioShell`.
