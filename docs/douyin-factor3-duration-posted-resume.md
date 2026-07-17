# Douyin Factor 3 — Duration + Posted Resume

Date: 2026-04-28
Status: Factor 3 implementation + focused verification complete

## Scope

Implement ONLY Factor 3 quality fixes for:
- `duration_seconds`
- `duration_text`
- `posted_at`
- `posted_text`

Out of scope:
- views/likes/comments/shares logic changes
- non-duration/non-posted UI redesign
- broad refactor

## What is already completed

1. End-to-end audit completed across:
   - extension extraction + canonical merge
   - backend capture persistence and response hydration
   - frontend canonical resolvers and rendering
2. Factor-3 audit log created:
   - [`docs/douyin-factor3-duration-posted-log.md`](./douyin-factor3-duration-posted-log.md)
3. This resume doc created.
4. Architecture doc prepared in parallel:
   - [`docs/douyin-factor3-duration-posted-architecture.md`](./douyin-factor3-duration-posted-architecture.md)

## Key findings recap

- Exact-id merge order already exists in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:661):
  1) network by `aweme_id`
  2) detail hydrate by `aweme_id`
  3) same-tile DOM fallback
- Risk remains in value quality guards, especially:
  - malformed duration values
  - malformed posted text (e.g. `13.0`)
  - default/fake midnight-like timestamp handling consistency
- Frontend currently renders any non-empty `posted_text` fallback string in [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:39), which can surface noisy strings if upstream sends them.

## Implementation outcome (completed)

1. Extension network normalization hardening for duration/posted — completed.
2. Extension detail-hydrate fallback hardening for duration/posted — completed.
3. Extension invalid-value guards + provenance tightening for duration/posted — completed.
4. Backend/API alignment — no code change required after validation.
5. Minimal frontend posted-text display guard — completed.
6. Focused tests — completed.
7. Verification commands + result capture — completed.
8. Final docs update with exact changes and evidence — completed.

## Change boundaries

Do not modify behavior for:
- view/like/comment/share extraction semantics
- thumbnail source policy (except no accidental coupling from Factor 3 edits)
- unrelated capture/inbox workflows

## Verification evidence

Passed:
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](../apps/extension-douyin-capture/package.json)
- [`npm --workspace @reup-douyin/web exec tsx src/test/capture-inbox-canonical.test.ts`](../apps/web/package.json)

Note:
- Full web suite command [`npm --workspace @reup-douyin/web run test`](../apps/web/package.json) fails due to unrelated existing path issue in [`review-board.test.ts`](../apps/web/src/test/review-board.test.ts:37).
