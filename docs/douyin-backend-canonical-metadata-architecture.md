# Douyin Backend Canonical Metadata Architecture

## Goal

Capture Inbox should receive one stable backend contract for real Douyin visible profile-grid thumbnail and metadata fields. The frontend should trust canonical response fields first and use raw JSON only for diagnostics.

## Canonical field model

Every staged Capture Inbox item should expose these canonical fields:

- `thumbnail_url`
- `duration_text`
- `duration_seconds`
- `posted_at`
- `posted_text`
- `view_count`
- `like_count`
- `comment_count`
- `preview_status`
- `media_status`

Also preserved:

- `source_video_external_id` as canonical backend external id, sourced from extension `aweme_id`, `video_id`, `id`, or video URL.
- `caption`, sourced from extension `title`, `desc`, or `description`.
- `source_url`, sourced from `source_video_url`, `url`, or `share_url`.
- `share_url`, sourced from extension `share_url`.
- `raw_payload_json`, preserving safe raw item fields that passed request schema validation.
- `metadata_json`, preserving companion canonical metadata and diagnostics.

## Direct storage

Existing `captured_items` columns are the direct storage location for display/query-critical fields:

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

No broad DB migration is required for this part because the narrow canonical contract can use these existing columns plus JSON metadata.

## Metadata JSON storage

`CapturedItem.metadata_json` stores canonical companions and diagnostics that do not need dedicated columns yet:

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
- `thumbnail_source_type`
- `thumbnail_source_types`
- `network_source`
- `extraction_diagnostics`
- safe `raw` diagnostic object from the extension when present

This keeps the frontend contract simple while preserving enough backend diagnostics to inspect where field loss occurs.

## API exposure

Capture Inbox API responses use `CapturedItemResponse` as the canonical response model. It exposes the required fields as top-level response properties:

- `thumbnail_url`
- `duration_text`
- `duration_seconds`
- `posted_at`
- `posted_text`
- `view_count`
- `like_count`
- `comment_count`
- `preview_status`
- `media_status`

`metadata_json` and `raw_payload_json` remain secondary diagnostic fields.

## Preview status truthfulness

Canonical `preview_status` values:

- `ready`: a valid thumbnail/preview-equivalent URL is present and usable for UI display.
- `missing`: no valid thumbnail/preview-equivalent URL is present.
- `pending`: reserved for a future asynchronous preview job when such a job has been requested but not completed.

For this extension capture path, `ready` is derived from a valid `thumbnail_url` or image-like `preview_url`; `missing` is used when both are absent. The backend must not mark preview as `ready` just because an item exists.

## Media status truthfulness

Canonical `media_status` values:

- `ready`: a genuinely usable media asset/source is captured and considered media-ready by the backend.
- `source_link_captured`: a Douyin source/share URL is captured, but no downloaded/processed media asset exists yet.
- `missing`: no usable source link or media asset is available.
- `pending`: reserved for a future asynchronous media job when such a job has been requested but not completed.

For this extension capture path, a visible Douyin source link maps to `source_link_captured`, not `ready`. `media_ready` remains false unless `media_status` is explicitly `ready`.

## End-to-end logging points

Safe logs should exist at these points:

1. Request receipt in `DouyinExtensionCaptureService.capture_current_page()`:
   - counts of videos with thumbnail, duration, posted, metrics, preview status, and media status.
2. Item normalization in `CaptureInboxService._build_item()`:
   - raw item index, source video external id, canonical field presence, preview/media status, and diagnostic source coverage.
3. Session staging after persistence:
   - persisted item counts for thumbnail, duration, posted, metrics, preview statuses, and media statuses.
4. API response routes:
   - response item counts with canonical field coverage, without logging raw payloads or secrets.

Logs must not include cookies, auth headers, credentials, local private paths, or full raw network payloads.

## Non-goals

- No UI redesign.
- No media downloading.
- No crawler behavior.
- No fabricated values.
- No broad migration unless a future part requires dedicated query/index behavior for additional metadata.
