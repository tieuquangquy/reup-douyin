# Phase 10F Fix Views Zero / Estimated Views Log

## Exact root cause of `Views 0`

The Tile Gallery first metric was still treating top-level `view_count = 0` as a real captured value even when its provenance indicated missing data, or no trusted provenance existed at all.

That suppressed the estimated-views fallback and caused cards to show misleading `Views 0`.

## Files/functions changed

- `apps/web/src/lib/captureInboxCanonical.ts`
  - `resolveKnownViewCountValue(...)`
  - `resolveEstimatedViews(...)`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `resolveViewMetricForCard(...)`
  - `compactMetricMetaForItem(...)`
- `apps/web/src/test/capture-inbox-canonical.test.ts`
- `apps/web/src/test/capture-inbox.test.ts`

## Real vs unknown view_count rules

Known real view count:

- non-zero `view_count` is accepted unless provenance explicitly says missing/fallback-only
- zero `view_count` is accepted only when trusted provenance exists
  - trusted `view_count_source`
  - or explicit raw/metadata stats prove zero

Unknown view count:

- `view_count = 0` with `view_count_source = missing` or `fallback_none`
- `view_count = 0` with no trusted provenance

## Estimated views formula

When real views are unknown and `like_count > 0`:

- low = `like_count * 20`
- base = `like_count * 33`
- high = `like_count * 100`

The card renders the compact low-high range.

## Tests run

- `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace @reup-douyin/web`

## Verification result

- Focused canonical resolver test passed
- Focused Capture Inbox frontend test passed
- Web typecheck passed
