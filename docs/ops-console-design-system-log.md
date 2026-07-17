# Ops Console Design System Log

## Status

Implemented and verified. This document records the audit, design decisions, scope, implementation results, and verification outcomes for creating a unified Ops Console Design System across Douyin Capture Inbox, Review Board, Reup Queue, Export Package, and Publish Handoff.

## Request

Create and apply a unified Ops Console Design System across the five operator workflow surfaces so the workflow feels visually and behaviorally consistent while preserving backend behavior and product boundaries.

## Touched areas

Implementation scope:

- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/review-board/ReviewBoardPage.tsx`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/components/operator-routes/ExportPackagesIndexPage.tsx`
- `apps/web/src/components/operator-routes/ExportPackageByIdPage.tsx`
- `apps/web/src/components/operator-routes/PublishHandoffsIndexPage.tsx`
- `apps/web/src/components/operator-routes/PublishHandoffByIdPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/test/reup-queue.test.ts`
- `apps/web/src/test/ops-console-design-system.test.ts`

No API, worker, database, crawler, publishing automation, or queue orchestration changes are planned.

## Audit summary

### Shared shell and style inventory

The app already has a partial shared foundation:

- `OpsConsoleShell` for ops-side navigation.
- `OperatorStudioShell` for operator-side navigation.
- `PageShell` for consistent page headers.
- `StatusBadge` with tone values: `good`, `warn`, `danger`, `muted`.
- `OpsShared.tsx` with older operational helpers:
  - `OpsPageHeader`
  - `OpsMetricCard`
  - `OpsPanel`
  - `OpsState`
  - formatting helpers
  - generic `statusTone`
- `globals.css` already contains reusable operator classes:
  - `operator-panel`
  - `operator-panel-heading`
  - `operator-quick-grid`
  - `operator-quick-card`
  - `operator-empty-state`
  - `intake-layout`
  - `intake-side`
  - `summary-list`
  - `field`
  - `selection-bar`
  - `state-panel`

The current implementation should extend this foundation rather than introducing a separate styling system.

### Douyin Capture Inbox

Current state: closest to the desired design language.

Observed patterns:

- Uses `OpsConsoleShell` and `PageShell`.
- Has workflow context, recommended next action, summary cards, filter/search/sort row, item cards, detail panel, session side panel, and sticky batch bar.
- Uses honest pending/missing labels and collapsed diagnostics.

Needed changes:

- Replace page-local duplicated components with shared Ops Console primitives where practical.
- Preserve capture-specific behavior and API calls.
- Keep session side panel as a domain-specific extension.

### Review Board

Current state: largest mismatch.

Observed patterns:

- Uses legacy `main.review-board`, `header.board-header`, `ReviewBoardToolbar`, `CandidateGrid`, `CandidateCard`, fixed modal `CandidateDetailDrawer`, and `CandidateSelectionBar`.
- Does not use `OpsConsoleShell` / `PageShell`.
- Selection bar and detail drawer are page-specific.
- Empty/loading/error states are page-specific.

Needed changes:

- Move to Ops Console shell and page template.
- Add workflow context and next-action guidance.
- Convert toolbar to shared filter/search pattern.
- Convert candidate cards to shared item card style while keeping thumbnail/score affordances.
- Convert drawer/detail into shared detail panel vocabulary.
- Convert selection bar to shared sticky batch action pattern.
- Preserve approved-candidate guard and `enqueueReupCandidates` transition.

### Reup Queue

Current state: recently redesigned and close to target.

Observed patterns:

- Uses `OpsConsoleShell` and `PageShell`.
- Has recommended action, summary cards, search/filter/sort, bucketed item cards, detail panel, and sticky batch bar.
- Contains duplicated page-local versions of the same patterns Capture Inbox uses.

Needed changes:

- Replace duplicated local primitives with shared components while preserving behavior and labels.
- Preserve batch operations, export package creation, publish handoff creation, and safety language.

### Export Package surfaces

Current state: uses shared shell/page primitives, but is lightweight and visually disconnected from Capture/Reup.

Observed patterns:

- Index and detail use `OperatorStudioShell`, `PageShell`, and `StatusBadge`.
- Index uses `operator-quick-card` list.
- Detail uses `operator-panel` sections and diagnostics details.

Needed changes:

