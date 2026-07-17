# Advanced Filters Panel Refactor Log

## Scope

- Task: refactor only the Capture Inbox Advanced filters panel UI/UX in `apps/web`
- Non-goals:
  - no backend or filter logic changes
  - no filter semantics changes
  - no extraction or data pipeline changes
  - no broad Capture Inbox page redesign

## Previous Panel Problems

- The panel read like a long stacked admin form instead of a compact filter workspace.
- Apply and Reset actions were too far from the top interaction zone.
- The panel gave poor visibility into currently active filters.
- Vertical spacing and grouping made the panel heavier than necessary.
- Exclusions looked like generic checkbox controls instead of intentional operator toggles.

## New Layout Strategy

- Move the main action row to the header so Apply, Reset, and Collapse are reachable immediately.
- Add a compact active-filter summary row under the header.
- Rebuild the body into four clearer grouped sections:
  - Time
  - Performance
  - Processing fit
  - Exclusions
- Reduce visual height with tighter spacing and more balanced grid layout.

## Top Action Row Changes

- Moved `Apply`, `Reset`, and `Collapse`/`Expand` into the panel header.
- Kept the action cluster in the top interaction zone so the operator no longer needs to travel to the bottom of the panel.

## Filter Summary Design

- Added a compact summary row directly under the header.
- When no filters are active, the panel shows `No filters applied`.
- When filters are active, the panel renders compact human-readable chips such as view ranges, engagement thresholds, text-density constraints, and exclusions.

## Grouping/Layout Redesign

- Rebuilt the body into four groups:
  - Time
  - Performance
  - Processing fit
  - Exclusions
- Replaced the long vertical form flow with a more balanced workspace grid.
- Paired min/max inputs visually so ranges scan as one concept.
- Reduced panel bulk with tighter spacing and smaller section shells.

## Exclusions Redesign

- Replaced generic checkbox-chip treatment with compact toggle rows.
- Added short helper copy so each exclusion reads like a meaningful switch instead of a random form field.
- Active exclusions now have clearer visual emphasis.

## Files Changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/advanced-filters-panel-refactor-log.md`
- `docs/advanced-filters-panel-refactor-resume.md`

## Tests Run

- `npm --workspace @reup-douyin/web run typecheck`
- `npx tsx src/test/capture-inbox.test.ts`
- `npx tsx src/test/capture-inbox-canonical.test.ts`

## Verification Result

- Passed.
- Advanced filters now read as a compact filtering workspace instead of a long admin form.
- Top actions are reachable immediately.
- Active filter state is visible through the summary row.
- Collapse/expand behavior remains intact.
- No backend or filter semantics changed.
