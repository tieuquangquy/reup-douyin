# Capture Metadata Part 2 Extension Log

Date: 2026-04-29
Scope: Part 2 only — extension-side normalization.

## Part 1 contract mapping (before implementation)

Source-of-truth docs reviewed:
- `docs/capture-metadata-part1-audit-log.md`
- `docs/capture-metadata-canonical-contract.md`
- `docs/capture-metadata-part1-audit-resume.md`

### Field availability map

#### present_canonical (already available in extension merge path)
- Time: `posted_at`, `posted_text`
- Performance: `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`
- Processing fit: `duration_seconds`, `duration_text`

#### missing (no reliable extension producer yet)
- `has_speech`
- `text_density`
- `has_heavy_watermark`
- `processing_complexity`
- `copyright_risk`

### Extension functions that build normalized payload
- `apps/extension-douyin-capture/src/extractor.ts`
  - `buildCanonicalVideoPayload(...)`
- `apps/extension-douyin-capture/src/popupTransport.ts`
  - direct fallback `buildCanonicalVideoPayload(...)`

### Implementation plan for Part 2
1. Keep exact-id source priority for time/performance/duration unchanged.
2. Add explicit provenance fields for canonical time/performance/duration in normalized payload.
3. Add explicit nullable placeholders for unsupported processing-fit semantic fields to keep missing values honest.
4. Keep no-leak and no-invention behavior.
5. Update extension types and focused tests.

## Change log
- [done] type updates in extension payload contract
  - Added explicit provenance enums/types in [`types.ts`](apps/extension-douyin-capture/src/types.ts): [`DurationSource`](apps/extension-douyin-capture/src/types.ts:47), [`MetricSource`](apps/extension-douyin-capture/src/types.ts:48), [`EngagementRateSource`](apps/extension-douyin-capture/src/types.ts:49)
  - Extended [`VideoPayload`](apps/extension-douyin-capture/src/types.ts:79) with:
    - time/performance provenance: `duration_source`, `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`, `engagement_rate_source`
    - explicit unsupported processing-fit semantic placeholders: `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk` (all nullable)
- [done] extractor canonical payload updates
  - Updated [`buildCanonicalVideoPayload(...)`](apps/extension-douyin-capture/src/extractor.ts:665) to preserve existing exact-id canonical priority while emitting explicit provenance fields.
  - Added explicit null assignment for unsupported processing-fit semantic fields (no invented values).
- [done] popupTransport direct-path alignment updates
  - Updated direct fallback [`buildCanonicalVideoPayload(...)`](apps/extension-douyin-capture/src/popupTransport.ts:384) to mirror new provenance and explicit-null processing-fit semantics.
- [done] focused normalization tests
  - Updated assertions in [`extractor.test.ts`](apps/extension-douyin-capture/src/extractor.test.ts:160) for new canonical count pipeline variables and provenance/explicit-null output fields.
- [done] verification run
  - [`npm run test`](apps/extension-douyin-capture/package.json:8) passed.
  - [`npm run typecheck`](apps/extension-douyin-capture/package.json:7) passed.