- Add Ops Console summary/next-action patterns.
- Apply shared item card/list patterns to package cards and package item cards.
- Apply common detail section vocabulary to the detail page.
- Preserve artifact-inspection behavior and manual handoff safety.

### Publish Handoff surfaces

Current state: uses shared shell/page primitives, but is lightweight and visually disconnected from Capture/Reup.

Observed patterns:

- Index and detail use `OperatorStudioShell`, `PageShell`, and `StatusBadge`.
- Detail explicitly states it is a manual handoff artifact and does not auto-publish.
- Payload and diagnostics are inspectable.

Needed changes:

- Add summary/next-action patterns.
- Apply shared item card/list patterns.
- Apply common detail section vocabulary.
- Preserve no-auto-publish language.

## Design decisions

1. Keep the existing CSS token base in `globals.css`.
2. Extend `OpsShared.tsx` into the unified design system entry point instead of adding a new dependency or external UI framework.
3. Keep `StatusBadge` tone-based at the visual layer, but add semantic helpers for domain statuses.
4. Use composition over rigid configuration. The shared primitives should provide shell, panel, card, detail, batch, and state scaffolding; pages should still own domain-specific text and actions.
5. Use shared CSS class names prefixed with `ops-console-` for new primitives, while allowing existing `operator-*` classes to remain compatible.
6. Preserve the current API calls and backend behavior.
7. Avoid adding product phases not requested: no crawler, video processing, scoring changes, queue implementation changes, DB schema, or auto-publish integration.

## Implementation plan

1. Create/update shared Ops Console primitives in `OpsShared.tsx`:
   - `OpsWorkflowContext`
   - `OpsNextActionBanner`
   - `OpsSummaryCards`
   - `OpsFilterBar`
   - `OpsItemCard`
   - `OpsDetailPanel`
   - `OpsDetailSection`
   - `OpsBatchActionBar`
   - `OpsStatePanel`
   - semantic status helpers.
2. Add supporting CSS to `globals.css`.
3. Refactor Capture Inbox to use shared primitives without changing behavior.
4. Refactor Review Board to use shared primitives and align with the operator workflow.
5. Refactor Reup Queue to use shared primitives without changing behavior.
6. Refactor Export Package and Publish Handoff index/detail pages to use shared summary, card, state, and detail patterns.
7. Add/update tests that assert design system adoption and workflow safety language.
8. Run focused tests and typecheck.
9. Update these docs with verification results and any deviations.

## Verification plan

Planned commands:

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npx tsx apps/web/src/test/review-board.test.ts`
- `npx tsx apps/web/src/test/reup-queue.test.ts`
- new Ops Console design system test, if added
- `npx tsx apps/web/src/test/route-nav.test.ts` if navigation or route files are touched
- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`
- `npm run typecheck`

## Verification results

Passed:

- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/review-board.test.ts && npx tsx apps/web/src/test/reup-queue.test.ts && npx tsx apps/web/src/test/ops-console-design-system.test.ts && npx tsx apps/web/src/test/route-nav.test.ts`
- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`

Focused typecheck was also run after major UI layers during implementation:

- After Review Board refactor.
- After Reup Queue refactor.
- After Export Package and Publish Handoff route refactors.

## Implementation results

- Added shared Ops Console primitives and CSS hooks in `OpsShared.tsx` and `globals.css`.
- Refactored Capture Inbox to shared workflow context, next action, summary, filter, item card, detail panel, and batch action primitives.
- Refactored Review Board from legacy board-specific layout to the shared Ops Console shell and primitives while preserving approved-only Reup Queue transition behavior.
- Refactored Reup Queue duplicated local presentation pieces into shared Ops Console primitives while preserving item actions, batch actions, export package creation, and publish handoff creation.
- Refactored Export Package and Publish Handoff index/detail pages to shared summary, item, state, and detail patterns.
- Added source-level design-system adoption coverage in `ops-console-design-system.test.ts`.

## Deviations

- `StatusBadge` was not changed directly; status tone reuse is exposed through shared Ops Console primitives and `statusTone`.
- Review Board legacy component files remain in the repository for compatibility/history, but the main page now owns the unified Ops Console composition.
- Export Package and Publish Handoff detail pages use shared summary/detail primitives but do not add a separate next-action banner because their primary workflow guidance is already in the page actions, summary cards, and manual-boundary copy.
