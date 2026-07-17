# Phase 22D-3C - Estimated Views Source Of Truth Filter Fix Resume

## Status

Phase 22D-3C implementation is complete pending final full build validation.

## Files changed

- `apps/web/src/lib/captureInboxFilterMetadata.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox-filter-metadata.test.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-phase22D-3C-estimated-views-source-of-truth-filter-fix-log.md`
- `docs/metadata-phase22D-3C-estimated-views-source-of-truth-filter-fix-resume.md`

## Root cause

Tile Gallery already displayed `Est. Views` through `resolveEstimatedViews(item)`, which derives a range from `like_count` when no trusted real `view_count` exists. The Advanced filter adapter and Metadata health counts did not use that same derived source, so items could visibly show estimated views while the filter adapter treated them as missing.

## Current behavior

- `getEstimatedViewsForItem(item)` is the shared frontend source of truth.
- Range filters use overlap matching, so `9K-43K` matches a `10K-20K` filter.
- Missing estimated views are excluded only when an estimated-view filter is active.
- Metadata health `missing_views` uses the shared helper and no longer marks like-derived `Est. Views` as missing.
- Highest views sorting uses the shared estimated midpoint.
- UI labels and active chips now say estimated views.

## Validation already run

- `npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts` passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` passed once during implementation before final docs/test updates.

## Remaining validation

Run before final report:

```sh
npx tsc --noEmit -p apps/web/tsconfig.typecheck.json
npm --workspace @reup-douyin/web run build
```

## Manual retest

1. Open Capture Inbox with a session whose cards show `Est. Views`.
2. Enter Min estimated views `10000` and Max estimated views `20000`.
3. Apply filters.
4. Confirm chips show `Est. views 10K-20K`.
5. Confirm cards with overlapping ranges such as `9K-43K` remain visible.
6. Confirm Metadata health no longer reports like-derived `Est. Views` cards as missing views.
7. Sort by Highest views and confirm ordering follows estimated midpoint.
