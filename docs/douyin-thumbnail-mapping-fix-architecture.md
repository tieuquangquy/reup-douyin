# Douyin Thumbnail Mapping Fix Architecture

## Goal

Provide truthful Capture Inbox thumbnails whenever an existing payload or downstream metadata source contains a usable image URL, while keeping the app local-first and SaaS-ready.

## Canonical Model

`thumbnail_url` is the canonical field across persistence, API response, web types, cards, and detail drawer.

Alias fields are ingestion hints only. They may be preserved in `raw_payload_json`, but the UI should not require every alias as a first-class top-level API field.

## End-to-End Data Path

```text
Douyin DOM/card metadata
  -> extension VideoPayload thumbnail fields
  -> DouyinExtensionVideoPayload request schema
  -> CaptureInboxService raw_item model_dump
  -> CapturedItem.thumbnail_url
  -> CapturedItemResponse.thumbnail_url
  -> web CapturedItem.thumbnail_url
  -> Capture Inbox card and drawer resolver
```

## Resolver Priority

Backend canonicalization and frontend display should use this priority:

1. Canonical `thumbnail_url`.
2. Explicit poster aliases: `poster_url`, `poster`.
3. Explicit cover aliases: `cover_url`, `cover`, `origin_cover`, `dynamic_cover`, `animated_cover`.
4. Image aliases: `thumb_url`, `thumbnail`, `image_url`, `image`.
5. List-like aliases: `url_list` and known nested URL arrays.
6. Preview artifact only if it is image-like.
7. Recursive raw/metadata fallback only when the key name indicates thumbnail/cover/poster/image semantics or the value itself is image-like.
8. Honest placeholder.

## Truthfulness Rules

- Do not fabricate thumbnails.
- Do not use a video page URL as an image thumbnail.
- Only use `preview_url` as an image if it is image-like.
- `data:image/*` URLs are acceptable if already present in payload; no generation is added.
- Preserve source URLs in raw metadata for diagnostics when safe.

## Extension Extraction Design

The extension should inspect only the visible card/link DOM it already uses for capture. It should prefer stable attributes in this order:

1. `img.currentSrc`.
2. `img.src`.
3. `source[srcset]` or `img[srcset]` first usable candidate.
4. `video[poster]`.
5. Image-like values from safe `data-*` attributes on the nearest card/link subtree.

The extractor must stay browser-local and avoid network calls, cookies, storage, or secret-bearing fields.

## Backend Design

The backend request schema accepts common thumbnail aliases as optional fields while keeping `thumbnail_url` canonical. Staging runs deterministic canonicalization before persisting `CapturedItem.thumbnail_url` and `preview_url`.

No migration is required because `captured_items.thumbnail_url`, `captured_items.preview_url`, and `captured_items.raw_payload_json` already exist.

Promotion from Capture Inbox into canonical source ingest also resolves thumbnails through the same payload priority, so already-staged thumbnail data is not lost during downstream handoff.

## Frontend Design

The Capture Inbox UI uses one shared resolver for:

- card image `src`;
- drawer thumbnail link;
- placeholder decision.

The UI should show the placeholder only when the resolver returns no usable image URL.

## Observability

Existing diagnostics should continue to expose `raw_payload_json` in the collapsed drawer. No secrets or private local paths should be logged or displayed beyond existing safe payload diagnostics.
