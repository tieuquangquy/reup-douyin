# Ops Console Layout Fix Log

## Scope

Fix the current layout/UI problems for:

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- Shared Ops Console layout primitives in `apps/web/src/components/ops-console/OpsShared.tsx`
- Related global styles in `apps/web/src/app/globals.css`
- Focused source tests for both pages and shared layout reuse

## Non-goals

- No backend business logic changes.
- No route contract changes.
- No API response meaning changes.
- No workflow meaning changes for Capture Inbox or Reup Queue.
- No new dependencies.

## Audit Findings Before Implementation

### Repository and boundary findings

`AGENTS.md` confirms `apps/web` owns the Next.js UI and API calls. This task remains inside the web boundary and does not alter API, worker, crawling, queue orchestration, video processing, or publishing automation.

### Current Capture Inbox rendering path

- Route: `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx`
- Page component: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- Existing shell primitives before the fix:
  - `OpsConsoleShell`
  - `PageShell`
  - `OpsWorkflowContext`
  - `OpsNextActionBanner`
  - `OpsSummaryCards`
  - `OpsFilterBar`
  - `OpsItemCard`
  - `OpsDetailPanel`
  - `OpsBatchActionBar`

### Current Reup Queue rendering path

- Actual route: `apps/web/src/app/selection/reup-queue/page.tsx`
- Page component: `apps/web/src/components/reup-queue/ReupQueuePage.tsx`
- Before the fix, it used the same broad primitive set as Capture Inbox, but still relied heavily on old `.intake-layout`, `.intake-form`, `.intake-side`, `.operator-panel`, `.bucket-list`, and ad hoc state panels.

### CSS findings

The most relevant CSS is in `apps/web/src/app/globals.css`:

- `.page-shell` only applied padding and had no centered max-width.
- `.intake-layout` used `grid-template-columns: minmax(620px, 1fr) 360px`.
- `.intake-side` was sticky and width-biased.
- `.ops-console-summary-grid` already used `repeat(auto-fit, minmax(180px, 1fr))`, but it lived inside a page shell with no width discipline and shared styles with older `.operator-metric-card` rules.
- `.operator-metric-card` had a fixed-ish minimum height and generic styles used by multiple pages.
- `.ops-console-filter-controls` used a plain wrapping flex row, which became visually noisy when many filter buttons were rendered.
- `.state-panel` was available, but Reup Queue still used raw `<div className="state-panel">` instead of the shared `OpsStatePanel` primitive.

## Root Cause Summary

The layout bug was not one isolated CSS typo. It came from mixed generations of layout primitives:

1. Capture Inbox and Reup Queue used shared Ops primitives for cards and details, but their page body still relied on older `.intake-layout` rules.
2. `.page-shell` lacked a max-width and centered content strategy, allowing wide displays to create excessive blank space and making section widths feel arbitrary.
3. Summary cards were technically grid-based, but their container sat in a page hierarchy that did not normalize width, spacing, or section rhythm.
4. Reup Queue rendered many filter chips inside the same flex row as form fields, causing hierarchy and wrapping problems.
5. Capture Inbox and Reup Queue duplicated page-local section markup instead of using a durable shared section/content-grid abstraction.

## Implementation Completed

- Added shared Ops Console layout primitives in `apps/web/src/components/ops-console/OpsShared.tsx`:
  - `OpsConsolePage`
  - `OpsSection`
  - `OpsContentGrid`
  - `OpsMainColumn`
  - `OpsSideColumn`
  - `OpsToolbar`
  - `OpsToolbarGroup`
  - `OpsEmptyState`
  - `OpsStatusBadge`
- Updated `OpsFilterBar` to use the shared `OpsToolbar` structure while preserving its public component name.
- Added durable layout CSS in `apps/web/src/app/globals.css`:
  - centered `ops-console-page` with max width
  - bounded main/detail `ops-console-content-grid`
  - sticky side column only on wide screens
  - grouped toolbar controls
  - responsive collapse at 1180px and 760px
  - strengthened summary grid/card sizing
- Refactored Capture Inbox away from legacy `intake-layout`, `intake-form`, and `intake-side` wrappers.
- Refactored Reup Queue away from legacy `intake-layout`, `intake-form`, and `intake-side` wrappers.
- Converted Reup Queue loading/error/empty states to shared `OpsStatePanel` and `OpsEmptyState`.
- Added/updated focused source assertions in:
  - `apps/web/src/test/ops-console-design-system.test.ts`
  - `apps/web/src/test/capture-inbox.test.ts`
  - `apps/web/src/test/reup-queue.test.ts`

## Verification Log

Command run from repository root:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/ops-console-design-system.test.ts && npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/reup-queue.test.ts
```

Result: passed.

Output summary:

```text
> typecheck
> tsc --noEmit -p tsconfig.typecheck.json

ops-console design system source tests passed
capture inbox UX redesign tests passed
reup-queue UI tests passed
```

## Remaining Limitations

- Verification is source/typecheck based. No browser screenshot or visual regression runner is configured in this repo.
- `PageShell` itself was not globally changed to avoid affecting unrelated pages; the durable layout is applied through `OpsConsolePage` inside the target pages.
