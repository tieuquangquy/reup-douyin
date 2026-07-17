# Capture Inbox Batch Toolbar + Overlay Controls Log

## Scope

Refine only two UI zones in Capture Inbox:

1. Batch actions toolbar
2. Per-tile top overlay controls (`Select` + readiness/status chip)

This change is visual hierarchy, readability, and accessibility polish only.

## Guardrails

- No data-flow changes.
- No backend/API changes.
- No action semantics changes (`promote`, `retry`, `exclude`, `delete`, `clear`).
- No gallery layout restructuring outside the two scoped zones.
- No extraction/extension/pipeline changes.

## Relevant files audited

- `AGENTS.md`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-action-hierarchy-fix-log.md`
- `docs/douyin-capture-inbox-action-hierarchy-fix-resume.md`

## Audit findings (before refinement)

### Batch action toolbar

In `BatchActionBar`, current action order/tone is:

- `Promote selected` → `primary`
- `Retry selected` → `secondary`
- `Exclude selected` → `danger`
- `Delete selected` → `danger`
- `Clear` is provided via `onClear`

Current behavior is semantically correct, but visual hierarchy can be improved for density and scanning:

- Exclude is currently destructive (`danger`) alongside delete.
- Clear affordance hierarchy can be made subtler versus operational actions.
- Selection helper copy is present but minimal.

### Tile overlay controls

Current top overlay in `MediaTile`:

- Left: white `Select` checkbox pill (`capture-inbox-tile-checkbox`)
- Right: status badge using global `status-badge` + tone class

Issues observed:

- Overlay controls can lose contrast over bright/complex thumbnails.
- Checkbox pill and status chip read as similar emphasis despite different intent.
- Focus-visible/readability for quick keyboard scan can be improved.

### CSS hooks already available

- `.capture-inbox-media-overlay`
- `.capture-inbox-tile-checkbox`
- `.capture-inbox-media-frame`
- `.ops-console-batch-action-bar`

These allow scoped refinements without broad page redesign.

### Tests likely impacted

`apps/web/src/test/capture-inbox.test.ts` currently asserts prior action-tone source snippets including:

- `Exclude selected` danger mapping in batch actions
- Existing overlay class names/markup presence

If toolbar hierarchy shifts (`Exclude` to non-danger) and overlay markup/classes are refined, test source assertions must be updated accordingly.

## Planned implementation (strict order)

1. Keep API/action semantics unchanged.
2. Refine `BatchActionBar` visual hierarchy only:
   - Keep `Promote selected` as primary.
   - Keep `Retry selected` as secondary.
   - Move `Exclude selected` to secondary hierarchy.
   - Keep `Delete selected` as sole destructive action.
   - Keep clear-selection control as tertiary/subtle.
3. Refine tile overlay controls:
   - Upgrade `Select` checkbox pill readability/contrast.
   - Upgrade readiness/status chip prominence and legibility.
4. Add a very subtle top overlay contrast aid only if needed for readability.
5. Update focused source tests for revised hierarchy/markup.
6. Run Capture Inbox test file and web typecheck.

## Non-goals

- No changes to contextual item footer actions.
- No changes to right inspector information architecture.
- No changes to filter/session ribbons/workspace split.
- No API schema/service changes.
