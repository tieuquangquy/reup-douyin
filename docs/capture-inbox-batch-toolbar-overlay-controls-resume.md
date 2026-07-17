# Capture Inbox Batch Toolbar + Overlay Controls Resume

## Task

Refine only Capture Inbox batch toolbar hierarchy and tile top overlay controls (`Select` + status chip), with docs-first execution and strict scope boundaries.

## Current status

Completed.

## Completed so far

- Reviewed `AGENTS.md` constraints.
- Audited current implementation in:
  - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `apps/web/src/app/globals.css`
  - `apps/web/src/test/capture-inbox.test.ts`
- Wrote docs-first log:
  - `docs/capture-inbox-batch-toolbar-overlay-controls-log.md`
- Implemented scoped UI refinements in:
  - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `apps/web/src/app/globals.css`
- Updated focused source assertions in:
  - `apps/web/src/test/capture-inbox.test.ts`

## Confirmed baseline

- Batch actions currently map to:
  - Promote: primary
  - Retry: secondary
  - Exclude: danger
  - Delete: danger
- Tile overlay currently contains:
  - Select checkbox pill (`capture-inbox-tile-checkbox`)
  - Right-side status badge
- Existing CSS hooks support scoped overlay refinements.

## Implementation summary

1. Batch bar hierarchy refined (visual only):
   - Kept `Promote selected` as `primary`.
   - Kept `Retry selected` as `secondary`.
   - Changed `Exclude selected` to `secondary`.
   - Kept `Delete selected` as the sole `danger` batch action.
   - Kept clear-selection behavior through existing `onClear` path.
2. Tile overlay Select control refined:
   - Added `capture-inbox-select-pill` class for stronger legibility and focus affordance.
   - Updated label to reflect state (`Selected` vs `Select`).
3. Tile overlay readiness/status chip refined:
   - Added `capture-inbox-ready-chip` and `is-ready` emphasis class for ready items.
4. Added subtle top-overlay contrast aid:
   - Introduced `capture-inbox-media-overlay-scrim` for thumbnail-agnostic readability.
5. Focused tests updated:
   - Batch tone expectation updated for `Exclude selected` secondary tone.
   - Added assertions for new overlay classes and selected-state label behavior.
   - Added CSS assertions for scrim/select pill/ready chip classes.

## Verification

Passed:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Output:

```text
capture inbox Media-first Triage Studio, canonical rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Scope lock

No backend, extraction, workflow, or data contract changes are allowed for this task.
