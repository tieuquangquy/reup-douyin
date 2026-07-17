# Phase 10F Tile Gallery Estimated Views Log

## Exact files/functions changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `compactMetricMetaForItem(...)`
  - `resolveViewMetricForCard(...)`
  - `resolveTrustedViewCount(...)`
  - `compactEstimatedViews(...)`
- `apps/web/src/lib/captureInboxCanonical.ts`
  - `resolveEstimatedViews(...)`
  - `hasTrustedViewCount(...)`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/capture-inbox-canonical.test.ts`

## Why `Views 0` was wrong

The card metric still treated `view_count = 0` as a real captured value even when the provenance said the field was effectively missing (`view_count_source = missing` or `fallback_none`).

That blocked the estimated-views fallback and left the card showing `Views 0` instead of a truthful estimate derived from likes.

## Estimated views formula

When real `view_count` is missing and `like_count` exists:

- low = `like_count * 20`
- base = `like_count * 33`
- high = `like_count * 100`

Tile cards render the compact low-high range, for example:

- likes `269` -> `Est. Views 5.4K–26.9K`

## Tile Gallery rendering behavior

- real trusted `view_count` exists:
  - first metric cell renders `Views`
  - value renders the compact real count
- real `view_count` missing but `like_count` exists:
  - first metric cell renders `Est. Views`
  - value renders the compact estimated range
- both missing:
  - first metric cell renders `Views`
  - value renders `—`

Estimated views do not overwrite canonical `view_count`.

## Tests run

- `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace @reup-douyin/web`

## Verification result

- Focused canonical resolver test passed.
- Focused Capture Inbox frontend test passed.
- Web typecheck passed.
