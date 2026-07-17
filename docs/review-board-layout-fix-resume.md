# Review Board Layout Fix Resume

## Current objective

Fix `selection/review-board` so Review Board renders under exactly one correct app shell, shows only one left sidebar, and uses the shared Ops Console page layout pattern used by the rest of the operator workflow.

## Audit summary

The duplicate sidebar bug is a shell composition bug:

1. `apps/web/src/app/selection/review-board/page.tsx` renders `OperatorReviewBoardPage`.
2. `OperatorReviewBoardPage` renders `OperatorStudioShell`.
3. `OperatorStudioShell` renders `AppShell` with the `operator` surface and therefore the `Operator Studio` sidebar.
4. `OperatorReviewBoardPage` nests `ReviewBoardPage` inside that shell.
5. `ReviewBoardPage` renders `OpsConsoleShell`.
6. `OpsConsoleShell` renders a second `AppShell` with the `ops` surface and therefore the `Ops Console` sidebar.
7. Result: two app shells and two sidebars around the Review Board content.

## Correct target composition

The target hierarchy should be:

```text
/selection/review-board
└─ ReviewBoardPage
   └─ OpsConsoleShell
      └─ AppShell(surface="ops")
         └─ Sidebar("Ops Console")
         └─ Review Board content
```

There must be no `OperatorStudioShell` wrapper around the Review Board route.

## Planned code changes

- Update `apps/web/src/app/selection/review-board/page.tsx` to render `ReviewBoardPage` directly.
- Refactor `apps/web/src/components/review-board/ReviewBoardPage.tsx` to reuse shared Ops Console layout primitives:
  - `OpsConsolePage`
  - `OpsContentGrid`
  - `OpsMainColumn`
  - `OpsSideColumn`
  - `OpsSection`
  - `OpsToolbarGroup`
- Remove Review Board usage of legacy layout wrappers:
  - `intake-layout`
  - `intake-form`
  - `intake-side`
- Update `apps/web/src/test/review-board.test.ts` to guard:
  - route no longer imports/renders `OperatorReviewBoardPage`
  - `OperatorReviewBoardPage` no longer appears in the route composition for `selection/review-board`
  - Review Board still uses `OpsConsoleShell`
  - shared Ops Console layout primitives are present
  - legacy intake layout wrappers are absent from Review Board
  - Reup Queue transition behavior source checks remain present

## Non-goals

- No backend/API changes.
- No candidate scoring/filtering behavior changes.
- No queue implementation changes.
- No business workflow changes.
- No CSS-only hiding of sidebars.
- No unrelated route or navigation redesign.

## Verification commands to run

```cmd
npm run typecheck --workspace apps/web
npx tsx apps/web/src/test/review-board.test.ts
```

A combined command may also be used:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/review-board.test.ts
```

## Status

Completed.

Implementation summary:

- `selection/review-board` now renders `ReviewBoardPage` directly.
- The Review Board route no longer uses the legacy `OperatorReviewBoardPage` wrapper, so the route no longer nests `OperatorStudioShell` around `OpsConsoleShell`.
- Review Board content now uses the shared Ops Console layout primitives instead of legacy intake layout wrappers.
- Focused source tests were updated to guard route composition, shared layout reuse, and removal of legacy wrappers.

Verification completed successfully:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/review-board.test.ts
```

```text
> typecheck
> tsc --noEmit -p tsconfig.typecheck.json

review-board state tests passed
```
