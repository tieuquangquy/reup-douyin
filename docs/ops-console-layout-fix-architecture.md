# Ops Console Layout Fix Architecture

## Goal

Create a durable shared Ops Console page layout for Capture Inbox and Reup Queue so both pages are readable, responsive, operator-friendly, and consistent.

## Root Cause Layout Analysis

The broken layout was caused by an incomplete migration to a shared Ops Console design system.

### Problem 1: Page shell had no width discipline

`PageShell` renders `.page-shell`, but the CSS only sets padding. It did not provide:

- centered content
- a max-width
- predictable section spacing
- a reusable content stack

On wide screens this produced large unused right-side whitespace and made card grids appear detached from the rest of the page.

### Problem 2: Legacy content grid still drove both pages

Both Capture Inbox and Reup Queue still used `.intake-layout` with:

- a hard left minimum column around 620px
- a fixed right column around 360px
- sticky side behavior inherited from older intake pages

This was acceptable for older forms, but it was not a general Ops Console layout. It made Capture Inbox and Reup Queue depend on old intake naming and created awkward width behavior.

### Problem 3: Summary cards were shared, but their parent layout was not

`OpsSummaryCards` already rendered `.ops-console-summary-grid` with a responsive grid. However, the grid was nested under generic panel/page containers without a full page layout contract. This meant the summary system could still look vertically stacked, uneven, or disconnected depending on available parent width and inherited panel behavior.

### Problem 4: Toolbar hierarchy was overloaded

`OpsFilterBar` wrapped every child in one flex row. Reup Queue had search, sort, and many filter chips in the same row, so operator controls looked like a pile of unrelated buttons. The fix provides a consistent toolbar pattern that separates controls from chip groups while still wrapping safely.

### Problem 5: Page-local sections duplicated structure

Both pages used repeated `section.operator-panel` markup and page-local headings. This made hierarchy inconsistent and increased the chance of future divergence.

## Chosen Shared Page Shell

The implementation uses a shared Ops Console page composition layer built from reusable primitives in `apps/web/src/components/ops-console/OpsShared.tsx`.

Implemented primitives:

- `OpsConsolePage`: wraps page content in a centered, max-width, consistent vertical stack.
- `OpsSection`: standard panel with title, description, optional actions, and consistent heading hierarchy.
- `OpsContentGrid`: a responsive main/detail layout with a flexible main column and bounded side column.
- `OpsMainColumn`: named main-column wrapper for page readability and CSS targeting.
- `OpsSideColumn`: named side/detail-column wrapper with wide-screen sticky behavior.
- `OpsToolbar`: standard search/sort/filter/action toolbar layout.
- `OpsToolbarGroup`: labeled wrapping group for filter chips or secondary toolbar actions.
- `OpsEmptyState`: shared empty/no-results pattern using the existing state panel visual language.
- `OpsStatusBadge`: wrapper around the existing status badge vocabulary.

`OpsFilterBar` remains available and now delegates to `OpsToolbar`, preserving compatibility while standardizing layout.

## Chosen Summary Grid System

Summary cards remain shared through `OpsSummaryCards`, with stronger CSS:

- `grid-template-columns: repeat(auto-fit, minmax(180px, 1fr))`
- cards use `min-height` and `height: 100%`
- cards use `min-width: 0` and `width: 100%`
- summary grid uses `align-items: stretch`
- no page-local width props

Expected behavior:

- Desktop: multiple cards per row depending on content width.
- Tablet: 2-3 cards per row.
- Mobile: cards wrap to fewer columns based on available width.

## Chosen Section Shell

`OpsSection` is now the standard section wrapper for the refactored target pages:

- Capture Inbox item list
- Capture Inbox session side panel
- Reup Queue grouped bucket list
- Reup Queue bucket panels
- Side panels where a detail primitive is not the direct wrapper

It renders `operator-panel ops-console-section` with a consistent heading and optional actions area.

## Chosen Responsive Breakpoints

CSS-driven responsive behavior:

- Wide desktop: `OpsConsolePage` is centered and bounded with `max-width: 1480px`.
- Below `1180px`: `OpsContentGrid` collapses from main/detail columns to one column and side columns stop being sticky.
- Below `760px`: page gaps tighten, headers/actions/toolbars stack, toolbar fields become full width, and item card title rows collapse.

## Shared Components Between Capture Inbox and Reup Queue

Both pages now use:

- `OpsConsoleShell`
- `PageShell`
- `OpsConsolePage`
- `OpsWorkflowContext`
- `OpsNextActionBanner`
- `OpsSummaryCards`
- `OpsFilterBar` backed by `OpsToolbar`
- `OpsToolbarGroup`
- `OpsContentGrid`
- `OpsMainColumn`
- `OpsSideColumn`
- `OpsSection`
- `OpsItemCard`
- `OpsDetailPanel`
- `OpsBatchActionBar`
- `OpsStatePanel` / `OpsEmptyState` where applicable

## Safety and Boundary Notes

- No API calls were changed.
- No backend files were changed.
- No route files were changed.
- Capture Inbox remains the staging workspace.
- Reup Queue remains the downstream processing workspace.
- The UI does not introduce raw secrets, cookies, tokens, or private local paths.
- Technical diagnostics remain behind detail panels/disclosures.
- Publishing automation remains explicitly out of scope.

## Verification Strategy and Result

Source tests assert:

- Capture Inbox uses the shared layout primitives.
- Reup Queue uses the same shared layout primitives.
- Summary grid CSS remains responsive and uses auto-fit/minmax.
- Legacy layout wrappers are removed from the two target pages.
- Both routes still render the same page components.

Verification command run from repository root:

```cmd
npm run typecheck --workspace apps/web && npx tsx apps/web/src/test/ops-console-design-system.test.ts && npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/reup-queue.test.ts
```

Result: passed.
