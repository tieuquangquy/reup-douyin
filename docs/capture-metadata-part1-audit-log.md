# Capture Metadata Part 1 Audit Log

Date: 2026-04-29
Scope: Part 1 only (audit + canonical contract definition). No pipeline implementation.

## Goal
Audit field availability and source priority for Capture Inbox metadata used by Time, Performance, and Processing fit controls across:
1. Extension normalization
2. Backend persistence/staging
3. API response exposure
4. Frontend type/render/filter usage

## Requested Field Set
- Time: `posted_at`
- Performance: `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`
- Processing fit: `duration_seconds`, `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`

## Evidence Summary by Layer

### Layer A — Extension normalization
Primary evidence files:
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/types.ts`

Key findings:
- Canonical payload builder uses explicit source-priority merge in extractor:
  - counts: network → detail hydrate → DOM fallback
  - posted_at: network/detail with DOM text fallback path
  - duration_seconds: network/detail with DOM fallback
- `thumbnail_source` and `posted_source` provenance are emitted.
- `engagement_rate` is computed from canonical counts.
- `networkCache.ts` normalizes network JSON metrics and posted timestamp candidate.
- Extension contract does not provide processing-fit semantic fields (`has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`) by default.

### Layer B — Backend staging/persistence
Primary evidence files:
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`

Key findings:
- Durable columns exist for:
  - `posted_at` (column)
  - `duration_seconds` (column)
- Performance metrics are persisted in `metadata_json` (canonicalized in `_build_item`) and re-read from `metadata_json` for advanced filtering.
- `engagement_rate` is recomputed/normalized in `_build_item` when needed.
- Processing-fit booleans/enums are currently expected from `metadata_json` in `_matches_advanced_filter`, but not canonically produced in `_build_item`.

### Layer C — API exposure
Primary evidence files:
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`

Key findings:
- `CapturedItemResponse` exposes requested Time + Performance fields directly.
- Response hydration reconstructs display metrics from `metadata_json` / `raw_payload_json` (`hydrate_card_grid_metadata`).
- Advanced filter request schema includes processing-fit controls:
  - `speech`, `max_text_density`, `exclude_heavy_watermark`, `exclude_high_processing_complexity`, `exclude_high_copyright_risk`
- Filtering logic enforces those controls from `metadata_json` keys.

### Layer D — Frontend usage
Primary evidence files:
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`

Key findings:
- Frontend `CapturedItem` type includes Time + Performance + duration fields.
- Advanced filter payload builder sends all requested controls to backend query endpoint.
- Tile quick metrics render from `view_count`, `like_count`, `comment_count`, `share_count`.
- No frontend-side computation for processing-fit semantic keys; expects backend-filtered results.

## Field Inventory Matrix

| Field | Extension Normalize | Backend Persist | API Expose | Frontend Type/Usage | Status |
|---|---|---|---|---|---|
| `posted_at` | Yes | Yes (column + metadata) | Yes | Yes | OK |
| `view_count` | Yes | Yes (`metadata_json`) | Yes | Yes | OK |
| `like_count` | Yes | Yes (`metadata_json`) | Yes | Yes | OK |
| `comment_count` | Yes | Yes (`metadata_json`) | Yes | Yes | OK |
| `share_count` | Yes | Yes (`metadata_json`) | Yes | Yes | OK |
| `engagement_rate` | Yes (derived) | Yes (`metadata_json`, derived fallback) | Yes | Yes | OK |
| `duration_seconds` | Yes | Yes (column + metadata) | Yes | Yes | OK |
| `has_speech` | No canonical producer | Read-only expectation in filter | Not first-class field in response | Not directly typed/used | GAP |
| `text_density` | No canonical producer | Read-only expectation in filter | Not first-class field in response | Not directly typed/used | GAP |
| `has_heavy_watermark` | No canonical producer | Read-only expectation in filter | Not first-class field in response | Not directly typed/used | GAP |
| `processing_complexity` | No canonical producer | Read-only expectation in filter | Not first-class field in response | Not directly typed/used | GAP |
| `copyright_risk` | No canonical producer | Read-only expectation in filter | Not first-class field in response | Not directly typed/used | GAP |

## Canonical Priority Findings

### Confirmed canonical source priority (current)
- `view_count`, `like_count`, `comment_count`, `share_count`:
  1. `network_json`
  2. `detail_hydrate`
  3. `dom_fallback`
- `duration_seconds`:
  1. `network_json`
  2. `detail_hydrate`
  3. `dom_fallback`
- `posted_at`:
  1. valid `network_json`
  2. valid `detail_hydrate`
  3. `dom_text` fallback semantics

### Gaps requiring Part 2+
- Processing-fit semantic keys are filter-consumed but not canonicalized in a single producer stage.
- API response does not currently expose them as first-class typed fields for UI observability.

## Non-goals honored in this task
- No extension implementation changes.
- No backend migration changes.
- No API contract mutation.
- No frontend behavior changes.
- No tests modified.
