# Ops Console Design System Architecture

## Goal

Create a reusable, low-complexity Ops Console Design System for the local-first operator workflow:

Capture Inbox -> Review Board -> Reup Queue -> Export Package -> Publish Handoff.

The design system must make these surfaces visually and behaviorally consistent without moving domain behavior out of the pages or changing backend contracts.

## Non-goals

- No crawler implementation.
- No video processing implementation.
- No scoring/filtering algorithm changes.
- No database schema changes.
- No queue implementation changes.
- No auto-publish integration.
- No new UI dependency or component library.
- No SaaS-only assumptions.

## Design principles

1. One workflow, many domain surfaces.
   - All pages should share layout, status language, action hierarchy, state panels, detail vocabulary, and batch affordances.
   - Each page keeps its domain-specific actions and API calls.

2. Operator-first density.
   - Show the next useful action.
   - Keep critical counts visible.
   - Keep details available without overwhelming the main list.
   - Keep diagnostics accessible but not dominant.

3. Honest system boundaries.
   - Export Package and Publish Handoff are inspectable artifacts.
   - Publish Handoff does not call platform APIs or auto-publish.
   - Missing downstream artifacts should be labeled plainly as pending/not created.

4. SaaS-ready but local-first.
   - Avoid hardcoded local paths.
   - Avoid single-user assumptions in visible language where avoidable.
   - Keep presentation components independent of storage, queue, database, and worker details.

## Shared component model

`apps/web/src/components/ops-console/OpsShared.tsx` is the intended shared entry point.

### `OpsWorkflowContext`

Purpose: consistent top context panel for workflow position and loaded/visible/selected counts.

Expected props:

- `steps`: string[]
- `currentStep`: string
- `metrics`: array of label/value/detail rows

Usage:

- Capture Inbox: current session and selected item counts.
- Review Board: loaded candidates, visible candidates, selected candidates.
- Reup Queue: loaded items, visible items, selected items.
- Export Package: packages/items/handoffs.
- Publish Handoff: handoffs/platform/package context.

### `OpsNextActionBanner`

Purpose: consistent recommended next-action guidance.

Expected props:

- `tone`: `good | warn | danger | muted`
- `title`: string
- `description`: string
- optional actions.

Usage examples:

- Capture Inbox: fix incomplete captures or promote ready captures.
- Review Board: approve strong candidates or send approved candidates to Reup Queue.
- Reup Queue: resolve failures or create export/handoff artifacts.
- Export Package: inspect package or create Publish Handoff.
- Publish Handoff: inspect payload and proceed manually outside this app.

### `OpsSummaryCards`

Purpose: consistent clickable summary cards that can act as filters.

Expected behavior:

- Cards have label, value, description, tone, active state, and optional click handler.
- Active cards use the same visual treatment across pages.
- Cards should be usable for pages with no filters by omitting click handlers.

### `OpsFilterBar`

Purpose: consistent search/filter/sort layout.

Expected behavior:

- Uses the existing `.field` style semantics.
- Supports page-owned form controls through composition.
- Avoids forcing every page into the same data model.

### `OpsItemCard`

Purpose: consistent item row/card shell.

Expected behavior:

- Supports optional selection checkbox.
- Supports title, eyebrow, metadata, status badge, metrics, and actions.
- Supports focused/selected states.
- Allows custom preview content for Review Board thumbnails.
- Allows link-style cards for Export Package and Publish Handoff index pages.

### `OpsDetailPanel` and `OpsDetailSection`

Purpose: consistent right-side or inline detail inspection.

Common section vocabulary:

1. Overview
2. Source / References
3. Metadata
4. Workflow / Lifecycle
5. Outputs / Downstream artifacts
6. Actions
7. Diagnostics

Diagnostics should usually be collapsed unless the page is explicitly a diagnostics page.

### `OpsBatchActionBar`

Purpose: consistent sticky batch action surface.

Expected behavior:

- Appears only when relevant or when selected count is non-zero.
- Shows selected count.
- Uses primary/secondary/danger hierarchy.
- Does not hide safety constraints.
- Should work as sticky in document flow rather than a disconnected modal when possible.

### `OpsStatePanel`

Purpose: consistent loading, empty, and error states.

Expected variants:

- `loading`
- `empty`
- `error`
- `success` or `info` when needed.

