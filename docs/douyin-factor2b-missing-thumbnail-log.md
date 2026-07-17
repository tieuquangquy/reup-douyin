# Douyin Factor 2B Missing Thumbnail Log

## Scope

Recover only still-missing thumbnails for captured Douyin items that already have correct `aweme_id` identity binding.

Allowed scope:

- `apps/extension-douyin-capture`
- minimal backend/API thumbnail pass-through for new debug fields
- focused thumbnail recovery tests and docs

Non-goals:

- no identity refactor
- no stats, duration, or posted fixes
- no UI redesign
- no full media download/generation pipeline
- no fake thumbnails

## Audit before patching

### Stage 1 — extension network cache

Network normalization is exact-id based through `NetworkVideoMetadata.aweme_id`. The failing thumbnail recovery gap was candidate order and field coverage, not identity binding.

Original observed cover candidate order:

1. `video.cover`
2. `video.origin_cover`
3. `video.dynamic_cover`
4. `video.animated_cover`
5. root `cover`
6. root `origin_cover`
7. root `dynamic_cover`

Failure:

- Required priority says `video.origin_cover.url_list` must be preferred before `video.cover.url_list`, then `video.dynamic_cover.url_list`.
- The normalizer skipped several equivalent item-level/video-level cover/poster fields, so real portrait thumbnails could remain unresolved even when present in network JSON.

### Stage 2 — extension detail hydrate

Detail hydrate is represented as optional exact-id `NetworkVideoMetadata[]` passed to `extractVideos()`. No live detail crawler was added.

Failure:

- Detail hydrate used the same normalized metadata shape, so it had the same cover/poster candidate coverage gap as network JSON.
- The canonical thumbnail chooser did not inspect `url_list` after the explicit hydrate fields.

### Stage 3 — item-local DOM fallback

DOM fallback was already item-local and uses only the discovered link/card root. It checks:

- `img.currentSrc`
- `img.src`
- `img.getAttribute("src")`
- `img.getAttribute("data-src")`
- `img.srcset`
- `img.getAttribute("srcset")`
- `video.poster`
- `video.getAttribute("poster")`
- `source[srcset]`
- selected dataset/attribute image fields
- inline `background-image`
- computed `background-image`

Failure:

- The fallback itself was not made broader, because it already matched the local-only requirement.
- Missing thumbnails previously lacked explicit `thumbnail_source: "missing"` and precise `thumbnail_missing_reason` diagnostics.

### Stage 4 — backend/API/frontend pass-through

Backend already derives thumbnails from `thumbnail_url`, aliases, `url_list`, and nested image-like data. Frontend already resolves canonical `thumbnail_url`, preview URL, metadata JSON, and raw payload JSON.

Failure:

- API schema did not accept `thumbnail_source: "missing"`.
- API schema did not model `thumbnail_missing_reason`.
- Backend metadata persistence did not explicitly preserve `thumbnail_missing_reason`.

No frontend resolver code was changed because no frontend drop was found in this audit.

## Implemented recovery order

For a visible item with exact `aweme_id`, canonical thumbnail recovery now follows:

1. exact network JSON cover recovery
   - `video.origin_cover.url_list`
   - `video.cover.url_list`
   - `video.dynamic_cover.url_list`
   - equivalent fields: `poster`, `poster_url`, `thumbnail`, `thumbnail_url`, `thumb_url`, `image`, `image_url`, `animated_cover`, plus object `url`, `uri`, `src`, `href`, `urls`, `urlList`
2. exact detail hydrate recovery
   - same normalized candidate extraction
   - same exact `aweme_id` guard
   - includes hydrate `url_list` fallback
3. item-local DOM fallback
   - local card/link only
   - image/video/srcset/dataset/background candidates
4. honest missing
   - `thumbnail_source: "missing"`
   - precise `thumbnail_missing_reason`

## Debug fields

Added/accepted debug provenance:

