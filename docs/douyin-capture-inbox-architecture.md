# Douyin Capture Inbox Architecture

## Purpose

The Douyin extension capture flow must stage raw browser-extension captures before anything reaches the canonical review pipeline. The Capture Inbox is the staging and readiness layer between real active-tab extension capture and the existing downstream entities.

## Current Audit Findings

### Extension payload shape

The extension emits `douyin_extension_capture.v1` payloads from the active browser tab:

- `capture_id`, `captured_at`, `schema_version`.
- `page`: URL, title, optional body text sample, detected page type, profile hints, and visible video link count.
- `profile`: optional profile identifiers such as `id`, `sec_uid`, `handle`, and display name.
- `videos`: visible DOM-derived video entries with possible `aweme_id`, `video_id`, source/share URLs, title/description, thumbnail/cover, duration, posted time, and statistics.
- `diagnostics`: browser-extension-safe diagnostics.

### Current backend capture endpoint

`POST /douyin-extension/capture-current-page` currently lives in the Douyin extension API boundary and calls the extension capture service directly. Existing safety checks reject challenge/login pages and secret-like keys before import.

### Current direct-to-review behavior

The current service converts the extension payload into an adapter payload, calls canonical source ingest, then immediately applies candidate scoring. That means a raw capture can create:

- `SourceProfile`
- `CrawlSession`
- `SourceVideo`
- `VideoMetricSnapshot`
- `VideoCandidate`

The response currently suggests the Review Board route. This is the behavior this architecture replaces.

### Existing Review Board source

The Review Board is already cleanly backed by `/candidates`, which lists persisted `VideoCandidate` rows and joins `SourceVideo`. The Review Board should remain unchanged as the downstream promoted-item review surface.

### Persistence and migration conventions

- SQLAlchemy models extend `BaseModel`.
- App enums live in `apps/api/src/enums/__init__.py`.
- Alembic imports `src.models` so new models must be exported from `apps/api/src/models/__init__.py`.
- Migrations are sequential under `apps/api/alembic/versions` and use PostgreSQL JSONB.

## Target Lifecycle

1. Extension capture submits active-tab payload to the existing endpoint.
2. Backend creates a `CaptureSession` scoped to the local/default workspace when absent.
3. Backend stores each raw visible item as a `CapturedItem` with raw payload, source URL, extracted identifiers, and safe diagnostics.
4. Backend runs synchronous lightweight enrichment suitable for request time:
   - normalize profile URL and identifiers;
   - normalize video URL and external video id;
   - merge statistics shapes;
   - calculate preview/media readiness from available thumbnail/cover/video URL fields;
   - dedupe against items in the same session and existing canonical `SourceVideo` rows.
5. Backend records reconciliation counts on the session.
6. Capture Inbox UI shows staged sessions/items, readiness, unknown values, skipped/excluded state, raw details, and manual actions.
7. Promotion converts ready non-excluded items into the canonical source ingest path and then applies candidate evaluation.
8. Only promoted canonical `VideoCandidate` rows appear on the Review Board.

## New Domain Models

### `CaptureSession`

Represents one extension capture submission. It owns source-page context, raw submission metadata, lifecycle state, and reconciliation counts.

Expected fields:

- `workspace_id`
- `capture_id`
- `source_platform`
- `capture_source`
- `status`
- `detected_page_type`
- `page_url`, `page_title`
- `submitted_profile_url`, `normalized_profile_identifier`
- count fields for captured, normalized, duplicate, skipped, ready, promoted, candidate-created, failed
- `started_at`, `finished_at`
- `metadata_json`, `diagnostics_json`, `raw_summary_json`, `result_summary_json`

### `CapturedItem`

Represents one raw video-like item from an extension capture. It is not a Review Board candidate.

Expected fields:

- `workspace_id`
- `capture_session_id`
- `source_platform`
- `status`
- `raw_item_index`
- `raw_payload_json`
- extracted profile/video identifiers and URLs
- normalized video id and URL
- title/caption, duration, posted time
- thumbnail/cover/preview fields
- readiness flags and reasons
- dedupe key and duplicate references
- optional promoted `source_video_id`, `video_candidate_id`, `crawl_session_id`
- `metadata_json`, `enrichment_json`, `error_code`, `error_message`

## Status Model

Capture sessions:

- `RECEIVED`: raw submission accepted.
- `ENRICHING`: lightweight normalization/readiness is running.
- `READY_FOR_REVIEW`: at least one item can be promoted or manually inspected.
- `PARTIALLY_PROMOTED`: some items promoted; others remain pending/skipped/failed.
- `PROMOTED`: all eligible items promoted or resolved.
- `FAILED`: unrecoverable session-level failure.

Captured items:

- `RAW`: persisted but not enriched.
- `ENRICHED`: normalized and classified.
- `READY`: sufficient for promotion.
- `NEEDS_ENRICHMENT`: missing required identity/URL fields.
- `PREVIEW_MISSING`: usable identity but preview/media is not ready.
- `DUPLICATE`: duplicate of an in-session or canonical item.
- `EXCLUDED`: operator skipped it.
- `PROMOTED`: canonical entities/candidate were created or updated.
- `FAILED`: item-level failure.

## Promotion Rules

An item is promotable when:

- it is not excluded;
- it is not an in-session duplicate;
- it has a normalized video URL;
- it has a normalized video external id or a deterministic fallback dedupe key;
- it has a normalized/submitted profile URL;
- it has enough preview context for an operator to understand it, or is explicitly promoted by the operator with a warning.

Promotion uses the canonical source ingest and candidate evaluation services. It must not create a second Review Board model.

## Count Reconciliation

The session summary must make count differences explicit:

- `visible_item_count`: extension DOM items submitted.
- `captured_item_count`: raw rows persisted.
- `normalized_item_count`: items with normalized URL/id/profile context.
- `duplicate_item_count`: duplicate raw rows or already-canonical rows.
- `ready_item_count`: items eligible for promotion.
- `skipped_item_count`: operator-excluded or unsupported rows.
- `promoted_item_count`: items that reached canonical source video/candidate flow.
- `candidate_created_count`: items with `VideoCandidate` rows created/updated.
- `failed_item_count`: item-level failures.

The UI must not imply all visible captures became Review Board candidates.

## UI Route

Use `/ops/extensions/douyin/capture-inbox` as an Ops Console route near the existing extension manager. This keeps raw capture staging operational/debug-adjacent while preserving `/selection/review-board` for promoted candidates.

## Observability

Log lifecycle transitions and actions with stable ids:

- `capture_session_id`
- `capture_id`
- `captured_item_id`
- `source_video_id`
- `video_candidate_id`
- `crawl_session_id`

Do not log secrets, cookies, tokens, or private local paths.

## Non-Goals

- No crawler implementation.
- No long-running worker queue implementation in this step.
- No second candidate/review architecture.
- No automatic publishing.
- No direct browser-secret or cookie capture.
