# Ops Console Layout Fix Resume

## Current Task

Fix and refactor the Capture Inbox and Reup Queue UI/layout into a shared Ops Console page layout so both workflows are operator-friendly, responsive, and visually consistent.

## Files Touched

Implementation touched:

- `apps/web/src/components/ops-console/OpsShared.tsx`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/reup-queue.test.ts`
- `apps/web/src/test/ops-console-design-system.test.ts`
- `docs/ops-console-layout-fix-log.md`
- `docs/ops-console-layout-fix-resume.md`
- `docs/ops-console-layout-fix-architecture.md`

No backend files, routes, API contracts, worker logic, queue logic, crawler logic, or publishing automation were changed.

## Audit Snapshot

Routes:

- Capture Inbox route: `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx`
- Reup Queue route: `apps/web/src/app/selection/reup-queue/page.tsx`

Page components:

- Capture Inbox: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- Reup Queue: `apps/web/src/components/reup-queue/ReupQueuePage.tsx`

Root cause found before implementation:

- The pages used shared cards/details but not a complete shared content layout.
- `.page-shell` had no max-width or centered content behavior.
- `.intake-layout` was a legacy two-column layout with hard minimums that created awkward whitespace and inconsistent responsive behavior.
- Summary cards were vulnerable to parent width and old generic `.operator-metric-card` behavior.
- Reup Queue filter chips and form controls shared a crowded flex row.

## Completed Implementation

- Added shared layout primitives:
  - `OpsConsolePage`
  - `OpsSection`
  - `OpsContentGrid`
  - `OpsMainColumn`
  - `OpsSideColumn`
  - `OpsToolbar`
  - `OpsToolbarGroup`
  - `OpsEmptyState`
  - `OpsStatusBadge`
- Updated `OpsFilterBar` to delegate to `OpsToolbar` so existing page code remains compatible.
- Added CSS for the shared layout:
  - centered max-width Ops Console page stack
  - bounded responsive main/detail content grid
  - toolbar grouping and wrapping
  - section heading/action rhythm
  - summary grid/card strengthening
  - 1180px content-grid collapse
  - 760px mobile toolbar/header/item collapse
- Refactored Capture Inbox to use the shared page/content/section primitives.
- Refactored Reup Queue to use the same shared page/content/section primitives.
- Replaced Reup Queue raw state panels with `OpsStatePanel` / `OpsEmptyState`.
- Updated source tests to assert shared layout reuse and removal of legacy target-page wrappers.

## Verification Commands Run

From repository root:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/ops-console-design-system.test.ts && npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/reup-queue.test.ts
```

Result: passed.

## Current Status

Implementation, focused tests, typecheck, and documentation updates are complete.

## Remaining Limitations

- No browser visual-regression tooling exists in this repo, so verification is type/source based.
- `PageShell` was left globally unchanged to avoid broad unrelated UI changes; the new shared layout is applied with `OpsConsolePage` in the target pages.
