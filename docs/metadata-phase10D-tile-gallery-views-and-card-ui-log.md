# Phase 10D Tile Gallery Views And Card UI Log

## Scope

- `apps/web` only
- Capture Inbox Tile Gallery card rendering
- view count visibility and compact media insight card layout

## Exact files/functions changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `MediaTile(...)`
  - `compactCardModelForItem(...)`
  - `compactQuickMetaForItem(...)`
  - `compactMetricMetaForItem(...)`
  - `compactMetricValueCard(...)`
  - `compactMetricDisplay(...)`
  - `compactPercentValueCard(...)`
- `apps/web/src/app/globals.css`
  - tile gallery media, chip, and metrics grid styles
- `apps/web/src/test/capture-inbox.test.ts`
  - updated source-inspection assertions for new card structure

## Views resolution and rendering

- Card `Views` now uses the existing canonical resolver chain through `resolveViewCount(item)`.
- Card rendering prefers numeric `item.view_count` when available and formats it with compact notation:
  - `1200 -> 1.2K`
  - `1200000 -> 1.2M`
- If the numeric field is unknown, the card falls back to resolved safe text.
- If the resolved value is still missing (`Not captured`), the card shows `—`.
- Known zero stays `0`.

## New card information hierarchy

1. Media block
   - fixed portrait media area
   - select pill and ready/metadata badges in overlay
2. Title
   - 2-line clamped title directly below media
3. Quick meta chips
   - `Duration`
   - `Posted`
   - `Preview`
4. Metrics grid
   - `Views`
   - `Likes`
   - `Comments`
   - `Shares`
   - `ER`
5. Actions
   - existing `Details`
   - `Re-evaluate intake`
   - `Promote`
   - `Delete`

## Thumbnail/media rendering improvement

- The tile now uses:
  - `object-fit: cover` on the foreground image
  - a subtle blurred thumbnail backdrop behind the image
- This removes the large dead bars caused by `contain` while preserving a polished portrait presentation.

## Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- `npm run typecheck --workspace @reup-douyin/web`

## Verification result

- Focused Capture Inbox tests passed.
- Web typecheck passed.
- `npm test --workspace @reup-douyin/web` is currently failing in an unrelated existing `review-board.test.ts` path-resolution issue (`apps/web/apps/web/...`), not from this change.
