# Douyin Network-First Pipeline Fix Architecture

## Decision context

The intended Douyin visible profile-grid capture pipeline is network-first. Network JSON should provide canonical metadata whenever an `aweme_id` can be matched to a visible card. DOM extraction should identify visible cards, visible order, source URLs, and fallback values only when network fields are unavailable.

Real item evidence was not available for this implementation pass. The user authorized a generic fix from high-level symptoms only. This architecture therefore records a deterministic contract and audited code risks rather than a real evidence truth matrix.

## Canonical item contract

Each visible profile-grid captured item should normalize the following fields:

| Field | Owner | Rule |
| --- | --- | --- |
| `aweme_id` | Extension/API | Stable Douyin item id; maps to backend `source_video_external_id`. |
| `title` | API response | Canonical display title; aliases stored caption when needed. |
| `source_url` | Extension/API | Visible source video URL. |
| `share_url` | Extension/API | Share URL from network JSON when available. |
| `thumbnail_url` | Extension/API | First real image-like cover candidate, with network candidates preferred. |
| `poster_aspect_ratio` | Extension/API | Numeric width/height ratio for poster display; profile-grid default is portrait. |
| `duration_seconds` | Extension/API | Numeric duration from network duration or DOM fallback. |
| `duration_text` | Extension/API | Human-readable duration; may be derived from seconds if text is missing. |
| `posted_at` | Extension/API | ISO timestamp derived from network `create_time` when available. |
| `posted_text` | Extension/API | DOM fallback text only. |
| `view_count` | Extension/API | Numeric play/view count. |
| `like_count` | Extension/API | Numeric digg/like count. |
| `comment_count` | Extension/API | Numeric comment count. |
| `preview_status` | Extension/API/Web | `ready` only when a real thumbnail/preview image exists; otherwise `missing`. |
| `source_link_status` | Extension/API/Web | `captured` when a source/share link exists; otherwise `missing`. |
| `media_asset_status` | Extension/API/Web | `not_generated` until an internal downstream asset exists; then `ready` or `failed`. |

## Status semantics

The old `media_status` field conflates two different concepts: external source-link capture and internal media asset readiness. This fix separates them.

- `preview_status`
  - `ready`: a real image-like preview/thumbnail URL exists.
  - `missing`: no real preview URL exists.
- `source_link_status`
  - `captured`: a source video URL or share URL exists.
  - `missing`: no source/share link exists.
- `media_asset_status`
  - `not_generated`: no internal media asset has been generated or downloaded.
  - `ready`: a downstream internal media asset is available.
  - `failed`: downstream asset generation failed.

The frontend should render these as separate labels: Preview, Source link, and Media asset.

## Extension flow

1. Page/network hooks observe fetch and XHR responses on Douyin pages.
2. Normalization recursively finds aweme-like records.
3. Network metadata is merged by `aweme_id` into visible DOM cards.
4. DOM card extraction remains responsible for visible-card membership and order.
5. Direct execute-script fallback remains a fallback path; it must mark network metadata as unavailable rather than pretending to be network-first.

## Backend flow

1. Request schema accepts the canonical fields and legacy fields for compatibility.
2. Ingest normalization derives canonical statuses server-side instead of trusting requested readiness blindly.
3. Metadata JSON stores requested and derived canonical fields for diagnostics.
4. API response exposes canonical fields so the frontend does not need to inspect raw payload details for normal rendering.
5. Safe logs include stable IDs and status counts only.

## Frontend flow

1. Shared resolvers read canonical response fields first.
2. Thumbnail rendering uses canonical `thumbnail_url` and `preview_url` only as compatibility fallback.
3. Duration, posted date, and metrics render canonical numeric/text fields and do not infer from unrelated raw fields.
4. Status chips render Preview, Source link, and Media asset separately.
5. Portrait poster thumbnails should use a portrait-friendly frame with `object-fit: contain` or a poster aspect-ratio CSS variable to avoid misleading crop.

## Fallback policy

- Network JSON wins over DOM when an item id match exists.
- DOM values are allowed only as fallback and should be recorded as such in diagnostics.
- Missing values must render as `Not captured` or `Missing`; do not synthesize fake values.
- Legacy `media_status` may be accepted for backward compatibility but should not be the primary UI contract.

## Implemented verification

- Extension tests/build passed with `npm --prefix apps/extension-douyin-capture test`.
- Web Capture Inbox resolver/UI tests passed with `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts` from `apps/web`.
- Web typecheck passed with `npm --prefix apps/web run typecheck`.
- API Douyin extension capture tests passed with `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- The Python environment does not currently provide `pytest`; use the passing `unittest` command for this focused test until the local environment includes `pytest`.

## Safe observability

Allowed logs:

- capture id
- item count
- number of items with network metadata
- number of thumbnail-ready items
- status counts
- item ids when already part of the capture contract

Forbidden logs:

- cookies
- auth tokens
- credentials
- full raw HAR payloads
- private local paths
- excessive raw HTML/network bodies
