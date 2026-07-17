# Douyin Thumbnail Real Grid Debug Resume

## Current Goal

Hard-fix thumbnail extraction for real visible Douyin profile card grids so Capture Inbox receives and displays a canonical `thumbnail_url` whenever a real image source exists in the card DOM.

## Completed Audit

- Read repository rules in `AGENTS.md`.
- Audited extension content-script extraction in `apps/extension-douyin-capture/src/extractor.ts`.
- Audited direct execute-script extraction in `apps/extension-douyin-capture/src/popupTransport.ts`.
- Audited extension payload shape in `apps/extension-douyin-capture/src/types.ts`.
- Audited backend request schemas in `apps/api/src/schemas/douyin_extension.py`.
- Audited backend persistence and normalization in `apps/api/src/services/capture_inbox_service.py`.
- Audited extension capture service boundary in `apps/api/src/services/douyin_extension_capture_service.py`.
- Audited Capture Inbox API response schemas/routes in `apps/api/src/schemas/capture_inbox.py` and `apps/api/src/api/routes/capture_inbox.py`.
- Audited frontend thumbnail resolver in `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`.
- Audited existing tests in extension, API, and web areas.

## Confirmed Root Causes

1. Direct execute-script capture path did not extract thumbnails at all. It collected video links and metadata, then sent items without `thumbnail_url`, `cover_url`, or `url_list` even when visible profile-grid posters existed in the card DOM.
2. Content-script thumbnail extraction was incomplete for real visible card grids. It covered some image element properties but missed required real-world sources such as raw `src`, `data-src`, image-like dataset values, inline `background-image`, and computed `background-image`.
3. The pipeline lacked end-to-end thumbnail debug logs, making it hard to prove whether the thumbnail was missed in extension extraction, dropped at backend normalization, omitted from API response, or ignored by the UI.

## Implemented Changes

1. Added robust card-local thumbnail extraction to the extension content-script path.
2. Added equivalent extraction to the direct execute-script path.
3. Added safe diagnostics in extension payloads with thumbnail candidate counts and source types, not secret/raw-cookie data.
4. Added backend receive and persist/normalize logs for thumbnail presence and selected canonical field.
5. Confirmed API responses expose canonical `thumbnail_url` and retain source payload evidence through existing `raw_payload_json`.
6. Added frontend resolver debug logging and tests proving canonical `thumbnail_url` is trusted first.
7. Ran focused verification commands.
8. Updated this resume and debug log with exact implementation and verification results.

## Verification Results

- `npm --workspace @reup-douyin/extension-douyin-capture run test` from the repository root: passed.
- `python -m unittest apps.api.tests.test_douyin_extension_capture_service` from the repository root: failed because the API tests import `src` relative to `apps/api`.
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`: passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` from the repository root: passed.

## Covered Verification Assertions

- Extension tests cover the required source patterns through focused source assertions:
  - `img.src`
  - `img.getAttribute("src")`
  - `img.getAttribute("data-src")`
  - `dataset` image-like values
  - `srcset`
  - inline `background-image`
  - computed `background-image`
  - direct execute-script thumbnail mapping
- Backend tests cover:
  - schema preservation for canonical thumbnail fields and source diagnostics
  - alias normalization priority
  - persisted `CapturedItem.thumbnail_url` and `preview_url` from canonical thumbnails
  - video-page placeholders rejected as thumbnails
- Frontend tests cover:
  - canonical `item.thumbnail_url` first priority
  - fallback aliases remain supported
  - real `<img>` rendering when a thumbnail resolves
  - placeholder only when no real thumbnail candidate exists
  - safe non-production resolver debug evidence
