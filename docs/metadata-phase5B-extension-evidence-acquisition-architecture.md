# Metadata Phase 5B Extension Evidence Acquisition Architecture

## Goal

Collect exact-id raw aweme evidence in the extension so Capture Inbox items can include:

- `raw_network_aweme`
- `raw_detail_aweme`
- `raw_dom_snapshot`
- `raw_evidence_summary`

without changing backend normalization.

## Root cause summary

The live extension path had two decisive breaks:

1. `contentScript.js` started at `document_idle`, so page hook injection could miss early Douyin responses.
2. `pageNetworkHook.ts` intercepted page-world responses but only populated `__DOUYIN_AWEME_CACHE__`; it did not publish normalized `NetworkVideoMetadata` into the cache/bridge that the content script and extractor actually read.

## Fixed execution flow

1. Content script loads at `document_start`.
2. Content script injects `pageNetworkHook.js` early into page world.
3. Page hook intercepts fetch/XHR responses.
4. Page hook recursively detects aweme-like records and normalizes them into bounded `NetworkVideoMetadata`.
5. Page hook classifies evidence source:
   - network/grid-like -> `raw_network_aweme`
   - detail/hydrate/share-like -> `raw_detail_aweme`
6. Page hook publishes normalized items into:
   - `window.__REUP_DOUYIN_NETWORK_CACHE__`
   - DOM cache element `#reup-douyin-network-cache`
   - `window.postMessage` with `REUP_DOUYIN_NETWORK_CACHE_UPDATE`
7. Content script receives bridged items and merges them into extension-side capture input.
8. Extractor exact-id matches `aweme_id` and attaches raw evidence to `VideoPayload`.

## Evidence detection shapes

Supported shapes:

- `aweme_list`
- `data.aweme_list`
- `data.list`
- `data`
- recursive object/array traversal

Aweme-like acceptance requires:

- explicit `aweme_id`
- plus at least one useful aweme-like key such as:
  - `video`
  - `video_info`
  - `statistics`
  - `stats`
  - `share_info`
  - `desc`
  - `create_time`

## Identity rule

- `aweme_id` is normalized as `String(aweme_id).trim()`
- attachment stays exact-id only
- no merge by index, title, thumbnail, or visible order

## Bridge/cache rule

- page-world hook is the source of raw network/detail evidence
- content script accepts only `REUP_DOUYIN_NETWORK_CACHE_UPDATE` messages from:
  - `event.source === window`
  - `event.origin === window.location.origin`
- payload is bounded and cached per exact `aweme_id`

## Downstream unchanged

This phase does not change:

- backend normalizer
- Capture Inbox UI
- filter policy
- hydration job

The backend continues to consume the same fields once extension-side evidence exists.
