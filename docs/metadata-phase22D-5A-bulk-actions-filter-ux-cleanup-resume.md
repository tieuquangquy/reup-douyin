# Phase 22D-5A - Bulk Actions Filter UX Cleanup Resume

## Completed

- Audited Capture Inbox Studio filters and Bulk toolbar controls.
- Removed duplicate `Select visible` from Studio filters.
- Kept `Select visible` only in the Bulk toolbar.
- Renamed Studio filter toggle group to `Quick filters`.
- Renamed Bulk toolbar `Clear` to `Clear selection`.
- Preserved Results summary above the Bulk toolbar.
- Preserved Smart Presets as filters outside the Bulk toolbar.
- Updated source-inspection tests for the filter/action separation.

## Files Changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-5A-bulk-actions-filter-ux-cleanup-log.md`
- `docs/metadata-phase22D-5A-bulk-actions-filter-ux-cleanup-resume.md`

## Behavior To Remember

- `Clear filters` resets filtering state only.
- `Clear selection` resets selected cards only.
- `Select visible` selects the current `visibleItems` list, which already includes Smart Preset and Advanced filter effects.
- Bulk action buttons remain disabled when no selected items are eligible.
- No backend bulk action behavior, crawler behavior, Smart Preset rules, item save/promote/re-check/delete semantics, or Reup Score formula were changed.

## Validation Status

- Passed: `npx tsx src/test/capture-inbox.test.ts` from `apps/web`.
- Passed: `npm --workspace @reup-douyin/web run typecheck`.
- Passed: `npm --workspace @reup-douyin/web run build`.
- Failed with known pre-existing Review Board path issue: `npm --workspace @reup-douyin/web run test` tries to read `apps/web/apps/web/src/components/review-board/ReviewBoardPage.tsx`.

## Suggested Next Steps

1. Fix the pre-existing Review Board test path duplication separately.
2. Re-run `npm --workspace @reup-douyin/web run test` after that path fix.
