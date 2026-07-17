# Phase 22D-3C - Estimated Views Source Of Truth Filter Fix Log

## Audit

- Tile Gallery renders `Est. Views` in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` through `resolveViewMetricForCard`.
- Before this phase, the card called `compactEstimatedViews(item)`, which used `resolveEstimatedViews(item)` from `apps/web/src/lib/captureInboxCanonical.ts`.
- `resolveEstimatedViews(item)` is computed on the frontend from `like_count` when there is no trusted real `view_count`.
- The existing estimate uses a like-rate range: low `like_count * 20`, base `like_count * 33`, high `like_count * 100`.
- Metadata health reported `Missing views = 59` because the Phase 22D-3B filter adapter did not include the Tile Gallery like-derived estimate as a valid estimated-view source.
- Advanced Min/Max views failed for the same reason: it filtered against adapter comparable values that were null for items whose cards still displayed `Est. Views`.

## Implementation

- Added `getEstimatedViewsForItem(item)` in `apps/web/src/lib/captureInboxFilterMetadata.ts` as the shared frontend estimated views source of truth.
- Added source/confidence categories for normalized fields, backend display, legacy display, derived-from-likes, view count fallback, and missing.
- Added priority order for normalized midpoint/min/max, camelCase aliases, nested metrics/performance aliases, backend display fields, legacy display fields, view count fallback, Tile Gallery like-derived estimate, then missing.
- Added `estimatedViewsRangeMatches(...)` with range-overlap semantics.
- Updated Advanced filtering to use range overlap instead of midpoint-only numeric matching.
- Updated Metadata health counts to treat shared estimated views as present, including derived-from-likes estimates.
- Updated Tile Gallery `Est. Views` display to use `getEstimatedViewsForItem(item)` while preserving real `Views` when a trusted captured view count exists.
- Updated `Highest views` sort to use the shared estimated views midpoint.
- Updated active chips and labels to say `Est. views`, `Min estimated views`, and `Max estimated views`.
- Added `advancedFilterDebug.estimatedViews` diagnostics and per-item `item_estimated_views_*` logs.

## Validation

- `npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts` passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` passed during implementation.

## Notes

- No Douyin extension crawler code was changed.
- No batch collection code was changed.
- No backend item save endpoint changes were required.
- The implementation does not fake real views; estimated values remain labeled as estimated views.
