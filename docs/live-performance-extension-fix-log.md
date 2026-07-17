# Live Performance Count Extension Fix Log (Part C only)

## Task

Part C only: fix live metadata extraction/normalization for performance count fields in extension path.

In scope fields only:

- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Out of scope:

- `posted_at`, `posted_text`
- `duration_seconds`, `duration_text`
- backend persistence/API
- frontend UI

## Baseline from Part A

Using [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md), extension already has canonical metric fallback in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:680), but live behavior still reports missing count values in UI.

Working hypothesis for Part C:

- count fields may be dropped due to overly permissive extraction mixing unrelated numeric fragments in DOM text
- count fields may also be missing in live because DOM fallback is accepted when not confidently tied to labeled metrics
- strict safe parsing and provenance must be preserved while keeping network/detail exact-id priority

## Required source priority

For each count field:

1. exact network JSON by `aweme_id`
2. exact detail hydrate by `aweme_id`
3. item-local DOM fallback only when safe
4. otherwise missing

## Planned changes (before implementation)

Target files (extension-only):

- [`apps/extension-douyin-capture/src/extractor.ts`](../apps/extension-douyin-capture/src/extractor.ts)
- [`apps/extension-douyin-capture/src/popupTransport.ts`](../apps/extension-douyin-capture/src/popupTransport.ts) (direct execution parity if required)
- extension tests focused on count fields only

No backend/frontend changes in Part C.

## Verification plan

Focused tests to add/update:

1. exact network counts map to canonical count fields
2. detail counts fill only when network count is missing
3. compact/raw count text parsed only when safe
4. invalid numeric fragments rejected
5. no cross-item leakage
6. popupTransport parity retained

## Implementation results

Changed files:

- [`apps/extension-douyin-capture/src/extractor.ts`](../apps/extension-douyin-capture/src/extractor.ts)
- [`apps/extension-douyin-capture/src/popupTransport.ts`](../apps/extension-douyin-capture/src/popupTransport.ts)
- [`apps/extension-douyin-capture/src/extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts)

Function-level changes:

1. [`extractMetrics()`](../apps/extension-douyin-capture/src/extractor.ts:590)
   - Removed unlabeled compact fallback from canonical `view_count` / `like_count` / `comment_count`.
   - Canonical values now come only from labeled metric patterns (`播放/观看/浏览`, `赞/获赞/喜欢`, `评论`, `分享`) to prevent unrelated numeric fragments from being normalized as counts.

2. [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:688)
   - Kept canonical count priority unchanged and explicit per field:
     - exact network by `aweme_id`
     - exact detail hydrate by `aweme_id`
     - item-local DOM fallback (now stricter because DOM parser is labeled-only)
     - otherwise missing
   - Preserved provenance fields: `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`.

3. [`extractMetrics()`](../apps/extension-douyin-capture/src/popupTransport.ts:819)
   - Applied the same labeled-only parsing behavior in direct execute-script fallback path for parity.

4. [`extractor.test.ts`](../apps/extension-douyin-capture/src/extractor.test.ts:193)
   - Added guard assertion to ensure canonical metric extraction does not use `?? compact.*` fallbacks for view/like/comment fields.

## Verification results

Command run:

- [`npm run extension:test`](../package.json:24)

Observed result: pass (exit code 0)

- `extension extractor tests passed`
- `extension identity / aweme_id mapping tests passed`
- `popup action hardening tests passed`
- `extension direct execution transport tests passed`
- extension build + dist module resolution tests passed
