# Douyin Card Grid Metadata Fix Architecture

## Goal

The capture path must preserve metadata that is already visible in the Douyin profile-grid UI. Each visible video card should produce a truthful staged Capture Inbox item without pretending that missing downstream assets are ready.

## Boundary model

### Browser extension

Owns DOM observation only. It may read visible card DOM, attributes, media elements, inline/computed styles, and visible text. It must not crawl hidden APIs, scrape cookies, read secrets, download media, or fabricate missing metadata.

Responsibilities:

- Find visible video links.
- Select a card root broad enough to include the poster and overlay metadata.
- Extract real thumbnail candidates from image/video/style sources.
- Emit the best portrait/poster candidate as canonical `thumbnail_url` and preserve `url_list` plus safe source diagnostics.
- Extract visible duration, posted text, and metrics when present.
- Preserve raw text for fields that cannot be safely parsed.
- Emit safe aggregate diagnostics only.

### API / Capture Inbox

Owns request validation, normalization, persistence, and API contracts. It must not run long work inline or pretend that a source link equals a downloaded media asset.

Responsibilities:

- Accept extension canonical fields.
- Normalize thumbnail aliases into `CapturedItem.thumbnail_url`.
- Store card-grid metadata in `metadata_json` for predictable API/UI access.
- Preserve original extension payload in `raw_payload_json`.
- Set `preview_url` only for actual preview image assets, not source video links.
- Set `preview_ready` only when a real thumbnail/preview image exists.
- Set `media_ready` only when a real media asset is available; for this local-first capture step, source URL alone should remain a captured reference, not media-ready.
- Log safe counts and booleans, never secrets or private local paths.

### Web Capture Inbox

Owns display only. It should trust canonical API fields first and use raw payload only as fallback evidence.

Responsibilities:

- Use canonical `thumbnail_url` as first priority.
- Render a placeholder only when no real image URL is available.
- Show duration/date text fallbacks when parsed canonical values are unavailable.
- Show views/likes/comments from canonical metadata first.
- Show preview/media readiness truthfully.
- Keep the current media-first Capture Inbox layout.

## Canonical fields

Extension payload and backend metadata should align on these names:

- `thumbnail_url`: best real poster/cover image URL.
- `duration_text`: visible duration string, for example `01:23`.
- `duration_seconds`: parsed duration only when unambiguous.
- `posted_text`: visible posted date/time text from the card.
- `posted_at`: parsed timestamp only when unambiguous.
- `view_count_text`: raw visible views/play count text.
- `view_count`: parsed numeric views only when safe.
- `like_count_text`: raw visible likes text.
- `like_count`: parsed numeric likes only when safe.
- `comment_count_text`: raw visible comments text.
- `comment_count`: parsed numeric comments only when safe.
- `preview_status`: `ready` when an actual image preview exists, otherwise `missing`.
- `media_status`: `source_link_captured` when only a Douyin URL exists; `ready` is reserved for a real media asset.

## Implemented flow

1. The extension starts from visible `a[href*="/video/"]` links.
2. It scores ancestors instead of stopping at the first shallow container, preserving access to poster media and overlay metadata.
3. It collects thumbnail candidates from media elements, source sets, video posters, dataset keys, image-like attributes, inline backgrounds, and computed backgrounds.
4. It scores candidates so likely poster/current/source-set/Douyin image URLs win over lower-confidence strings.
5. It extracts visible duration, posted text, and metrics from card/link/title/ARIA text without fabricating missing values.
6. It sends canonical fields plus safe diagnostics to the API.
7. The API accepts the canonical fields, stores predictable values in `metadata_json`, preserves the raw payload, and avoids using source URLs as previews.
8. Capture Inbox API responses hydrate canonical metadata fields from `metadata_json` and raw fallback payloads.
9. The web app renders canonical thumbnail and metadata fields first, falling back to raw evidence only when safe.

## Supported visible DOM patterns

The implementation should support these visible card evidence sources:

- Anchor to `/video/{id}` wrapping or near card content.
- Descendant `img` sources: `currentSrc`, `src`, raw `src`, `data-src`, and `srcset`.
- Descendant `source[srcset]` candidates.
- Descendant `video[poster]` candidates.
- Image-like dataset keys containing thumb, cover, poster, image, or img.
- Image-like attributes including `src`, `data-src`, `poster`, and thumbnail hint keys.
- Inline `background-image` URLs.
- Computed `background-image` URLs.
- Visible card text, link text, title, and ARIA labels for metadata.

## Canonical persistence and response shape

Capture Inbox now keeps the original extension payload in `raw_payload_json` and stores normalized card-grid metadata in `metadata_json`. The public item response exposes canonical duration, posted, metric, preview status, and media status fields so the web app does not need to depend on a raw nested stats shape.

## Readiness semantics

Preview readiness:

- Ready only when `thumbnail_url` or a real image `preview_url` exists.
- Not ready when only `source_url` exists.

Media readiness:

- `source_link_captured` means the original Douyin URL was captured.
- `ready` is reserved for a real media asset state outside this task.
- Phase 1 extension capture does not mark media ready from source URL alone.

## Logging strategy

Safe extension diagnostics may include counts and source type names:

- number of visible videos
- number with thumbnail candidates
- total thumbnail candidate count
- number with duration text
- number with posted text
- number with view/like/comment counts
- source type names such as `img.currentSrc` or `computed.backgroundImage`

Safe backend logs may include:

- capture id
- diagnostics id
- raw item index
- source video external id
- booleans for metadata presence
- candidate counts
- readiness statuses

Logs must not include cookies, auth tokens, credentials, private local paths, or full sensitive payload dumps.

## Non-goals

- No external Douyin API crawling.
- No source media download.
- No generated thumbnails.
- No automatic publish integration.
- No new queue/database architecture.