## Status badge system

Visual tones remain:

- `good`
- `warn`
- `danger`
- `muted`

Semantic mapping should be centralized with helper functions so pages do not repeatedly reimplement status-to-tone logic.

Suggested semantic groups:

- Good: `READY`, `APPROVED`, `READY_TO_EXPORT`, `EXPORTED`, `HANDOFF_CREATED`, `COMPLETED`, `SUCCEEDED`, `ACTIVE`, `READY_FOR_REVIEW`.
- Warning: `PENDING`, `NEEDS_REVIEW`, `NEEDS_METADATA`, `NEEDS_MEDIA`, `PROCESSING`, `HELD`, `RETRYABLE`, `READY_TO_PROCESS`.
- Danger: `FAILED`, `FAILED_NEEDS_ATTENTION`, `REJECTED`, `BLOCKED`, `INVALID`, `DUPLICATE` when duplicate blocks promotion.
- Muted: `CANCELLED`, `SKIPPED`, `ARCHIVED`, unknown/missing status.

Pages may override tone when domain context demands it.

## Action hierarchy

- Primary: one main forward workflow action.
- Secondary: useful safe actions that do not advance the main workflow.
- Tertiary/link: inspect, open details, copy, navigate.
- Danger: reject, cancel, destructive state changes.

Shared components should support this hierarchy through class names and explicit props, but pages own action legality.

## Page application strategy

### Capture Inbox

- Keep existing behavior.
- Replace local duplicate layout pieces with shared primitives.
- Keep session list panel domain-specific.

### Review Board

- Wrap with `OpsConsoleShell` and `PageShell`.
- Replace old header/toolbar/grid/card/detail/selection patterns with shared primitives.
- Preserve candidate scoring, preview thumbnail, status mutations, and Reup Queue transition guard.

### Reup Queue

- Keep recent operator-first design.
- Replace local duplicate layout pieces with shared primitives.
- Preserve queue actions, batch actions, export package creation, publish handoff creation, and no-auto-publish messaging.

### Export Package

- Add workflow context, next action, summary cards, shared item card list, and shared detail sections.
- Preserve package inspection and create-handoff behavior.

### Publish Handoff

- Add workflow context, next action, summary cards, shared item card list, and shared detail sections.
- Preserve manual handoff / no platform API language.

## Implementation status

Implemented in `apps/web/src/components/ops-console/OpsShared.tsx` and applied to the requested operator workflow surfaces. The final shared primitive set includes:

- `OpsWorkflowContext`
- `OpsNextActionBanner`
- `OpsSummaryCards`
- `OpsFilterBar`
- `OpsItemCard`
- `OpsDetailPanel`
- `OpsDetailSection`
- `OpsBatchActionBar`
- `OpsStatePanel`
- `OpsMetadataList`
- `OpsActionRow`
- `statusTone`

`OpsDetailPanel` intentionally allows optional children so empty-selection states can use the same detail-panel shell without adding placeholder markup.

## CSS strategy

- Continue using `globals.css` and existing design tokens.
- Add `ops-console-*` classes for design-system-specific layouts.
- Reuse existing `operator-panel`, `operator-panel-heading`, `operator-quick-card`, `state-panel`, and `app-status-badge` styles where possible.
- Ensure responsive behavior at the existing breakpoints near 980px and 640px.

## Testing strategy

Tests should remain source-level where the repo already uses source assertions.

Expected assertions:

- Five surfaces import or use shared Ops Console primitives.
- Review Board uses `OpsConsoleShell` / `PageShell`.
- Shared next-action, summary, item, detail, batch, and state vocabulary exists.
- Publish Handoff safety copy remains explicit.
- Reup Queue export/handoff actions remain available.
- Route navigation tests pass if touched.

Implemented coverage:

- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/review-board.test.ts`
- `apps/web/src/test/reup-queue.test.ts`
- `apps/web/src/test/ops-console-design-system.test.ts`
- `apps/web/src/test/route-nav.test.ts`

Passed verification:

- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/review-board.test.ts && npx tsx apps/web/src/test/reup-queue.test.ts && npx tsx apps/web/src/test/ops-console-design-system.test.ts && npx tsx apps/web/src/test/route-nav.test.ts`
- `npx tsc --noEmit --project apps/web/tsconfig.typecheck.json`
