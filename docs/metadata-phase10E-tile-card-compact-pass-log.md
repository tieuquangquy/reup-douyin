# Phase 10E Tile Card Compact Pass Log

## Exact files/functions changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
  - `MediaTile(...)`
  - `compactQuickMetaForItem(...)`
  - `compactMetricMetaForItem(...)`
  - `compactMetricValueCard(...)`
  - `compactMetricDisplay(...)`
- `apps/web/src/app/globals.css`
  - compact media height
  - tile quick meta spacing
  - tile metrics grid sizing
- `apps/web/src/test/capture-inbox.test.ts`

## Views behavior

- Main card `Views` now prefers canonical numeric `view_count`.
- Numeric values are formatted compactly:
  - `278 -> 278`
  - `1200 -> 1.2K`
  - `1200000 -> 1.2M`
- If numeric `view_count` is missing, the card uses the existing safe resolved fallback text.
- If the resolved value is still unknown, the card shows `—`.
- Unknown views are no longer coerced into `0`.

## Removed from main card

- `Preview` quick chip removed from the primary Tile Gallery card
- `ER` removed from the primary metrics row/grid

These fields remain available elsewhere where already supported, including the right-side details inspector.

## Media height / thumbnail presentation

- The main card media block no longer uses the tall portrait aspect-ratio presentation.
- It now uses a shorter compact fixed-height media frame:
  - `height: clamp(220px, 26vw, 290px)`
- Thumbnail rendering still uses:
  - `object-fit: cover`
  - subtle blurred backdrop treatment
- This keeps thumbnails visually full while making cards materially shorter and easier to scan.

## Tests run

- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace @reup-douyin/web`

## Verification result

- Focused Capture Inbox frontend test passed.
- Web typecheck passed.
