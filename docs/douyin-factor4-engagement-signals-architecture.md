# Douyin Factor 4 — Engagement Signals Architecture

## Scope
This design applies **only** to Factor 4 engagement signals in the capture pipeline:
- `view_count`
- `like_count`
- `comment_count`
- `share_count`
- derived `engagement_rate`

Out of scope:
- broad duration/posted rewrites
- UI redesign
- non-engagement refactors

## Canonical Source Priority (Strict)
For each discovered card/video, by exact `aweme_id`:
1. exact network JSON metadata
2. exact detail-hydrate metadata
3. item-local DOM fallback parse

No cross-item borrowing is allowed. If a value is unavailable at higher priority, only then fallback to lower priority.

## Data Flow

### 1) Extension network ingest
- File: `apps/extension-douyin-capture/src/networkCache.ts`
- Responsibility:
  - normalize network aweme records to numeric-safe engagement fields
  - keep raw text when useful for diagnostics
  - mark low-confidence/invalid values as null

### 2) Extension canonical merge
- File: `apps/extension-douyin-capture/src/extractor.ts`
- Responsibility:
  - resolve exact-id metadata using canonical map + detail hydrate
  - merge engagement fields with strict source order
  - apply fallback parsing from local card text only when higher sources missing
  - reject ambiguous compact fragments

### 3) Popup direct execution parity
- File: `apps/extension-douyin-capture/src/popupTransport.ts`
- Responsibility:
  - keep metric parse behavior consistent with extractor path to avoid divergence

### 4) API ingest + persistence
- File: `apps/api/src/services/capture_inbox_service.py`
- Responsibility:
  - preserve canonical engagement values in staged item metadata
  - keep transformations minimal and schema-safe

### 5) API schemas
- Files:
  - `apps/api/src/schemas/douyin_extension.py`
  - `apps/api/src/schemas/capture_inbox.py`
- Responsibility:
  - accept/preserve extension engagement fields
  - expose canonical `share_count` and `engagement_rate` in response model with minimal widening

### 6) Web type + render alignment
- File: `apps/web/src/types/capture-inbox.ts`
- Responsibility:
  - typed exposure for canonical engagement fields
  - no broad card redesign; minimal display alignment only

## Normalization Rules

### Numeric counts
- Accept only non-negative finite integers.
- Treat invalid/negative/NaN/infinite as null.
- For compact strings (`k`, `m`, `w`, `万`, `亿`), parse only when unambiguous and high confidence.

### Engagement rate
- Derive only when:
  - `view_count` is trustworthy and `> 0`
  - numerator parts (`like_count`, `comment_count`, `share_count`) are trustworthy numeric values (missing treated as 0 only if source trustworthy/null-by-absence, not parse-failure noise)
- Formula:
  - `(like_count + comment_count + share_count) / view_count`
- If prerequisites fail, set `engagement_rate = null`.

## Provenance and Rejection Markers
- Keep lightweight provenance markers in metadata (network/detail/dom) for debugging.
- Add rejection marker/code for invalid compact parse or suspicious tokens.
- Never promote rejected values into canonical fields.

## Testing Strategy (Focused)

### Extension tests
- Update/add tests in:
  - `apps/extension-douyin-capture/src/extractor.test.ts`
  - related metric parsing tests if needed
- Validate:
  - exact-id precedence
  - no cross-item leakage
  - compact parse guards
  - invalid-value suppression

### API tests
- Add/adjust focused tests in `apps/api/tests` for capture inbox schema/serialization path.
- Validate `share_count` + `engagement_rate` preservation/exposure.

### Web tests
- Add/adjust focused type/canonical tests for rendered/consumed engagement fields only.

## Verification Gates
1. Extension targeted tests pass.
2. API targeted tests pass.
3. Web targeted tests pass.
4. No unrelated suite changes required for this scoped factor.

## Rollout Notes
- Keep implementation incremental and patch-sized.
- Preserve backward compatibility where possible by keeping optional fields nullable.
- Document any contract additions explicitly in Factor-4 log/resume after tests pass.
