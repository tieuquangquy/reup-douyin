# Advanced Filters Compact-Priority Refactor Log

## 1) Previous Panel Problems
- [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:634) still presents a tall, form-heavy body with four full groups.
- [`.capture-inbox-advanced-group`](apps/web/src/app/globals.css:3141) gives all sections equal visual weight, including low-frequency policy toggles.
- [`.capture-inbox-advanced-exclusions`](apps/web/src/app/globals.css:3181) occupies a full visible block, increasing vertical height and reducing scan speed.
- Main operator filters (time/performance/duration) compete visually with policy toggles.

## 2) Why Exclusions Move Out Of Main Visible Panel
- Exclusions are still needed semantically but are lower-frequency for day-to-day triage.
- Keeping Exclusions as a full first-class visible section makes the panel taller and less operator-friendly.
- Compact-first triage UX should keep high-frequency filters dominant and keep policy toggles secondary but accessible.

## 3) New Primary Filter Hierarchy (Implemented)
Main visible panel body now prioritizes:
1. `Time`
2. `Performance`
3. `Processing fit`

Implemented in [`AdvancedFilterPanel()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:655) with compact-priority group ordering and layout.

## 4) Height/Weight Reduction Strategy (Implemented)
- Reduced top-level panel density in [`.capture-inbox-advanced-panel`](apps/web/src/app/globals.css:3064) (`gap` and `padding` tightened).
- Tightened summary, group, pair, and field spacing across:
  - [`.capture-inbox-advanced-summary`](apps/web/src/app/globals.css:3104)
  - [`.capture-inbox-advanced-group`](apps/web/src/app/globals.css:3145)
  - [`.capture-inbox-advanced-pair`](apps/web/src/app/globals.css:3181)
- Applied compact two-column emphasis in [`.capture-inbox-advanced-workspace`](apps/web/src/app/globals.css:3135).

## 5) Active Filter Summary Strategy (Implemented)
- Kept summary compact and chip-oriented in [`.capture-inbox-advanced-summary`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:668).
- Exclusions remain represented via summary chips from [`advancedFilterSummaryItems()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:115), while no longer occupying a full primary body section.

## 6) Files Changed
- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/app/globals.css`](apps/web/src/app/globals.css)
- [`apps/web/src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- [`docs/advanced-filters-compact-priority-refactor-log.md`](docs/advanced-filters-compact-priority-refactor-log.md)
- [`docs/advanced-filters-compact-priority-refactor-resume.md`](docs/advanced-filters-compact-priority-refactor-resume.md)

## 7) Tests Run
- [`npx -w apps/web tsx src/test/capture-inbox.test.ts`](apps/web/src/test/capture-inbox.test.ts)
- [`npm run typecheck --workspace apps/web`](package.json:11)

## 8) Verification Result
- Focused frontend assertions passed, including compact-priority advanced panel structure, risk disclosure placement, and summary chip expectations.
- Web typecheck passed with no TypeScript errors.
