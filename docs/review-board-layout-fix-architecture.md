# Review Board Layout Fix Architecture

## Decision

Review Board should render as an Ops Console workflow surface and should own exactly one `OpsConsoleShell` through `ReviewBoardPage`. The `selection/review-board` route must not wrap Review Board in `OperatorStudioShell`.

## Current broken architecture

The current route composition nests two complete app shells:

```text
apps/web/src/app/selection/review-board/page.tsx
└─ OperatorReviewBoardPage
   └─ OperatorStudioShell
      └─ AppShell(surface="operator")
         └─ Sidebar: Operator Studio
         └─ ReviewBoardPage
            └─ OpsConsoleShell
               └─ AppShell(surface="ops")
                  └─ Sidebar: Ops Console
                  └─ PageShell + Review Board content
```

This is broken because shells are not layout primitives that can be safely nested. Each shell owns global page chrome: sidebar, topbar, and app content area. Nesting them duplicates global navigation and pushes the Review Board content into the wrong visual hierarchy.

## Correct parent shell

The chosen parent shell is `OpsConsoleShell`.

Reasons:

1. Review Board is part of the operational workflow sequence: Capture Inbox -> Review Board -> Reup Queue -> Export Package -> Publish Handoff.
2. Capture Inbox and Reup Queue already use `OpsConsoleShell` plus the shared Ops Console page primitives.
3. Export Package and Publish Handoff surfaces are Ops Console-style workflow handoff surfaces.
4. The requested fix explicitly asks Review Board to align with the shared Ops Console page layout used by the rest of the operator workflow.
5. Keeping `OpsConsoleShell` in `ReviewBoardPage` preserves the existing Review Board page API and local page ownership while allowing route-level composition to stay simple.

## Target architecture

```text
apps/web/src/app/selection/review-board/page.tsx
└─ ReviewBoardPage
   └─ OpsConsoleShell
      └─ AppShell(surface="ops")
         └─ Sidebar: Ops Console
         └─ PageShell
            └─ OpsConsolePage
               ├─ workflow/context section
               ├─ recommendation banner
               ├─ summary cards
               ├─ filter/search toolbar
               ├─ OpsContentGrid
               │  ├─ OpsMainColumn
               │  │  └─ candidate list section
               │  └─ OpsSideColumn
               │     └─ detail panel
               └─ batch action bar
```

Only one `AppShell` exists in the route tree, so only one `Sidebar` can render.

## Layout alignment

Review Board should align with the shared Ops Console workflow layout by using these primitives from `apps/web/src/components/ops-console/OpsShared.tsx`:

- `OpsConsolePage` for centered page width and vertical stacking.
- `OpsWorkflowContext` for workflow sequence and metrics.
- `OpsNextActionBanner` for recommended next operator action.
- `OpsSummaryCards` for summary metrics.
- `OpsFilterBar` and `OpsToolbarGroup` for filter/search controls.
- `OpsContentGrid` for main list plus side detail arrangement.
- `OpsMainColumn` for candidate list content.
- `OpsSideColumn` for the candidate detail panel.
- `OpsSection` for titled content sections and section-level actions.
- `OpsItemCard`, `OpsDetailPanel`, and `OpsBatchActionBar` for candidate rows, details, and batch actions.

Legacy wrappers `intake-layout`, `intake-form`, and `intake-side` should not be used by Review Board after this fix.

## Removed legacy composition

The route-level `OperatorStudioShell` wrapper around Review Board is legacy composition for this page. Removing it from the `selection/review-board` route prevents nested global chrome and removes the visible `Operator Studio` sidebar from the Review Board page.

`OperatorReviewBoardPage` may remain in the codebase if other routes or future cleanup need it, but `selection/review-board` must not use it. Keeping the change route-scoped avoids broad navigation churn.

## Preserved behavior

The fix must preserve:

- candidate loading through `fetchCandidates`
- filter preset loading through `fetchFilterPresets`
- preset application through `applyCandidatePreset`
- status updates through `bulkUpdateCandidateStatus`
- selection state and bulk actions
- detail panel focus behavior
- approved-candidate queueing through `enqueueReupCandidates`
- `/review-board` redirect behavior to `/selection/review-board`
- existing links into `/selection/review-board`, including query parameters from the legacy redirect route

## Testing approach

Use source tests to catch composition regressions because the bug is visible shell nesting caused by route/component imports:

- Assert `selection/review-board/page.tsx` imports `ReviewBoardPage` directly.
- Assert the route source does not reference `OperatorReviewBoardPage`.
- Assert `ReviewBoardPage` uses `OpsConsoleShell` and shared Ops Console layout primitives.
- Assert legacy intake layout wrappers are absent from `ReviewBoardPage`.
- Keep existing behavioral source guards for Reup Queue transition actions.

## Future note

If the product later decides that selection workflow routes should move physically under `/ops`, that should be handled as a separate route migration with redirects and navigation updates. This fix keeps the public route stable and corrects the shell composition bug in place.
