# Live Metadata Gap Audit Resume (Part A only)

## Status

- Part A (audit-only): Completed
- Implementation changes for Part B/C/D/E: Not started

## Scope completed

Audited only requested metadata fields:

- `posted_at`, `posted_text`
- `duration_seconds`, `duration_text`
- `view_count`, `like_count`, `comment_count`, `share_count`

Audited stages:

1. Extension normalize/extract
2. Backend staging/persistence
3. API response exposure/hydration
4. Frontend consume/render

## Findings summary

1. Extension path is present and explicit for all target fields in [`buildCanonicalVideoPayload()`](../apps/extension-douyin-capture/src/extractor.ts:680).
2. Backend persist path exists for all target fields in [`_build_item()`](../apps/api/src/services/capture_inbox_service.py:688).
3. API response hydrator exposes target value fields in [`CapturedItemResponse`](../apps/api/src/schemas/capture_inbox.py:24) / [`hydrate_card_grid_metadata()`](../apps/api/src/schemas/capture_inbox.py:100).
4. Frontend compact metric strip uses direct numeric fields in [`compactMetricMetaForItem()`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1307), which can render `—` when numeric values are null even if text fallback exists.
5. Provenance enum mismatch remains for source labels (`dom_text` vs `dom_fallback`) in API schema literals for duration/metric source fields (value-field pipeline remains intact).

## Exact likely failure location for observed "metrics missing"

Primary likely stage:

- Frontend render path (compact metric row), not upstream extraction/persistence.

Secondary (provenance-only):

- API source enum whitelist for duration/metric source fields can drop `dom_text` labels.

## Narrow next split plan (no implementation yet)

### Part B — Extension normalization only (posted + duration)

- Confirm/normalize posted + duration source/value consistency at extension output boundary.
- No backend/api/frontend edits.

### Part C — Extension normalization only (views/likes/comments/shares)

- Confirm/normalize metric numeric + text fallback semantics at extension output boundary.
- No backend/api/frontend edits.

### Part D — Backend persist + API expose only

- Align source-enum compatibility across backend/API for duration/metric provenance values.
- Keep storage and API contracts stable; no frontend edits.

### Part E — Frontend consume/render verification only

- Use canonical metric resolvers where compact tile currently uses direct numbers.
- Verify metric display behavior for numeric-missing/text-present cases.
- No extension extraction changes.

## Audit artifacts

- Detailed log: [`docs/live-metadata-gap-audit-log.md`](./live-metadata-gap-audit-log.md)
- This resume: [`docs/live-metadata-gap-audit-resume.md`](./live-metadata-gap-audit-resume.md)
