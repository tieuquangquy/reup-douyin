# Phase 10E Tile Card Compact Pass Resume

## What changed

- Capture Inbox Tile Gallery cards are now shorter and denser.
- Main card information hierarchy is now:
  1. compact media block
  2. title
  3. quick meta row: `Duration`, `Posted`
  4. metrics row: `Views`, `Likes`, `Comments`, `Shares`
  5. action row

## Views logic

- numeric canonical `view_count` wins
- safe existing fallback text is used if numeric value is absent
- if still unknown, render `—`
- known zero remains `0`

## Main card removals

- `Preview` removed from quick meta on the main card
- `ER` removed from main card metrics

## Media update

- media block shortened with a fixed-height compact frame
- thumbnail still uses `cover` and blurred backdrop treatment

## Verification

- `npx tsx apps/web/src/test/capture-inbox.test.ts` passed
- `npm run typecheck --workspace @reup-douyin/web` passed
