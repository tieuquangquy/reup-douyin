# Live Posted/Duration Extension Fix Resume (Part B only)

## Status

- Part B scope initialized
- Docs-first step completed
- Extension implementation completed for posted + duration normalization
- Extension verification tests passed

## Scope lock

Only fields in this task:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`

Only extension path may be changed:

- [`apps/extension-douyin-capture`](../apps/extension-douyin-capture)

Explicit non-goals:

- no views/likes/comments/shares changes
- no backend/API changes
- no frontend UI changes

## Source of truth

Part A artifacts used:

- [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md)
- [`docs/live-metadata-gap-audit-resume.md`](./live-metadata-gap-audit-resume.md)

## Next execution steps

## Completed implementation

1. Updated [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:680) to set [`posted_text`](../apps/extension-douyin-capture/src/types.ts:103) from canonical posted priority (`networkPostedAt` → `detailPostedAt` → DOM posted text) while keeping [`posted_at`](../apps/extension-douyin-capture/src/extractor.ts:776) on the same trusted priority.
2. Updated posted source selection in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:720) to require parsed DOM posted timestamp (`domPostedAt`) instead of raw DOM text.
3. Hardened duration parsing in [`extractDuration()`](../apps/extension-douyin-capture/src/extractor.ts:646) and direct-fallback parity path [`extractDuration()`](../apps/extension-douyin-capture/src/popupTransport.ts:897) to reject invalid minute/second ranges.
4. Hardened [`validDurationText()`](../apps/extension-douyin-capture/src/extractor.ts:999) to accept only trusted `mm:ss`/`hh:mm:ss` values with proper segment bounds.
5. Updated extension assertions in [`extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts:152) for canonical posted behavior and posted source guard.

## Verification

Executed [`npm run extension:test`](../package.json:24) from workspace root.

Result:

- `extension extractor tests passed`
- `extension identity / aweme_id mapping tests passed`
- `popup action hardening tests passed`
- `extension direct execution transport tests passed`
- extension build + dist resolution tests passed

## Scope confirmation

- No backend/API files changed.
- No frontend files changed.
- No engagement metric logic changed.
- Part B remained extension-only and posted/duration-only.
