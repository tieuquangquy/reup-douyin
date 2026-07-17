# Phase 21D-7 Final Compact UI Polish Resume

## Status

Completed.

## Summary

Phase 21D-7 finalized the compact Douyin Scanner popup UI before backend classification work. The popup now defaults collection settings to collapsed, uses clearer API wording, presents the pre-scan empty state as a lighter hint, and reduces footer action visual weight so the primary scanner action remains dominant.

## Files changed

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `docs/metadata-phase21D-7-final-compact-ui-polish-log.md`
- `docs/metadata-phase21D-7-final-compact-ui-polish-resume.md`

## Settings collapsed behavior

Collection settings are collapsed by default with `Collection settings`, `New + incomplete · Next 10 · Safe`, and an `Edit` button. The local toggle expands the `Mode`, `Batch`, and `Speed` selects and changes the control to `Done`. Initialization forces collapsed state and the expansion state is not persisted.

## API wording change

The idle user-facing API chip now reads `API not checked`. Ready and offline labels remain `API ready` and `API offline`.

## Empty state polish

The pre-scan empty state now reads `Scan a profile to build the collection plan.` and uses the lighter `scanner-hint` treatment instead of the heavier card styling.

## Footer polish

Footer hierarchy now keeps `Capture Inbox` secondary blue, `Advanced` neutral, and `Reset` as a lower-weight danger ghost. The primary action button remains the largest and visually dominant control.

## Validation

- `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` passed.

## Next phase recommendation

Recommended next phase: 21B backend data model + classification endpoint.
