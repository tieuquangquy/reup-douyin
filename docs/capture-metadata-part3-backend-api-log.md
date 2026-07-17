# Capture Metadata Part 3 Backend/API Log

Date: 2026-04-29
Scope: Part 3 only — backend ingest/persistence/API exposure for canonical Time + Performance + Processing fit fields.
Status: Completed

## Preconditions and scope guard

- Read [`AGENTS.md`](AGENTS.md) and applied repository boundaries.
- Scope locked to backend only:
  - allowed: [`apps/api/src/schemas/douyin_extension.py`](apps/api/src/schemas/douyin_extension.py), [`apps/api/src/services/capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py), [`apps/api/src/schemas/capture_inbox.py`](apps/api/src/schemas/capture_inbox.py), backend tests/docs.
  - disallowed in this task: extension normalization and frontend/UI changes.

## 1) Audit evidence (ingest → persist → expose)

### Ingest schema acceptance

- Current extension ingest payload schema is [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:123).
- Findings:
  - Accepts canonical Time/Performance fields (`posted_at`, counts, `engagement_rate`, `duration_seconds`).
  - Does **not** yet accept Part 2 provenance fields:
    - `duration_source`
    - `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`
    - `engagement_rate_source`
  - Does **not** yet accept processing-fit semantic fields:
    - `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`
  - `posted_source` currently typed as `"network_json" | "dom_text" | "fallback_none"`; Part 2 may emit `"detail_hydrate"`, so schema should include it for compatibility.

### Persistence path

- Canonical staging is built in [`CaptureInboxService._build_item(...)`](apps/api/src/services/capture_inbox_service.py:688).
- Findings:
  - Already persists:
    - top-level columns: `duration_seconds`, `posted_at`
    - metadata mirror: time/performance fields and source markers (e.g. `posted_source`, `thumbnail_source`).
  - Existing metadata compaction step removes all `None` values:
    - [`metadata_json = {key: value for key, value in metadata_json.items() if value is not None}`](apps/api/src/services/capture_inbox_service.py:776)
  - This conflicts with Part 3 requirement to preserve explicit null semantics for unsupported processing-fit fields (`null` must remain explicit where intentionally unknown).

### API exposure path

- Response schema is [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24), with hydration in [`hydrate_card_grid_metadata(...)`](apps/api/src/schemas/capture_inbox.py:89).
- Findings:
  - Already exposes first-class canonical Time/Performance fields.
  - Does **not** yet expose first-class processing-fit semantic fields.
  - Does **not** yet expose metric/duration/engagement provenance fields from Part 2.
- Routes in [`apps/api/src/api/routes/capture_inbox.py`](apps/api/src/api/routes/capture_inbox.py) already return `CapturedItemResponse`; no route-shape change needed if schema is expanded.

### Model and migration check

- [`CapturedItem`](apps/api/src/models/capture_inbox.py:56) already has JSON storage (`metadata_json`) plus key top-level columns.
- No new SQL columns are strictly required for Part 3 because new fields can be persisted in `metadata_json` and exposed via schema hydration.
- Migration status: **No DB migration required** for this Part 3 scope.

## 2) Intended implementation (Part 3)

1. Extend ingest schema in [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:123) with missing provenance and processing-fit fields.
2. Update [`_build_item(...)`](apps/api/src/services/capture_inbox_service.py:688) to persist:
   - provenance keys (`*_source`)
   - processing-fit semantic keys (including explicit null when intentionally unknown)
3. Adjust metadata null-pruning behavior to keep explicit-null canonical keys for Part 3 semantic contract while remaining backward compatible.
4. Extend [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) and [`hydrate_card_grid_metadata(...)`](apps/api/src/schemas/capture_inbox.py:89) to expose new fields first-class.
5. Add focused tests in [`apps/api/tests/test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py) for:
   - persistence of canonical/provenance/processing-fit fields,
   - explicit null retention for semantic keys,
   - response exposure and backward compatibility for old rows.

## 3) Verification

- Ran backend test suite slice via [`python -m unittest tests.test_douyin_extension_capture_service -v`](apps/api/tests/test_douyin_extension_capture_service.py) from [`apps/api`](apps/api).
- Result: 29 tests passed.

## 4) Non-goals (enforced)

- No extension code edits.
- No frontend Tile Gallery/UI edits.
- No redesign of API routes; schema-only exposure extension.
- No unrelated queue/worker/crawler/video-processing changes.
