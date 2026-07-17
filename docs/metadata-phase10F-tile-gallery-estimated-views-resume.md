# Phase 10F Tile Gallery Estimated Views Resume

## Summary

Tile Gallery now renders estimated views directly in the first metric cell when real views are missing.

## Current behavior

- Trusted real view count:
  - `Views <real value>`
- Missing real views + numeric likes:
  - `Est. Views <low-high range>`
- Missing both:
  - `Views —`

## Important rule

Estimated views remain presentation-only frontend data.

- no backend change
- no canonical `view_count` overwrite
- no real ER recomputation from estimated views

## Tests

- `npx tsx apps/web/src/test/capture-inbox-canonical.test.ts`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm run typecheck --workspace @reup-douyin/web`
