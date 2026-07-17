# Douyin Thumbnail Real Grid Debug Architecture

## Objective

Create a trustworthy thumbnail pipeline from real Douyin profile card-grid DOM to Capture Inbox UI.

Canonical field: `thumbnail_url`.

## Pipeline

```text
Douyin visible card DOM
  -> extension card-local extractor
  -> extension payload videos[].thumbnail_url
  -> API request schema
  -> Capture Inbox persistence normalization
  -> CapturedItem.thumbnail_url
  -> Capture Inbox API response
  -> frontend thumbnail resolver
  -> media tile image or truthful placeholder
```

## Extension Extraction Contract

For each discovered video card, both the content-script extractor and direct execute-script fallback search only card-local/link-local DOM roots and emit:

- `thumbnail_url`: first deterministic real image candidate.
- `cover_url`: alias mirroring `thumbnail_url` for compatibility.
- `url_list`: deduplicated ordered candidate list.
- diagnostic evidence: source pattern counts or source labels, without secrets.

Supported real image source patterns:

- `HTMLImageElement.currentSrc`
- `HTMLImageElement.src`
- `img.getAttribute("src")`
- `img.getAttribute("data-src")`
- image-like `dataset` fields such as cover/thumb/poster/image keys
- `srcset` from `img` and `source`
- `video[poster]`
- inline `style.backgroundImage`
- computed `background-image`
- safe image-like nested values embedded in data attributes when they are direct URLs or simple `srcset`-like values

## Backend Contract

The API accepts `thumbnail_url` as canonical and continues accepting aliases for backward compatibility:

- `poster_url`
- `cover_url`
- `thumb_url`
- `image_url`
- `thumbnail`
- `cover`
- `poster`
- `origin_cover`
- `dynamic_cover`
- `animated_cover`
- `image`
- `url_list`

Persistence must normalize these into `CapturedItem.thumbnail_url` with deterministic priority. It must reject video-page URLs masquerading as thumbnails.

## API Response Contract

Capture Inbox item responses must expose:

- `thumbnail_url`
- `preview_url`
- `raw_payload_json`
- `metadata_json`

`thumbnail_url` is the canonical UI source. `raw_payload_json` remains diagnostic evidence, not the primary UI contract.

## Frontend Contract

The Capture Inbox thumbnail resolver must trust sources in this order:

1. `item.thumbnail_url`
2. explicit thumbnail aliases in `item.raw_payload_json`
3. image-like `item.preview_url`
4. explicit thumbnail aliases in `item.metadata_json`
5. nested image-like URLs in raw payload or metadata

If none are real image-like candidates, the UI renders the existing truthful placeholder. It must not fabricate or infer fake thumbnails from video URLs.

## Logging / Observability

The hard-fix adds safe debug evidence across extension diagnostics, backend receive/stage logs, backend per-item normalization logs, and frontend non-production resolver logs.

Safe debug logs include:

- capture id
- video id or raw item index
- whether a thumbnail candidate exists
- selected source type
- number of candidates
- whether canonical `thumbnail_url` was persisted/exposed/resolved

Safe debug logs must not include:

- cookies
- auth tokens
- credentials
- complete private local paths
- raw secret-bearing payloads

## Non-Goals

- No full video/media downloading.
- No crawler implementation.
- No Capture Inbox redesign.
- No fake placeholder thumbnails.
- No unrelated Douyin extraction expansion.
