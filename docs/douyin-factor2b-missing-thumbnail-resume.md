# Douyin Factor 2B Missing Thumbnail Resume

## Current task

Recover only still-missing thumbnails for Douyin captured items that already have correct `aweme_id` identity binding.

## Scope guardrails followed

- Thumbnail recovery only.
- Recovery remains exact-id based.
- Identity mapping was not redesigned.
- Duration, posted, views, likes, and comments were not changed as product behavior.
- Capture Inbox UI was not redesigned.
- No crawler or media download pipeline was added.

## Final audit summary

- Extension network cache was exact-id based, but cover candidate order and field coverage were too narrow.
- Detail hydrate uses the same exact-id `NetworkVideoMetadata` shape, so improving normalized cover extraction improves detail hydrate without live crawling.
- DOM fallback was already item-local and broad enough; this task only added honest missing provenance/reason.
- Backend/API already preserved recovered canonical thumbnails, but needed narrow acceptance/persistence for `thumbnail_source: "missing"` and `thumbnail_missing_reason`.
- Frontend resolver already renders canonical/recovered `thumbnail_url`; no frontend change was needed.

## Implemented recovery order

1. exact network JSON cover recovery
   - `video.origin_cover.url_list`
   - `video.cover.url_list`
   - `video.dynamic_cover.url_list`
   - equivalent cover/poster/thumbnail/image fields
2. exact detail hydrate recovery
   - same exact-id candidate extraction
   - includes hydrate `url_list` fallback
3. item-local DOM fallback
   - local card/link image/video/srcset/dataset/background candidates only
4. honest missing
   - `thumbnail_source: "missing"`
   - `thumbnail_missing_reason`

## Files changed

- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extractor.identity.test.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `docs/douyin-factor2b-missing-thumbnail-log.md`
- `docs/douyin-factor2b-missing-thumbnail-resume.md`

## Verification

Passed:

```cmd
npx --workspace apps/extension-douyin-capture tsx src/extractor.identity.test.ts && npx --workspace apps/extension-douyin-capture tsx src/extractor.test.ts && npx --workspace apps/extension-douyin-capture tsx src/popupTransport.test.ts && npm --workspace apps/extension-douyin-capture run typecheck && npm --workspace apps/extension-douyin-capture test
```

Passed:

```cmd
python -m unittest tests.test_douyin_extension_capture_service
```

Working directory: `apps/api`.

Not runnable in current environment:

```cmd
python -m pytest apps/api/tests/test_douyin_extension_capture_service.py
```

Reason: active Python environment does not have `pytest` installed.

## Recovery measurement

No live Douyin failing batch was available. Fixture measurement:

- 2 missing-thumbnail fixtures recover real thumbnails from upstream data.
- 2 all-failed fixtures remain missing with truthful reasons.
- 1 neighbor-leak fixture proves recovered thumbnails do not contaminate another `aweme_id`.

## Status

Factor 2B implementation and verification are complete.
