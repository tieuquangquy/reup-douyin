# Live Metadata Part E Frontend Resume (Part E only)

## Status

- Part E scope initialized
- Audit completed for frontend consumption/render/filter wiring
- Docs-first step completed

## Scope lock

Only target fields in this task:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Allowed change area:

- [`apps/web`](../apps/web)
- tiny shared frontend type alignment only if strictly required
- focused frontend docs/tests for this wiring

Explicit non-goals:

- no extension changes
- no backend changes
- no broad UI redesign
- no unrelated metadata expansion

## Audit outcome snapshot

1. Field presence in frontend type: available.
2. Card compact rendering: already uses shared duration/posted + metric helpers; refine/verify behavior for target fields.
3. Inspector details: add clearer richer-value surface for target fields.
4. Advanced filters: controls + payload mapping already exist; validate target-field mapping and apply/reset behavior via focused tests.

## Next execution steps

1. wire/refine compact on-card display for posted/duration/counts
2. wire/refine inspector richer target-value display
3. confirm/adjust advanced filter mapping for target fields only
4. add/update focused frontend tests
5. run verification
6. update Part E docs with changed files and results

## Completed work

1. Compact card display wiring (posted/duration/counts)
   - Compact quick metadata remains canonical and compact (`Duration`, `Posted`, `Preview`).
   - Compact metric strip now reads canonical resolver outputs for:
     - `Views`
     - `Likes`
     - `Comments`
     - `Shares`

2. Inspector rich wiring
   - Added explicit **Live capture fields** section in right inspector.
   - Section renders: duration, posted, views, likes, comments, shares.

3. Advanced filter wiring verification
   - Existing `buildAdvancedFilterPayload(...)` mapping was preserved and verified for target fields.
   - Apply/reset flow remains backend-driven (`queryCaptureInboxItems` payload + query state reset).

4. Focused tests and type safety
   - Added share resolver/type assertions to capture inbox source test.
   - Added canonical fixture alignment for `share_count_text`.

5. Verification run
   - `npm --workspace @reup-douyin/web run typecheck` ✅
   - `npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox.test.ts` ✅
   - `npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox-canonical.test.ts` ✅

## Final changed files (Part E)

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/lib/captureInboxCanonical.ts`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/capture-inbox-canonical.test.ts`
- `docs/live-metadata-partE-frontend-log.md`
- `docs/live-metadata-partE-frontend-resume.md`
