# Douyin Thumbnail Real Grid Debug Log

## Scope

This log tracks the narrow hard-fix for real visible Douyin profile card-grid thumbnails not appearing in Capture Inbox.

## Problem

A real Douyin profile page shows visible card-grid poster images, but captured items render as `No thumbnail available` in Capture Inbox.

## Audit Order

1. Extension DOM extraction.
2. Extension payload shape.
3. Backend request schema and persistence.
4. API response shape.
5. Frontend thumbnail resolver.

## Initial Findings

### Extension content-script extractor

- `apps/extension-douyin-capture/src/extractor.ts` already calls a card thumbnail routine from `extractVideos`.
- Current coverage is incomplete for real visible grid cases:
  - checks `image.currentSrc`, `image.src`, and `image.srcset`
  - does not explicitly read `img.getAttribute("src")`
  - does not explicitly read `img.getAttribute("data-src")`
  - does not inspect all safe `dataset` thumbnail/image-like values
  - does not inspect inline `background-image`
  - does not inspect computed `background-image`
  - does not emit thumbnail source diagnostics

### Extension direct execute-script fallback

- `apps/extension-douyin-capture/src/popupTransport.ts` contains a separate in-page extractor.
- This path currently collects videos but does not call any thumbnail extraction routine.
- If popup capture uses this direct execution path, visible thumbnail DOM can be present while the payload contains no `thumbnail_url`, `cover_url`, or `url_list`.
- This is the strongest current root-cause candidate for the reported real profile grid case.

### Backend schema and persistence

- `apps/api/src/schemas/douyin_extension.py` accepts canonical `thumbnail_url` and multiple aliases.
- `apps/api/src/services/capture_inbox_service.py` normalizes thumbnail aliases into `CapturedItem.thumbnail_url` through `_thumbnail_url_from_payload`.
- `raw_payload_json` is retained for inspection.
- The backend likely does not drop valid thumbnails when they arrive, but it lacks focused debug logging for receive/normalize/persist evidence.

### API response

- `apps/api/src/schemas/capture_inbox.py` exposes `thumbnail_url` and `raw_payload_json` on `CapturedItemResponse`.
- `apps/api/src/api/routes/capture_inbox.py` serializes items through `CapturedItemResponse`.

### Frontend resolver

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` already checks `item.thumbnail_url` first in `thumbnailUrlForItem`.
- Placeholder rendering is truthful when no resolver candidate exists.
- It needs stronger test coverage and safe debug evidence for resolver input/output.

## Implementation Notes

- Extension source patterns implemented in `apps/extension-douyin-capture/src/extractor.ts`:
  - `image.currentSrc`
  - `image.src`
  - `img.getAttribute("src")`
  - `img.getAttribute("data-src")`
  - `img.srcset` and `source.srcset`
  - `video.poster`
  - image-like `dataset` keys
  - image-like attributes
  - inline `background-image`
  - computed `background-image`
- Direct execution parity implemented in `apps/extension-douyin-capture/src/popupTransport.ts`; the fallback in-page extractor now calls the same card-local thumbnail mapping shape and emits canonical `thumbnail_url`, `cover_url`, `url_list`, and `thumbnail_source_types`.
- Backend request schema now preserves `thumbnail_source_types` in `apps/api/src/schemas/douyin_extension.py`.
- Backend receive and persistence logging added in `apps/api/src/services/douyin_extension_capture_service.py` and `apps/api/src/services/capture_inbox_service.py` using safe counts, source labels, capture ids, and item ids.
- Capture Inbox resolver logging added in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`; it emits safe non-production resolver evidence and still trusts `item.thumbnail_url` first.
- Tests added/updated:
  - `apps/extension-douyin-capture/src/extractor.test.ts`
  - `apps/api/tests/test_douyin_extension_capture_service.py`
  - `apps/web/src/test/capture-inbox.test.ts`
- Verification commands run:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test` from the repository root: passed.
  - `python -m unittest apps.api.tests.test_douyin_extension_capture_service` from the repository root: failed because the API tests import `src` relative to `apps/api`.
  - `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`: passed.
  - `npx tsx apps/web/src/test/capture-inbox.test.ts` from the repository root: passed.

## Confirmed Root Causes

1. The direct execute-script capture path in `apps/extension-douyin-capture/src/popupTransport.ts` discovered video cards but never extracted thumbnails from those cards, so visible grid posters were dropped before the backend saw them.
2. The content-script extractor in `apps/extension-douyin-capture/src/extractor.ts` only covered a subset of real-card image patterns and missed common lazy/background variants such as raw `src`, `data-src`, dataset values, inline `background-image`, and computed `background-image`.
3. The pipeline lacked stage-specific thumbnail diagnostics, making it difficult to tell whether missing thumbnails were extraction misses, backend normalization drops, API response omissions, or frontend resolver misses.

## End-To-End Normalization

The extension now emits canonical `videos[].thumbnail_url` with compatibility aliases and a candidate list. The API schema accepts and preserves those fields. Capture Inbox persistence normalizes `thumbnail_url` and supported aliases into `CapturedItem.thumbnail_url`, sets `preview_url` to the thumbnail when available, and retains the raw payload for diagnostics. The Capture Inbox API exposes `thumbnail_url`, and the frontend resolver uses it before raw payload aliases or metadata fallbacks.

## Guardrails

- Do not fake thumbnails.
- Do not add media downloading.
- Do not redesign Capture Inbox.
- Do not broaden extraction into unrelated Douyin features.
- Do not log secrets, cookies, tokens, credentials, or private local paths.
