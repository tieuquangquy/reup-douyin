# Review Board + Reup Queue UX Sync Log

## Scope

Normalize the operator UX/UI for Review Board and Reup Queue so both pages align with the current Capture Inbox direction without changing business semantics.

## Non-goals

- No backend workflow or API semantics changes.
- No new queue, crawler, processing, publishing, scoring, or filtering features.
- No redesign of unrelated pages.
- No alternate layout system beyond the current Ops Console primitives and Capture Inbox-inspired workflow anatomy.

## Audit summary

### Capture Inbox reference

Capture Inbox now uses a compact workflow anatomy:

1. compact page header and actions
2. compact context/status strips
3. clean filter toolbar
4. media-aware workspace
5. explicit active item state separate from checkbox selection
6. right-side sticky inspector on desktop
7. selected-item batch action bar
8. shared loading/error/empty panels

### Review Board current state

Review Board already uses Ops Console shell primitives, but still has mixed legacy page rhythm:

- workflow context and next-action banner are visually heavy compared with Capture Inbox
- summary uses larger cards instead of a compact status strip
- active detail state is object-based and falls back to the first visible candidate
- candidate selection and detail focus need clearer separation
- row action hierarchy exposes multiple primary actions
- thumbnail preview uses inline styles and should become reusable page CSS

### Reup Queue current state

Reup Queue also uses Ops Console shell primitives, but differs from the Capture Inbox direction:

- workflow context, next-action banner, and summary cards create a competing top layout
- focused item falls back to hidden/all items or the first visible item
- checkbox selection currently changes focused detail item
- bucket-heavy workspace is useful but visually different from Review Board and Capture Inbox
- row action hierarchy makes details primary instead of the next workflow transition
- batch actions mark most non-danger actions as primary
- detail panel sections need clearer lifecycle/media/export/publish grouping

## Planned implementation

1. Create docs-first architecture, resume, user guide, and log files.
2. Refactor Review Board to compact status strip, clean toolbar, media-aware list, explicit right inspector, and normalized action hierarchy.
3. Refactor Reup Queue to compact status strip, clean toolbar, media-aware workspace, explicit right inspector, decoupled selection/focus, and normalized batch actions.
4. Update focused source assertion tests.
5. Run Review Board test, Reup Queue test, and web typecheck.

## Progress

- Read AGENTS.md.
- Audited Capture Inbox reference behavior and CSS.
- Audited Review Board component, state, filters, cards, inspector, actions, and tests.
- Audited Reup Queue component, state, filters, buckets, inspector, actions, batch bar, and tests.
- Audited shared Ops Console primitives and relevant global CSS.
- Created docs-first log, resume, architecture, and user guide files.
- Normalized Review Board around compact status strip, clean filters, media-aware candidate cards, explicit right inspector state, and selected-item batch actions.
- Normalized Reup Queue around compact status strip, clean filters, media-aware queue cards, explicit right inspector state, decoupled selection/focus, and selected-item batch actions.
- Added shared CSS for workflow media previews and reusable workflow right inspectors.
- Updated Review Board and Reup Queue source assertion tests for the new compact workflow direction.

## Verification

- `npx tsx apps/web/src/test/review-board.test.ts` passed.
- `npx tsx apps/web/src/test/reup-queue.test.ts` passed.
- `npm run typecheck --workspace apps/web` passed.
