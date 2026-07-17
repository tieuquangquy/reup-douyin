# Douyin Backend Canonical Metadata Log

## Scope

Part 2 focuses on the backend path that receives the richer Douyin extension capture payload, normalizes visible-card thumbnail and metadata fields, persists them, exposes them through Capture Inbox API responses, and logs safe end-to-end field coverage.

Allowed areas:

- `apps/api` schemas, services, models, routes, and focused tests related to Douyin extension capture and Capture Inbox staging.
- Docs for backend canonical metadata behavior.

Non-goals:

- No Capture Inbox UI redesign.
- No crawler implementation.
- No media download or video processing implementation.
- No fabricated metadata.
- No broad database redesign.

## Backend audit

### 1. Extension capture request schema

Current request schema is `DouyinExtensionCaptureRequest` in `apps/api/src/schemas/douyin_extension.py`.

Currently accepted visible-card fields include:

- `thumbnail_url`, `poster_url`, `cover_url`, `thumb_url`, `image_url`, `thumbnail`, `cover`, `poster`, `origin_cover`, `dynamic_cover`, `animated_cover`, `image`, `url_list`
- `duration_seconds`, `duration`, `duration_text`
- `posted_at`, `create_time`, `posted_text`
- `view_count`, `view_count_text`, `like_count`, `like_count_text`, `comment_count`, `comment_count_text`
- `preview_status`
- `media_status`
- `statistics`, `stats`, `extraction_diagnostics`, `thumbnail_source_types`

Current gaps found:

- `preview_status` only accepts `ready` and `missing`; it does not accept canonical `pending`.
- `media_status` accepts `source_link_captured`, `missing`, and `ready`, but does not accept canonical `pending`.
- Singular `thumbnail_source_type`, `network_source`, and raw diagnostic payloads from the enriched extension shape are not explicitly modeled.
- Pydantic's default extra-field behavior means unmodeled fields are ignored unless explicitly stored elsewhere.

### 2. Capture-current-page service

`DouyinExtensionCaptureService.capture_current_page()` in `apps/api/src/services/douyin_extension_capture_service.py`:

- rejects secret-like payload keys before staging;
- resolves page/profile classification;
- logs aggregate request coverage for thumbnails, duration, posted text, and metrics;
- delegates persistence to `CaptureInboxService.stage_extension_capture()`;
- logs aggregate staged item counts.

Current gaps found:

- Logging does not include explicit preview/media status distribution.
- Logging does not clearly compare request coverage, normalized coverage, persisted item coverage, and response coverage.

### 3. Normalization layer

`CaptureInboxService._build_item()` in `apps/api/src/services/capture_inbox_service.py` is the main backend normalization layer.

Currently normalized directly into dedicated columns:

- source external id -> `CapturedItem.source_video_external_id`
- source URL -> `CapturedItem.source_url`
- share URL -> `CapturedItem.share_url`
- title/description -> `CapturedItem.caption`
- `duration_seconds` -> `CapturedItem.duration_seconds`
- `posted_at` -> `CapturedItem.posted_at`
- `thumbnail_url` -> `CapturedItem.thumbnail_url`
- `preview_url` -> `CapturedItem.preview_url`

Currently normalized into `CapturedItem.metadata_json`:

- `thumbnail_url`
- `duration_text`
- `duration_seconds`
- `posted_text`
- `posted_at`
- `view_count`, `view_count_text`
- `like_count`, `like_count_text`
- `comment_count`, `comment_count_text`
- `preview_status`
- `media_status`
- `thumbnail_source_types`
- `extraction_diagnostics`

Current gaps found:

- Preview/media status handling is only partly canonical. It treats preview as `ready` when a thumbnail exists, but cannot represent `pending`.
- `media_status` is set to `source_link_captured` when a source URL exists, but `media_ready` is only true for literal `ready`. This is mostly truthful, but API semantics need a stable canonical contract.
- No explicit helper centralizes status normalization.
- No explicit helper centralizes canonical metadata extraction for request, persistence, and response logging.

### 4. Persistence models

`CapturedItem` in `apps/api/src/models/capture_inbox.py` already has stable dedicated columns for the narrow canonical fields that benefit from querying or direct display:

- `source_video_external_id`
- `source_url`
- `share_url`
- `caption`
- `duration_seconds`
- `posted_at`
- `thumbnail_url`
- `preview_url`
- `preview_ready`
- `media_ready`
- `metadata_json`
- `raw_payload_json`

Current persistence pattern is suitable for Part 2 without a broad migration: keep query/display-critical canonical values in existing columns and store text/raw/diagnostic companion fields in `metadata_json`.

### 5. Capture Inbox API response

`CapturedItemResponse` in `apps/api/src/schemas/capture_inbox.py` already exposes:

- `thumbnail_url`
- `duration_text`
- `duration_seconds`
- `posted_at`
- `posted_text`
- `view_count`, `view_count_text`
- `like_count`, `like_count_text`
- `comment_count`, `comment_count_text`
- `preview_status`
- `media_status`
- raw and metadata JSON secondary fields

Current gaps found:

- `preview_status` and `media_status` do not accept `pending`.
- The response validator derives `media_status = source_link_captured` from `source_url` if no status is present, which should remain a truthful source-link state but should not be treated as ready media.
- Response logging is absent in Capture Inbox routes.

### 6. Where fields can be lost

Potential loss points:

1. Request schema: unmodeled fields are ignored.
2. `_build_item()`: fields can be omitted from dedicated columns or `metadata_json`.
3. `_enrich_item()`: readiness booleans can misrepresent status if status normalization is not explicit.
4. API response hydration: response can derive ambiguous fallback status values if metadata is incomplete.
5. Route response: no safe log currently confirms canonical field exposure.

## Implementation plan

1. Expand request schema to accept `pending`, singular thumbnail source diagnostics, network source, and raw metadata diagnostics.
2. Add centralized canonical status helpers for preview/media.
3. Normalize canonical metadata once in `_build_item()` and persist it consistently.
4. Keep existing dedicated columns; store text/count/status diagnostics in `metadata_json`.
5. Update API response literals and hydration to include `pending` while keeping `source_link_captured` as a non-ready media source state.
6. Add safe logs at request receipt, item normalization, staging persistence, and API response exposure.
7. Add focused backend tests for schema acceptance, normalization, persistence, statuses, API response exposure, missing values, and raw metadata preservation.

## Final implementation notes

Implemented backend changes:

- Request schema now accepts `pending` preview/media statuses plus `thumbnail_source_type`, `network_source`, and safe `raw` metadata diagnostics.
- `CaptureInboxService._build_item()` now normalizes and persists canonical thumbnail, duration, posted, metric, preview/media status, thumbnail-source, network-source, raw metadata, and extraction diagnostic fields.
- Existing `captured_items` columns remain the durable direct storage for display-critical canonical fields; companion text/status/diagnostic fields are stored in `metadata_json`.
- Preview/media status derivation is centralized and conservative:
  - preview is `ready` only when a valid thumbnail/preview URL exists;
  - preview is `missing` when absent;
  - media is `source_link_captured` for source/share links without a downloaded/processed media asset;
  - media is `missing` when no source/share link exists;
  - `ready` is not fabricated from extension optimism.
- Capture Inbox API responses now accept and expose `pending` status literals while preserving `source_link_captured` as a non-ready media state.
- Safe end-to-end logs now cover item normalization, persisted session summaries, and response exposure using counts/booleans/status distributions only.

Verification:

- `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py` could not run because this Windows Python environment does not have `pytest` installed.
- `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_extension_capture_service` passed: 17 tests.
