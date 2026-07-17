# Live Performance Count Extension Fix Resume (Part C only)

## Status

- Part C scope initialized
- Docs-first step completed
- Extension implementation completed for views/likes/comments/shares normalization
- Extension verification tests passed

## Scope lock

Only fields in this task:

- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Only extension path may be changed:

- [`apps/extension-douyin-capture`](../apps/extension-douyin-capture)

Explicit non-goals:

- no posted/duration changes
- no backend/API changes
- no frontend UI changes

## Source of truth

Part A artifacts used:

- [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md)
- [`docs/live-metadata-gap-audit-resume.md`](./live-metadata-gap-audit-resume.md)

## Completed implementation

1. Updated [`extractMetrics()`](../apps/extension-douyin-capture/src/extractor.ts:590) to use labeled-only metric parsing for `view_count`, `like_count`, `comment_count`, and `share_count` without unlabeled compact fallback.
2. Preserved canonical count priority in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:688): network by exact id -> detail by exact id -> item-local DOM fallback -> missing.
3. Applied the same labeled-only metric parsing in direct fallback parity path [`extractMetrics()`](../apps/extension-douyin-capture/src/popupTransport.ts:819).
4. Updated guard coverage in [`extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts:193) to ensure unlabeled compact numeric fragments are not used for canonical count fields.

## Verification

Executed [`npm run extension:test`](../package.json:24) from workspace root.

Result:

- `extension extractor tests passed`
- `extension identity / aweme_id mapping tests passed`
- `popup action hardening tests passed`
- `extension direct execution transport tests passed`
- extension build + dist resolution tests passed

## Scope confirmation

- No posted/duration logic changed in this Part C task.
- No backend/API files changed.
- No frontend files changed.
