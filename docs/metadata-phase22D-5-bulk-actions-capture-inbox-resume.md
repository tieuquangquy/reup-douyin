# Phase 22D-5 Bulk Actions Capture Inbox Resume

## Completed
- Audited frontend card actions, action endpoint wiring, item identifiers, promotion eligibility, and delete semantics.
- Reused existing batch-capable backend session action endpoint; no backend code changes were required.
- Implemented visible-item scoped bulk selection and clear-on-scope-change behavior.
- Added bulk eligibility helper and compact result summaries.
- Added bulk toolbar with Select visible, Clear, Promote, Re-check, and Delete.
- Added custom bulk confirmation dialog, including destructive delete warning and Escape close support.
- Updated source-inspection tests for Phase 22D-5 expectations.

## Important Semantics
- Selection is scoped to currently visible items only.
- Select visible selects only IDs in the current filtered/preset/sorted gallery.
- Bulk Promote sends only READY/ENRICHED selected items.
- Bulk Re-check sends selected non-promoted items to `re_evaluate_intake`.
- Bulk Delete sends selected non-promoted items to `delete_items`.
- Delete hard-deletes staged captured-item rows on the existing backend and skips promoted items.

## Validation
- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- `npm --workspace @reup-douyin/web run test` still fails before Phase 22D-5 tests on an existing Windows path duplication issue: `apps\web\apps\web\src\components\review-board\ReviewBoardPage.tsx`.
