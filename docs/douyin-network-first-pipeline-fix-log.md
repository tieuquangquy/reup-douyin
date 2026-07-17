# Douyin Network-First Pipeline Fix Log

## Scope

This log tracks the generic network-first Douyin capture pipeline fix across extension, API, and web UI boundaries.

## Evidence limitation

No real HAR, network JSON, extension payload, API response, screenshot, or log evidence is accessible in the workspace. The requested `evidence` folder is not available. The user explicitly authorized proceeding from the high-level observed symptoms only, without a one-item real-evidence truth matrix.

Because of that authorization, this fix does not claim to prove the exact source of any real item mismatch. It documents audited root-cause candidates and implements a deterministic contract intended to prevent the known symptom class.

## High-level observed symptoms used

- Thumbnail capture/rendering is inconsistent for visible Douyin profile-grid items.
- Real Douyin grid cards are portrait poster-like thumbnails, but the web UI uses a 16:9 crop.
- Duration can render as `Not captured` despite network metadata being expected.
- Posted can render as a wrong numeric-looking value such as `23.7`.
- Counts can be shifted or incomplete.
- Status labels conflate preview readiness, source-link capture, and internal media asset generation.

## Audit summary

- Extension content-script capture already reads page/network cache and merges network metadata into DOM cards.
- Extension direct execute-script fallback remains DOM-only and can bypass network metadata.
- Extension payload still emits the old `media_status` value for source-link capture.
- Backend schema accepts and stores the old conflated media status.
- Backend API response exposes old `media_status` rather than separate source-link and media-asset states.
- Frontend resolver still has a single media status resolver that treats a source/share URL as media readiness-like information.
- Frontend thumbnail frame crops portrait thumbnails through a fixed 16:9 frame and `object-fit: cover`.

## Implementation completed

- Extension payloads now carry `preview_status`, `source_link_status`, and `media_asset_status` separately while preserving legacy `media_status` compatibility.
- Content-script capture is labeled `content_script_network_first_v1`; direct execute-script fallback is labeled `direct_execute_script_dom_fallback_v1`.
- Network metadata normalization prioritizes Douyin cover candidates and propagates portrait `poster_aspect_ratio` metadata.
- Backend request/response schemas accept and expose canonical Douyin item fields including `aweme_id`, `title`, `poster_aspect_ratio`, `source_link_status`, and `media_asset_status`.
- Backend ingest derives preview readiness from real image-like URLs, derives source-link status from source/share links, and keeps internal media assets `not_generated` unless a downstream asset is explicitly ready or failed.
- Frontend canonical resolvers render thumbnail, duration, posted, metrics, Preview, Source link, and Media asset from canonical response fields first.
- Capture Inbox media tiles now use a poster aspect-ratio CSS variable and `object-fit: contain` to avoid misleading portrait-thumbnail crops.
- Safe logging was added across extension/backend/frontend using counts, statuses, and stable ids rather than raw HAR, secrets, cookies, credentials, or private local paths.

## Verification

- Passed: `npm --prefix apps/extension-douyin-capture test`.
- Passed: `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts` from `apps/web`.
- Passed: `npm --prefix apps/web run typecheck`.
- Passed: `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`.
- Noted but not blocking: `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py` could not run because `pytest` is not installed in the active Python environment.
- Noted but not blocking: invoking `npm --prefix apps/web run test -- capture-inbox.test.ts capture-inbox-canonical.test.ts` from the repository root appends extra arguments to the full web script and triggered a pre-existing duplicated path lookup in unrelated tests; the targeted Capture Inbox web tests passed when run from `apps/web`.

## Planned touched areas

- [`apps/extension-douyin-capture/src/types.ts`](../apps/extension-douyin-capture/src/types.ts)
- [`apps/extension-douyin-capture/src/networkCache.ts`](../apps/extension-douyin-capture/src/networkCache.ts)
- [`apps/extension-douyin-capture/src/pageNetworkHook.ts`](../apps/extension-douyin-capture/src/pageNetworkHook.ts)
- [`apps/extension-douyin-capture/src/extractor.ts`](../apps/extension-douyin-capture/src/extractor.ts)
- [`apps/extension-douyin-capture/src/popupTransport.ts`](../apps/extension-douyin-capture/src/popupTransport.ts)
- [`apps/api/src/schemas/douyin_extension.py`](../apps/api/src/schemas/douyin_extension.py)
- [`apps/api/src/services/capture_inbox_service.py`](../apps/api/src/services/capture_inbox_service.py)
- [`apps/api/src/schemas/capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py)
- [`apps/api/src/api/routes/capture_inbox.py`](../apps/api/src/api/routes/capture_inbox.py)
- [`apps/web/src/types/capture-inbox.ts`](../apps/web/src/types/capture-inbox.ts)
- [`apps/web/src/lib/captureInboxCanonical.ts`](../apps/web/src/lib/captureInboxCanonical.ts)
- [`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`](../apps/web/src/components/capture-inbox/CaptureInboxPage.tsx)
- [`apps/web/src/app/globals.css`](../apps/web/src/app/globals.css)

## Non-goals

- No crawler implementation.
- No video download or processing implementation.
- No auto-publishing integration.
- No database migration for new physical columns; canonical additions remain response/payload/metadata contract fields.
- No claim that the unavailable real evidence has been verified.
