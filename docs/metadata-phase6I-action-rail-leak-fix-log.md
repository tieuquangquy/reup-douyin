# Phase 6I-C Action Rail Leak Fix Log

## Root cause

- The previous action-rail candidate filter was still too broad.
- It could accept background profile grid cards when those cards were visible behind the modal and happened to fall near the right-side viewport band.
- Once accepted, the vertical fallback could reuse that background card text as modal `comment_count`, `favorite_count`, or `share_count`.
- The live symptom was a probe block with text beginning like:
  - `872 ... 豆瓣9.7 ...`
  which is clearly profile-card/caption text, not a compact modal rail count.

## Scope

- `apps/extension-douyin-capture`
- focused tests/docs only

## Intended fix

1. Hard reject profile grid/card candidates.
2. Only build action blocks from compact numeric count nodes in the right-side modal rail.
3. Pair each compact count node with the nearest icon/button above it in the same x band.
4. Sort accepted blocks by y coordinate and map:
   - first = like
   - second = comment
   - third = favorite
   - fourth = share
5. Expose accepted/rejected candidate diagnostics in probe output.
