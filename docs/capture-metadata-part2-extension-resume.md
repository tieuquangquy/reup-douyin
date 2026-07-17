# Capture Metadata Part 2 Extension Resume

Date: 2026-04-29
Status: Completed

## Scope lock
- Only extension normalization changes (`apps/extension-douyin-capture`) plus extension-focused docs/tests.
- No backend persistence changes.
- No API schema changes.
- No frontend Tile Gallery wiring.

## Part 1 contract alignment
- Time/performance/duration fields are canonicalized with exact-id priority.
- Processing-fit semantic flags are not reliably available at extension stage and must remain explicitly missing/null in Part 2.

## Implementation summary
- Added extension-only canonical provenance fields to [`VideoPayload`](apps/extension-douyin-capture/src/types.ts:79):
  - `duration_source`
  - `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`
  - `engagement_rate_source`
- Preserved source-priority merge behavior in [`buildCanonicalVideoPayload(...)`](apps/extension-douyin-capture/src/extractor.ts:665) and made provenance explicit without changing exact-id safety rules.
- Kept unsupported processing-fit semantic fields explicitly missing as nullable `null` outputs in extension payload:
  - `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`
- Mirrored the same contract in direct fallback path [`buildCanonicalVideoPayload(...)`](apps/extension-douyin-capture/src/popupTransport.ts:384).
- Extended focused tests in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:160) to assert:
  - canonical source-priority still intact
  - provenance fields are emitted
  - unsupported processing-fit semantic fields stay explicit null

## Verification
- [`npm run test`](apps/extension-douyin-capture/package.json:8): passed
- [`npm run typecheck`](apps/extension-douyin-capture/package.json:7): passed

## Scope confirmation
- Only extension code/docs/tests changed.
- No backend persistence/API/frontend changes were introduced.
