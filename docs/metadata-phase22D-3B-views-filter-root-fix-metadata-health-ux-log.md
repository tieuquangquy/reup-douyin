# Phase 22D-3B Views Filter Root Fix + Metadata Health UX Log

## Summary
Implemented Phase 22D-3B for Capture Inbox only. The Advanced estimated views filter now uses a canonical frontend metadata adapter that can derive comparable values from normalized fields, aliases, numeric min/max pairs, exact view counts, and display ranges such as `9K-43K`, `9K to 43K`, and `10万-20万`. The old Data quality toggle row was replaced with an operator-facing Metadata health card section.

## Audit Findings
- Frontend item type already exposes normalized snake_case fields: `estimated_views_text_raw`, `estimated_views_display`, `estimated_views_min`, `estimated_views_max`, `estimated_views_mid`, and `estimated_views_parse_confidence`.
- The web API client returns Capture Inbox JSON as typed responses without mapping or dropping estimated-view fields.
- Backend schema hydrates normalized estimated views through `normalize_douyin_estimated_views` and serializes the normalized fields plus metadata quality flags.
- Backend normalization supports range delimiters including `-`, `–`, `—`, `~`, `至`, and `到`.
- The frontend root cause was the fallback comparable-view path: if numeric normalized fields were missing/null but only display text like `9K-43K` was available, the previous parser treated the range as invalid and returned `null`. With a min views filter active, `null` values fail the predicate, so every item could be hidden.

## Implementation
- Added `apps/web/src/lib/captureInboxFilterMetadata.ts` with:
  - `getDouyinItemMetadataForFilters(item)` canonical adapter.
  - `getComparableEstimatedViews(item)` comparable-view resolver.
  - range/scalar parsing for K/M/B, `万`, `亿`, commas, decimals, and supported range delimiters.
  - `metadataHealthMatches` and `metadataHealthCounts` helpers.
- Refactored `CaptureInboxPage.tsx` Advanced filters to use adapter-derived metadata instead of raw item fields.
- Added diagnostics for active views filtering:
  - `filter_adapter_used`
  - `views_source_field`
  - `views_source_value`
  - `views_comparable_value`
- Replaced old boolean Data quality draft fields with `metadataHealthFilters: MetadataHealthFilter[]`.
- Metadata health counts are computed from the loaded Studio-filtered set before Advanced filters are applied.
- Metadata health selections use OR behavior.

## Comparable Views Priority
1. `estimated_views_mid`
2. `estimatedViewsMid`
3. `metrics.estimated_views_mid`
4. `performance.estimated_views_mid`
5. average of `estimated_views_min` / `estimated_views_max`
6. average of `estimatedViewsMin` / `estimatedViewsMax`
7. `view_count`
8. `views`
9. `metrics.views`
10. parsed `estimated_views_display`
11. parsed `estimated_views_text_raw`
12. parsed `estimated_views`
13. parsed display fields from nested metadata/performance payloads

## Metadata Health UX
- New section name: `Metadata health`.
- Subtitle: `Find items that are ready, incomplete, or missing key Douyin fields.`
- Cards:
  - Complete — All key fields
  - Missing posted — No posted date
  - Missing thumbnail — No thumbnail
  - Missing duration — No duration
  - Missing views — No estimate
  - Missing metrics — likes/comments/shares
  - Actionable — Needs review/fix
- Active chips:
  - `Metadata: Complete`
  - `Missing posted`
  - `Missing thumbnail`
  - `Missing duration`
  - `Missing views`
  - `Missing metrics`
  - `Actionable only`

## Tests Added/Updated
- Added `apps/web/src/test/capture-inbox-filter-metadata.test.ts` for parser, adapter, diagnostics, metadata health counts, OR behavior, and a 59-item display-range regression fixture.
- Updated `apps/web/src/test/capture-inbox.test.ts` source-inspection assertions for the helper module and new Metadata health UI/CSS.

## Validation Status
Validated during implementation:
- `npx tsx apps/web/src/test/capture-inbox-filter-metadata.test.ts`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npx tsc --noEmit -p apps/web/tsconfig.typecheck.json` passed before final source-inspection patch; rerun in final validation.

## Manual Retest Notes
1. Open Capture Inbox with a session containing Douyin items that show estimated views as ranges.
2. Set Advanced filter `Min views` to `1000`.
3. Confirm items with displays like `9K-43K`, `24K-118K`, `432K`, and `86K-432K` remain visible.
4. Confirm dev console diagnostics show the adapter source field and comparable value.
5. Toggle Metadata health cards and confirm counts reflect the Studio-filtered loaded set before Advanced filters.
