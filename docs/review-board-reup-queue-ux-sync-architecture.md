# Review Board + Reup Queue UX Sync Architecture

## Goal

Review Board and Reup Queue should feel like consecutive stages in the same local-first operator workflow family as Capture Inbox. The implementation should reuse existing Ops Console primitives and Capture Inbox-inspired compact patterns while preserving all existing business semantics.

## Shared UX language

Capture Inbox, Review Board, and Reup Queue share this operator grammar:

1. **Compact header**: concise page title, workflow-position subtitle, and a small set of high-value actions.
2. **Compact context/status strip**: status counts are shown as compact pills rather than large cards or banners.
3. **Clean filter toolbar**: search, sort, and state filters are grouped predictably.
4. **Media-aware workspace**: each list item exposes a thumbnail or consistent media placeholder plus compact metadata.
5. **Right-side sticky inspector**: desktop detail work happens in a sticky side panel with explicit open/close state.
6. **Clear action hierarchy**: one primary workflow action at most per item area; secondary inspection/navigation actions stay secondary.
7. **Consistent batch actions**: selection creates a sticky batch bar; checkbox selection does not secretly change active detail identity.
8. **Consistent state panels**: loading, errors, empty lists, and empty inspectors use shared state/empty/detail panels.

## Chosen page anatomy

Both Review Board and Reup Queue should render in this order:

1. `OpsConsoleShell`
2. `PageShell`
3. `OpsConsolePage`
4. compact status strip
5. filter toolbar
6. optional page notice/state panels
7. `OpsContentGrid`
   - `OpsMainColumn`: media-aware item workspace
   - `OpsSideColumn`: right-side sticky inspector
8. `OpsBatchActionBar` for selected work

The architecture intentionally keeps `OpsContentGrid`, `OpsMainColumn`, and `OpsSideColumn` so the pages remain within the existing Ops Console layout system. Capture Inbox uses a page-specific 70/30 workspace, but Review Board and Reup Queue can keep the shared bounded grid because it already provides sticky right-side behavior.

## Inspector model

Each page uses explicit active/open state:

- `activeCandidateId` / `reviewInspectorOpen` for Review Board
- `activeItemId` / `queueInspectorOpen` for Reup Queue

The active record is derived from the visible collection. If filters remove the active record, the inspector closes and active id resets. This prevents stale hidden details from remaining selected after filter changes.

Checkbox selection is independent from active inspector identity. Selecting or clearing rows must not change the inspector record. Opening details requires an explicit Details/Inspect action or media/title focus interaction.

Desktop uses sticky `OpsSideColumn`. Narrow screens inherit the shared single-column layout; the inspector remains in document flow rather than introducing another layout system.

## Action hierarchy rules

### Item cards

- Primary action: the most direct workflow transition for that item, if safe and eligible.
- Secondary actions: details/inspect, external links, and non-transition utilities.
- Danger actions: reject/cancel/block actions.
- Do not render multiple primary buttons in the same compact action row unless one is clearly page-level and one is item-level.

### Page header

- Keep refresh/navigation actions lightweight.
- Avoid putting batch-only actions in the header when they already exist in the selected-item batch bar.

### Inspector

- Inspector actions are explicit and contextual.
- Inspector may repeat primary workflow transitions for the active record because that is where detailed confirmation happens.

## Badge/status normalization rules

- Preserve raw backend enum values for API calls and diagnostics.
- User-facing labels use title/sentence case.
- Positive terminal or ready states use good tone.
- Work-in-progress or waiting states use warn tone.
- Failed/rejected/blocked states use danger tone.
- Cancelled/archived/completed-as-history states use muted tone when they are no longer actionable.
- Related stages use parallel wording:
  - `Approved`
  - `In review`
  - `Rejected`
  - `Ready to process`
  - `Waiting for media`
  - `Waiting for metadata`
  - `Ready to export`
  - `Export package created`
  - `Ready for publish handoff`
  - `Publish handoff created`

## Batch action rules

- Batch bars appear only when one or more items are selected.
- Batch bars state selected count and, when helpful, eligible count.
- One or two most common safe batch actions can use primary tone.
- Destructive actions use danger tone.
- Other lifecycle actions use secondary/default tone.
- Clearing selection is always available from the batch bar.

## Page-specific deviations

### Review Board

Review Board centers candidate judgement. It can show score and review evidence more prominently than Reup Queue. Its inspector sections are:

1. overview
2. source/references
3. score and review metadata
4. downstream state/actions
5. diagnostics/raw details

### Reup Queue

Reup Queue centers downstream operational readiness. It can retain lightweight buckets if the buckets explain lifecycle state without creating a competing layout. Its inspector sections are:

1. overview
2. queue lifecycle
3. source/review origin
4. media prep
5. export package
6. publish handoff
7. diagnostics/raw details

## Implemented state

Review Board implements the anatomy with `ReviewStatusStrip`, `ReviewFilterBar`, a media-aware `ReviewCandidateCard`, explicit `activeCandidateId` / `reviewInspectorOpen` state, and `ReviewRightInspector`.

Reup Queue implements the anatomy with `QueueStatusStrip`, `FilterSearchRow`, media-aware `QueueItemCard`, explicit `activeItemId` / `queueInspectorOpen` state, and `QueueRightInspector`.

Both pages derive active records from the visible collection and close the inspector when filtering removes the active record. Checkbox selection remains independent from active detail identity.

Shared CSS in `apps/web/src/app/globals.css` provides reusable `.workflow-right-inspector` and `.workflow-media-preview` styles while retaining existing Ops Console grid boundaries.

## Verification

- `npx tsx apps/web/src/test/review-board.test.ts` passed.
- `npx tsx apps/web/src/test/reup-queue.test.ts` passed.
- `npm run typecheck --workspace apps/web` passed.

## Intentional constraints

- No backend semantics change.
- No new dependencies.
- No hidden publishing automation.
- No long-running processing in UI code.
- No future SaaS-only assumptions added to Phase 1 local-first UI.