- `thumbnail_source`: `network_json`, `detail_hydrate`, `dom_fallback`, `missing`
- `thumbnail_missing_reason`: `network_cover_missing`, `detail_hydrate_not_run`, `detail_hydrate_no_cover`, `dom_cover_missing`, `backend_drop`, `api_drop`, `frontend_resolver_drop`, `thumbnail_unresolved`

These fields are diagnostic metadata and are not new user-facing UI copy.

## Implementation details

Changed extension files:

- `apps/extension-douyin-capture/src/networkCache.ts`
  - changed network/detail cover order to origin cover, cover, dynamic cover, then equivalent poster/thumbnail/image fields.
  - broadened `coverList()` to read common object fields and `urls`.
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
  - mirrored the same cover candidate order and field coverage inside the injected page hook.
- `apps/extension-douyin-capture/src/extractor.ts`
  - added explicit missing provenance/reason.
  - changed hydrate thumbnail selection to inspect `thumbnail_url`, `origin_cover`, `cover_url`, `dynamic_cover`, and `url_list`.
  - preserved reason in payload, `raw`, and `extraction_diagnostics`.
- `apps/extension-douyin-capture/src/popupTransport.ts`
  - direct execute-script fallback now emits `thumbnail_source: "missing"` and `thumbnail_missing_reason` when local DOM thumbnail recovery fails.
- `apps/extension-douyin-capture/src/types.ts`
  - added `ThumbnailMissingReason` and `thumbnail_source: "missing"`.

Changed backend files:

- `apps/api/src/schemas/douyin_extension.py`
  - added `DouyinThumbnailSource` with `missing`.
  - added `DouyinThumbnailMissingReason`.
  - accepted `thumbnail_missing_reason` on extension video payloads.
- `apps/api/src/services/capture_inbox_service.py`
  - preserves `thumbnail_missing_reason` in `metadata_json`.
  - includes the reason in safe card-metadata logging.

Changed tests:

- `apps/extension-douyin-capture/src/extractor.identity.test.ts`
  - exact-id network origin-cover priority.
  - detail hydrate poster-alias recovery.
  - honest missing when network/detail/DOM fail.
  - `detail_hydrate_no_cover` diagnostics.
  - no thumbnail leakage from a recovered `aweme_id` to a neighboring missing `aweme_id`.
- `apps/extension-douyin-capture/src/extractor.test.ts`
  - updated expected network thumbnail priority to origin cover.
- `apps/api/tests/test_douyin_extension_capture_service.py`
  - schema accepts `thumbnail_source: "missing"` and `thumbnail_missing_reason`.
  - backend persists missing-thumbnail reason without inventing a preview.

## Verification

Commands run:

```cmd
npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts && npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts && npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts && npm --workspace apps/extension-douyin-capture run typecheck && npm --workspace apps/extension-douyin-capture test
```

Result: passed.

```cmd
python -m pytest apps/api/tests/test_douyin_extension_capture_service.py
```

Result: failed because `pytest` is not installed in the active Python environment (`No module named pytest`).

```cmd
python -m unittest apps.api.tests.test_douyin_extension_capture_service
```

Result: failed from repository root because the API test imports expect `apps/api` as the working directory (`No module named 'src'`).

```cmd
python -m unittest tests.test_douyin_extension_capture_service
```

Working directory: `apps/api`.

Result: passed, 21 tests.

## Recovery measurement

No live Douyin batch was available in this task, so live recovered-count measurement was not possible. Fixture coverage shows:

- 1 exact-id network missing-thumbnail fixture recovered from `video.origin_cover.url_list`.
- 1 exact-id detail hydrate missing-thumbnail fixture recovered from equivalent `video.poster_url.url_list`.
- 1 all-failed fixture remains missing with `detail_hydrate_not_run`.
- 1 all-failed detail fixture remains missing with `detail_hydrate_no_cover`.
- 1 neighboring missing item remains missing while another item recovers, proving no cross-item thumbnail contamination.
