# Capture Metadata Canonical Contract (Part 1 Definition)

Date: 2026-04-29
Status: Contract definition only. No implementation in this task.

## 1) Canonical Field Contract

### Time
- `posted_at`
  - Type: ISO datetime string (nullable)
  - Canonical priority:
    1. `network_json` valid timestamp
    2. `detail_hydrate` valid timestamp
    3. null + optional `posted_text` for UI context
  - Persistence target:
    - `captured_items.posted_at` column
    - mirror in `captured_items.metadata_json.posted_at` (string)
  - API exposure:
    - `CapturedItemResponse.posted_at`
    - `CapturedItemResponse.posted_text`
  - Frontend usage:
    - date filtering, tile metadata, detail panel

### Performance
- `view_count`, `like_count`, `comment_count`, `share_count`
  - Type: integer (nullable)
  - Canonical priority for each metric:
    1. `network_json`
    2. `detail_hydrate`
    3. `dom_fallback`
  - Persistence target:
    - canonical values in `captured_items.metadata_json`
  - API exposure:
    - first-class numeric fields on `CapturedItemResponse`
  - Frontend usage:
    - tile quick metrics + advanced range filters

- `engagement_rate`
  - Type: float [0..1] (nullable)
  - Canonical value rule:
    - derive from canonical counts `(likes+comments+shares)/views` when views > 0
    - fallback to provided source value only if valid and no better derivation exists
  - Persistence target:
    - `captured_items.metadata_json.engagement_rate`
  - API exposure:
    - `CapturedItemResponse.engagement_rate`
  - Frontend usage:
    - advanced min/max engagement filter

### Processing fit
- `duration_seconds`
  - Type: float/integer seconds (nullable)
  - Canonical priority:
    1. `network_json`
    2. `detail_hydrate`
    3. `dom_fallback`
  - Persistence target:
    - `captured_items.duration_seconds` column + metadata mirror
  - API exposure:
    - `CapturedItemResponse.duration_seconds`
  - Frontend usage:
    - advanced min/max duration filter

- `has_speech`
  - Type: boolean (nullable)
  - Current state: filter-consumed key only; no canonical producer
  - Contract target:
    - canonical producer writes `metadata_json.has_speech`
    - API exposes first-class nullable boolean

- `text_density`
  - Type: enum `"low" | "medium" | "high"` (nullable)
  - Current state: filter-consumed key only
  - Contract target:
    - canonical producer writes `metadata_json.text_density`
    - API exposes first-class nullable enum

- `has_heavy_watermark`
  - Type: boolean (nullable)
  - Current state: filter-consumed key only
  - Contract target:
    - canonical producer writes `metadata_json.has_heavy_watermark`
    - API exposes first-class nullable boolean

- `processing_complexity`
  - Type: enum `"low" | "medium" | "high" | "blocking"` (nullable)
  - Current state: filter-consumed key only
  - Contract target:
    - canonical producer writes `metadata_json.processing_complexity`
    - API exposes first-class nullable enum

- `copyright_risk`
  - Type: enum `"low" | "medium" | "high" | "true"` (nullable)
  - Current state: filter-consumed key only
  - Contract target:
    - canonical producer writes `metadata_json.copyright_risk`
    - API exposes first-class nullable enum

## 2) Provenance Contract

For fields with multi-source merge, preserve explicit provenance keys:
- `thumbnail_source`
- `posted_source`
- (recommended extension in Part 2): metric-level provenance map for auditability

Minimum accepted provenance policy:
- Never merge by index across items.
- Only merge by exact stable item identity (aweme_id / external id binding).
- Reject context-mismatched network records.

## 3) Persistence Contract Boundaries

- Stable query/filter fields should be first-class where practical (`posted_at`, `duration_seconds` already are).
- Rapidly evolving diagnostics and intermediate derivations may remain in `metadata_json`.
- When a field is used by operator filtering, it must have:
  1. deterministic write path
  2. deterministic read path
  3. documented fallback behavior

## 4) API Contract Requirements

Capture Inbox list/query responses must provide operator-ready values without frontend reconstruction beyond display formatting.

Required first-class response fields:
- Time/Performance/Duration fields listed above (already present).

Planned first-class response additions (Part 3 candidate):
- `has_speech`
- `text_density`
- `has_heavy_watermark`
- `processing_complexity`
- `copyright_risk`

## 5) Part 2 / Part 3 / Part 4 split (execution plan only)

### Part 2 — Extension + backend canonical production alignment
Primary targets:
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/api/src/services/capture_inbox_service.py`
- (if needed) `apps/api/src/schemas/douyin_extension.py`

Goals:
- Ensure processing-fit semantic keys are produced deterministically into staged metadata.
- Keep current source-priority behavior for time/performance/duration stable.
- Preserve idempotent item-local merge behavior.

Risks:
- false positives/negatives for semantic heuristics
- accidental overwrite of better network values

### Part 3 — API schema exposure + filter coherence
Primary targets:
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`

Goals:
- expose processing-fit fields first-class in `CapturedItemResponse`
- keep advanced filter request and service filtering semantics aligned

Risks:
- schema drift between request filters and response fields
- backward compatibility for consumers expecting metadata-only keys

### Part 4 — Frontend typing + Tile Gallery/Advanced panel wiring
Primary targets:
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`

Goals:
- consume new first-class fields safely
- keep compact-priority advanced panel behavior unchanged
- add tests for new field rendering/filter observability

Risks:
- UI regressions from conditional rendering changes
- brittle tests tied to copy instead of behavior

## 6) Explicit non-goals in Part 1

- No DB migration.
- No runtime field production changes.
- No API contract mutation.
- No frontend behavior changes.
- No test updates.
