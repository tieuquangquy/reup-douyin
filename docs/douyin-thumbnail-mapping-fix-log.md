# Douyin Thumbnail Mapping Fix Log

## Objective

Hard-fix Douyin Capture Inbox thumbnail/data mapping so thumbnails are truthfully and reliably available whenever the extension payload or downstream metadata already contains a usable image source.

## Scope

Touched areas expected for this task:

- Browser extension extraction and payload typing.
- Backend extension request schema and Capture Inbox staging normalization.
- Capture Inbox API response contract where needed.
- Web Capture Inbox item type and UI resolver.
- Focused source tests for extension, backend, and web behavior.

Non-goals:

- No crawler implementation.
- No video download or media processing pipeline.
- No generated/fake thumbnails.
- No automated publishing integration.
- No database schema expansion unless existing canonical `captured_items.thumbnail_url` proves insufficient.

## Audit Findings

### Extension

`apps/extension-douyin-capture/src/extractor.ts` currently builds each `VideoPayload` from video links, title text, and metrics only. It does not inspect nearby `img`, `picture`, `source`, `video[poster]`, or image-like data attributes on the card/link subtree.

`apps/extension-douyin-capture/src/types.ts` currently defines `VideoPayload` without thumbnail-capable fields. That means the extension cannot type-safely emit `thumbnail_url`, `cover_url`, `poster_url`, or related raw image fields.

Root cause part 1: image data available in the DOM is lost at extraction time.

### Backend request schema

`apps/api/src/schemas/douyin_extension.py` currently accepts `thumbnail_url` and `cover_url`, but not `poster_url`, `dynamic_cover`, `origin_cover`, `animated_cover`, nested `cover`, `poster`, or `url_list`. Since staging uses `payload.model_dump(exclude_none=True)`, undeclared Pydantic fields are not a reliable persistence path.

Root cause part 2: even if clients send broader thumbnail-capable fields, backend request validation may drop them before staging.

### Backend staging and persistence

`apps/api/src/services/capture_inbox_service.py` already stores `CapturedItem.thumbnail_url` and `preview_url`, and has a recursive image-like resolver. However, it only sees fields that survive request validation and `model_dump`. Promotion adapter fallback currently uses only `raw.get("thumbnail_url")` and `raw.get("cover_url")`.

Root cause part 3: backend normalization can persist a canonical `thumbnail_url`, but input coverage and promotion fallback priority are incomplete.

### API response

`apps/api/src/schemas/capture_inbox.py` already exposes canonical `thumbnail_url` on `CapturedItemResponse`. No public API rename is needed.

### Web

`apps/web/src/types/capture-inbox.ts` already declares `thumbnail_url`. `apps/web/src/lib/api.ts` does not transform Capture Inbox responses, so API fields flow directly into the UI.

`apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` has a centralized resolver, but its priority should be made deterministic and aligned with the canonical backend field: `thumbnail_url`, then explicit raw aliases, then image-like preview artifact, then nested raw/metadata fallback, then placeholder.

## Planned Fix

1. Extend extension `VideoPayload` with optional thumbnail-capable fields.
2. Update extension extraction to collect the nearest truthful image candidate from the card/link subtree and expose it as canonical `thumbnail_url`, preserving source aliases where applicable.
3. Expand backend request schema for common raw thumbnail aliases and nested payload shapes that are safe and dependency-light.
4. Keep `captured_items.thumbnail_url` as the canonical persistence/API field.
5. Make backend resolver priority deterministic and preserve usable raw image fields in `raw_payload_json`.
6. Make frontend resolver priority deterministic and use the same canonical-first model for cards and drawer links.
7. Add/update focused tests.

## Implementation Completed

- Extension `VideoPayload` now exposes canonical `thumbnail_url` plus common poster/cover/image aliases and `url_list`.
- Extension extraction now inspects the nearest card/link subtree for `img`, `source[srcset]`, `video[poster]`, and safe image-like `data-*` attributes, then emits the first truthful image candidate as canonical `thumbnail_url` and preserves the candidate list.
- Backend `DouyinExtensionVideoPayload` now accepts common thumbnail aliases and nested cover/poster/image payload shapes before staging.
- Backend staging keeps `captured_items.thumbnail_url` as the canonical persisted/API field and resolves it with deterministic priority from the raw payload.
- Backend promotion adapter now reuses the same thumbnail resolver when mapping staged items into source-ingest payloads.
- Web Capture Inbox cards and detail drawer now use one canonical-first resolver so both surfaces agree on real thumbnails versus the honest placeholder.

## Verification Log

Commands run:

1. `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
   - Result: passed.
2. `npm --workspace @reup-douyin/extension-douyin-capture exec -- tsx src/extractor.test.ts`
   - Result: passed.
3. `npm run typecheck --workspace apps/web`
   - Result: passed.
4. `npx tsx apps/web/src/test/capture-inbox.test.ts`
   - Result: passed.
5. `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`
   - Result: passed, 15 tests.

One earlier combined verification attempt failed because the API unittest was executed from the repository root, where `src` was not on the Python import path. Re-running the API test from `apps/api` verified the backend changes successfully.
