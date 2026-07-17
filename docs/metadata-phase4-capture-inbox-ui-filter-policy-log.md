# Metadata Phase 4 Capture Inbox UI + Filter Policy Log

## Scope

Phase 4 only: make Capture Inbox UI and filter policy consume backend metadata status/source/reason fields from Phase 3 so Time / Performance / Processing fit becomes operator-usable.

In-scope:
- `apps/web` Capture Inbox UI behavior.
- Frontend type contract alignment to Phase 3 API fields.
- Frontend tests and Phase 4 docs.

Out-of-scope:
- Backend normalizer logic changes.
- Extension capture changes.
- Hydration queue/job implementation.
- Review Board / Reup Queue redesign.

## Audit Findings (Before Implementation)

### 1) Frontend contract coverage (`CapturedItem`)

File audited: `apps/web/src/types/capture-inbox.ts`

Already present:
- `metadata_status`
- `time_status`
- `performance_status`
- `processing_fit_status`
- `metadata_missing_reason`
- `time_missing_reason`
- `performance_missing_reason`
- `processing_fit_missing_reason`
- `posted_source`, `duration_source`, `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`, `engagement_rate_source`
- `metadata_source_summary`

Gap found:
- `raw_evidence_summary` is not explicitly typed on `CapturedItem`.
- Source unions still include legacy labels and miss some Phase 3 literals (`dom_snapshot`, `existing_canonical`, `missing`) for strict typed consumption.

### 2) Tile/card rendering behavior

File audited: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

Current behavior:
- Card already shows metadata pill via `metadataStatusLabel(item.metadata_status)`.
- Quick row uses `resolveDuration`, `resolvePosted`, `resolvePreviewStatus`.
- Metric row uses `resolveViewCount`, `resolveLikeCount`, `resolveCommentCount`, `resolveShareCount`.

Gap found:
- Missing values are still rendered per-field as repeated `Not captured`, which is noisy.
- No compact grouped missing summary such as `Time missing · Performance missing`.
- Card does not distinguish “field unavailable because metadata missing” versus simple empty per-field fallback in compact UX.

### 3) Right inspector behavior

File audited: `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

Current behavior:
- Inspector already has a `Metadata` section with:
  - metadata status
  - group statuses with reasons
  - source summary
  - source/provenance rows

Gaps found:
- Section title should explicitly communicate metadata diagnostics quality intent.
- `raw_evidence_summary` compact view is missing.
- Field layout can better separate quality diagnostics from generic metadata rows.

### 4) Advanced filters and policy behavior

Files audited:
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/types/capture-inbox.ts`

Current behavior:
- Operator filter chips are workflow-oriented (`Captured`, `Ready`, `Duplicates`, `Needs action`, `Failed`, `Promoted`).
- Advanced filter query is backend-driven via `queryCaptureInboxItems` and existing numeric/date fields.
- No metadata-status grouping filter in UI.

Gaps found:
- No dedicated grouping for:
  - Metadata complete
  - Metadata partial
  - Needs metadata
  - Metadata failed
- No explicit helper text that missing metadata items don’t match dependent advanced filters and are grouped as needs metadata.
- No compact summary showing matched vs needs-metadata vs filtered-out split for operator clarity.

## Phase 4 UI Design

### Card display policy
- Keep compact card height.
- Continue showing canonical values when captured.
- Replace repeated missing field spam with one grouped metadata-missing hint line.
- Status mapping:
  - `complete` → `Metadata complete`
  - `partial` → `Metadata partial`
  - `missing` → `Needs metadata`
  - `pending_hydration` → `Metadata pending`
  - `failed` → `Metadata failed`

### Inspector design
- Add dedicated `Metadata quality` section.
- Show:
  - item-level metadata status
  - time/performance/processing-fit statuses + reasons
  - source provenance rows
  - compact `raw_evidence_summary` rendering (boolean summary only)
- Keep raw blobs out of this section.

### Filter policy design
- Add metadata grouping operator filter options:
  - All
  - Metadata complete
  - Metadata partial
  - Needs metadata
  - Metadata failed
- Keep backend advanced filter behavior unchanged.
- Add explicit helper copy: items missing required metadata are grouped as needs metadata and won’t satisfy dependent numeric/date filters.
- Add compact counts summary: matched / needs metadata / filtered out.

## Planned Files (Phase 4)

- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/capture-inbox-canonical.test.ts` (if needed)
- `docs/metadata-phase4-capture-inbox-ui-filter-policy-log.md`
- `docs/metadata-phase4-capture-inbox-ui-filter-policy-resume.md`

## Verification Plan

- Frontend contract tests for Phase 3 fields in `CapturedItem`.
- Card rendering tests for complete/partial/missing/failed metadata states.
- Inspector tests for metadata quality section and evidence summary.
- Filter policy tests for metadata grouping and missing-metadata helper policy.

## Implementation Completed

Updated files:
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`

Implemented behavior:
- Expanded provenance/source unions for Phase 3-compatible literals (including `dom_snapshot`, `existing_canonical`, and `missing` where applicable).
- Added typed `raw_evidence_summary` on `CapturedItem`.
- Added metadata grouping filter state and controls in the Studio filter toolbar (`all`, `complete`, `partial`, `needs-metadata`, `failed`).
- Added compact grouped missing metadata line on cards to reduce repeated missing-field spam.
- Renamed inspector section to `Metadata quality` and added `Raw evidence` summary row.
- Added helper copy in advanced filters describing missing metadata policy.
- Added helper functions for metadata grouping/filter formatting:
  - `matchesMetadataFilter`
  - `compactMetadataMissingLine`
  - `formatRawEvidenceSummary`

## Verification Results

Executed:
- `npx tsx apps/web/src/test/capture-inbox.test.ts`

Result:
- Passed (`capture inbox Media-first Triage Studio, canonical rendering, metadata status rendering, session ribbon, status strip, filter toolbar, right-side inspector, state sync, action hierarchy, and polish tests passed`).
